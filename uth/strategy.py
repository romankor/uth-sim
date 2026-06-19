"""Optimal player strategy.

Pre-flop (4x) and flop (2x) decisions use the published Wizard of Odds basic
strategy charts. The river decision (1x bet vs fold) is solved *exactly*: with
all five community cards known we enumerate every C(45, 2) = 990 dealer hole-card
combination and bet whenever the expected value of betting beats folding. This is
provably optimal for the river and replaces the chart's "21 outs" heuristic.
"""

from .evaluator import (
    TWO_PAIR, PAIR, board_state, eval_with_board, eval7, category_of,
)
from .paytables import blind_payout


def preflop_raise(hole):
    """Return True to raise 4x pre-flop with the two hole cards."""
    c1, c2 = hole
    r1 = (c1 >> 2) + 2
    r2 = (c2 >> 2) + 2
    suited = (c1 & 3) == (c2 & 3)

    if r1 == r2:                     # pocket pair: raise 33 or higher
        return r1 >= 3
    hi = r1 if r1 > r2 else r2
    lo = r2 if r1 > r2 else r1
    if hi == 14:                     # any Ace
        return True
    if hi == 13:                     # King: suited any, offsuit 5+
        return True if suited else lo >= 5
    if hi == 12:                     # Queen: suited 6+, offsuit 8+
        return lo >= 6 if suited else lo >= 8
    if hi == 11:                     # Jack: suited 8+, offsuit T
        return lo >= 8 if suited else lo == 10
    return False


def flop_raise(hole, flop):
    """Return True to raise 2x on the flop (hole + three community cards)."""
    cards = (hole[0], hole[1], flop[0], flop[1], flop[2])
    if category_of(eval7(cards)) >= TWO_PAIR:
        return True

    r1 = (hole[0] >> 2) + 2
    r2 = (hole[1] >> 2) + 2
    flop_ranks = ((flop[0] >> 2) + 2, (flop[1] >> 2) + 2, (flop[2] >> 2) + 2)

    # Hidden pair (uses a hole card), excluding a pair of deuces.
    if r1 == r2 and r1 >= 3:
        return True
    if (r1 >= 3 and r1 in flop_ranks) or (r2 >= 3 and r2 in flop_ranks):
        return True

    # Four to a flush including a hidden card of ten or higher.
    for s in range(4):
        suited = [c for c in cards if (c & 3) == s]
        if len(suited) == 4:
            for hc in hole:
                if (hc & 3) == s and ((hc >> 2) + 2) >= 10:
                    return True
    return False


def river_should_bet(hole, board):
    """Exact river decision: True to bet 1x, False to fold.

    EV is measured in ante units and includes the Play, Ante, and Blind bets
    (Trips is unaffected by this choice). Folding loses the Ante and Blind for a
    fixed -2; we bet whenever the averaged EV over all dealer holdings exceeds it.
    """
    state = board_state(board)
    player_score = eval_with_board(state, hole[0], hole[1])
    blind_win = blind_payout(player_score)

    seen = (hole[0], hole[1], board[0], board[1], board[2], board[3], board[4])
    seen_set = set(seen)
    remaining = [c for c in range(52) if c not in seen_set]

    total = 0.0
    count = 0
    n = len(remaining)
    for i in range(n):
        ci = remaining[i]
        for j in range(i + 1, n):
            dealer_score = eval_with_board(state, ci, remaining[j])
            dealer_qualifies = category_of(dealer_score) >= PAIR
            if player_score > dealer_score:
                v = 1.0                       # Play bet wins
                if dealer_qualifies:
                    v += 1.0                  # Ante wins
                v += blind_win                # Blind pays per table
            elif player_score < dealer_score:
                v = -1.0                      # Play loses
                if dealer_qualifies:
                    v -= 1.0                  # Ante loses
                v -= 1.0                      # Blind loses
            else:
                v = 0.0                       # tie pushes everything
            total += v
            count += 1

    ev_bet = total / count
    return ev_bet > -2.0
