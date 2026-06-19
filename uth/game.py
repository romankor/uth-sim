"""Play and settle a single hand of Ultimate Texas Hold'em.

Bet sizes are in ante units. Each hand stakes an Ante (1) and Blind (1), an
optional Trips side bet, and a Play bet of 4x / 2x / 1x depending on when the
player raises (or 0 if they fold at the river).

Settlement rules:
  * Play  — even money on win, loses on loss, pushes on tie, regardless of
            whether the dealer qualifies.
  * Ante  — pushes when the dealer fails to qualify (no pair or better);
            otherwise even money on win, loses on loss, pushes on tie.
  * Blind — pays the Blind pay table on a winning hand (straight or better,
            else pushes), loses on a loss, pushes on a tie.
  * Trips — pays the Trips pay table on the player's seven-card hand (trips or
            better) regardless of fold or dealer hand.
"""

from .evaluator import (
    PAIR, eval7, category_of, board_state, eval_with_board,
)
from .paytables import (
    BLIND_PAYTABLE, TRIPS_PAYTABLES, DEFAULT_TRIPS_TABLE,
    blind_payout, trips_payout,
)
from .strategy import preflop_raise, flop_raise, river_should_bet


class Config:
    """Simulation configuration shared by every hand."""

    def __init__(self, trips_bet=1.0, trips_table=DEFAULT_TRIPS_TABLE,
                 blind_table=None, n_dead=0):
        self.trips_bet = float(trips_bet)
        self.trips_table = TRIPS_PAYTABLES[trips_table]
        self.blind_table = blind_table or BLIND_PAYTABLE
        # Number of other players' hole cards known to the hero (2 per opponent).
        # These are removed from the dealer's pool, making play dead-card aware.
        self.n_dead = int(n_dead)


class HandResult:
    __slots__ = ("net", "wagered", "play_bet", "decision",
                 "trips_net", "ante_net", "blind_net", "play_net", "cv")

    def __init__(self, net, wagered, play_bet, decision,
                 trips_net, ante_net, blind_net, play_net, cv):
        self.net = net
        self.wagered = wagered
        self.play_bet = play_bet
        self.decision = decision          # "4x" | "2x" | "1x" | "fold"
        self.trips_net = trips_net
        self.ante_net = ante_net
        self.blind_net = blind_net
        self.play_net = play_net
        self.cv = cv                      # blind multiplier (control variate)


def play_hand(deck, rng, cfg):
    """Shuffle ``deck`` in place, play one hand, and return a HandResult."""
    rng.shuffle(deck)
    hole = (deck[0], deck[1])
    dealer_hole = (deck[2], deck[3])
    board = (deck[4], deck[5], deck[6], deck[7], deck[8])

    # --- Betting decisions ---------------------------------------------------
    if preflop_raise(hole):
        play_bet, decision = 4.0, "4x"
    elif flop_raise(hole, board[:3]):
        play_bet, decision = 2.0, "2x"
    elif river_should_bet(hole, board):
        play_bet, decision = 1.0, "1x"
    else:
        play_bet, decision = 0.0, "fold"

    wagered = 1.0 + 1.0 + cfg.trips_bet + play_bet  # ante + blind + trips + play

    # --- Trips side bet (independent of fold / dealer) -----------------------
    player_score = eval7((hole[0], hole[1], board[0], board[1], board[2], board[3], board[4]))
    trips_net = 0.0
    if cfg.trips_bet:
        mult = trips_payout(player_score, cfg.trips_table)
        trips_net = cfg.trips_bet * mult if mult is not None else -cfg.trips_bet

    cv = blind_payout(player_score, cfg.blind_table)
    if decision == "fold":
        ante_net, blind_net = -1.0, -1.0
        net = trips_net + ante_net + blind_net
        return HandResult(net, wagered, 0.0, decision, trips_net, ante_net, blind_net, 0.0, cv)

    # --- Showdown ------------------------------------------------------------
    dealer_score = eval7((dealer_hole[0], dealer_hole[1],
                          board[0], board[1], board[2], board[3], board[4]))
    dealer_qualifies = category_of(dealer_score) >= PAIR

    if player_score > dealer_score:
        outcome = 1
    elif player_score < dealer_score:
        outcome = -1
    else:
        outcome = 0

    play_net = play_bet * outcome
    ante_net = (1.0 * outcome) if dealer_qualifies else 0.0
    if outcome > 0:
        blind_net = blind_payout(player_score, cfg.blind_table)
    elif outcome < 0:
        blind_net = -1.0
    else:
        blind_net = 0.0

    net = trips_net + play_net + ante_net + blind_net
    return HandResult(net, wagered, play_bet, decision,
                      trips_net, ante_net, blind_net, play_net, cv)


class HandEV:
    """Exact expected value of one dealt hand, integrated over dealer holes."""

    __slots__ = ("ev", "m2", "wagered", "play_bet", "decision",
                 "trips_ev", "ante_ev", "blind_ev", "play_ev", "cv")

    def __init__(self, ev, m2, wagered, play_bet, decision,
                 trips_ev, ante_ev, blind_ev, play_ev, cv):
        self.ev = ev            # exact E[net] for this deal (Ante+Blind+Play)
        self.m2 = m2            # exact E[net^2] for this deal
        self.wagered = wagered
        self.play_bet = play_bet
        self.decision = decision
        self.trips_ev = trips_ev
        self.ante_ev = ante_ev
        self.blind_ev = blind_ev
        self.play_ev = play_ev
        self.cv = cv            # blind multiplier of the player's hand (control variate)


def exact_hand_ev(deck, rng, cfg):
    """Deal a player hand + board and return its exact :class:`HandEV`.

    Only the player's two hole cards and the five community cards are sampled;
    the dealer's hand is integrated out by enumerating all C(45, 2) = 990
    possible dealer holdings. The returned EV is the exact conditional mean for
    this deal, which makes the Monte Carlo average converge far faster than
    dealing a single random dealer hand.
    """
    rng.shuffle(deck)
    dead = deck[7:7 + cfg.n_dead] if cfg.n_dead else ()
    return ev_for_deal((deck[0], deck[1]),
                       (deck[2], deck[3], deck[4], deck[5], deck[6]), cfg, dead)


def ev_for_deal(hole, board, cfg, dead=()):
    """Exact :class:`HandEV` for an explicit player hand and five-card board.

    ``dead`` are other players' hole cards, which are removed from the dealer's
    possible holdings (the river decision and the EV become dead-card aware).
    """
    state = board_state(board)
    player_score = eval_with_board(state, hole[0], hole[1])
    blind_win = blind_payout(player_score, cfg.blind_table)

    # The Trips side bet depends only on the player's seven-card hand, so its EV
    # is handled analytically by the simulator (see paytables.trips_analytics)
    # rather than sampled here. This deal's EV covers Ante + Blind + Play only.

    # Decide the player's action (uses only the player's own information).
    if preflop_raise(hole):
        play_bet, decision, decide_river = 4.0, "4x", False
    elif flop_raise(hole, board[:3]):
        play_bet, decision, decide_river = 2.0, "2x", False
    else:
        play_bet, decision, decide_river = 1.0, "1x", True  # tentative; may fold

    # Enumerate every possible dealer holding and tally outcomes. Dead cards
    # (other players' holes) are excluded from the dealer's possible pool.
    seen = {hole[0], hole[1], board[0], board[1], board[2], board[3], board[4]}
    seen.update(dead)
    remaining = [c for c in range(52) if c not in seen]
    n = len(remaining)
    win = lose = tie = win_q = lose_q = 0
    for i in range(n):
        ci = remaining[i]
        for j in range(i + 1, n):
            ds = eval_with_board(state, ci, remaining[j])
            if player_score > ds:
                win += 1
                if category_of(ds) >= PAIR:
                    win_q += 1
            elif player_score < ds:
                lose += 1
                if category_of(ds) >= PAIR:
                    lose_q += 1
            else:
                tie += 1
    total = win + lose + tie

    def moments(pb):
        """Exact (mean, E[x^2]) of the net for a given Play bet over dealer holes."""
        win_nq = win - win_q
        lose_nq = lose - lose_q
        # Net for each outcome class (Play + Ante + Blind).
        v_win_q = pb + 1.0 + blind_win
        v_win_nq = pb + blind_win                      # Ante pushes
        v_lose_q = -pb - 1.0 - 1.0
        v_lose_nq = -pb - 1.0                          # Ante pushes
        v_tie = 0.0
        s = (win_q * v_win_q + win_nq * v_win_nq
             + lose_q * v_lose_q + lose_nq * v_lose_nq + tie * v_tie)
        s2 = (win_q * v_win_q * v_win_q + win_nq * v_win_nq * v_win_nq
              + lose_q * v_lose_q * v_lose_q + lose_nq * v_lose_nq * v_lose_nq
              + tie * v_tie * v_tie)
        return s / total, s2 / total

    if decide_river:
        ev_bet, m2_bet = moments(1.0)
        ev_fold = -2.0
        if ev_bet <= ev_fold:                          # fold is better
            play_bet, decision = 0.0, "fold"
            ev, m2 = ev_fold, ev_fold * ev_fold
        else:
            ev, m2 = ev_bet, m2_bet
    else:
        ev, m2 = moments(play_bet)

    wagered = 1.0 + 1.0 + cfg.trips_bet + play_bet

    if decision == "fold":
        ante_ev, blind_ev, play_ev = -1.0, -1.0, 0.0
    else:
        play_ev = play_bet * (win - lose) / total
        ante_ev = (win_q - lose_q) / total
        blind_ev = (win * blind_win - lose) / total

    return HandEV(ev, m2, wagered, play_bet, decision,
                  0.0, ante_ev, blind_ev, play_ev, blind_win)
