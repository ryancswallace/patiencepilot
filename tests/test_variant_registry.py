"""Tests for variant registry resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import pytest

from patiencepilot import (
    GameState,
    InvalidStateError,
    KlondikeRules,
    UnsupportedVariantError,
    VariantDefinition,
    VariantOptions,
    VariantRegistry,
    new_game,
    resolve_state_variant,
    resolve_variant,
    validate_state,
    variant_names,
    variant_options_from_state,
)
from patiencepilot.moves import Move, MoveResult
from patiencepilot.variants.base import Seed

pytestmark = pytest.mark.unit


def test_default_registry_resolves_klondike_by_name_and_options() -> None:
    rules = resolve_variant(" KlOnDiKe ", {"draw_count": 3, "redeals": 1})

    assert rules == KlondikeRules(draw_count=3, redeals=1)
    assert variant_names() == ("klondike",)


def test_registry_extracts_options_from_state() -> None:
    state = GameState.empty(draw_count=3, redeals_allowed=2)

    assert variant_options_from_state(state) == {"draw_count": 3, "redeals": 2}
    assert resolve_state_variant(state) == KlondikeRules(draw_count=3, redeals=2)


def test_engine_resolves_named_variants_for_new_games_and_state_validation() -> None:
    state = new_game("klondike", seed=7, options={"draw_count": 3, "redeals": None})

    assert state.draw_count == 3
    assert state.redeals_allowed is None
    validate_state(state, "klondike")


@pytest.mark.parametrize(
    "options",
    [
        {"draw_count": "3"},
        {"draw_count": True},
        {"redeals": "none"},
        {"redeals": False},
        {"turn": 3},
    ],
)
def test_registry_rejects_invalid_klondike_options(options: dict[str, object]) -> None:
    with pytest.raises(InvalidStateError):
        resolve_variant("klondike", options)


def test_registry_rejects_unsupported_variant_names() -> None:
    with pytest.raises(UnsupportedVariantError, match="unsupported variant"):
        resolve_variant("spider")

    with pytest.raises(UnsupportedVariantError, match="cannot be empty"):
        resolve_variant(" ")


def test_new_game_rejects_options_with_concrete_rule_object() -> None:
    with pytest.raises(InvalidStateError, match="variant options"):
        new_game(KlondikeRules(), options={"draw_count": 3})


def test_registry_can_be_extended_without_mutating_existing_registry() -> None:
    registry = VariantRegistry(())
    extended_registry = registry.register(
        VariantDefinition(
            name=MiniRules.name,
            factory=_mini_factory,
            state_options=_mini_options_from_state,
            aliases=("mini-alias",),
        )
    )

    assert registry.names == ()
    assert extended_registry.names == ("mini",)
    assert extended_registry.resolve("mini-alias") == MiniRules()


@dataclass(frozen=True, slots=True)
class MiniRules:
    """Minimal variant for registry tests."""

    name: ClassVar[str] = "mini"

    def new_game(self, seed: Seed = None) -> GameState:
        """Return a new empty mini game."""
        _ = seed
        return GameState.empty(variant=self.name)

    def validate_state(self, state: GameState) -> None:
        """Validate a mini game state."""
        if state.variant != self.name:
            msg = f"expected variant {self.name!r}"
            raise UnsupportedVariantError(msg)

    def legal_moves(self, state: GameState) -> tuple[Move, ...]:
        """Return no legal mini moves."""
        self.validate_state(state)
        return ()

    def apply_move(self, state: GameState, move: Move) -> MoveResult:
        """Reject all mini moves."""
        _ = (state, move)
        msg = "mini has no legal moves"
        raise NotImplementedError(msg)

    def is_won(self, state: GameState) -> bool:
        """Return whether the mini state is won."""
        self.validate_state(state)
        return True


def _mini_factory(options: VariantOptions) -> MiniRules:
    """Return mini rules for registry tests."""
    assert options == {}
    return MiniRules()


def _mini_options_from_state(state: GameState) -> dict[str, object]:
    """Return mini options for registry tests."""
    assert state.variant == MiniRules.name
    return {}
