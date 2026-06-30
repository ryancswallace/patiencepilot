"""Tests for canonical notation and serialization."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest

from patiencepilot import (
    SCHEMA_VERSION,
    DrawFromStock,
    GameSession,
    InvalidStateError,
    NotationError,
    PlayerView,
    RecycleWaste,
    TableauToFoundation,
    TableauToTableau,
    ValidationResult,
    WasteToFoundation,
    WasteToTableau,
    deserialize_move,
    deserialize_player_view,
    deserialize_state,
    migrate_state_payload,
    move_from_id,
    move_to_id,
    serialize_move,
    serialize_player_view,
    serialize_state,
    state_from_text,
    state_to_text,
    validate_move_id,
    validate_serialized_move,
    validate_serialized_state,
    validate_state_text,
)
from patiencepilot.moves import Move

pytestmark = pytest.mark.unit


def _state_text_with(
    variant: str,
    *,
    foundations: str = "FOUNDATIONS H=- D=- C=- S=-",
    stock: str = "STOCK: -",
    waste: str = "WASTE: -",
    tableau: tuple[str, ...] = ("T0: -", "T1: -", "T2: -", "T3: -", "T4: -", "T5: -", "T6: -"),
) -> str:
    """Return state text with one part replaced."""
    return "\n".join((variant, foundations, stock, waste, *tableau))


def _minimal_state_payload() -> dict[str, object]:
    """Return a minimal valid serialized state payload."""
    return {
        "schema_version": SCHEMA_VERSION,
        "variant": "klondike",
        "options": {"draw_count": 1, "redeals": None},
        "foundations": [[], [], [], []],
        "tableau": [[], [], [], [], [], [], []],
        "stock": [],
        "waste": [],
        "redeals_used": 0,
    }


def _minimal_player_view_payload() -> dict[str, object]:
    """Return a minimal valid serialized player-view payload."""
    return {
        "schema_version": SCHEMA_VERSION,
        "variant": "klondike",
        "options": {"draw_count": 1, "redeals": None},
        "foundations": [[], [], [], []],
        "tableau": [[], [], [], [], [], [], []],
        "waste": [],
        "seen_cards": [],
        "unknown": {"hidden_tableau_counts": [0, 0, 0, 0, 0, 0, 0], "stock_count": 0, "unseen_cards": []},
        "redeals_used": 0,
    }


def _set_foundation_to_non_list(payload: dict[str, object]) -> None:
    """Corrupt a foundation payload."""
    foundations = cast("list[object]", payload["foundations"])
    foundations[0] = "bad"


def _set_tableau_column_to_non_list(payload: dict[str, object]) -> None:
    """Corrupt a tableau column payload."""
    tableau = cast("list[object]", payload["tableau"])
    tableau[0] = "bad"


def _set_tableau_item_to_non_mapping(payload: dict[str, object]) -> None:
    """Corrupt a tableau item payload."""
    tableau = cast("list[object]", payload["tableau"])
    tableau[0] = ["bad"]


def _set_tableau_face_up_to_non_bool(payload: dict[str, object]) -> None:
    """Corrupt tableau face-up metadata."""
    tableau = cast("list[object]", payload["tableau"])
    tableau[0] = [{"card": "AS", "face_up": "yes"}]


def _set_player_unknown_count_to_non_int(payload: dict[str, object]) -> None:
    """Corrupt player-view unknown counts."""
    unknown = cast("dict[str, object]", payload["unknown"])
    unknown["hidden_tableau_counts"] = ["bad", 0, 0, 0, 0, 0, 0]


def _set_player_tableau_column_to_non_list(payload: dict[str, object]) -> None:
    """Corrupt a player-view tableau column."""
    tableau = cast("list[object]", payload["tableau"])
    tableau[0] = "bad"


def _set_player_tableau_item_to_non_mapping(payload: dict[str, object]) -> None:
    """Corrupt a player-view tableau item."""
    tableau = cast("list[object]", payload["tableau"])
    tableau[0] = ["bad"]


def _set_player_tableau_face_up_to_non_bool(payload: dict[str, object]) -> None:
    """Corrupt player-view face-up metadata."""
    tableau = cast("list[object]", payload["tableau"])
    tableau[0] = [{"card": None, "face_up": "yes"}]


def _set_player_tableau_card_to_non_string(payload: dict[str, object]) -> None:
    """Corrupt player-view card metadata."""
    tableau = cast("list[object]", payload["tableau"])
    tableau[0] = [{"card": 3, "face_up": True}]


@pytest.mark.parametrize(
    ("move", "move_id"),
    [
        (DrawFromStock(), "DRAW"),
        (RecycleWaste(), "RECYCLE"),
        (WasteToFoundation(), "W->F"),
        (WasteToTableau(destination=3), "W->T3"),
        (TableauToFoundation(source=0), "T0->F"),
        (TableauToTableau(source=0, destination=3), "T0->T3"),
        (TableauToTableau(source=0, destination=3, count=2), "T0->T3:2"),
    ],
)
def test_move_ids_round_trip(move: Move, move_id: str) -> None:
    assert move_to_id(move) == move_id
    assert move_from_id(move_id) == move


def test_move_id_parser_accepts_lowercase_and_whitespace() -> None:
    assert move_from_id(" t0 -> t3 : 2 ") == TableauToTableau(source=0, destination=3, count=2)
    assert move_from_id("\nw -> f\t") == WasteToFoundation()


def test_move_serialization_round_trips_json_compatible_payload() -> None:
    move = TableauToTableau(source=2, destination=6, count=4)

    payload = serialize_move(move)

    assert payload == {"id": "T2->T6:4"}
    assert deserialize_move(payload) == move


def test_validation_result_without_diagnostics_has_no_message() -> None:
    result = ValidationResult()

    assert result.ok
    assert result.message is None


@pytest.mark.parametrize(
    "move",
    [
        WasteToTableau(destination=-1),
        TableauToFoundation(source=-1),
        TableauToTableau(source=0, destination=1, count=0),
        TableauToTableau(source=-1, destination=1, count=1),
        TableauToTableau(source=0, destination=-1, count=1),
    ],
)
def test_move_to_id_rejects_invalid_values(move: Move) -> None:
    with pytest.raises(NotationError):
        move_to_id(move)


def test_move_to_id_rejects_unsupported_move_objects() -> None:
    with pytest.raises(NotationError, match="unsupported move"):
        move_to_id(cast("Move", object()))


@pytest.mark.parametrize(
    "move_id",
    [
        "",
        "T->F",
        "T0->T1:0",
        "W->X",
        "REVEAL:T0",
    ],
)
def test_move_from_id_rejects_invalid_ids(move_id: str) -> None:
    with pytest.raises(NotationError):
        move_from_id(move_id)


def test_deserialize_move_requires_id_string() -> None:
    with pytest.raises(NotationError, match="'id' string"):
        deserialize_move({})

    with pytest.raises(NotationError, match="'id' string"):
        deserialize_move({"id": 3})


def test_deserialize_move_rejects_unsupported_schema_version() -> None:
    with pytest.raises(NotationError, match="unsupported move schema_version"):
        deserialize_move({"schema_version": 2, "id": "DRAW"})


def test_move_validation_reports_success_and_failure() -> None:
    assert validate_move_id("DRAW").ok

    result = validate_move_id("")

    assert not result.ok
    assert result.diagnostics[0].path == "move_id"


def test_serialized_move_validation_reports_success_and_failure() -> None:
    assert validate_serialized_move({"id": "DRAW"}).ok

    result = validate_serialized_move({"id": 3})

    assert not result.ok
    assert result.diagnostics[0].path == "move"


def test_state_text_notation_round_trips_exact_hidden_cards() -> None:
    state = GameSession.new(seed=12).state

    text = state_to_text(state)

    assert "VARIANT klondike draw_count=1 redeals=none redeals_used=0" in text
    assert "[" in text
    assert state_from_text(text) == state
    assert validate_state_text(text).ok


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "state notation must contain"),
        (_state_text_with("BROKEN klondike"), "state notation must start"),
        (_state_text_with("VARIANT klondike broken"), "invalid variant option token"),
        (_state_text_with("VARIANT klondike draw_count=x"), "draw_count must be an integer"),
        (_state_text_with("VARIANT klondike redeals=x"), "redeals must be an integer"),
        (_state_text_with("VARIANT klondike custom=value"), "unsupported klondike option"),
        (_state_text_with("VARIANT klondike", foundations="NOPE"), "FOUNDATIONS"),
        (_state_text_with("VARIANT klondike", foundations="FOUNDATIONS bad"), "invalid foundation token"),
        (_state_text_with("VARIANT klondike", foundations="FOUNDATIONS X=-"), "unknown suit code"),
        (_state_text_with("VARIANT klondike", stock="NOPE: -"), "STOCK"),
        (_state_text_with("VARIANT klondike", waste="NOPE: -"), "WASTE"),
        (_state_text_with("VARIANT klondike", tableau=("T1: -",)), "expected tableau line T0"),
        (_state_text_with("VARIANT klondike", foundations="FOUNDATIONS H=NOPE D=- C=- S=-"), "foundation\\[H\\]"),
    ],
)
def test_state_text_notation_reports_malformed_input(text: str, message: str) -> None:
    with pytest.raises((InvalidStateError, NotationError), match=message):
        state_from_text(text)


def test_state_json_serialization_is_schema_aware() -> None:
    state = GameSession.new(seed=13).state

    payload = serialize_state(state)

    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["options"] == {"draw_count": 1, "redeals": None}
    assert deserialize_state(payload) == state

    legacy_payload = dict(payload)
    legacy_payload.pop("schema_version")

    assert migrate_state_payload(legacy_payload)["schema_version"] == SCHEMA_VERSION
    assert deserialize_state(legacy_payload) == state


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda payload: payload.__setitem__("schema_version", 2), "unsupported state schema_version"),
        (lambda payload: payload.__setitem__("variant", 3), "variant must be a string"),
        (lambda payload: payload.__setitem__("options", []), "options must be a mapping"),
        (lambda payload: payload.__setitem__("options", {"draw_count": "1"}), "draw_count must be an integer"),
        (lambda payload: payload.__setitem__("options", {"draw_count": 1, "redeals": "many"}), "redeals"),
        (lambda payload: payload.__setitem__("redeals_used", "0"), "redeals_used must be an integer"),
        (lambda payload: payload.__setitem__("foundations", "bad"), "foundations must be a list"),
        (_set_foundation_to_non_list, "foundations\\[0\\] must be a list"),
        (lambda payload: payload.__setitem__("tableau", "bad"), "tableau must be a list"),
        (_set_tableau_column_to_non_list, "tableau\\[0\\] must be a list"),
        (_set_tableau_item_to_non_mapping, "tableau\\[0\\]\\[0\\] must be a mapping"),
        (_set_tableau_face_up_to_non_bool, "tableau\\[0\\]\\[0\\]\\.face_up must be a boolean"),
        (lambda payload: payload.__setitem__("stock", "bad"), "stock must be a list"),
        (lambda payload: payload.__setitem__("stock", [None]), "stock\\[0\\] must be a card-code string"),
    ],
)
def test_deserialize_state_reports_malformed_payloads(
    mutate: Callable[[dict[str, object]], object],
    message: str,
) -> None:
    payload = _minimal_state_payload()
    mutate(payload)

    with pytest.raises(NotationError, match=message):
        deserialize_state(payload)


def test_state_validation_diagnostics_are_structured() -> None:
    result = validate_state_text("NOT_A_STATE")

    assert not result.ok
    assert result.message is not None
    assert result.diagnostics[0].path == "state_text"
    assert result.diagnostics[0].error_type == "NotationError"


def test_serialized_state_validation_reports_payload_paths() -> None:
    state = GameSession.new(seed=14).state
    payload = serialize_state(state)
    payload["tableau"][0][0]["card"] = "NOPE"

    result = validate_serialized_state(payload)

    assert not result.ok
    assert result.message is not None
    assert "tableau[0][0].card" in result.message


def test_player_view_serialization_round_trips_visible_and_history_metadata() -> None:
    state = GameSession.new(seed=15).state
    seen_card = state.stock[0]
    view = PlayerView.from_state(state, seen_cards=(seen_card,))

    payload = serialize_player_view(view)

    assert payload["schema_version"] == SCHEMA_VERSION
    assert seen_card.code in payload["seen_cards"]
    assert payload["tableau"][1][0] == {"card": None, "face_up": False}
    assert deserialize_player_view(payload) == view


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda payload: payload.__setitem__("schema_version", 2), "unsupported player-view schema_version"),
        (_set_player_unknown_count_to_non_int, "hidden_tableau_counts\\[0\\] must be an integer"),
        (_set_player_tableau_column_to_non_list, "tableau\\[0\\] must be a list"),
        (_set_player_tableau_item_to_non_mapping, "tableau\\[0\\]\\[0\\] must be a mapping"),
        (_set_player_tableau_face_up_to_non_bool, "tableau\\[0\\]\\[0\\]\\.face_up must be a boolean"),
        (_set_player_tableau_card_to_non_string, "tableau\\[0\\]\\[0\\]\\.card must be a card-code string"),
    ],
)
def test_deserialize_player_view_reports_malformed_payloads(
    mutate: Callable[[dict[str, object]], object],
    message: str,
) -> None:
    payload = _minimal_player_view_payload()
    mutate(payload)

    with pytest.raises(NotationError, match=message):
        deserialize_player_view(payload)
