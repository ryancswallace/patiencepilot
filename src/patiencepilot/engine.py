"""Pure engine functions for Solitaire game state transitions."""

from __future__ import annotations

from .exceptions import InvalidStateError
from .moves import Move, MoveResult
from .state import GameState
from .variants.base import Seed, Variant
from .variants.registry import VariantOptions, resolve_state_variant, resolve_variant, variant_options_from_state


def new_game(
    variant: Variant | str | None = None,
    seed: Seed = None,
    options: VariantOptions | None = None,
) -> GameState:
    """Return a new game state.

    Args:
        variant: Rule set or registered variant name to use. Defaults to
            Klondike draw-one with unlimited redeals.
        seed: Optional deterministic random seed.
        options: Variant options when ``variant`` is a name or omitted.
    """
    rules = _coerce_variant(variant, options)
    return rules.new_game(seed=seed)


def validate_state(state: GameState, variant: Variant | str | None = None) -> None:
    """Validate that ``state`` is coherent for its variant.

    Args:
        state: State to validate.
        variant: Optional explicit rule set or registered variant name. When
            omitted, rules are resolved from state metadata.
    """
    _resolve_variant(state, variant).validate_state(state)


def legal_moves(state: GameState, variant: Variant | str | None = None) -> tuple[Move, ...]:
    """Return legal moves available from ``state``."""
    return _resolve_variant(state, variant).legal_moves(state)


def apply_move(state: GameState, move: Move, variant: Variant | str | None = None) -> MoveResult:
    """Apply ``move`` to ``state`` and return the resulting state and effects."""
    return _resolve_variant(state, variant).apply_move(state, move)


def is_won(state: GameState, variant: Variant | str | None = None) -> bool:
    """Return whether ``state`` is won."""
    return _resolve_variant(state, variant).is_won(state)


def _coerce_variant(variant: Variant | str | None, options: VariantOptions | None) -> Variant:
    """Return a variant rules object from a name, object, or default."""
    if isinstance(variant, str):
        return resolve_variant(variant, options)
    if variant is None:
        return resolve_variant(options=options)
    if options is not None:
        msg = "variant options can only be used with registered variant names"
        raise InvalidStateError(msg)
    return variant


def _resolve_variant(state: GameState, variant: Variant | str | None) -> Variant:
    """Resolve a rule set for a state."""
    if isinstance(variant, str):
        return resolve_variant(variant, variant_options_from_state(state))
    if variant is not None:
        return variant
    return resolve_state_variant(state)
