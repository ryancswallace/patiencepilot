"""Playing card primitives."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum


class Color(Enum):
    """A playing card color."""

    RED = "red"
    BLACK = "black"


class Suit(Enum):
    """A French-suited playing card suit."""

    HEARTS = "H"
    DIAMONDS = "D"
    CLUBS = "C"
    SPADES = "S"

    @property
    def color(self) -> Color:
        """Return the suit color."""
        if self in {Suit.HEARTS, Suit.DIAMONDS}:
            return Color.RED
        return Color.BLACK

    @property
    def code(self) -> str:
        """Return the compact one-letter suit code."""
        return self.value

    @classmethod
    def from_code(cls, code: str) -> Suit:
        """Return the suit represented by a compact one-letter code.

        Args:
            code: One of ``H``, ``D``, ``C``, or ``S``.

        Raises:
            ValueError: If ``code`` is not a known suit code.
        """
        normalized = code.strip().upper()
        for suit in cls:
            if suit.code == normalized:
                return suit
        msg = f"unknown suit code: {code!r}"
        raise ValueError(msg)


class Rank(IntEnum):
    """A playing card rank from ace through king."""

    ACE = 1
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13

    @property
    def code(self) -> str:
        """Return the compact rank code."""
        return {
            Rank.ACE: "A",
            Rank.TEN: "T",
            Rank.JACK: "J",
            Rank.QUEEN: "Q",
            Rank.KING: "K",
        }.get(self, str(self.value))

    @classmethod
    def from_code(cls, code: str) -> Rank:
        """Return the rank represented by a compact code.

        Args:
            code: One of ``A``, ``2`` through ``10``, ``T``, ``J``, ``Q``, or
                ``K``.

        Raises:
            ValueError: If ``code`` is not a known rank code.
        """
        normalized = code.strip().upper()
        if normalized == "10":
            normalized = "T"
        for rank in cls:
            if rank.code == normalized:
                return rank
        msg = f"unknown rank code: {code!r}"
        raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Card:
    """A standard playing card."""

    rank: Rank
    suit: Suit

    @property
    def color(self) -> Color:
        """Return the card color."""
        return self.suit.color

    @property
    def code(self) -> str:
        """Return the compact card code."""
        return f"{self.rank.code}{self.suit.code}"

    @classmethod
    def from_code(cls, code: str) -> Card:
        """Return the card represented by a compact code.

        Args:
            code: A rank code followed by a suit code, such as ``AS`` or
                ``10H``.

        Raises:
            ValueError: If ``code`` is not a valid card code.
        """
        normalized = code.strip().upper()
        if len(normalized) < 2:
            msg = f"card code is too short: {code!r}"
            raise ValueError(msg)
        return cls(rank=Rank.from_code(normalized[:-1]), suit=Suit.from_code(normalized[-1]))

    def __str__(self) -> str:
        """Return the compact card code."""
        return self.code


def standard_deck() -> tuple[Card, ...]:
    """Return a standard 52-card deck in deterministic order."""
    return tuple(Card(rank=rank, suit=suit) for suit in Suit for rank in Rank)
