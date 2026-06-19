"""Pay tables for the Blind bet and the Trips side bet.

Payouts are expressed as the profit per unit staked ("to 1"): a win returns the
stake plus this multiple. The Blind bet only pays on a winning hand of a
straight or better and otherwise pushes; the Trips bet pays on the player's hand
of trips or better regardless of the dealer.
"""

from .evaluator import (
    STRAIGHT_FLUSH, QUADS, FULL_HOUSE, FLUSH, STRAIGHT, TRIPS,
    category_of, top_rank_of,
)

# Standard Blind bet pay table (to 1). Anything below a straight pushes.
BLIND_PAYTABLE = {
    "royal_flush": 500.0,
    "straight_flush": 50.0,
    "quads": 10.0,
    "full_house": 3.0,
    "flush": 1.5,
    "straight": 1.0,
}

# Trips side-bet pay tables (to 1). Several casino variants exist; the default
# ("pay_table_1") is the most common and yields a Trips house edge of ~1.9%.
TRIPS_PAYTABLES = {
    "pay_table_1": {
        "royal_flush": 50.0,
        "straight_flush": 40.0,
        "quads": 30.0,
        "full_house": 8.0,
        "flush": 7.0,
        "straight": 4.0,
        "trips": 3.0,
    },
    "pay_table_5": {
        "royal_flush": 50.0,
        "straight_flush": 40.0,
        "quads": 30.0,
        "full_house": 9.0,
        "flush": 7.0,
        "straight": 4.0,
        "trips": 3.0,
    },
    "pay_table_6": {
        "royal_flush": 50.0,
        "straight_flush": 40.0,
        "quads": 20.0,
        "full_house": 7.0,
        "flush": 6.0,
        "straight": 5.0,
        "trips": 3.0,
    },
}

DEFAULT_TRIPS_TABLE = "pay_table_1"


# Exact frequencies of every category among all C(52,7) = 133,784,560 seven-card
# hands. The Trips bet pays on the player's seven-card hand regardless of the
# dealer, so its EV and variance are exact constants computed from this table —
# no sampling, and no dependence on whether a rare royal has been dealt yet.
SEVEN_CARD_FREQUENCIES = {
    "royal_flush": 4_324,
    "straight_flush": 37_260,     # excludes royals
    "quads": 224_848,
    "full_house": 3_473_184,
    "flush": 4_047_644,           # excludes straight flushes
    "straight": 6_180_020,        # excludes straight flushes
    "trips": 6_461_620,
    "below_trips": 113_355_660,   # two pair + one pair + high card (Trips loses)
}
SEVEN_CARD_TOTAL = 133_784_560


def trips_analytics(table, bet=1.0):
    """Exact (mean, second moment) of the Trips bet net per hand, in ante units."""
    freq = SEVEN_CARD_FREQUENCIES
    total = SEVEN_CARD_TOTAL
    s = s2 = 0.0
    for cat, count in freq.items():
        if cat == "below_trips":
            v = -bet                       # the Trips bet loses
        else:
            v = bet * table[cat]           # wins this multiple
        s += count * v
        s2 += count * v * v
    return s / total, s2 / total


def blind_cv_mean(table=BLIND_PAYTABLE):
    """Analytical E[blind multiplier] over a random 7-card hand.

    The blind multiplier (0 below a straight, up to 500 for a royal) is a
    function only of the player's hand, so its mean is exact. It is used as a
    control variate to cancel the enormous variance the rare 500:1 royal would
    otherwise inject into the sampled house-edge estimate.
    """
    f = SEVEN_CARD_FREQUENCIES
    s = (f["royal_flush"] * table["royal_flush"]
         + f["straight_flush"] * table["straight_flush"]
         + f["quads"] * table["quads"]
         + f["full_house"] * table["full_house"]
         + f["flush"] * table["flush"]
         + f["straight"] * table["straight"])
    return s / SEVEN_CARD_TOTAL


def blind_payout(score, table=BLIND_PAYTABLE):
    """Profit multiple on a *winning* Blind bet for the player's hand."""
    cat = category_of(score)
    if cat == STRAIGHT_FLUSH:
        return table["royal_flush"] if top_rank_of(score) == 14 else table["straight_flush"]
    if cat == QUADS:
        return table["quads"]
    if cat == FULL_HOUSE:
        return table["full_house"]
    if cat == FLUSH:
        return table["flush"]
    if cat == STRAIGHT:
        return table["straight"]
    return 0.0  # pushes below a straight


def trips_payout(score, table):
    """Profit multiple on the Trips bet, or ``None`` if the bet loses."""
    cat = category_of(score)
    if cat == STRAIGHT_FLUSH:
        return table["royal_flush"] if top_rank_of(score) == 14 else table["straight_flush"]
    if cat == QUADS:
        return table["quads"]
    if cat == FULL_HOUSE:
        return table["full_house"]
    if cat == FLUSH:
        return table["flush"]
    if cat == STRAIGHT:
        return table["straight"]
    if cat == TRIPS:
        return table["trips"]
    return None  # below trips: the bet loses
