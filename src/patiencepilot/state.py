"""Game state value objects."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TypeAlias

from .cards import Card, Suit

N_TABLEAU_COLUMNS = 7
SUIT_ORDER: tuple[Suit, ...] = tuple(Suit)


@dataclass(frozen=True, slots=True)
class UnknownCard:
    """A placeholder for a card whose identity is not known yet."""

    label: str = "unknown"


CardValue: TypeAlias = Card | UnknownCard


@dataclass(frozen=True, slots=True)
class StackCard:
    """A card in a tableau stack with visibility metadata."""

    card: CardValue
    face_up: bool

    @classmethod
    def visible(cls, card: Card) -> StackCard:
        """Return a face-up tableau card."""
        return cls(card=card, face_up=True)

    @classmethod
    def hidden(cls, card: CardValue) -> StackCard:
        """Return a face-down tableau card."""
        return cls(card=card, face_up=False)

    @property
    def known_card(self) -> Card | None:
        """Return the exact card identity when it is known."""
        if isinstance(self.card, Card):
            return self.card
        return None

    @property
    def visible_card(self) -> Card | None:
        """Return the card when it is both known and face up."""
        if self.face_up:
            return self.known_card
        return None


def empty_foundations() -> tuple[tuple[Card, ...], ...]:
    """Return empty foundation stacks in suit order."""
    return tuple(() for _ in SUIT_ORDER)


def empty_tableau() -> tuple[tuple[StackCard, ...], ...]:
    """Return empty tableau columns."""
    return tuple(() for _ in range(N_TABLEAU_COLUMNS))


@dataclass(frozen=True, slots=True)
class GameState:
    """A complete immutable Solitaire game snapshot."""

    foundations: tuple[tuple[Card, ...], ...]
    tableau: tuple[tuple[StackCard, ...], ...]
    stock: tuple[Card, ...]
    waste: tuple[Card, ...]
    variant: str = "klondike"
    draw_count: int = 1
    redeals_allowed: int | None = None
    redeals_used: int = 0

    @classmethod
    def empty(cls, *, variant: str = "klondike", draw_count: int = 1, redeals_allowed: int | None = None) -> GameState:
        """Return an empty state for constructing focused tests or fixtures."""
        return cls(
            foundations=empty_foundations(),
            tableau=empty_tableau(),
            stock=(),
            waste=(),
            variant=variant,
            draw_count=draw_count,
            redeals_allowed=redeals_allowed,
        )

    def foundation(self, suit: Suit) -> tuple[Card, ...]:
        """Return the foundation stack for ``suit``."""
        return self.foundations[SUIT_ORDER.index(suit)]

    @property
    def top_waste(self) -> Card | None:
        """Return the top waste card, if any."""
        if not self.waste:
            return None
        return self.waste[-1]

    def iter_known_cards(self) -> Iterator[Card]:
        """Yield every exact card identity present in the state."""
        for foundation in self.foundations:
            yield from foundation
        for column in self.tableau:
            for stack_card in column:
                if stack_card.known_card is not None:
                    yield stack_card.known_card
        yield from self.stock
        yield from self.waste
