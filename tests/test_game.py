"""Game settlement and house-edge validation."""

import itertools
import random

from uth.evaluator import eval7, category_of, PAIR
from uth.game import Config, play_hand, ev_for_deal
from uth.paytables import blind_payout
from uth.simulator import simulate, default_workers


def _brute_ev(hole, board, play_bet, cfg):
    """Independent reference EV (Ante+Blind+Play) over all dealer holdings."""
    seen = set(hole) | set(board)
    rem = [c for c in range(52) if c not in seen]
    pscore = eval7(list(hole) + list(board))
    bw = blind_payout(pscore, cfg.blind_table)
    total = 0.0
    count = 0
    for d1, d2 in itertools.combinations(rem, 2):
        dscore = eval7([d1, d2] + list(board))
        dq = category_of(dscore) >= PAIR
        o = 1 if pscore > dscore else (-1 if pscore < dscore else 0)
        v = play_bet * o
        if dq:
            v += o                       # Ante (pushes if dealer doesn't qualify)
        if o > 0:
            v += bw                      # Blind pays the table on a win
        elif o < 0:
            v -= 1.0                      # Blind loses
        total += v
        count += 1
    return total / count


def test_exact_ev_matches_brute_force():
    """The fast incremental EV must equal an independent eval7-based settlement."""
    cfg = Config(trips_bet=1.0)
    rng = random.Random(99)
    deck = list(range(52))
    checked = 0
    for _ in range(300):
        rng.shuffle(deck)
        hole = (deck[0], deck[1])
        board = tuple(deck[2:7])
        r = ev_for_deal(hole, board, cfg)
        if r.decision == "fold":
            assert abs(r.ev - (-2.0)) < 1e-9
        else:
            ref = _brute_ev(hole, board, r.play_bet, cfg)
            assert abs(r.ev - ref) < 1e-9, (r.decision, r.ev, ref)
            checked += 1
    assert checked > 0


def test_wagered_accounting():
    cfg = Config(trips_bet=1.0)
    rng = random.Random(7)
    deck = list(range(52))
    for _ in range(2000):
        r = play_hand(deck, rng, cfg)
        assert r.wagered == 2.0 + cfg.trips_bet + r.play_bet
        assert r.decision in ("4x", "2x", "1x", "fold")
        if r.decision == "fold":
            assert r.play_bet == 0.0


def test_house_edge_in_expected_range():
    """The chart+exact-river house edge should sit near ~2.3% of the ante.

    The estimate must be statistically consistent with that target given the
    (variance-reduced) confidence interval, which keeps the test robust to noise
    while still catching gross logic errors.
    """
    stats = simulate(80_000, seed=1, cfg=Config(trips_bet=0.0),
                     workers=default_workers(), mode="ev")
    # The true value must lie within ~4 sigma of the estimate (the deterministic
    # test_exact_ev_matches_brute_force carries the exactness guarantee).
    assert abs(stats.house_edge - 2.35) < 4 * stats.house_edge_ci95, \
        (stats.house_edge, stats.house_edge_ci95)


def test_trips_added_analytically_in_ev_mode():
    no_trips = simulate(2_000, seed=3, cfg=Config(trips_bet=0.0), workers=1, mode="ev")
    with_trips = simulate(2_000, seed=3, cfg=Config(trips_bet=1.0), workers=1, mode="ev")
    # Same deals; Trips shifts EV by exactly its analytical (negative) value.
    assert with_trips.trips_ev_per_hand < 0.0
    assert abs((with_trips.ev_per_hand - no_trips.ev_per_hand)
               - with_trips.trips_ev_per_hand) < 1e-9
