"""Command-line interface for the Ultimate Texas Hold'em EV engine."""

import argparse
import sys
import time

from .game import Config
from .paytables import TRIPS_PAYTABLES, DEFAULT_TRIPS_TABLE
from .simulator import simulate, default_workers


def _progress(done, total):
    pct = done / total * 100.0
    sys.stderr.write(f"\r  simulating… {done:,}/{total:,} ({pct:5.1f}%)")
    sys.stderr.flush()
    if done >= total:
        sys.stderr.write("\n")


def build_parser():
    p = argparse.ArgumentParser(
        prog="uth-sim",
        description="Monte Carlo EV engine for Ultimate Texas Hold'em (optimal strategy).",
    )
    p.add_argument("-n", "--hands", type=int, default=100_000,
                   help="number of hands to simulate (default: 100,000)")
    p.add_argument("-s", "--seed", type=int, default=0,
                   help="base RNG seed (default: 0)")
    p.add_argument("-w", "--workers", type=int, default=default_workers(),
                   help="parallel worker processes (default: all CPUs)")
    p.add_argument("--no-trips", action="store_true",
                   help="do not place the Trips side bet")
    p.add_argument("--trips-bet", type=float, default=1.0,
                   help="Trips bet size in ante units (default: 1.0)")
    p.add_argument("--trips-table", choices=sorted(TRIPS_PAYTABLES),
                   default=DEFAULT_TRIPS_TABLE,
                   help=f"Trips pay table (default: {DEFAULT_TRIPS_TABLE})")
    p.add_argument("--mode", choices=("ev", "play"), default="ev",
                   help="ev: exact dealer-integrated EV (default, fast convergence); "
                        "play: sample one dealer hand per deal (realized variance)")
    p.add_argument("--quiet", action="store_true",
                   help="suppress the progress indicator")
    return p


def format_report(stats, args, elapsed):
    d = stats.decisions
    h = stats.hands
    pct = lambda k: d[k] / h * 100.0 if h else 0.0
    mode_note = ("exact dealer-integrated EV; Trips analytical"
                 if stats.mode == "ev" else "realized single-deal results")
    ante_pb = stats.sum_ante / h
    play_pb = stats.sum_play / h
    # In EV mode the Blind is reported via the control variate (base - ante - play);
    # in play mode it is the directly observed average.
    blind_pb = (stats.base_ev_per_hand - ante_pb - play_pb
                if stats.mode == "ev" else stats.sum_blind / h)
    lines = [
        "",
        "=" * 60,
        " Ultimate Texas Hold'em — Monte Carlo EV report",
        "=" * 60,
        f" Hands simulated     : {h:,}",
        f" Mode                : {stats.mode}  ({mode_note})",
        f" Trips side bet      : {'off' if args.no_trips else f'{args.trips_bet:g}u ({args.trips_table})'}",
        f" Seed / workers      : {args.seed} / {args.workers}",
        f" Elapsed             : {elapsed:.2f}s  ({h / elapsed:,.0f} hands/s)" if elapsed > 0 else "",
        "-" * 60,
        f" EV per hand         : {stats.ev_per_hand:+.5f} antes",
    ]
    if stats.mode == "ev":
        lines.append(
            f" House edge (Ante)   : {stats.base_house_edge:+.4f}%  ± {stats.house_edge_ci95:.4f} (95% CI)")
        if not args.no_trips:
            lines.append(
                f" Trips edge (/Trips) : {stats.trips_house_edge:+.4f}%  (exact, analytical)")
    else:
        lines.append(
            f" House edge (/ante)  : {stats.house_edge:+.4f}%  ± {stats.house_edge_ci95:.4f} (95% CI)")
    lines += [
        f" Element of risk     : {stats.element_of_risk:+.4f}%  (/ total wagered)",
        f" Std dev per hand    : {stats.result_std_dev:.4f} antes",
        f" Avg total wagered   : {stats.avg_total_bet:.4f} antes/hand",
        "-" * 60,
        " Expected net per bet (antes/hand):",
        f"   Ante              : {ante_pb:+.5f}",
        f"   Blind             : {blind_pb:+.5f}",
        f"   Play              : {play_pb:+.5f}",
        f"   Trips             : {stats.trips_ev_per_hand:+.5f}" if not args.no_trips else "   Trips             : (not bet)",
        "-" * 60,
        " Decision frequencies:",
        f"   Raise 4x (pre)    : {pct('4x'):5.2f}%",
        f"   Bet 2x (flop)     : {pct('2x'):5.2f}%",
        f"   Bet 1x (river)    : {pct('1x'):5.2f}%",
        f"   Fold              : {pct('fold'):5.2f}%",
        "=" * 60,
    ]
    return "\n".join(line for line in lines if line != "")


def main(argv=None):
    args = build_parser().parse_args(argv)
    cfg = Config(
        trips_bet=0.0 if args.no_trips else args.trips_bet,
        trips_table=args.trips_table,
    )
    progress = None if args.quiet else _progress
    start = time.time()
    stats = simulate(args.hands, seed=args.seed, cfg=cfg,
                     workers=max(1, args.workers), mode=args.mode,
                     progress=progress)
    elapsed = time.time() - start
    print(format_report(stats, args, elapsed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
