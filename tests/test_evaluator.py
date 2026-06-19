"""Evaluator correctness: known hands and self-consistency vs best-of-21."""

import itertools
import random

from uth.cards import parse_card
from uth.evaluator import (
    eval7, category_of, top_rank_of,
    HIGH_CARD, PAIR, TWO_PAIR, TRIPS, STRAIGHT, FLUSH, FULL_HOUSE, QUADS,
    STRAIGHT_FLUSH,
)


def cat(cards):
    return category_of(eval7([parse_card(c) for c in cards]))


def test_known_categories():
    assert cat(["As", "Ks", "Qs", "Js", "Ts"]) == STRAIGHT_FLUSH
    assert cat(["9s", "8s", "7s", "6s", "5s"]) == STRAIGHT_FLUSH
    assert cat(["As", "2s", "3s", "4s", "5s"]) == STRAIGHT_FLUSH  # wheel sf
    assert cat(["Ah", "Ad", "Ac", "As", "Kd"]) == QUADS
    assert cat(["Ah", "Ad", "Ac", "Ks", "Kd"]) == FULL_HOUSE
    assert cat(["Ah", "Th", "7h", "4h", "2h"]) == FLUSH
    assert cat(["9h", "8d", "7c", "6s", "5h"]) == STRAIGHT
    assert cat(["Ah", "2d", "3c", "4s", "5h"]) == STRAIGHT  # wheel
    assert cat(["Ah", "Ad", "Ac", "Ks", "Qd"]) == TRIPS
    assert cat(["Ah", "Ad", "Ks", "Kd", "Qc"]) == TWO_PAIR
    assert cat(["Ah", "Ad", "Ks", "Qd", "Jc"]) == PAIR
    assert cat(["Ah", "Kd", "Qs", "Jd", "9c"]) == HIGH_CARD


def test_royal_is_top_ace():
    royal = eval7([parse_card(c) for c in ["As", "Ks", "Qs", "Js", "Ts"]])
    assert category_of(royal) == STRAIGHT_FLUSH and top_rank_of(royal) == 14
    low_sf = eval7([parse_card(c) for c in ["9s", "8s", "7s", "6s", "5s"]])
    assert royal > low_sf


def test_ordering_between_categories():
    quads = eval7([parse_card(c) for c in ["Ah", "Ad", "Ac", "As", "Kd"]])
    fh = eval7([parse_card(c) for c in ["Ah", "Ad", "Ac", "Ks", "Kd"]])
    flush = eval7([parse_card(c) for c in ["Ah", "Th", "7h", "4h", "2h"]])
    assert quads > fh > flush


def test_seven_card_matches_best_of_five():
    """Direct 7-card score must equal the best of all 5-card subsets."""
    rng = random.Random(12345)
    deck = list(range(52))
    for _ in range(5000):
        rng.shuffle(deck)
        seven = deck[:7]
        best = max(eval7(c) for c in itertools.combinations(seven, 5))
        assert eval7(seven) == best


def test_kicker_resolution():
    a = eval7([parse_card(c) for c in ["Ah", "Ad", "Ks", "Qd", "Jc", "9c", "8h"]])
    b = eval7([parse_card(c) for c in ["Ah", "Ad", "Ks", "Qd", "Tc", "9c", "8h"]])
    assert a > b  # same pair of aces, J kicker beats T kicker
