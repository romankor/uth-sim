"""Command-line dead-card-aware strategy advisor.

Examples
--------
    # Pre-flop, you hold As Kd; five opponents' ten cards are known
    python -m uth.advise --hole "AsKd" --dead "2c 2h 7d 9s Jh Js 4c 4d Tc Th"

    # On the flop / river, also pass the community cards
    python -m uth.advise --hole "AsKd" --board "Ah 7c 2d" --dead "..."
    python -m uth.advise --hole "AsKd" --board "Ah 7c 2d Ts 3h" --dead "..."
"""

import argparse
import random
import sys

from .cards import parse_cards, hand_str
from .game import Config
from .advisor import solve_preflop, solve_flop, solve_river


def _solve(street, hole, board, dead, cfg, rng, samples):
    if street == "preflop":
        return solve_preflop(hole, dead, cfg, rng, board_samples=samples)
    if street == "flop":
        return solve_flop(hole, board, dead, cfg)
    return solve_river(hole, board, dead, cfg)


def _fmt(res):
    s = res["street"]
    if s == "preflop":
        return (f"raise 4x: EV {res['ev_raise4x']:+.4f} (±{res['ci_raise4x']:.4f})   "
                f"check: EV {res['ev_check']:+.4f} (±{res['ci_check']:.4f})")
    if s == "flop":
        return (f"bet 2x: EV {res['ev_raise2x']:+.4f}   "
                f"check: EV {res['ev_check']:+.4f}")
    return (f"bet 1x: EV {res['ev_bet']:+.4f}   "
            f"fold: EV {res['ev_fold']:+.4f}")


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="uth-advise",
        description="Dead-card-aware optimal decision for one UTH hand.")
    p.add_argument("--hole", required=True, help="your two hole cards, e.g. 'AsKd'")
    p.add_argument("--board", default="", help="community cards: 3 (flop) or 5 (river)")
    p.add_argument("--dead", default="", help="other players' known hole cards")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--preflop-samples", type=int, default=8000,
                   help="Monte Carlo boards for the pre-flop decision")
    p.add_argument("--trips-table", default="pay_table_1")
    args = p.parse_args(argv)

    hole = parse_cards(args.hole)
    board = parse_cards(args.board)
    dead = parse_cards(args.dead)
    if len(hole) != 2:
        p.error("--hole must be exactly two cards")
    if len(board) not in (0, 3, 5):
        p.error("--board must be 0, 3, or 5 cards")
    all_cards = hole + board + dead
    if len(set(all_cards)) != len(all_cards):
        p.error("a card is repeated across --hole/--board/--dead")

    street = {0: "preflop", 3: "flop", 5: "river"}[len(board)]
    cfg = Config(trips_bet=0.0, trips_table=args.trips_table)

    with_dead = _solve(street, hole, tuple(board), dead, cfg, random.Random(args.seed), args.preflop_samples)
    base = _solve(street, hole, tuple(board), [], cfg, random.Random(args.seed), args.preflop_samples)

    print()
    print("=" * 64)
    print(f" UTH advisor — {street.upper()} decision")
    print("=" * 64)
    print(f" Your hand   : {hand_str(hole)}")
    if board:
        print(f" Board       : {hand_str(board)}")
    print(f" Dead cards  : {hand_str(dead) if dead else '(none)'}  ({len(dead)} cards)")
    print("-" * 64)
    print(f" Ignoring dead cards : {base['action'].upper():9}  | {_fmt(base)}")
    print(f" Using dead cards    : {with_dead['action'].upper():9}  | {_fmt(with_dead)}")
    print("-" * 64)
    if base["action"] != with_dead["action"]:
        print(f" >> The dead cards CHANGE the optimal play: "
              f"{base['action']} -> {with_dead['action']}")
    else:
        print(" >> Same optimal action; the dead cards only nudge the EVs.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
