"""Pure engine functions for Solitaire game state transitions."""

from __future__ import annotations

from .exceptions import UnsupportedVariantError
from .moves import Move, MoveResult
from .state import GameState
from .variants.base import Seed, Variant
from .variants.klondike import KlondikeRules


def new_game(variant: Variant | None = None, seed: Seed = None) -> GameState:
    """Return a new game state.

    Args:
        variant: Rule set to use. Defaults to Klondike draw-one with unlimited
            redeals.
        seed: Optional deterministic random seed.
    """
    rules = variant if variant is not None else KlondikeRules()
    return rules.new_game(seed=seed)


def validate_state(state: GameState, variant: Variant | None = None) -> None:
    """Validate that ``state`` is coherent for its variant.

    Args:
        state: State to validate.
        variant: Optional explicit rule set. When omitted, rules are resolved
            from state metadata.
    """
    _resolve_variant(state, variant).validate_state(state)


def legal_moves(state: GameState, variant: Variant | None = None) -> tuple[Move, ...]:
    """Return legal moves available from ``state``."""
    return _resolve_variant(state, variant).legal_moves(state)


def apply_move(state: GameState, move: Move, variant: Variant | None = None) -> MoveResult:
    """Apply ``move`` to ``state`` and return the resulting state and effects."""
    return _resolve_variant(state, variant).apply_move(state, move)


def is_won(state: GameState, variant: Variant | None = None) -> bool:
    """Return whether ``state`` is won."""
    return _resolve_variant(state, variant).is_won(state)


def _resolve_variant(state: GameState, variant: Variant | None) -> Variant:
    """Resolve a rule set for a state."""
    if variant is not None:
        return variant
    if state.variant == KlondikeRules.name:
        return KlondikeRules(draw_count=state.draw_count, redeals=state.redeals_allowed)
    msg = f"unsupported variant: {state.variant!r}"
    raise UnsupportedVariantError(msg)
