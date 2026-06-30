"""Structured move and move-result types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .cards import Card
from .state import GameState


@dataclass(frozen=True, slots=True)
class TableauToTableau:
    """Move one or more visible cards between tableau columns."""

    source: int
    destination: int
    count: int = 1


@dataclass(frozen=True, slots=True)
class TableauToFoundation:
    """Move the top visible card from a tableau column to its foundation."""

    source: int


@dataclass(frozen=True, slots=True)
class WasteToTableau:
    """Move the top waste card to a tableau column."""

    destination: int


@dataclass(frozen=True, slots=True)
class WasteToFoundation:
    """Move the top waste card to its foundation."""


@dataclass(frozen=True, slots=True)
class DrawFromStock:
    """Draw one or more cards from stock to waste."""


@dataclass(frozen=True, slots=True)
class RecycleWaste:
    """Recycle the waste pile into stock when the rules allow it."""


Move: TypeAlias = (
    TableauToTableau | TableauToFoundation | WasteToTableau | WasteToFoundation | DrawFromStock | RecycleWaste
)


@dataclass(frozen=True, slots=True)
class MovedCards:
    """Effect describing cards moved between locations."""

    cards: tuple[Card, ...]
    source: str
    destination: str


@dataclass(frozen=True, slots=True)
class RevealedTableauCard:
    """Effect describing a tableau card automatically revealed by the engine."""

    column: int
    card: Card


@dataclass(frozen=True, slots=True)
class DrewStockCards:
    """Effect describing cards drawn from stock to waste."""

    cards: tuple[Card, ...]


@dataclass(frozen=True, slots=True)
class RecycledWaste:
    """Effect describing waste cards recycled into stock."""

    count: int


MoveEffect: TypeAlias = MovedCards | RevealedTableauCard | DrewStockCards | RecycledWaste


@dataclass(frozen=True, slots=True)
class MoveResult:
    """The result of applying a legal move."""

    move: Move
    state: GameState
    effects: tuple[MoveEffect, ...] = ()
