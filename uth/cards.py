"""Card representation.

A card is an integer in ``0..51`` encoded as ``(rank - 2) * 4 + suit`` where
``rank`` is ``2..14`` (14 = Ace) and ``suit`` is ``0..3``. This packing lets us
recover the rank with ``(card >> 2) + 2`` and the suit with ``card & 3``.
"""

RANKS = range(2, 15)  # 2..14, where 11=J, 12=Q, 13=K, 14=A
SUITS = range(4)

RANK_CHARS = {
    2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "T",
    11: "J", 12: "Q", 13: "K", 14: "A",
}
SUIT_CHARS = {0: "s", 1: "h", 2: "d", 3: "c"}

CHAR_RANKS = {v: k for k, v in RANK_CHARS.items()}
CHAR_SUITS = {v: k for k, v in SUIT_CHARS.items()}

FULL_DECK = tuple(range(52))


def rank_of(card):
    return (card >> 2) + 2


def suit_of(card):
    return card & 3


def make_card(rank, suit):
    return (rank - 2) * 4 + suit


def card_str(card):
    return RANK_CHARS[rank_of(card)] + SUIT_CHARS[suit_of(card)]


def parse_card(text):
    """Parse a string like ``'As'`` or ``'Th'`` into a card int."""
    text = text.strip()
    return make_card(CHAR_RANKS[text[0].upper()], CHAR_SUITS[text[1].lower()])


def hand_str(cards):
    return " ".join(card_str(c) for c in cards)


def parse_cards(text):
    """Parse a string of cards (e.g. ``'As Kd'``, ``'AsKd'``, ``'As,Kd'``).

    Returns a list of card ints and raises ``ValueError`` on a bad or duplicate
    card.
    """
    tokens = []
    cleaned = "".join(ch for ch in text if ch.isalnum())
    if len(cleaned) % 2 != 0:
        raise ValueError(f"cannot parse cards from {text!r}")
    for i in range(0, len(cleaned), 2):
        tokens.append(parse_card(cleaned[i:i + 2]))
    if len(set(tokens)) != len(tokens):
        raise ValueError(f"duplicate card in {text!r}")
    return tokens
