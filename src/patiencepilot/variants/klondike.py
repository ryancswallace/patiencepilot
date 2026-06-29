"""Klondike Solitaire rules."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, replace
from itertools import pairwise
from typing import ClassVar

from patiencepilot.cards import Card, Rank, Suit, standard_deck
from patiencepilot.exceptions import InvalidMoveError, InvalidStateError, UnsupportedVariantError
from patiencepilot.moves import (
    DrawFromStock,
    DrewStockCards,
    Move,
    MovedCards,
    MoveEffect,
    MoveResult,
    RecycledWaste,
    RecycleWaste,
    RevealedTableauCard,
    TableauToFoundation,
    TableauToTableau,
    WasteToFoundation,
    WasteToTableau,
)
from patiencepilot.state import N_TABLEAU_COLUMNS, SUIT_ORDER, GameState, StackCard
from patiencepilot.variants.base import Seed


@dataclass(frozen=True, slots=True)
class KlondikeRules:
    """Rules and options for Klondike Solitaire."""

    draw_count: int = 1
    redeals: int | None = None

    name: ClassVar[str] = "klondike"

    def __post_init__(self) -> None:
        """Validate immutable rule options."""
        if self.draw_count < 1:
            msg = "draw_count must be at least 1"
            raise InvalidStateError(msg)
        if self.redeals is not None and self.redeals < 0:
            msg = "redeals must be non-negative or None"
            raise InvalidStateError(msg)

    def new_game(self, seed: Seed = None) -> GameState:
        """Return a new shuffled Klondike game state.

        Args:
            seed: Optional deterministic random seed.
        """
        deck = list(standard_deck())
        # Solitaire deals need deterministic game randomness for reproducible seeds.
        random.Random(seed).shuffle(deck)  # nosec B311
        return self.deal(deck)

    def deal(self, deck: Sequence[Card]) -> GameState:
        """Deal ``deck`` into a Klondike starting state.

        Args:
            deck: A complete 52-card deck. The end of the sequence is treated
                as the top of the deck.

        Raises:
            InvalidStateError: If ``deck`` is not a unique 52-card deck.
        """
        if len(deck) != len(standard_deck()) or len(set(deck)) != len(standard_deck()):
            msg = "Klondike deals require a unique 52-card deck"
            raise InvalidStateError(msg)

        cards = list(deck)
        tableau: list[tuple[StackCard, ...]] = []
        for column_index in range(N_TABLEAU_COLUMNS):
            column: list[StackCard] = []
            for row_index in range(column_index + 1):
                column.append(StackCard(card=cards.pop(), face_up=row_index == column_index))
            tableau.append(tuple(column))

        return GameState(
            foundations=tuple(() for _ in SUIT_ORDER),
            tableau=tuple(tableau),
            stock=tuple(cards),
            waste=(),
            variant=self.name,
            draw_count=self.draw_count,
            redeals_allowed=self.redeals,
        )

    def validate_state(self, state: GameState) -> None:
        """Validate that ``state`` is coherent for Klondike.

        Raises:
            InvalidStateError: If the state is malformed.
            UnsupportedVariantError: If the state belongs to another variant.
        """
        if state.variant != self.name:
            msg = f"expected variant {self.name!r}, got {state.variant!r}"
            raise UnsupportedVariantError(msg)
        if state.draw_count != self.draw_count:
            msg = f"state draw_count {state.draw_count} does not match rules draw_count {self.draw_count}"
            raise InvalidStateError(msg)
        if state.redeals_allowed != self.redeals:
            msg = f"state redeals_allowed {state.redeals_allowed!r} does not match rules redeals {self.redeals!r}"
            raise InvalidStateError(msg)
        if state.redeals_used < 0:
            msg = "redeals_used must be non-negative"
            raise InvalidStateError(msg)
        if self.redeals is not None and state.redeals_used > self.redeals:
            msg = "redeals_used cannot exceed redeals_allowed"
            raise InvalidStateError(msg)
        if len(state.foundations) != len(SUIT_ORDER):
            msg = "foundations must contain one stack per suit"
            raise InvalidStateError(msg)
        if len(state.tableau) != N_TABLEAU_COLUMNS:
            msg = f"Klondike tableau must contain {N_TABLEAU_COLUMNS} columns"
            raise InvalidStateError(msg)

        known_cards = tuple(state.iter_known_cards())
        if len(set(known_cards)) != len(known_cards):
            msg = "state contains duplicate known cards"
            raise InvalidStateError(msg)

        for suit in Suit:
            self._validate_foundation(suit, state.foundation(suit))

        for column_index, column in enumerate(state.tableau):
            for stack_card in column:
                if stack_card.face_up and stack_card.visible_card is None:
                    msg = f"tableau column {column_index} contains a face-up unknown card"
                    raise InvalidStateError(msg)

    def legal_moves(self, state: GameState) -> tuple[Move, ...]:
        """Return legal Klondike moves available from ``state``."""
        self.validate_state(state)
        moves: list[Move] = []

        if state.stock:
            moves.append(DrawFromStock())
        elif state.waste and self._can_recycle(state):
            moves.append(RecycleWaste())

        if state.waste:
            waste_card = state.waste[-1]
            if self._can_move_to_foundation(waste_card, state.foundation(waste_card.suit)):
                moves.append(WasteToFoundation())
            for destination in range(N_TABLEAU_COLUMNS):
                if self._can_place_on_tableau(waste_card, state.tableau[destination]):
                    moves.append(WasteToTableau(destination=destination))

        for source, column in enumerate(state.tableau):
            top_card = self._top_visible_card(column)
            if top_card is not None and self._can_move_to_foundation(top_card, state.foundation(top_card.suit)):
                moves.append(TableauToFoundation(source=source))

            for start_index in range(len(column)):
                moving_stack = column[start_index:]
                if not self._is_movable_tableau_stack(moving_stack):
                    continue
                moving_card = moving_stack[0].visible_card
                if moving_card is None:
                    continue
                count = len(moving_stack)
                for destination in range(N_TABLEAU_COLUMNS):
                    if source == destination:
                        continue
                    if self._can_place_on_tableau(moving_card, state.tableau[destination]):
                        moves.append(TableauToTableau(source=source, destination=destination, count=count))

        return tuple(moves)

    def apply_move(self, state: GameState, move: Move) -> MoveResult:
        """Apply a legal Klondike move and return the result.

        Raises:
            InvalidMoveError: If ``move`` is not legal from ``state``.
            InvalidStateError: If ``state`` is malformed.
        """
        self.validate_state(state)

        if isinstance(move, DrawFromStock):
            result = self._draw_from_stock(state, move)
        elif isinstance(move, RecycleWaste):
            result = self._recycle_waste(state, move)
        elif isinstance(move, WasteToFoundation):
            result = self._waste_to_foundation(state, move)
        elif isinstance(move, WasteToTableau):
            result = self._waste_to_tableau(state, move)
        elif isinstance(move, TableauToFoundation):
            result = self._tableau_to_foundation(state, move)
        elif isinstance(move, TableauToTableau):
            result = self._tableau_to_tableau(state, move)
        else:
            msg = f"unsupported Klondike move: {move!r}"
            raise InvalidMoveError(msg)

        self.validate_state(result.state)
        return result

    def is_won(self, state: GameState) -> bool:
        """Return whether all cards have been moved to the foundations."""
        self.validate_state(state)
        return all(len(state.foundation(suit)) == len(Rank) for suit in Suit)

    def _draw_from_stock(self, state: GameState, move: DrawFromStock) -> MoveResult:
        """Draw cards from stock to waste."""
        if not state.stock:
            msg = "cannot draw from an empty stock"
            raise InvalidMoveError(msg)

        stock = list(state.stock)
        waste = list(state.waste)
        drawn: list[Card] = []
        for _ in range(min(self.draw_count, len(stock))):
            card = stock.pop()
            waste.append(card)
            drawn.append(card)

        next_state = replace(state, stock=tuple(stock), waste=tuple(waste))
        return MoveResult(move=move, state=next_state, effects=(DrewStockCards(cards=tuple(drawn)),))

    def _recycle_waste(self, state: GameState, move: RecycleWaste) -> MoveResult:
        """Recycle waste into stock."""
        if state.stock:
            msg = "cannot recycle waste while stock is not empty"
            raise InvalidMoveError(msg)
        if not state.waste:
            msg = "cannot recycle an empty waste pile"
            raise InvalidMoveError(msg)
        if not self._can_recycle(state):
            msg = "redeal limit has been reached"
            raise InvalidMoveError(msg)

        next_state = replace(
            state,
            stock=tuple(reversed(state.waste)),
            waste=(),
            redeals_used=state.redeals_used + 1,
        )
        return MoveResult(move=move, state=next_state, effects=(RecycledWaste(count=len(state.waste)),))

    def _waste_to_foundation(self, state: GameState, move: WasteToFoundation) -> MoveResult:
        """Move waste top card to its foundation."""
        if not state.waste:
            msg = "cannot move from an empty waste pile"
            raise InvalidMoveError(msg)
        card = state.waste[-1]
        foundations = self._append_to_foundation(state, card)
        next_state = replace(state, foundations=foundations, waste=state.waste[:-1])
        return MoveResult(
            move=move,
            state=next_state,
            effects=(MovedCards(cards=(card,), source="waste", destination=f"foundation[{card.suit.code}]"),),
        )

    def _waste_to_tableau(self, state: GameState, move: WasteToTableau) -> MoveResult:
        """Move waste top card to a tableau column."""
        self._validate_column_index(move.destination)
        if not state.waste:
            msg = "cannot move from an empty waste pile"
            raise InvalidMoveError(msg)
        card = state.waste[-1]
        destination_column = state.tableau[move.destination]
        if not self._can_place_on_tableau(card, destination_column):
            msg = f"cannot move {card} to tableau column {move.destination}"
            raise InvalidMoveError(msg)

        tableau = self._replace_tableau_column(
            state.tableau,
            move.destination,
            (*destination_column, StackCard.visible(card)),
        )
        next_state = replace(state, tableau=tableau, waste=state.waste[:-1])
        return MoveResult(
            move=move,
            state=next_state,
            effects=(MovedCards(cards=(card,), source="waste", destination=f"tableau[{move.destination}]"),),
        )

    def _tableau_to_foundation(self, state: GameState, move: TableauToFoundation) -> MoveResult:
        """Move tableau top card to its foundation."""
        self._validate_column_index(move.source)
        source_column = state.tableau[move.source]
        card = self._top_visible_card(source_column)
        if card is None:
            msg = f"tableau column {move.source} has no visible top card"
            raise InvalidMoveError(msg)

        foundations = self._append_to_foundation(state, card)
        tableau = self._replace_tableau_column(state.tableau, move.source, source_column[:-1])
        tableau, reveal_effects = self._reveal_top_card(tableau, move.source)
        next_state = replace(state, foundations=foundations, tableau=tableau)
        return MoveResult(
            move=move,
            state=next_state,
            effects=(
                MovedCards(
                    cards=(card,),
                    source=f"tableau[{move.source}]",
                    destination=f"foundation[{card.suit.code}]",
                ),
                *reveal_effects,
            ),
        )

    def _tableau_to_tableau(self, state: GameState, move: TableauToTableau) -> MoveResult:
        """Move visible tableau cards between columns."""
        self._validate_column_index(move.source)
        self._validate_column_index(move.destination)
        if move.source == move.destination:
            msg = "source and destination tableau columns must differ"
            raise InvalidMoveError(msg)
        if move.count < 1:
            msg = "tableau move count must be at least 1"
            raise InvalidMoveError(msg)

        source_column = state.tableau[move.source]
        if move.count > len(source_column):
            msg = f"tableau column {move.source} does not contain {move.count} cards"
            raise InvalidMoveError(msg)

        moving_stack = source_column[-move.count :]
        if not self._is_movable_tableau_stack(moving_stack):
            msg = "tableau move must contain a face-up descending alternating-color stack"
            raise InvalidMoveError(msg)

        moving_card = moving_stack[0].visible_card
        if moving_card is None:
            msg = "tableau move starts with an unknown card"
            raise InvalidMoveError(msg)

        destination_column = state.tableau[move.destination]
        if not self._can_place_on_tableau(moving_card, destination_column):
            msg = f"cannot move {moving_card} to tableau column {move.destination}"
            raise InvalidMoveError(msg)

        tableau = self._replace_tableau_column(state.tableau, move.source, source_column[: -move.count])
        tableau = self._replace_tableau_column(tableau, move.destination, (*destination_column, *moving_stack))
        tableau, reveal_effects = self._reveal_top_card(tableau, move.source)
        moved_cards = tuple(stack_card.visible_card for stack_card in moving_stack)
        if any(card is None for card in moved_cards):
            msg = "tableau move contains an unknown card"
            raise InvalidMoveError(msg)
        cards = tuple(card for card in moved_cards if card is not None)
        next_state = replace(state, tableau=tableau)
        return MoveResult(
            move=move,
            state=next_state,
            effects=(
                MovedCards(
                    cards=cards,
                    source=f"tableau[{move.source}]",
                    destination=f"tableau[{move.destination}]",
                ),
                *reveal_effects,
            ),
        )

    def _append_to_foundation(self, state: GameState, card: Card) -> tuple[tuple[Card, ...], ...]:
        """Return foundations with ``card`` appended to its foundation."""
        foundation = state.foundation(card.suit)
        if not self._can_move_to_foundation(card, foundation):
            msg = f"cannot move {card} to foundation"
            raise InvalidMoveError(msg)

        foundations = list(state.foundations)
        foundations[SUIT_ORDER.index(card.suit)] = (*foundation, card)
        return tuple(foundations)

    def _reveal_top_card(
        self,
        tableau: tuple[tuple[StackCard, ...], ...],
        column_index: int,
    ) -> tuple[tuple[tuple[StackCard, ...], ...], tuple[MoveEffect, ...]]:
        """Reveal the top card in a tableau column when possible."""
        column = tableau[column_index]
        if not column or column[-1].face_up:
            return tableau, ()

        top_card = column[-1].known_card
        if top_card is None:
            return tableau, ()

        revealed_column = (*column[:-1], StackCard.visible(top_card))
        return (
            self._replace_tableau_column(tableau, column_index, revealed_column),
            (RevealedTableauCard(column=column_index, card=top_card),),
        )

    @staticmethod
    def _replace_tableau_column(
        tableau: tuple[tuple[StackCard, ...], ...],
        column_index: int,
        column: tuple[StackCard, ...],
    ) -> tuple[tuple[StackCard, ...], ...]:
        """Return tableau with one column replaced."""
        next_tableau = list(tableau)
        next_tableau[column_index] = column
        return tuple(next_tableau)

    @staticmethod
    def _validate_column_index(column_index: int) -> None:
        """Validate a tableau column index."""
        if column_index < 0 or column_index >= N_TABLEAU_COLUMNS:
            msg = f"tableau column index out of range: {column_index}"
            raise InvalidMoveError(msg)

    @staticmethod
    def _validate_foundation(suit: Suit, foundation: tuple[Card, ...]) -> None:
        """Validate one foundation stack."""
        for expected_rank, card in enumerate(foundation, start=Rank.ACE.value):
            if card.suit != suit or card.rank.value != expected_rank:
                msg = f"foundation {suit.code} is not ordered from ace upward"
                raise InvalidStateError(msg)

    @staticmethod
    def _top_visible_card(column: tuple[StackCard, ...]) -> Card | None:
        """Return the visible top card for a tableau column."""
        if not column:
            return None
        return column[-1].visible_card

    @staticmethod
    def _can_move_to_foundation(card: Card, foundation: tuple[Card, ...]) -> bool:
        """Return whether ``card`` can move to ``foundation``."""
        if not foundation:
            return card.rank == Rank.ACE
        top_card = foundation[-1]
        return card.suit == top_card.suit and card.rank.value == top_card.rank.value + 1

    @staticmethod
    def _can_place_on_tableau(card: Card, destination: tuple[StackCard, ...]) -> bool:
        """Return whether ``card`` can be placed on a tableau destination."""
        if not destination:
            return card.rank == Rank.KING
        top_card = destination[-1].visible_card
        if top_card is None:
            return False
        return card.color != top_card.color and card.rank.value == top_card.rank.value - 1

    @staticmethod
    def _is_movable_tableau_stack(stack: tuple[StackCard, ...]) -> bool:
        """Return whether ``stack`` is a movable face-up Klondike sequence."""
        if not stack:
            return False

        visible_cards = tuple(stack_card.visible_card for stack_card in stack)
        if any(card is None for card in visible_cards):
            return False

        cards = tuple(card for card in visible_cards if card is not None)
        return all(
            lower.color != upper.color and upper.rank.value == lower.rank.value - 1 for lower, upper in pairwise(cards)
        )

    def _can_recycle(self, state: GameState) -> bool:
        """Return whether waste can be recycled into stock."""
        return self.redeals is None or state.redeals_used < self.redeals
