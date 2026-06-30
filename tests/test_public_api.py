"""Tests for public package exports and exception hierarchy."""

from __future__ import annotations

import pytest

import patiencepilot

pytestmark = pytest.mark.unit


def test_public_api_exports_expected_names() -> None:
    expected_exports = {
        "Advice",
        "AdviceProvider",
        "Card",
        "Color",
        "DEFAULT_VARIANT_REGISTRY",
        "DrawFromStock",
        "DrewStockCards",
        "DummySolver",
        "GameState",
        "GameSession",
        "InvalidMoveError",
        "InvalidStateError",
        "KlondikeRules",
        "MoveResult",
        "MovedCards",
        "NotationError",
        "PatiencePilotError",
        "PatiencePilotApp",
        "PlayerStackCard",
        "PlayerView",
        "Rank",
        "RecycleWaste",
        "RecycledWaste",
        "RevealedTableauCard",
        "RankedMove",
        "SCHEMA_VERSION",
        "SerializedGameState",
        "SerializedMove",
        "SerializedPlayerStackCard",
        "SerializedPlayerView",
        "SerializedSession",
        "SerializedStackCard",
        "SerializedUnknownCardConstraints",
        "SessionStep",
        "SearchLimit",
        "Solver",
        "SolverLimitError",
        "StackCard",
        "Suit",
        "TableauToFoundation",
        "TableauToTableau",
        "UnknownCardConstraints",
        "UnsupportedVariantError",
        "ValidationDiagnostic",
        "Variant",
        "VariantDefinition",
        "VariantOptions",
        "VariantRegistry",
        "ValidationReport",
        "ValidationResult",
        "WasteToFoundation",
        "WasteToTableau",
        "__version__",
        "apply_move",
        "deserialize_move",
        "deserialize_player_view",
        "deserialize_state",
        "export_session",
        "import_session",
        "is_won",
        "legal_moves",
        "migrate_session_payload",
        "migrate_state_payload",
        "move_from_id",
        "move_to_id",
        "new_game",
        "resolve_state_variant",
        "resolve_variant",
        "serialize_move",
        "serialize_player_view",
        "serialize_state",
        "standard_deck",
        "state_from_text",
        "state_to_text",
        "validate_move_id",
        "validate_serialized_move",
        "validate_serialized_state",
        "validate_session_payload",
        "validate_state",
        "validate_state_payload",
        "validate_state_text",
        "variant_names",
        "variant_options_from_state",
        "visible_klondike_moves",
    }

    assert set(patiencepilot.__all__) == expected_exports

    for name in patiencepilot.__all__:
        assert hasattr(patiencepilot, name)


def test_package_version_is_resolved() -> None:
    assert patiencepilot.__version__
    assert "unknown" not in patiencepilot.__version__
