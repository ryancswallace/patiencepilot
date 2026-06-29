"""Shared interfaces for Solitaire variants."""

from __future__ import annotations

from typing import ClassVar, Protocol, TypeAlias

from patiencepilot.moves import Move, MoveResult
from patiencepilot.state import GameState

Seed: TypeAlias = int | str | bytes | bytearray | None


class Variant(Protocol):
    """Protocol implemented by Solitaire rule sets."""

    name: ClassVar[str]

    def new_game(self, seed: Seed = None) -> GameState:
        """Return a new game state."""
        ...

    def validate_state(self, state: GameState) -> None:
        """Validate that ``state`` is coherent for this variant."""
        ...

    def legal_moves(self, state: GameState) -> tuple[Move, ...]:
        """Return legal moves available from ``state``."""
        ...

    def apply_move(self, state: GameState, move: Move) -> MoveResult:
        """Apply ``move`` and return the resulting state and effects."""
        ...

    def is_won(self, state: GameState) -> bool:
        """Return whether ``state`` is a winning state."""
        ...
