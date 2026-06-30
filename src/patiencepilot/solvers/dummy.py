"""Trivial solver implementations."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from patiencepilot.cards import Card, Rank
from patiencepilot.exceptions import UnsupportedVariantError
from patiencepilot.moves import (
    DrawFromStock,
    Move,
    RecycleWaste,
    TableauToFoundation,
    TableauToTableau,
    WasteToFoundation,
    WasteToTableau,
)
from patiencepilot.solvers.base import Advice, RankedMove, SearchLimit
from patiencepilot.state import N_TABLEAU_COLUMNS
from patiencepilot.view import PlayerStackCard, PlayerView


@dataclass(frozen=True, slots=True)
class DummySolver:
    """Deterministic solver that recommends the first visible legal move."""

    name: str = "dummy"

    def suggest(self, view: PlayerView, *, limit: SearchLimit | None = None) -> Advice:
        """Return the first legal move available in ``view``.

        The solver derives legal moves only from player-visible information:
        foundations, waste, visible tableau cards, stock count, and redeal
        metadata. It does not reconstruct or inspect hidden card identities.
        """
        moves = visible_klondike_moves(view)
        if not moves:
            return Advice(recommendations=(), solver_name=self.name, limit=limit, nodes_searched=0, depth_reached=0)
        return Advice(
            recommendations=(RankedMove(move=moves[0], rank=1),),
            solver_name=self.name,
            limit=limit,
            nodes_searched=len(moves),
            depth_reached=0,
        )


def visible_klondike_moves(view: PlayerView) -> tuple[Move, ...]:
    """Return Klondike moves legal from player-visible state."""
    if view.variant != "klondike":
        msg = f"dummy solver only supports 'klondike', got {view.variant!r}"
        raise UnsupportedVariantError(msg)

    moves: list[Move] = []
    if view.stock_count:
        moves.append(DrawFromStock())
    elif view.waste and _can_recycle(view):
        moves.append(RecycleWaste())

    if view.waste:
        waste_card = view.waste[-1]
        if _can_move_to_foundation(waste_card, view.foundation(waste_card.suit)):
            moves.append(WasteToFoundation())
        for destination in range(N_TABLEAU_COLUMNS):
            if _can_place_on_tableau(waste_card, view.tableau[destination]):
                moves.append(WasteToTableau(destination=destination))

    for source, column in enumerate(view.tableau):
        top_card = _top_visible_card(column)
        if top_card is not None and _can_move_to_foundation(top_card, view.foundation(top_card.suit)):
            moves.append(TableauToFoundation(source=source))

        for start_index in range(len(column)):
            moving_stack = column[start_index:]
            if not _is_movable_tableau_stack(moving_stack):
                continue
            moving_card = moving_stack[0].visible_card
            if moving_card is None:
                continue
            count = len(moving_stack)
            for destination in range(N_TABLEAU_COLUMNS):
                if source == destination:
                    continue
                if _can_place_on_tableau(moving_card, view.tableau[destination]):
                    moves.append(TableauToTableau(source=source, destination=destination, count=count))

    return tuple(moves)


def _top_visible_card(column: tuple[PlayerStackCard, ...]) -> Card | None:
    """Return the top card when it is visible."""
    if not column:
        return None
    return column[-1].visible_card


def _can_move_to_foundation(card: Card, foundation: tuple[Card, ...]) -> bool:
    """Return whether ``card`` can move to ``foundation``."""
    if not foundation:
        return card.rank == Rank.ACE
    top_card = foundation[-1]
    return card.suit == top_card.suit and card.rank.value == top_card.rank.value + 1


def _can_place_on_tableau(card: Card, destination: tuple[PlayerStackCard, ...]) -> bool:
    """Return whether ``card`` can be placed on a tableau destination."""
    if not destination:
        return card.rank == Rank.KING
    top_card = destination[-1].visible_card
    if top_card is None:
        return False
    return card.color != top_card.color and card.rank.value == top_card.rank.value - 1


def _is_movable_tableau_stack(stack: tuple[PlayerStackCard, ...]) -> bool:
    """Return whether ``stack`` is a movable visible Klondike sequence."""
    if not stack:
        return False

    visible_cards = tuple(stack_card.visible_card for stack_card in stack)
    if any(card is None for card in visible_cards):
        return False

    cards = tuple(card for card in visible_cards if card is not None)
    return all(
        lower.color != upper.color and upper.rank.value == lower.rank.value - 1 for lower, upper in pairwise(cards)
    )


def _can_recycle(view: PlayerView) -> bool:
    """Return whether the player-visible waste pile can be recycled."""
    return view.redeals_allowed is None or view.redeals_used < view.redeals_allowed


__all__ = ["DummySolver", "visible_klondike_moves"]
