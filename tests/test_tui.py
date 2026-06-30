"""Tests for the Textual terminal user interface."""

from __future__ import annotations

import asyncio
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from textual.widgets import Button, Input, Static

import patiencepilot.tui as tui_entry
import patiencepilot.ui.tui as tui
from patiencepilot import (
    Advice,
    Card,
    DrawFromStock,
    DrewStockCards,
    GameSession,
    GameState,
    MovedCards,
    PatiencePilotApp,
    Rank,
    RecycledWaste,
    RevealedTableauCard,
    SearchLimit,
    Suit,
)
from patiencepilot.view import PlayerView

pytestmark = pytest.mark.unit


def test_tui_packaging_declares_script_and_optional_extra() -> None:
    config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]

    assert project["scripts"]["patiencepilot-tui"] == "patiencepilot.tui:main"
    assert project["optional-dependencies"]["tui"] == ["textual>=6.12,<7"]


def test_tui_entry_point_delegates_to_textual_app(monkeypatch: pytest.MonkeyPatch) -> None:
    launched: dict[str, tui.TuiOptions] = {}

    def fake_run(app: tui.PatiencePilotTui) -> None:
        launched["options"] = app.options

    monkeypatch.setattr(tui.PatiencePilotTui, "run", fake_run)

    code = tui_entry.main(["--seed", "7", "--draw-count", "3", "--redeals", "1"])

    assert code == 0
    assert launched["options"].seed == 7
    assert launched["options"].draw_count == 3
    assert launched["options"].redeals == 1


def test_tui_options_parse_paths_seed_and_redeals(tmp_path: Path) -> None:
    load_path = tmp_path / "load.json"
    save_path = tmp_path / "save.json"
    args = tui.build_parser().parse_args(
        ["--seed", "game", "--draw-count", "3", "--redeals", "none", "--load", str(load_path), "--save", str(save_path)]
    )

    options = tui.options_from_args(args)

    assert options.seed == "game"
    assert options.draw_count == 3
    assert options.redeals is None
    assert options.load_path == load_path
    assert options.save_path == save_path
    assert tui._parse_redeals("2") == 2
    with pytest.raises(ValueError, match="invalid literal"):
        tui._parse_redeals("many")


def test_tui_renderers_hide_hidden_cards_and_show_game_context() -> None:
    session = GameSession.new(seed=7)
    hidden_card = next(
        stack_card.card for column in session.state.tableau for stack_card in column if not stack_card.face_up
    )

    board = tui.render_board(session)
    moves = tui.render_legal_moves(session)
    history = tui.render_history(session)

    assert "Stock:" in board
    assert "Foundations:" in board
    assert "##" in board
    assert hidden_card.code not in board
    assert "Legal moves" in moves
    assert "DRAW" in moves
    assert history == "History\n\nNo moves yet."


def test_tui_renderers_handle_won_state_and_effects() -> None:
    foundations = tuple(tuple(Card(rank=rank, suit=suit) for rank in Rank) for suit in Suit)
    session = GameSession(GameState(foundations=foundations, tableau=((), (), (), (), (), (), ()), stock=(), waste=()))
    effects = (
        DrewStockCards(cards=(Card.from_code("AS"),)),
        MovedCards(cards=(Card.from_code("KH"),), source="waste", destination="tableau[0]"),
        RecycledWaste(count=3),
        RevealedTableauCard(column=1, card=Card.from_code("2C")),
    )

    assert "No legal moves" in tui.render_legal_moves(session)
    assert "moved AS" in tui.render_status("Done", effects)
    assert "recycled 3 cards" in tui.render_status("Done", effects)
    assert "revealed 2C" in tui.render_status("Done", effects)


def test_tui_read_json_object_rejects_non_object_payload(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON object"):
        tui._read_json_object(path)


def test_tui_mounted_app_can_apply_undo_redo_save_and_load(tmp_path: Path) -> None:
    async def scenario() -> None:
        save_path = tmp_path / "game.json"
        app = tui.PatiencePilotTui(tui.TuiOptions(seed=7, save_path=save_path))
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.pause()
            assert "Stock:" in _static_text(app, "#board")

            app.query_one("#move-input", Input).value = "DRAW"
            app._apply_entered_move()
            await pilot.pause()
            assert app.session.move_history == (DrawFromStock(),)
            assert app.query_one("#move-input", Input).value == ""

            app.action_undo()
            await pilot.pause()
            assert app.session.move_history == ()

            app.action_redo()
            await pilot.pause()
            assert app.session.move_history == (DrawFromStock(),)

            app.action_save()
            assert save_path.exists()
            app.action_new_game()
            assert app.session.move_history == ()
            app.action_load()
            assert app.session.move_history == (DrawFromStock(),)

    asyncio.run(scenario())


def test_tui_mounted_app_reports_errors_and_advice_status(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = tui.PatiencePilotTui(tui.TuiOptions(seed=8))
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.pause()
            app.action_undo()
            assert "no moves to undo" in _static_text(app, "#status")

            app.action_redo()
            assert "no moves to redo" in _static_text(app, "#status")

            app.action_save()
            assert "Start with --save" in _static_text(app, "#status")

            app.action_load()
            assert "Start with --load" in _static_text(app, "#status")

            app._apply_entered_move()
            assert "Enter a move ID" in _static_text(app, "#status")

            app.query_one("#move-input", Input).value = "NOPE"
            app._apply_entered_move()
            assert "invalid move id" in _static_text(app, "#status")

            app._request_advice()
            assert "no advice provider configured" in _static_text(app, "#status")

            app.service.advice_provider = RecordingAdviceProvider()
            app._request_advice()
            assert app.query_one("#move-input", Input).value == "DRAW"

            app.service.advice_provider = EmptyAdviceProvider()
            app._request_advice()
            assert "No advice available" in _static_text(app, "#status")

    asyncio.run(scenario())


def test_tui_mount_recovers_from_load_errors(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = tui.PatiencePilotTui(tui.TuiOptions(load_path=tmp_path / "missing.json"))
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.pause()
            assert "Could not load" in _static_text(app, "#status")
            assert app.service.session is not None

    asyncio.run(scenario())


def test_tui_button_and_input_events_dispatch_to_actions() -> None:
    async def scenario() -> None:
        app = tui.PatiencePilotTui(tui.TuiOptions(seed=9))
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.pause()
            move_input = app.query_one("#move-input", Input)
            move_input.value = "DRAW"

            app.on_input_submitted(cast("Input.Submitted", SimpleNamespace(input=move_input)))
            assert app.session.move_history == (DrawFromStock(),)

            for button_id in ("undo", "redo", "draw", "new", "save", "load", "advice", "apply"):
                app.on_button_pressed(cast("Button.Pressed", SimpleNamespace(button=SimpleNamespace(id=button_id))))

    asyncio.run(scenario())


def test_tui_quick_draw_reports_when_no_draw_or_recycle_is_available() -> None:
    async def scenario() -> None:
        foundations = tuple(tuple(Card(rank=rank, suit=suit) for rank in Rank) for suit in Suit)
        session = GameSession(
            GameState(foundations=foundations, tableau=((), (), (), (), (), (), ()), stock=(), waste=())
        )
        service = PatiencePilotApp()
        service.use_session(session)
        app = tui.PatiencePilotTui(app_service=service)
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.pause()
            app.action_quick_draw()
            assert "No draw or recycle" in _static_text(app, "#status")

    asyncio.run(scenario())


def test_tui_board_render_handles_empty_tableau() -> None:
    session = GameSession(GameState.empty())

    board = tui.render_board(session)

    assert "Stock:" in board
    assert "T0" in board


def _static_text(app: tui.PatiencePilotTui, selector: str) -> str:
    """Return static widget text."""
    return str(app.query_one(selector, Static).content)


class RecordingAdviceProvider:
    """Advice provider that records the player-known view."""

    seen_limit: SearchLimit | None = None
    seen_view: PlayerView | None = None

    def suggest(self, view: PlayerView, *, limit: SearchLimit | None = None) -> Advice:
        """Return a single draw recommendation."""
        self.seen_view = view
        self.seen_limit = limit
        return Advice.from_move(DrawFromStock(), solver_name="tui-test", limit=limit)


class EmptyAdviceProvider:
    """Advice provider with no recommendation."""

    def suggest(self, view: PlayerView, *, limit: SearchLimit | None = None) -> Advice:
        """Return empty advice."""
        return Advice(recommendations=(), solver_name="empty", limit=limit)
