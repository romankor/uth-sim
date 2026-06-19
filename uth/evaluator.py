"""Poker hand evaluator.

``eval7`` scores any 5-, 6-, or 7-card hand directly (no 5-card subset loop) and
returns a single integer where a larger value is a strictly stronger hand. The
score packs the category in the high bits and up to five ordered tiebreak ranks
in 4-bit nibbles below it, so two scores can be compared with ``<`` / ``>``.

The river decision enumerates 990 dealer hole-card combinations sharing the same
five community cards, so ``board_state`` / ``eval_with_board`` let that hot loop
reuse the board's rank/suit histogram and only fold in the two new cards.
"""

# Hand categories, ordered weakest (0) to strongest (8).
HIGH_CARD = 0
PAIR = 1
TWO_PAIR = 2
TRIPS = 3
STRAIGHT = 4
FLUSH = 5
FULL_HOUSE = 6
QUADS = 7
STRAIGHT_FLUSH = 8

CATEGORY_NAMES = {
    HIGH_CARD: "High Card",
    PAIR: "Pair",
    TWO_PAIR: "Two Pair",
    TRIPS: "Three of a Kind",
    STRAIGHT: "Straight",
    FLUSH: "Flush",
    FULL_HOUSE: "Full House",
    QUADS: "Four of a Kind",
    STRAIGHT_FLUSH: "Straight Flush",
}


def _straight_high(mask):
    """Return the high rank of the best straight in a rank bitmask, else 0.

    The wheel (A-2-3-4-5) is handled by mirroring an Ace down to a low bit.
    """
    m = mask
    if m & (1 << 14):
        m |= (1 << 1)  # Ace plays low for the wheel
    run = 0
    for r in range(14, 0, -1):
        if (m >> r) & 1:
            run += 1
            if run == 5:
                return r + 4  # highest card of the 5-in-a-row ending at r
        else:
            run = 0
    return 0


def _eval_core(rc, sc, sr, rmask):
    """Score a hand from its precomputed histograms.

    ``rc`` rank counts (index 2..14), ``sc`` suit counts (0..3),
    ``sr`` per-suit rank bitmasks, ``rmask`` union rank bitmask.
    """
    # Straight flush (and royal) — needs 5+ of one suit forming a straight.
    flush_suit = -1
    for s in range(4):
        if sc[s] >= 5:
            flush_suit = s
            break
    if flush_suit >= 0:
        sf_high = _straight_high(sr[flush_suit])
        if sf_high:
            return (STRAIGHT_FLUSH << 20) | (sf_high << 16)

    quad = 0
    trips = []
    pairs = []
    for r in range(14, 1, -1):
        c = rc[r]
        if c == 4:
            quad = r
        elif c == 3:
            trips.append(r)
        elif c == 2:
            pairs.append(r)

    if quad:
        kicker = 0
        for r in range(14, 1, -1):
            if r != quad and rc[r]:
                kicker = r
                break
        return (QUADS << 20) | (quad << 16) | (kicker << 12)

    # Full house: a set of trips plus another trips or a pair.
    if trips:
        trip = trips[0]
        pair = trips[1] if len(trips) > 1 else 0
        if pairs and pairs[0] > pair:
            pair = pairs[0]
        if pair:
            return (FULL_HOUSE << 20) | (trip << 16) | (pair << 12)

    if flush_suit >= 0:
        top = []
        m = sr[flush_suit]
        for r in range(14, 1, -1):
            if (m >> r) & 1:
                top.append(r)
                if len(top) == 5:
                    break
        return ((FLUSH << 20) | (top[0] << 16) | (top[1] << 12)
                | (top[2] << 8) | (top[3] << 4) | top[4])

    straight_high = _straight_high(rmask)
    if straight_high:
        return (STRAIGHT << 20) | (straight_high << 16)

    if trips:
        trip = trips[0]
        ks = []
        for r in range(14, 1, -1):
            if r != trip and rc[r]:
                ks.append(r)
                if len(ks) == 2:
                    break
        return (TRIPS << 20) | (trip << 16) | (ks[0] << 12) | (ks[1] << 8)

    if len(pairs) >= 2:
        p1, p2 = pairs[0], pairs[1]
        kicker = 0
        for r in range(14, 1, -1):
            if r != p1 and r != p2 and rc[r]:
                kicker = r
                break
        return (TWO_PAIR << 20) | (p1 << 16) | (p2 << 12) | (kicker << 8)

    if len(pairs) == 1:
        p = pairs[0]
        ks = []
        for r in range(14, 1, -1):
            if r != p and rc[r]:
                ks.append(r)
                if len(ks) == 3:
                    break
        return (PAIR << 20) | (p << 16) | (ks[0] << 12) | (ks[1] << 8) | (ks[2] << 4)

    ks = []
    for r in range(14, 1, -1):
        if rc[r]:
            ks.append(r)
            if len(ks) == 5:
                break
    return ((HIGH_CARD << 20) | (ks[0] << 16) | (ks[1] << 12)
            | (ks[2] << 8) | (ks[3] << 4) | ks[4])


def eval7(cards):
    """Score a hand of 5 to 7 cards. Larger is stronger."""
    rc = [0] * 15
    sc = [0, 0, 0, 0]
    sr = [0, 0, 0, 0]
    rmask = 0
    for c in cards:
        r = (c >> 2) + 2
        s = c & 3
        rc[r] += 1
        sc[s] += 1
        bit = 1 << r
        sr[s] |= bit
        rmask |= bit
    return _eval_core(rc, sc, sr, rmask)


def board_state(board):
    """Precompute the histograms for a fixed set of board cards."""
    rc = [0] * 15
    sc = [0, 0, 0, 0]
    sr = [0, 0, 0, 0]
    rmask = 0
    for c in board:
        r = (c >> 2) + 2
        s = c & 3
        rc[r] += 1
        sc[s] += 1
        bit = 1 << r
        sr[s] |= bit
        rmask |= bit
    return rc, sc, sr, rmask


def eval_with_board(state, c1, c2):
    """Score the board plus two extra cards, reusing ``board_state(board)``."""
    rc0, sc0, sr0, rmask0 = state
    rc = rc0[:]
    sc = sc0[:]
    sr = sr0[:]
    rmask = rmask0
    for c in (c1, c2):
        r = (c >> 2) + 2
        s = c & 3
        rc[r] += 1
        sc[s] += 1
        bit = 1 << r
        sr[s] |= bit
        rmask |= bit
    return _eval_core(rc, sc, sr, rmask)


def category_of(score):
    return score >> 20


def top_rank_of(score):
    return (score >> 16) & 0xF
