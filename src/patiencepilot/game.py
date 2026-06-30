"""Session wrapper and convenience functions for Solitaire games."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from . import engine
from .engine import apply_move, is_won, legal_moves, new_game, validate_state
from .exceptions import InvalidMoveError
from .moves import Move, MoveResult
from .state import GameState
from .variants.base import Seed, Variant
from .variants.registry import VariantOptions


@dataclass(frozen=True, slots=True)
class SessionStep:
    """One move applied within a game session."""

    move: Move
    before: GameState
    result: MoveResult

    @property
    def after(self) -> GameState:
        """Return the state after the move was applied."""
        return self.result.state


@dataclass(slots=True)
class GameSession:
    """Thin mutable wrapper around pure engine state transitions."""

    state: GameState
    variant: Variant | str | None = None
    seed: Seed = None
    metadata: dict[str, object] = field(default_factory=dict)
    ui_state: dict[str, object] = field(default_factory=dict)
    _history: list[SessionStep] = field(default_factory=list, init=False, repr=False)
    _redo_stack: list[SessionStep] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        """Validate the starting state."""
        engine.validate_state(self.state, self.variant)

    @classmethod
    def new(
        cls,
        variant: Variant | str | None = None,
        *,
        seed: Seed = None,
        options: VariantOptions | None = None,
        metadata: Mapping[str, object] | None = None,
        ui_state: Mapping[str, object] | None = None,
    ) -> GameSession:
        """Return a session around a newly dealt game.

        Args:
            variant: Rule set or registered variant name to use. Defaults to
                Klondike draw-one with unlimited redeals.
            seed: Optional deterministic random seed.
            options: Variant options when ``variant`` is a name or omitted.
            metadata: Optional session metadata for callers or persistence.
            ui_state: Optional UI-only state for adapters.
        """
        state = engine.new_game(variant, seed=seed, options=options)
        return cls(
            state=state,
            variant=variant,
            seed=seed,
            metadata={} if metadata is None else dict(metadata),
            ui_state={} if ui_state is None else dict(ui_state),
        )

    @property
    def history(self) -> tuple[SessionStep, ...]:
        """Return applied session steps in order."""
        return tuple(self._history)

    @property
    def redo_history(self) -> tuple[SessionStep, ...]:
        """Return undone session steps available for redo, oldest first."""
        return tuple(reversed(self._redo_stack))

    @property
    def move_history(self) -> tuple[Move, ...]:
        """Return moves applied in this session."""
        return tuple(step.move for step in self._history)

    @property
    def result_history(self) -> tuple[MoveResult, ...]:
        """Return move results applied in this session."""
        return tuple(step.result for step in self._history)

    @property
    def last_result(self) -> MoveResult | None:
        """Return the most recent move result, if any."""
        if not self._history:
            return None
        return self._history[-1].result

    @property
    def can_undo(self) -> bool:
        """Return whether the session has a move to undo."""
        return bool(self._history)

    @property
    def can_redo(self) -> bool:
        """Return whether the session has a move to redo."""
        return bool(self._redo_stack)

    def legal_moves(self) -> tuple[Move, ...]:
        """Return legal moves from the current state."""
        return engine.legal_moves(self.state, self.variant)

    def validate_state(self) -> None:
        """Validate the current state."""
        engine.validate_state(self.state, self.variant)

    def is_won(self) -> bool:
        """Return whether the current state is won."""
        return engine.is_won(self.state, self.variant)

    def apply_move(self, move: Move) -> MoveResult:
        """Apply ``move`` to the current state and record history.

        Args:
            move: Move to apply.
        """
        before = self.state
        result = engine.apply_move(before, move, self.variant)
        self.state = result.state
        self._history.append(SessionStep(move=move, before=before, result=result))
        self._redo_stack.clear()
        return result

    def undo(self) -> SessionStep:
        """Undo the most recent move.

        Raises:
            InvalidMoveError: If there is no move to undo.
        """
        if not self._history:
            msg = "no moves to undo"
            raise InvalidMoveError(msg)

        step = self._history.pop()
        self.state = step.before
        self._redo_stack.append(step)
        return step

    def redo(self) -> MoveResult:
        """Redo the most recently undone move.

        Raises:
            InvalidMoveError: If there is no move to redo.
        """
        if not self._redo_stack:
            msg = "no moves to redo"
            raise InvalidMoveError(msg)

        undone_step = self._redo_stack.pop()
        before = self.state
        result = engine.apply_move(before, undone_step.move, self.variant)
        self.state = result.state
        self._history.append(SessionStep(move=undone_step.move, before=before, result=result))
        return result

    def clear_history(self) -> None:
        """Clear undo and redo history without changing the current state."""
        self._history.clear()
        self._redo_stack.clear()


def new_klondike_game(
    *,
    seed: Seed = None,
    draw_count: int = 1,
    redeals: int | None = None,
) -> GameState:
    """Return a new Klondike game state.

    Args:
        seed: Optional deterministic random seed.
        draw_count: Number of cards drawn from stock at once.
        redeals: Number of waste-to-stock redeals allowed, or ``None`` for
            unlimited redeals.
    """
    return new_game("klondike", seed=seed, options={"draw_count": draw_count, "redeals": redeals})


__all__ = [
    "GameSession",
    "SessionStep",
    "apply_move",
    "is_won",
    "legal_moves",
    "new_game",
    "new_klondike_game",
    "validate_state",
]
