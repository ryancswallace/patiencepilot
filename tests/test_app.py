"""Tests for the application orchestration layer."""

from __future__ import annotations

from dataclasses import replace

import pytest

from patiencepilot import (
    Advice,
    DrawFromStock,
    DummySolver,
    InvalidStateError,
    NotationError,
    PatiencePilotApp,
    PlayerView,
    SearchLimit,
    ValidationReport,
    deserialize_state,
    export_session,
    import_session,
    migrate_session_payload,
    serialize_state,
    state_to_text,
    validate_session_payload,
    validate_state_payload,
)
from patiencepilot.game import GameSession
from patiencepilot.state import GameState

pytestmark = pytest.mark.unit


def test_app_selects_variant_and_starts_session() -> None:
    app = PatiencePilotApp()

    rules = app.select_variant("klondike", {"draw_count": 3, "redeals": 1})
    session = app.new_session(seed=7, metadata={"source": "test"}, ui_state={"selected": "stock"})

    assert rules.name == "klondike"
    assert app.session is session
    assert session.state.draw_count == 3
    assert session.state.redeals_allowed == 1
    assert session.seed == 7
    assert session.metadata == {"source": "test"}
    assert session.ui_state == {"selected": "stock"}


def test_app_selects_solver_by_registry_name_or_alias() -> None:
    app = PatiencePilotApp()

    solver = app.select_solver("trivial")

    assert isinstance(solver, DummySolver)
    assert app.advice_provider is solver


def test_app_delegates_session_moves_undo_and_redo() -> None:
    app = PatiencePilotApp()
    session = app.new_session(seed=8)
    initial_state = session.state

    result = app.apply_move(DrawFromStock())

    assert session.state == result.state
    assert session.state != initial_state

    assert app.undo().state == initial_state
    assert app.redo() == result


def test_app_validation_reports_success_and_package_errors() -> None:
    app = PatiencePilotApp()
    app.new_session(seed=9)

    assert app.validate() == ValidationReport(ok=True)

    invalid_state = GameState.empty(variant="spider")
    report = app.validate(invalid_state)

    assert not report.ok
    assert report.error_type == "UnsupportedVariantError"
    assert report.message is not None


def test_app_validation_reports_missing_active_session() -> None:
    report = PatiencePilotApp().validate()

    assert not report.ok
    assert report.error_type == "InvalidStateError"
    assert report.diagnostics[0].path == "state"


def test_session_export_import_round_trips_history_and_redo() -> None:
    session = GameSession.new(seed=10)
    first_result = session.apply_move(DrawFromStock())
    session.undo()
    seen_card = session.state.stock[0]
    payload = export_session(session, seen_cards=(seen_card,))

    assert payload["schema_version"] == 1
    assert payload["variant"] == "klondike"
    assert payload["history"] == []
    assert payload["redo"] == [{"id": "DRAW"}]
    assert payload["seen_cards"] == [seen_card.code]
    assert payload["current_state"]["schema_version"] == 1
    assert payload["state_notation"].startswith("VARIANT klondike")
    assert seen_card.code in payload["player_view"]["seen_cards"]

    imported = import_session(payload)

    assert imported.state == session.state
    assert imported.move_history == ()
    assert [step.move for step in imported.redo_history] == [DrawFromStock()]
    assert imported.metadata["seen_cards"] == [seen_card.code]
    assert imported.redo() == first_result


def test_app_export_accepts_explicit_session_without_active_session() -> None:
    session = GameSession.new(seed=10)

    payload = PatiencePilotApp().export_session(session)

    assert payload["current_state"] == serialize_state(session.state)


def test_app_import_session_updates_active_session_and_variant_selection() -> None:
    app = PatiencePilotApp()
    session = app.new_session(seed=11)
    app.apply_move(DrawFromStock())
    payload = app.export_session()
    imported_app = PatiencePilotApp()

    imported = imported_app.import_session(payload)

    assert imported_app.session is imported
    assert imported.state == session.state
    assert imported.move_history == (DrawFromStock(),)
    assert imported_app.variant == "klondike"
    assert imported_app.options == {"draw_count": 1, "redeals": None}


def test_state_serialization_round_trips_exact_hidden_cards() -> None:
    state = GameSession.new(seed=12).state

    payload = serialize_state(state)

    assert payload["tableau"][1][0]["face_up"] is False
    assert deserialize_state(payload) == state


def test_import_session_rejects_payloads_that_do_not_match_history() -> None:
    session = GameSession.new(seed=13)
    payload = export_session(session)
    changed_state = replace(session.state, stock=session.state.stock[:-1])
    payload["current_state"] = serialize_state(changed_state)
    payload.pop("state_notation")

    with pytest.raises(NotationError, match="history does not reproduce"):
        import_session(payload)


def test_import_session_rejects_state_notation_that_does_not_match_current_state() -> None:
    session = GameSession.new(seed=13)
    payload = export_session(session)
    payload["state_notation"] = state_to_text(replace(session.state, stock=session.state.stock[:-1]))

    with pytest.raises(NotationError, match="state_notation does not match"):
        import_session(payload)


def test_session_payload_migration_defaults_alpha_fields() -> None:
    session = GameSession.new(seed=16)
    payload = export_session(session)
    payload.pop("schema_version")
    payload.pop("metadata")
    payload.pop("ui_state")
    payload.pop("seen_cards")
    payload.pop("player_view")
    payload.pop("state_notation")

    migrated = migrate_session_payload(payload)

    assert migrated["schema_version"] == 1
    assert migrated["metadata"] == {}
    assert migrated["ui_state"] == {}
    assert migrated["seen_cards"] == []
    assert import_session(payload).state == session.state


def test_session_payload_migration_supports_legacy_state_key() -> None:
    session = GameSession.new(seed=16)
    payload = {"state": serialize_state(session.state)}

    migrated = migrate_session_payload(payload)

    assert migrated["current_state"] == serialize_state(session.state)
    assert migrated["initial_state"] == serialize_state(session.state)
    assert migrated["variant"] == "klondike"
    assert migrated["options"] == {"draw_count": 1, "redeals": None}
    assert import_session(payload).state == session.state


def test_session_payload_migration_defaults_variant_when_current_state_is_not_mapping() -> None:
    migrated = migrate_session_payload({})

    assert migrated["variant"] == "klondike"
    assert migrated["options"] == {}


def test_session_payload_migration_rejects_unsupported_schema_versions() -> None:
    with pytest.raises(NotationError, match="unsupported session schema_version"):
        migrate_session_payload({"schema_version": 999})


def test_session_payload_validation_returns_diagnostics() -> None:
    report = validate_session_payload({"schema_version": 999})

    assert not report.ok
    assert report.error_type == "NotationError"
    assert report.diagnostics[0].path == "session"


def test_session_payload_validation_reports_success() -> None:
    payload = export_session(GameSession.new(seed=16))

    assert validate_session_payload(payload).ok


def test_state_payload_validation_reports_success_and_diagnostics() -> None:
    payload = serialize_state(GameSession.new(seed=16).state)

    assert validate_state_payload(payload).ok

    report = validate_state_payload({"schema_version": 999})

    assert not report.ok
    assert report.error_type == "NotationError"
    assert report.diagnostics[0].path == "state"


def test_import_session_rejects_non_mapping_history_items() -> None:
    payload: dict[str, object] = dict(export_session(GameSession.new(seed=16)))
    payload["history"] = ["DRAW"]

    with pytest.raises(NotationError, match="history items must be mappings"):
        import_session(payload)


def test_session_seen_card_metadata_accepts_card_objects_and_rejects_bad_values() -> None:
    session = GameSession.new(seed=16)
    seen_card = session.state.stock[0]
    session.metadata["seen_cards"] = [seen_card]

    payload = export_session(session)

    assert payload["seen_cards"] == [seen_card.code]

    session.metadata["seen_cards"] = [3]
    with pytest.raises(NotationError, match=r"metadata.seen_cards\[0\]"):
        export_session(session)


def test_session_seen_card_metadata_ignores_non_sequence_values() -> None:
    session = GameSession.new(seed=16, metadata={"seen_cards": "AS"})

    payload = export_session(session)

    assert payload["seen_cards"] == []


def test_import_session_accepts_bytes_seed_and_rejects_invalid_seed_values() -> None:
    payload = export_session(GameSession.new(seed=16))
    payload["seed"] = b"seed"

    assert import_session(payload).seed == b"seed"

    payload["seed"] = []
    with pytest.raises(NotationError, match="seed must be"):
        import_session(payload)


def test_advice_requests_are_delegated_to_provider() -> None:
    app = PatiencePilotApp()
    session = app.new_session(seed=14)
    provider = RecordingAdviceProvider()
    limit = SearchLimit(node_limit=1)

    advice = app.request_advice(provider=provider, limit=limit)

    assert advice.best_move == DrawFromStock()
    assert provider.seen_view is not None
    assert provider.seen_view.stock_count == len(session.state.stock)
    assert provider.seen_limit == limit


def test_advice_requests_require_a_provider() -> None:
    app = PatiencePilotApp()
    app.new_session(seed=15)

    with pytest.raises(InvalidStateError, match="no advice provider configured"):
        app.request_advice()


def test_app_requires_active_session_for_session_operations() -> None:
    app = PatiencePilotApp()

    with pytest.raises(InvalidStateError, match="no active session"):
        app.apply_move(DrawFromStock())


class RecordingAdviceProvider:
    """Test advice provider."""

    seen_limit: SearchLimit | None = None
    seen_view: PlayerView | None = None

    def suggest(self, view: PlayerView, *, limit: SearchLimit | None = None) -> Advice:
        """Return simple test advice."""
        self.seen_view = view
        self.seen_limit = limit
        return Advice.from_move(DrawFromStock(), solver_name="recording", limit=limit)
