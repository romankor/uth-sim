"""Dead-card-aware strategy solver.

In Ultimate Texas Hold'em every player plays only against the dealer, so the
other players' hole cards are *dead cards*: they cannot appear in the dealer's
hand or on the board. Knowing them shrinks the pool the dealer (and the
remaining board) is drawn from, which can shift a marginal decision.

This module solves each street's decision exactly where it is cheap and by
Monte Carlo where full enumeration is not, always conditioning on a supplied set
of dead cards:

* ``solve_river`` — exact. Enumerate every possible dealer holding from the pool
  (52 − your 2 − board 5 − dead) and bet 1x iff it beats folding.
* ``solve_flop`` — exact. Enumerate the two remaining board cards and, for each,
  the dealer's holding; compare raising 2x against checking-then-optimal-river.
* ``solve_preflop`` — Monte Carlo over boards (the dealer is integrated exactly
  per board). The check-line uses the standard flop heuristic with an exact,
  dead-card-aware river, which is an excellent and fast approximation.
"""

import math

from .evaluator import board_state, eval_with_board, category_of, PAIR
from .paytables import blind_payout
from .strategy import flop_raise


def _pool(*groups):
    used = set()
    for g in groups:
        used.update(g)
    return [c for c in range(52) if c not in used]


def _showdown_stats(hole, board, dealer_pool):
    """Tally player vs every two-card dealer holding drawn from ``dealer_pool``."""
    state = board_state(board)
    ps = eval_with_board(state, hole[0], hole[1])
    win = lose = tie = win_q = lose_q = 0
    n = len(dealer_pool)
    for i in range(n):
        ci = dealer_pool[i]
        for j in range(i + 1, n):
            ds = eval_with_board(state, ci, dealer_pool[j])
            if ps > ds:
                win += 1
                if category_of(ds) >= PAIR:
                    win_q += 1
            elif ps < ds:
                lose += 1
                if category_of(ds) >= PAIR:
                    lose_q += 1
            else:
                tie += 1
    return ps, win, lose, tie, win_q, lose_q


def _showdown_ev(stats, play_bet, blind_table):
    """Exact EV (Ante+Blind+Play) for a committed Play bet over the tallied pool."""
    ps, win, lose, tie, win_q, lose_q = stats
    total = win + lose + tie
    bw = blind_payout(ps, blind_table)
    return (play_bet * (win - lose) / total
            + (win_q - lose_q) / total
            + (win * bw - lose) / total)


def solve_river(hole, board, dead, cfg):
    """Exact river decision (bet 1x vs fold) given five board cards and dead cards."""
    pool = _pool(hole, board, dead)
    stats = _showdown_stats(hole, board, pool)
    ev_bet = _showdown_ev(stats, 1.0, cfg.blind_table)
    ev_fold = -2.0
    return {
        "street": "river",
        "action": "bet 1x" if ev_bet > ev_fold else "fold",
        "ev_bet": ev_bet,
        "ev_fold": ev_fold,
        "dealer_combos": len(pool) * (len(pool) - 1) // 2,
    }


def solve_flop(hole, flop, dead, cfg):
    """Exact flop decision (bet 2x vs check) by enumerating turn+river and dealer."""
    pool = _pool(hole, flop, dead)
    n = len(pool)
    sum_2x = sum_check = 0.0
    boards = 0
    for a in range(n):
        for b in range(a + 1, n):
            board = (flop[0], flop[1], flop[2], pool[a], pool[b])
            dealer_pool = pool[:a] + pool[a + 1:b] + pool[b + 1:]
            stats = _showdown_stats(hole, board, dealer_pool)
            sum_2x += _showdown_ev(stats, 2.0, cfg.blind_table)
            sum_check += max(_showdown_ev(stats, 1.0, cfg.blind_table), -2.0)
            boards += 1
    ev_2x = sum_2x / boards
    ev_check = sum_check / boards
    return {
        "street": "flop",
        "action": "bet 2x" if ev_2x >= ev_check else "check",
        "ev_raise2x": ev_2x,
        "ev_check": ev_check,
        "boards": boards,
    }


def solve_preflop(hole, dead, cfg, rng, board_samples=4000):
    """Monte Carlo pre-flop decision (raise 4x vs check), dead-card aware.

    The check-line value uses the standard flop heuristic (it sees only the
    flop, so there is no look-ahead) with an exact dead-card-aware river.
    """
    pool = _pool(hole, dead)
    s4 = ss4 = sc = ssc = 0.0
    for _ in range(board_samples):
        board = tuple(rng.sample(pool, 5))
        bset = set(board)
        dealer_pool = [c for c in pool if c not in bset]
        stats = _showdown_stats(hole, board, dealer_pool)
        ev4 = _showdown_ev(stats, 4.0, cfg.blind_table)
        if flop_raise(hole, board[:3]):
            cont = _showdown_ev(stats, 2.0, cfg.blind_table)
        else:
            cont = max(_showdown_ev(stats, 1.0, cfg.blind_table), -2.0)
        s4 += ev4
        ss4 += ev4 * ev4
        sc += cont
        ssc += cont * cont
    n = board_samples
    ev4m, evcm = s4 / n, sc / n
    ci4 = 1.96 * math.sqrt(max(0.0, ss4 / n - ev4m ** 2) / n)
    cic = 1.96 * math.sqrt(max(0.0, ssc / n - evcm ** 2) / n)
    return {
        "street": "preflop",
        "action": "raise 4x" if ev4m >= evcm else "check",
        "ev_raise4x": ev4m,
        "ev_check": evcm,
        "ci_raise4x": ci4,
        "ci_check": cic,
        "samples": n,
    }
