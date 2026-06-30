"""Player-known views of authoritative game state."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from .cards import Card, Suit, standard_deck
from .exceptions import InvalidStateError
from .state import N_TABLEAU_COLUMNS, SUIT_ORDER, GameState


@dataclass(frozen=True, slots=True)
class PlayerStackCard:
    """A tableau card as known to a player."""

    card: Card | None
    face_up: bool

    def __post_init__(self) -> None:
        """Validate player-view visibility invariants."""
        if self.face_up and self.card is None:
            msg = "face-up player-view cards must expose a card"
            raise InvalidStateError(msg)
        if not self.face_up and self.card is not None:
            msg = "face-down player-view cards must not expose a card"
            raise InvalidStateError(msg)

    @classmethod
    def visible(cls, card: Card) -> PlayerStackCard:
        """Return a face-up player-visible tableau card."""
        return cls(card=card, face_up=True)

    @classmethod
    def hidden(cls) -> PlayerStackCard:
        """Return a face-down player-hidden tableau card."""
        return cls(card=None, face_up=False)

    @property
    def visible_card(self) -> Card | None:
        """Return the card if it is visible to the player."""
        return self.card if self.face_up else None


@dataclass(frozen=True, slots=True)
class UnknownCardConstraints:
    """Constraints for cards not currently identified in the player view."""

    hidden_tableau_counts: tuple[int, ...]
    stock_count: int
    unseen_cards: tuple[Card, ...]

    def __post_init__(self) -> None:
        """Validate unknown-card constraint counts."""
        if len(self.hidden_tableau_counts) != N_TABLEAU_COLUMNS:
            msg = f"hidden_tableau_counts must contain {N_TABLEAU_COLUMNS} entries"
            raise InvalidStateError(msg)
        if any(count < 0 for count in self.hidden_tableau_counts):
            msg = "hidden tableau counts must be non-negative"
            raise InvalidStateError(msg)
        if self.stock_count < 0:
            msg = "stock_count must be non-negative"
            raise InvalidStateError(msg)

    @property
    def hidden_tableau_count(self) -> int:
        """Return the total number of face-down tableau cards."""
        return sum(self.hidden_tableau_counts)

    @property
    def hidden_position_count(self) -> int:
        """Return the number of hidden positions in stock and tableau."""
        return self.stock_count + self.hidden_tableau_count


@dataclass(frozen=True, slots=True)
class PlayerView:
    """A state projection containing only what a perfect human player may know."""

    foundations: tuple[tuple[Card, ...], ...]
    tableau: tuple[tuple[PlayerStackCard, ...], ...]
    waste: tuple[Card, ...]
    seen_cards: tuple[Card, ...]
    unknown: UnknownCardConstraints
    variant: str = "klondike"
    draw_count: int = 1
    redeals_allowed: int | None = None
    redeals_used: int = 0

    @classmethod
    def from_state(cls, state: GameState, *, seen_cards: Iterable[Card] = ()) -> PlayerView:
        """Project an authoritative game state into a player-known view.

        Args:
            state: Authoritative state to project.
            seen_cards: Cards observed earlier in the game, even if they are no
                longer visible.
        """
        tableau = tuple(
            tuple(
                PlayerStackCard.visible(stack_card.card) if stack_card.face_up else PlayerStackCard.hidden()
                for stack_card in column
            )
            for column in state.tableau
        )
        visible_cards = tuple(cls._iter_visible_cards(state))
        known_cards = _standard_deck_ordered_unique((*seen_cards, *visible_cards))
        known_set = set(known_cards)
        unknown = UnknownCardConstraints(
            hidden_tableau_counts=tuple(
                sum(1 for stack_card in column if not stack_card.face_up) for column in state.tableau
            ),
            stock_count=len(state.stock),
            unseen_cards=tuple(card for card in standard_deck() if card not in known_set),
        )
        return cls(
            foundations=state.foundations,
            tableau=tableau,
            waste=state.waste,
            seen_cards=known_cards,
            unknown=unknown,
            variant=state.variant,
            draw_count=state.draw_count,
            redeals_allowed=state.redeals_allowed,
            redeals_used=state.redeals_used,
        )

    def foundation(self, suit: Suit) -> tuple[Card, ...]:
        """Return the visible foundation stack for ``suit``."""
        return self.foundations[SUIT_ORDER.index(suit)]

    @property
    def stock_count(self) -> int:
        """Return the number of cards hidden in stock."""
        return self.unknown.stock_count

    def iter_visible_cards(self) -> Iterator[Card]:
        """Yield cards currently visible to the player."""
        yield from self._iter_visible_cards(self)

    @staticmethod
    def _iter_visible_cards(state: GameState | PlayerView) -> Iterator[Card]:
        """Yield visible cards from an authoritative state or player view."""
        for foundation in state.foundations:
            yield from foundation
        for column in state.tableau:
            for stack_card in column:
                if stack_card.visible_card is not None:
                    yield stack_card.visible_card
        yield from state.waste


def _standard_deck_ordered_unique(cards: Iterable[Card]) -> tuple[Card, ...]:
    """Return unique cards in standard deck order."""
    card_set = set(cards)
    return tuple(card for card in standard_deck() if card in card_set)
