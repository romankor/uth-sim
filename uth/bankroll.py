"""Bankroll / variance simulator.

Plays realized hands (``mode="play"``: a single random dealer hand per deal,
full payout structure) and tracks how a flat-betting bankroll evolves. Reports
the single-hand outcome distribution and, for several horizons, the final
bankroll distribution, risk of ruin, and worst drawdown across many sessions.

Money is the ante unit times the net result of each hand. A session stops early
(``busted``) once the bankroll can no longer cover one maximum hand.
"""

import argparse
import math
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor

from .game import Config, play_hand
from .simulator import _mp_context, default_workers


def _max_commitment(cfg):
    """Largest amount a single hand can require: Ante + Blind + 4x Play + Trips."""
    return 1.0 + 1.0 + 4.0 + cfg.trips_bet


def _run_sessions(args):
    n_hands, n_sessions, start, ante, cfg, ruin_level, seed = args
    rng = random.Random(seed)
    deck = list(range(52))
    finals = []
    drawdowns = []
    busted = 0
    survived_until = []
    for _ in range(n_sessions):
        bk = start
        peak = start
        max_dd = 0.0
        bust_hand = None
        for h in range(n_hands):
            if bk < ruin_level:
                busted += 1
                bust_hand = h
                break
            bk += play_hand(deck, rng, cfg).net * ante
            if bk > peak:
                peak = bk
            dd = peak - bk
            if dd > max_dd:
                max_dd = dd
        finals.append(bk)
        drawdowns.append(max_dd)
        if bust_hand is not None:
            survived_until.append(bust_hand)
    return finals, drawdowns, busted, survived_until


def simulate_bankroll(n_hands, n_sessions, start, ante, cfg,
                      seed=0, workers=1, ruin_level=None):
    if ruin_level is None:
        ruin_level = _max_commitment(cfg) * ante
    workers = max(1, workers)
    base, rem = divmod(n_sessions, workers)
    tasks = [(n_hands, base + (1 if i < rem else 0), start, ante, cfg, ruin_level, seed + i + 1)
             for i in range(workers) if base + (1 if i < rem else 0)]
    finals, drawdowns, survived = [], [], []
    busted = 0
    if workers == 1:
        f, d, b, s = _run_sessions(tasks[0])
        finals, drawdowns, busted, survived = f, d, b, s
    else:
        with ProcessPoolExecutor(max_workers=workers, mp_context=_mp_context()) as ex:
            for f, d, b, s in ex.map(_run_sessions, tasks):
                finals += f
                drawdowns += d
                busted += b
                survived += s
    return {
        "finals": finals,
        "drawdowns": drawdowns,
        "busted": busted,
        "survived": survived,
        "n_hands": n_hands,
        "n_sessions": len(finals),
        "start": start,
    }


def _pct(sorted_vals, q):
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, int(q * len(sorted_vals)))
    return sorted_vals[idx]


def single_hand_stats(n, ante, cfg, seed=0, workers=1):
    """Exact mean (EV mode) and realized std (play mode) of one hand, in money."""
    from .simulator import simulate
    ev_s = simulate(n, seed=seed, cfg=cfg, workers=workers, mode="ev")
    play_s = simulate(n, seed=seed + 1, cfg=cfg, workers=workers, mode="play")
    ev = ev_s.ev_per_hand * ante
    std = play_s.result_std_dev * ante
    return ev, std, ev_s, play_s


def _fmt_money(x):
    return f"${x:,.0f}"


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="uth-bankroll",
        description="Bankroll / variance simulator for Ultimate Texas Hold'em.")
    p.add_argument("-b", "--bankroll", type=float, default=50_000)
    p.add_argument("-a", "--ante", type=float, default=100)
    p.add_argument("--horizons", default="1,100,1000,10000",
                   help="comma-separated hand counts to evaluate")
    p.add_argument("--sessions", type=int, default=20_000,
                   help="sessions per horizon (auto-scaled down for long horizons)")
    p.add_argument("--trips", action="store_true", help="also bet 1 unit Trips")
    p.add_argument("--trips-table", default="pay_table_1")
    p.add_argument("-s", "--seed", type=int, default=0)
    p.add_argument("-w", "--workers", type=int, default=default_workers())
    args = p.parse_args(argv)

    cfg = Config(trips_bet=1.0 if args.trips else 0.0, trips_table=args.trips_table)
    horizons = [int(h) for h in args.horizons.split(",") if h]
    workers = max(1, args.workers)

    print("=" * 66)
    print(" Ultimate Texas Hold'em — bankroll / variance simulator")
    print("=" * 66)
    print(f" Start bankroll : {_fmt_money(args.bankroll)}")
    print(f" Flat Ante      : {_fmt_money(args.ante)}  (Blind {_fmt_money(args.ante)} too; "
          f"Trips {'on' if args.trips else 'off'})")
    print(f" Bet per hand   : {_fmt_money(args.ante)} up to "
          f"{_fmt_money(_max_commitment(cfg) * args.ante)} (when raising 4x)")

    ev, std, ev_s, play_s = single_hand_stats(400_000, args.ante, cfg,
                                               seed=args.seed, workers=workers)
    avg_bet = ev_s.avg_total_bet * args.ante
    print("-" * 66)
    print(" Single hand:")
    print(f"   Expected result : {ev:+,.2f}  ({ev_s.house_edge:+.3f}% of Ante)")
    print(f"   Std deviation   : {_fmt_money(std)}   (avg wagered {_fmt_money(avg_bet)}/hand)")
    print("-" * 66)
    print(f" {'hands':>7} {'mean end':>12} {'median':>11} {'P(ahead)':>9} "
          f"{'5th %':>11} {'95th %':>11} {'risk of ruin':>13} {'med. max DD':>12}")

    for n_hands in horizons:
        # Scale sessions so total work stays bounded.
        sess = max(1200, min(args.sessions, 2_500_000 // max(1, n_hands)))
        res = simulate_bankroll(n_hands, sess, args.bankroll, args.ante, cfg,
                                seed=args.seed + n_hands, workers=workers)
        finals = sorted(res["finals"])
        m = sum(finals) / len(finals)
        ahead = sum(1 for x in finals if x > args.bankroll) / len(finals)
        ruin = res["busted"] / res["n_sessions"]
        dd = sorted(res["drawdowns"])
        med_dd = _pct(dd, 0.50)
        print(f" {n_hands:>7} {_fmt_money(m):>12} {_fmt_money(_pct(finals,0.5)):>11} "
              f"{ahead*100:>8.1f}% {_fmt_money(_pct(finals,0.05)):>11} "
              f"{_fmt_money(_pct(finals,0.95)):>11} {ruin*100:>12.2f}% {_fmt_money(med_dd):>12}")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
