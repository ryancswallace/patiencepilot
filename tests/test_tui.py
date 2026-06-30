"""Tests for the Textual terminal user interface."""

from __future__ import annotations

import asyncio
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import Protocol, cast

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
    TableauToFoundation,
    TableauToTableau,
    WasteToFoundation,
    WasteToTableau,
    move_to_id,
    standard_deck,
)
from patiencepilot.moves import RecycleWaste
from patiencepilot.view import PlayerStackCard, PlayerView, UnknownCardConstraints

pytestmark = pytest.mark.unit


class _PausePilot(Protocol):
    """Minimal protocol for Textual test pilots used by helper coroutines."""

    async def pause(self) -> None:
        """Let the Textual app process pending messages."""
        ...


def test_tui_packaging_declares_script_and_optional_extra() -> None:
    config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]

    assert project["scripts"]["patiencepilot-tui"] == "patiencepilot.tui:main"
    assert project["scripts"]["patp-tui"] == "patiencepilot.tui:main"
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


def test_tui_entry_point_reports_missing_textual(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_import_module(name: str) -> object:
        assert name == "patiencepilot.ui.tui"
        raise ModuleNotFoundError("No module named 'textual'", name="textual")

    monkeypatch.setattr(tui_entry, "import_module", fake_import_module)

    code = tui_entry.main([])

    assert code == 2
    assert "require Textual" in capsys.readouterr().out


def test_tui_options_parse_paths_seed_and_redeals(tmp_path: Path) -> None:
    load_path = tmp_path / "load.json"
    save_path = tmp_path / "save.json"
    args = tui.build_parser().parse_args(
        [
            "--seed",
            "game",
            "--draw-count",
            "3",
            "--redeals",
            "none",
            "--load",
            str(load_path),
            "--save",
            str(save_path),
            "--real-world",
        ]
    )

    options = tui.options_from_args(args)

    assert options.seed == "game"
    assert options.draw_count == 3
    assert options.redeals is None
    assert options.load_path == load_path
    assert options.save_path == save_path
    assert options.real_world is True
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


def test_tui_layout_keeps_control_buttons_visible_at_normal_terminal_size() -> None:
    async def scenario() -> None:
        app = tui.PatiencePilotTui(tui.TuiOptions(seed=1))
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            side_region = app.query_one("#side-panel").region
            board_region = app.query_one("#board-panel").region
            input_region = app.query_one("#move-input", Input).region

            assert side_region.width >= 38
            assert abs(board_region.width - side_region.width) <= 1
            for button_id in ("apply", "draw", "undo", "redo", "new", "save", "load", "advice"):
                button_region = app.query_one(f"#{button_id}", Button).region
                assert button_region.x >= side_region.x
                assert button_region.x + button_region.width <= side_region.x + side_region.width
                assert button_region.y + button_region.height <= input_region.y

    asyncio.run(scenario())


def test_tui_mounted_app_can_apply_displayed_legal_move_number() -> None:
    async def scenario() -> None:
        app = tui.PatiencePilotTui(tui.TuiOptions(seed=1))
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.pause()
            legal_move_ids = tuple(move_to_id(move) for move in app.session.legal_moves())

            app.query_one("#move-input", Input).value = "2"
            app._apply_entered_move()
            await pilot.pause()

            assert move_to_id(app.session.move_history[-1]) == legal_move_ids[1]
            assert f"Applied {legal_move_ids[1]}." in _static_text(app, "#status")

    asyncio.run(scenario())


def test_tui_real_world_setup_wizard_creates_known_session() -> None:
    async def scenario() -> None:
        app = tui.PatiencePilotTui(tui.TuiOptions(real_world=True, draw_count=3, redeals=1))
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.pause()
            assert "Real-world mirror setup" in _static_text(app, "#board")

            for card_code in ("AS", "2H", "3C", "4D", "5S", "6H", "7C"):
                app.query_one("#move-input", Input).value = card_code
                app._apply_entered_move()
                await pilot.pause()

            assert app._known_session is not None
            assert app._known_session.view.stock_count == 24
            assert app._known_session.view.draw_count == 3
            assert app._known_session.view.redeals_allowed == 1
            assert "Real-world mirror" in _static_text(app, "#board")
            assert "DRAW" in _static_text(app, "#legal-moves")

    asyncio.run(scenario())


def test_tui_real_world_setup_rejects_visible_duplicates() -> None:
    async def scenario() -> None:
        app = tui.PatiencePilotTui(tui.TuiOptions(real_world=True))
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.pause()
            app.query_one("#move-input", Input).value = "AS"
            app._apply_entered_move()
            app.query_one("#move-input", Input).value = "AS"
            app._apply_entered_move()
            await pilot.pause()

            assert "card AS is already visible" in _static_text(app, "#status")
            assert app._real_world_setup is not None
            assert app._real_world_setup.tableau_cards == [Card.from_code("AS")]

    asyncio.run(scenario())


def test_tui_real_world_draw_prompts_for_newly_visible_cards() -> None:
    async def scenario() -> None:
        app = tui.PatiencePilotTui(tui.TuiOptions(real_world=True, draw_count=3))
        async with app.run_test(size=(110, 40)) as pilot:
            await _finish_real_world_setup(app, pilot)

            app.query_one("#move-input", Input).value = "DRAW"
            app._apply_entered_move()
            await pilot.pause()
            assert "Enter the 3 drawn cards" in _static_text(app, "#status")

            app.query_one("#move-input", Input).value = "8D 9S TH"
            app._apply_entered_move()
            await pilot.pause()

            assert app._known_session is not None
            assert app._known_session.view.waste[-3:] == (
                Card.from_code("8D"),
                Card.from_code("9S"),
                Card.from_code("TH"),
            )
            assert app._known_session.view.stock_count == 21
            assert app._known_session.move_history == (DrawFromStock(),)

    asyncio.run(scenario())


def test_tui_real_world_accepts_displayed_legal_move_number() -> None:
    async def scenario() -> None:
        app = tui.PatiencePilotTui(tui.TuiOptions(real_world=True))
        async with app.run_test(size=(110, 40)) as pilot:
            await _finish_real_world_setup(app, pilot)

            app.query_one("#move-input", Input).value = "1"
            app._apply_entered_move()
            await pilot.pause()

            assert app._real_world_prompt is not None
            assert app._real_world_prompt.move == DrawFromStock()
            assert "Enter the drawn card" in _static_text(app, "#status")

    asyncio.run(scenario())


def test_tui_real_world_tableau_move_prompts_for_revealed_card() -> None:
    async def scenario() -> None:
        app = tui.PatiencePilotTui(tui.TuiOptions(real_world=True))
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.pause()
            view = PlayerView(
                foundations=cast("tuple[tuple[Card, ...], ...]", tuple(() for _ in Suit)),
                tableau=(
                    (PlayerStackCard.hidden(), PlayerStackCard.visible(Card.from_code("AS"))),
                    (),
                    (),
                    (),
                    (),
                    (),
                    (),
                ),
                waste=(),
                seen_cards=(Card.from_code("AS"),),
                unknown=UnknownCardConstraints(
                    hidden_tableau_counts=(1, 0, 0, 0, 0, 0, 0),
                    stock_count=0,
                    unseen_cards=tuple(card for card in standard_deck() if card != Card.from_code("AS")),
                ),
            )
            app._real_world_setup = None
            app._known_session = tui.KnownGameSession(view=view)
            app._refresh()

            app.query_one("#move-input", Input).value = "T0->F"
            app._apply_entered_move()
            await pilot.pause()
            assert "Enter the newly revealed card on T0" in _static_text(app, "#status")

            app.query_one("#move-input", Input).value = "2C"
            app._apply_entered_move()
            await pilot.pause()

            assert app._known_session is not None
            assert app._known_session.view.tableau[0][-1].visible_card == Card.from_code("2C")
            assert app._known_session.view.foundation(Suit.SPADES) == (Card.from_code("AS"),)
            assert app._known_session.move_history == (TableauToFoundation(source=0),)

    asyncio.run(scenario())


def test_tui_real_world_reveal_validation_keeps_prompt_active() -> None:
    async def scenario() -> None:
        app = tui.PatiencePilotTui(tui.TuiOptions(real_world=True))
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.pause()
            view = PlayerView(
                foundations=cast("tuple[tuple[Card, ...], ...]", tuple(() for _ in Suit)),
                tableau=(
                    (PlayerStackCard.hidden(), PlayerStackCard.visible(Card.from_code("AS"))),
                    (PlayerStackCard.visible(Card.from_code("2C")),),
                    (),
                    (),
                    (),
                    (),
                    (),
                ),
                waste=(),
                seen_cards=(Card.from_code("AS"), Card.from_code("2C")),
                unknown=UnknownCardConstraints(
                    hidden_tableau_counts=(1, 0, 0, 0, 0, 0, 0),
                    stock_count=0,
                    unseen_cards=tuple(
                        card for card in standard_deck() if card not in {Card.from_code("AS"), Card.from_code("2C")}
                    ),
                ),
            )
            app._real_world_setup = None
            app._known_session = tui.KnownGameSession(view=view)
            app._refresh()

            app.query_one("#move-input", Input).value = "T0->F"
            app._apply_entered_move()
            await pilot.pause()
            app.query_one("#move-input", Input).value = "2C"
            app._apply_entered_move()

            assert app._real_world_prompt is not None
            assert app._known_session is not None
            assert app._known_session.move_history == ()
            assert "card 2C is already visible" in _static_text(app, "#status")

    asyncio.run(scenario())


def test_tui_real_world_advice_uses_known_view() -> None:
    async def scenario() -> None:
        service = PatiencePilotApp()
        service.advice_provider = RecordingAdviceProvider()
        app = tui.PatiencePilotTui(tui.TuiOptions(real_world=True), app_service=service)
        async with app.run_test(size=(110, 40)) as pilot:
            await _finish_real_world_setup(app, pilot)
            app._request_advice()

            provider = service.advice_provider
            assert isinstance(provider, RecordingAdviceProvider)
            assert app._known_session is not None
            assert provider.seen_view is app._known_session.view
            assert app.query_one("#move-input", Input).value == "DRAW"

    asyncio.run(scenario())


def test_tui_real_world_buttons_handle_prompts_undo_redo_and_disabled_persistence() -> None:
    async def scenario() -> None:
        app = tui.PatiencePilotTui(tui.TuiOptions(real_world=True))
        async with app.run_test(size=(110, 40)) as pilot:
            await _finish_real_world_setup(app, pilot)

            app.action_save()
            assert "Saving real-world mirror sessions" in _static_text(app, "#status")

            app.action_load()
            assert "Loading real-world mirror sessions" in _static_text(app, "#status")

            app.action_undo()
            assert "no moves to undo" in _static_text(app, "#status")

            app.action_redo()
            assert "no moves to redo" in _static_text(app, "#status")

            app.action_quick_draw()
            await pilot.pause()
            assert "Enter the drawn card" in _static_text(app, "#status")

            app.action_undo()
            assert "before undoing" in _static_text(app, "#status")

            app.action_redo()
            assert "before redoing" in _static_text(app, "#status")

            app.query_one("#move-input", Input).value = "8D"
            app._apply_entered_move()
            await pilot.pause()
            assert app._known_session is not None
            assert app._known_session.move_history == (DrawFromStock(),)

            app.action_undo()
            await pilot.pause()
            assert app._known_session.move_history == ()

            app.action_redo()
            await pilot.pause()
            assert app._known_session.move_history == (DrawFromStock(),)

            app.action_new_game()
            await pilot.pause()
            assert app._real_world_setup is not None
            assert "Real-world mirror setup" in _static_text(app, "#board")

    asyncio.run(scenario())


def test_tui_real_world_prompt_validation_and_advice_states() -> None:
    async def scenario() -> None:
        app = tui.PatiencePilotTui(tui.TuiOptions(real_world=True, draw_count=3))
        async with app.run_test(size=(110, 40)) as pilot:
            await _finish_real_world_setup(app, pilot)

            app.query_one("#move-input", Input).value = "DRAW"
            app._apply_entered_move()
            await pilot.pause()

            app.query_one("#move-input", Input).value = "8D 9S"
            app._apply_entered_move()
            assert "Enter exactly 3 drawn card" in _static_text(app, "#status")

            app.query_one("#move-input", Input).value = "8D 8D TH"
            app._apply_entered_move()
            assert "card 8D is already visible" in _static_text(app, "#status")

            app._request_advice()
            assert "before asking for advice" in _static_text(app, "#status")

            app.query_one("#move-input", Input).value = "8D 9S TH"
            app._apply_entered_move()
            await pilot.pause()

            app.service.advice_provider = EmptyAdviceProvider()
            app._request_advice()
            assert "No advice available" in _static_text(app, "#status")

            app.service.advice_provider = None
            app._request_advice()
            assert "No advice provider configured" in _static_text(app, "#status")

            app.query_one("#move-input", Input).value = "999"
            app._apply_entered_move()
            assert "Move number 999" in _static_text(app, "#status")

            app.query_one("#move-input", Input).value = "NOPE"
            app._apply_entered_move()
            assert "invalid move id" in _static_text(app, "#status")

    asyncio.run(scenario())


def test_tui_known_state_helpers_cover_waste_tableau_recycle_and_validation() -> None:
    view = tui._new_real_world_view(
        tuple(Card.from_code(code) for code in ("AS", "2H", "3C", "4D", "5S", "6H", "7C")),
        draw_count=1,
        redeals=None,
    )
    waste_view = tui._replace_player_view(view, stock_count=0, waste=(Card.from_code("KS"), Card.from_code("AH")))

    recycled, reveal_column = tui._apply_known_immediate_move(waste_view, RecycleWaste())
    assert reveal_column is None
    assert recycled.stock_count == 2
    assert recycled.waste == ()
    assert recycled.redeals_used == 1

    founded, reveal_column = tui._apply_known_immediate_move(waste_view, WasteToFoundation())
    assert reveal_column is None
    assert founded.foundation(Suit.HEARTS) == (Card.from_code("AH"),)

    tabled, reveal_column = tui._apply_known_immediate_move(waste_view, WasteToTableau(destination=0))
    assert reveal_column is None
    assert tabled.tableau[0][-1].visible_card == Card.from_code("AH")

    moved, reveal_column = tui._apply_known_immediate_move(view, TableauToTableau(source=6, destination=0))
    assert reveal_column == 6
    assert moved.tableau[0][-1].visible_card == Card.from_code("7C")

    with pytest.raises(ValueError, match="requires newly visible"):
        tui._apply_known_immediate_move(view, DrawFromStock())
    with pytest.raises(ValueError, match="requires exactly 7"):
        tui._new_real_world_view((Card.from_code("AS"),), draw_count=1, redeals=None)
    with pytest.raises(ValueError, match="Enter exactly one"):
        tui._parse_one_card("AS 2H")
    with pytest.raises(ValueError, match="Enter at least one"):
        tui._parse_card_list(" ")
    with pytest.raises(ValueError, match="invalid card code"):
        tui._parse_card_list("ZZ")
    previously_seen_view = tui._replace_player_view(view, extra_seen=(Card.from_code("8S"),))
    with pytest.raises(ValueError, match="has already been seen"):
        tui._validate_revealed_tableau_card(Card.from_code("8S"), previously_seen_view)
    with pytest.raises(ValueError, match="source card is not visible"):
        tui._require_visible_top((PlayerStackCard.hidden(),), "T0->F")
    with pytest.raises(ValueError, match="no source card"):
        tui._require_visible_top((), "T0->F")
    with pytest.raises(ValueError, match="no hidden tableau"):
        tui._reveal_pending_tableau_card(view, WasteToFoundation(), Card.from_code("8S"))


def test_tui_known_renderers_handle_no_moves_and_history() -> None:
    foundations = tuple(tuple(Card(rank=rank, suit=suit) for rank in Rank) for suit in Suit)
    view = PlayerView(
        foundations=foundations,
        tableau=((), (), (), (), (), (), ()),
        waste=(),
        seen_cards=tuple(card for foundation in foundations for card in foundation),
        unknown=UnknownCardConstraints(hidden_tableau_counts=(0, 0, 0, 0, 0, 0, 0), stock_count=0, unseen_cards=()),
    )
    session = tui.KnownGameSession(view=view)

    assert "No legal moves" in tui.render_known_legal_moves(view)
    assert tui.render_known_history(session) == "History\n\nNo moves yet."
    session.history.append(tui.KnownStep(move=WasteToFoundation(), before=view, after=view))
    assert "W->F" in tui.render_known_history(session)


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

            app.query_one("#move-input", Input).value = "999"
            app._apply_entered_move()
            assert "Move number 999 is not in the legal move list." in _static_text(app, "#status")

            app._request_advice()
            assert app.query_one("#move-input", Input).value == "DRAW"
            assert "Advice: try DRAW." in _static_text(app, "#status")

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


async def _finish_real_world_setup(app: tui.PatiencePilotTui, pilot: _PausePilot) -> None:
    """Complete real-world setup with deterministic visible tableau cards."""
    for card_code in ("AS", "2H", "3C", "4D", "5S", "6H", "7C"):
        app.query_one("#move-input", Input).value = card_code
        app._apply_entered_move()
        await pilot.pause()


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
