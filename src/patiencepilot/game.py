"""Convenience functions for Klondike games."""

from __future__ import annotations

from .engine import apply_move, is_won, legal_moves, new_game, validate_state
from .state import GameState
from .variants.base import Seed
from .variants.klondike import KlondikeRules


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
    return new_game(KlondikeRules(draw_count=draw_count, redeals=redeals), seed=seed)


__all__ = [
    "apply_move",
    "is_won",
    "legal_moves",
    "new_game",
    "new_klondike_game",
    "validate_state",
]
