"""Dead-card-aware advisor tests."""

import itertools
import random

from uth.cards import parse_cards
from uth.evaluator import eval7, category_of, PAIR
from uth.game import Config
from uth.paytables import blind_payout
from uth.advisor import solve_river, solve_flop, solve_preflop


def _brute_river_bet_ev(hole, board, dead, cfg):
    seen = set(hole) | set(board) | set(dead)
    pool = [c for c in range(52) if c not in seen]
    ps = eval7(list(hole) + list(board))
    bw = blind_payout(ps, cfg.blind_table)
    total = ev = 0.0
    for d1, d2 in itertools.combinations(pool, 2):
        ds = eval7([d1, d2] + list(board))
        dq = category_of(ds) >= PAIR
        o = 1 if ps > ds else (-1 if ps < ds else 0)
        v = 1.0 * o + (o if dq else 0) + (bw if o > 0 else (-1.0 if o < 0 else 0))
        ev += v
        total += 1
    return ev / total


def test_river_matches_brute_force():
    cfg = Config(trips_bet=0.0)
    rng = random.Random(3)
    deck = list(range(52))
    for _ in range(40):
        rng.shuffle(deck)
        hole = (deck[0], deck[1])
        board = tuple(deck[2:7])
        dead = deck[7:17]
        res = solve_river(hole, board, dead, cfg)
        assert abs(res["ev_bet"] - _brute_river_bet_ev(hole, board, dead, cfg)) < 1e-9


def test_dead_cards_shrink_dealer_pool():
    cfg = Config(trips_bet=0.0)
    hole = parse_cards("AsKd")
    board = parse_cards("Qh7c2d5s9c")
    assert solve_river(hole, board, [], cfg)["dealer_combos"] == 45 * 44 // 2
    dead = parse_cards("2h2c3d3s4h4c5d5h")  # 8 dead -> pool of 37
    assert solve_river(hole, board, dead, cfg)["dealer_combos"] == 37 * 36 // 2


def test_flopped_quads_raises_2x():
    cfg = Config(trips_bet=0.0)
    hole = parse_cards("AsAh")
    flop = parse_cards("AdAc7d")
    res = solve_flop(hole, flop, [], cfg)
    assert res["action"] == "bet 2x"
    assert res["ev_raise2x"] > res["ev_check"]


def test_premium_pair_raises_4x():
    cfg = Config(trips_bet=0.0)
    res = solve_preflop(parse_cards("AsAh"), [], cfg, random.Random(1), board_samples=1500)
    assert res["action"] == "raise 4x"
