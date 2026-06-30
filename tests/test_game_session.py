"""Tests for the game session wrapper."""

from __future__ import annotations

import pytest

from patiencepilot import DrawFromStock, GameSession, InvalidMoveError, KlondikeRules, new_game

pytestmark = pytest.mark.unit


def test_new_session_tracks_seed_metadata_ui_state_and_current_state() -> None:
    metadata = {"source": "test"}
    ui_state = {"selected": "stock"}

    session = GameSession.new(
        "klondike",
        seed=7,
        options={"draw_count": 3, "redeals": 1},
        metadata=metadata,
        ui_state=ui_state,
    )

    assert session.seed == 7
    assert session.state.draw_count == 3
    assert session.state.redeals_allowed == 1
    assert session.metadata == metadata
    assert session.ui_state == ui_state
    assert session.metadata is not metadata
    assert session.ui_state is not ui_state
    assert session.history == ()
    assert session.redo_history == ()
    assert not session.can_undo
    assert not session.can_redo


def test_session_apply_undo_and_redo_preserve_pure_engine_state() -> None:
    session = GameSession.new(KlondikeRules(draw_count=3), seed=11)
    initial_state = session.state
    move = DrawFromStock()

    result = session.apply_move(move)

    assert initial_state.stock
    assert len(initial_state.stock) == 24
    assert len(session.state.stock) == 21
    assert session.state == result.state
    assert session.move_history == (move,)
    assert session.result_history == (result,)
    assert session.last_result == result
    assert session.history[0].before == initial_state
    assert session.history[0].after == result.state
    assert session.can_undo
    assert not session.can_redo

    undone_step = session.undo()

    assert undone_step.result == result
    assert session.state == initial_state
    assert session.history == ()
    assert session.redo_history == (undone_step,)
    assert not session.can_undo
    assert session.can_redo

    redone_result = session.redo()

    assert redone_result == result
    assert session.state == result.state
    assert session.move_history == (move,)
    assert session.redo_history == ()


def test_applying_a_new_move_clears_redo_history() -> None:
    session = GameSession.new(seed=12)
    first_result = session.apply_move(DrawFromStock())
    session.undo()

    assert session.redo_history

    second_result = session.apply_move(DrawFromStock())

    assert second_result == first_result
    assert session.redo_history == ()
    assert not session.can_redo


def test_session_delegates_legal_moves_validation_and_win_checks() -> None:
    session = GameSession(state=new_game(seed=9))

    assert DrawFromStock() in session.legal_moves()
    assert not session.is_won()

    session.validate_state()


def test_undo_and_redo_require_available_history() -> None:
    session = GameSession.new(seed=13)

    with pytest.raises(InvalidMoveError, match="no moves to undo"):
        session.undo()

    with pytest.raises(InvalidMoveError, match="no moves to redo"):
        session.redo()
