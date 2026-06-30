"""Textual terminal user interface."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, cast

from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Static

from patiencepilot import __version__
from patiencepilot.app import PatiencePilotApp
from patiencepilot.cards import Card, standard_deck
from patiencepilot.exceptions import PatiencePilotError
from patiencepilot.game import GameSession
from patiencepilot.moves import (
    DrawFromStock,
    DrewStockCards,
    Move,
    MovedCards,
    MoveEffect,
    RecycledWaste,
    RecycleWaste,
    RevealedTableauCard,
    TableauToFoundation,
    TableauToTableau,
    WasteToFoundation,
    WasteToTableau,
)
from patiencepilot.notation import move_from_id, move_to_id
from patiencepilot.solvers import DummySolver, SearchLimit, visible_klondike_moves
from patiencepilot.state import SUIT_ORDER, StackCard
from patiencepilot.variants.base import Seed
from patiencepilot.view import PlayerStackCard, PlayerView, UnknownCardConstraints


@dataclass(frozen=True, slots=True)
class TuiOptions:
    """Configuration for launching the TUI."""

    seed: Seed = None
    draw_count: int = 1
    redeals: int | None = None
    load_path: Path | None = None
    save_path: Path | None = None
    real_world: bool = False


@dataclass(frozen=True, slots=True)
class KnownStep:
    """One move applied to a player-known real-world mirror session."""

    move: Move
    before: PlayerView
    after: PlayerView


@dataclass(slots=True)
class KnownGameSession:
    """Mutable TUI session for mirroring a real-world player-known state."""

    view: PlayerView
    history: list[KnownStep] = field(default_factory=list)
    redo: list[KnownStep] = field(default_factory=list)

    @property
    def move_history(self) -> tuple[Move, ...]:
        """Return applied move history."""
        return tuple(step.move for step in self.history)


@dataclass(slots=True)
class RealWorldSetup:
    """Guided initial setup state for a real-world Klondike game."""

    tableau_cards: list[Card] = field(default_factory=list)


@dataclass(slots=True)
class RealWorldPrompt:
    """Prompt requiring user-entered newly visible card identities."""

    kind: str
    message: str
    move: Move
    before: PlayerView
    interim: PlayerView | None = None
    count: int = 1


class PatiencePilotTui(App[None]):
    """Interactive Textual application for playing Solitaire."""

    CSS = """
    Screen {
        background: #0d1117;
        color: #f0f6fc;
    }

    #layout {
        height: 1fr;
        padding: 1;
    }

    #board-panel {
        width: 1fr;
        min-width: 34;
        padding: 1;
        border: round #2f81f7;
        background: #111827;
    }

    #side-panel {
        width: 1fr;
        min-width: 38;
        padding: 1;
        border: round #3fb950;
        background: #0f172a;
    }

    .panel-title {
        text-style: bold;
        color: #79c0ff;
        margin-bottom: 1;
    }

    #board {
        height: 1fr;
        color: #e6edf3;
    }

    #move-input {
        margin: 0 0 1 0;
    }

    #buttons {
        height: 8;
        margin-bottom: 1;
    }

    .button-row {
        height: 4;
    }

    #status {
        height: 4;
        margin-top: 1;
        color: #ffa657;
    }

    #legal-moves {
        height: 1fr;
        margin-top: 1;
        padding: 1;
        border: tall #30363d;
        background: #0b1220;
    }

    #history {
        height: 6;
        margin-top: 1;
        padding: 1;
        border: tall #30363d;
        color: #c9d1d9;
    }

    Button {
        width: 1fr;
        min-width: 7;
        margin: 1 1 0 0;
    }

    Button.primary {
        background: #238636;
    }

    Button.warning {
        background: #9e6a03;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        ("d", "quick_draw", "Draw"),
        ("u", "undo", "Undo"),
        ("r", "redo", "Redo"),
        ("n", "new_game", "New"),
        ("s", "save", "Save"),
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        options: TuiOptions | None = None,
        *,
        app_service: PatiencePilotApp | None = None,
    ) -> None:
        """Initialize the TUI app."""
        super().__init__()
        self.options = TuiOptions() if options is None else options
        self.service = PatiencePilotApp() if app_service is None else app_service
        if self.service.advice_provider is None:
            self.service.advice_provider = DummySolver()
        self._last_effects: tuple[MoveEffect, ...] = ()
        self._status = "Ready."
        self._known_session: KnownGameSession | None = None
        self._real_world_setup: RealWorldSetup | None = None
        self._real_world_prompt: RealWorldPrompt | None = None

    def compose(self) -> ComposeResult:
        """Compose the terminal layout."""
        yield Header(show_clock=True)
        with Horizontal(id="layout"):
            with Vertical(id="board-panel"):
                yield Static("Patience Pilot", classes="panel-title")
                yield Static("", id="board")
            with Vertical(id="side-panel"):
                yield Static("Controls", classes="panel-title")
                with Vertical(id="buttons"):
                    with Horizontal(classes="button-row"):
                        yield Button("Apply", id="apply", variant="success", classes="primary")
                        yield Button("Draw", id="draw")
                        yield Button("Undo", id="undo")
                        yield Button("Redo", id="redo")
                    with Horizontal(classes="button-row"):
                        yield Button("New", id="new", variant="primary")
                        yield Button("Save", id="save")
                        yield Button("Load", id="load")
                        yield Button("Advice", id="advice", classes="warning")
                yield Input(placeholder="Move ID or number, e.g., DRAW or 2", id="move-input")
                yield Static("", id="legal-moves")
                yield Static("", id="history")
                yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        """Start or load a game when the TUI mounts."""
        if self.options.real_world:
            self._start_real_world_setup()
        else:
            self._load_or_start_session()
        self._refresh()
        self.query_one("#move-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle control button presses."""
        button_id = event.button.id
        if button_id == "apply":
            self._apply_entered_move()
        elif button_id == "draw":
            self.action_quick_draw()
        elif button_id == "undo":
            self.action_undo()
        elif button_id == "redo":
            self.action_redo()
        elif button_id == "new":
            self.action_new_game()
        elif button_id == "save":
            self.action_save()
        elif button_id == "load":
            self.action_load()
        elif button_id == "advice":
            self._request_advice()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Apply an entered move ID."""
        if event.input.id == "move-input":
            self._apply_entered_move()

    def action_quick_draw(self) -> None:
        """Apply DRAW or RECYCLE when either is legal."""
        if self._is_real_world_mode:
            self._apply_known_quick_draw()
            return
        legal_ids = tuple(move_to_id(move) for move in self.session.legal_moves())
        if "DRAW" in legal_ids:
            self._apply_move_id("DRAW")
        elif "RECYCLE" in legal_ids:
            self._apply_move_id("RECYCLE")
        else:
            self._set_status("No draw or recycle move is currently legal.")

    def action_undo(self) -> None:
        """Undo the latest move."""
        if self._is_real_world_mode:
            self._undo_known_move()
            return
        try:
            step = self.session.undo()
        except PatiencePilotError as error:
            self._set_status(str(error))
            return
        self._last_effects = ()
        self._set_status(f"Undid {move_to_id(step.move)}.")

    def action_redo(self) -> None:
        """Redo the latest undone move."""
        if self._is_real_world_mode:
            self._redo_known_move()
            return
        try:
            result = self.session.redo()
        except PatiencePilotError as error:
            self._set_status(str(error))
            return
        self._last_effects = result.effects
        self._set_status(f"Redid {move_to_id(result.move)}.")

    def action_new_game(self) -> None:
        """Start a new game."""
        if self._is_real_world_mode:
            self._start_real_world_setup()
            self._last_effects = ()
            self._set_status("Started real-world setup.")
            return
        self._start_new_session()
        self._last_effects = ()
        self._set_status("Started a new game.")

    def action_save(self) -> None:
        """Save the active session."""
        if self._is_real_world_mode:
            self._set_status("Saving real-world mirror sessions is not yet supported.")
            return
        if self.options.save_path is None:
            self._set_status("Start with --save PATH to enable saving.")
            return
        try:
            self._write_session(self.options.save_path)
        except OSError as error:
            self._set_status(str(error))
            return
        self._set_status(f"Saved to {self.options.save_path}.")

    def action_load(self) -> None:
        """Load the configured session path."""
        if self._is_real_world_mode:
            self._set_status("Loading real-world mirror sessions is not yet supported.")
            return
        path = self.options.load_path or self.options.save_path
        if path is None:
            self._set_status("Start with --load PATH to enable loading.")
            return
        try:
            self.service.import_session(_read_json_object(path))
        except (OSError, json.JSONDecodeError, PatiencePilotError, ValueError) as error:
            self._set_status(str(error))
            return
        self._last_effects = ()
        self._set_status(f"Loaded {path}.")

    @property
    def session(self) -> GameSession:
        """Return the active session."""
        if self.service.session is None:
            self._start_new_session()
        if self.service.session is None:
            msg = "no active session"
            raise RuntimeError(msg)
        return self.service.session

    def _load_or_start_session(self) -> None:
        """Load a saved session or start a new one."""
        if self.options.load_path is not None:
            try:
                self.service.import_session(_read_json_object(self.options.load_path))
            except (OSError, json.JSONDecodeError, PatiencePilotError, ValueError) as error:
                self._status = f"Could not load {self.options.load_path}: {error}. Started a new game."
                self._start_new_session()
            return
        if self.service.session is not None:
            return
        self._start_new_session()

    def _start_new_session(self) -> None:
        """Start a new session from launch options."""
        self.service.select_variant(
            "klondike",
            {"draw_count": self.options.draw_count, "redeals": self.options.redeals},
        )
        self.service.new_session(seed=self.options.seed)

    @property
    def _is_real_world_mode(self) -> bool:
        """Return whether the TUI is mirroring player-known real-world state."""
        return self.options.real_world or self._known_session is not None or self._real_world_setup is not None

    def _start_real_world_setup(self) -> None:
        """Start guided setup for a physical-card Klondike game."""
        self._known_session = None
        self._real_world_prompt = None
        self._real_world_setup = RealWorldSetup()
        self._last_effects = ()
        self._status = "Enter the visible card on T0, e.g. AS."
        self._set_input_placeholder("Visible T0 card, e.g. AS")

    def _apply_entered_move(self) -> None:
        """Apply the current move input value."""
        move_input = self.query_one("#move-input", Input).value.strip()
        if not move_input:
            self._set_status("Enter a move ID first.")
            return
        if self._is_real_world_mode:
            self._handle_real_world_input(move_input)
            return
        try:
            move_id = _move_id_from_input(self.session, move_input)
        except ValueError as error:
            self._set_status(str(error))
            return
        self._apply_move_id(move_id)

    def _apply_move_id(self, move_id: str) -> None:
        """Apply a move by ID."""
        try:
            move = move_from_id(move_id)
            result = self.service.apply_move(move)
        except PatiencePilotError as error:
            self._set_status(str(error))
            return
        self._last_effects = result.effects
        self.query_one("#move-input", Input).value = ""
        if self.session.is_won():
            self._set_status(f"Applied {move_to_id(move)}. You won!")
        else:
            self._set_status(f"Applied {move_to_id(move)}.")

    def _request_advice(self) -> None:
        """Ask the configured advice provider for a move."""
        if self._is_real_world_mode:
            self._request_known_advice()
            return
        try:
            advice = self.service.request_advice(limit=SearchLimit(depth_limit=1))
        except PatiencePilotError as error:
            self._set_status(str(error))
            return
        best_move = advice.best_move
        if best_move is None:
            self._set_status("No advice available.")
            return
        self.query_one("#move-input", Input).value = move_to_id(best_move)
        self._set_status(f"Advice: try {move_to_id(best_move)}.")

    def _handle_real_world_input(self, text: str) -> None:
        """Handle setup, prompt, or move input for a real-world mirror game."""
        if self._real_world_setup is not None:
            self._add_real_world_setup_card(text)
            return
        if self._real_world_prompt is not None:
            self._complete_real_world_prompt(text)
            return
        self._apply_known_entered_move(text)

    def _add_real_world_setup_card(self, text: str) -> None:
        """Add one visible tableau card during real-world setup."""
        setup = self._real_world_setup
        if setup is None:
            return
        column = len(setup.tableau_cards)
        try:
            card = _parse_one_card(text)
            _validate_no_duplicate_cards((*setup.tableau_cards, card))
        except ValueError as error:
            self._set_status(str(error))
            return

        setup.tableau_cards.append(card)
        self.query_one("#move-input", Input).value = ""
        if len(setup.tableau_cards) == 7:
            view = _new_real_world_view(
                setup.tableau_cards,
                draw_count=self.options.draw_count,
                redeals=self.options.redeals,
            )
            self._known_session = KnownGameSession(view=view)
            self._real_world_setup = None
            self._set_input_placeholder("Move ID or number, e.g., DRAW or 2")
            self._set_status("Real-world mirror ready. Enter a move or ask for advice.")
            return

        next_column = column + 1
        self._set_input_placeholder(f"Visible T{next_column} card, e.g. 7D")
        self._set_status(f"Recorded T{column}={card.code}. Enter the visible card on T{next_column}.")

    def _complete_real_world_prompt(self, text: str) -> None:
        """Complete an active real-world prompt with newly observed cards."""
        prompt = self._real_world_prompt
        if prompt is None:
            return
        try:
            if prompt.kind == "draw":
                cards = _parse_card_list(text)
                if len(cards) != prompt.count:
                    msg = f"Enter exactly {prompt.count} drawn card(s)."
                    raise ValueError(msg)
                _validate_new_visible_cards(cards, prompt.before)
                after = _replace_player_view(
                    prompt.before,
                    stock_count=prompt.before.stock_count - prompt.count,
                    waste=(*prompt.before.waste, *cards),
                    extra_seen=cards,
                )
                self._real_world_prompt = None
                self._commit_known_step(prompt.move, prompt.before, after, f"Applied {move_to_id(prompt.move)}.")
                return

            if prompt.kind == "reveal" and prompt.interim is not None:
                card = _parse_one_card(text)
                _validate_revealed_tableau_card(card, prompt.interim)
                after = _reveal_pending_tableau_card(prompt.interim, prompt.move, card)
                self._real_world_prompt = None
                status = f"Applied {move_to_id(prompt.move)} and revealed {card.code}."
                self._commit_known_step(prompt.move, prompt.before, after, status)
                return
        except ValueError as error:
            self._set_status(str(error))
            return

        self._set_status("No real-world prompt is active.")

    def _apply_known_entered_move(self, text: str) -> None:
        """Apply the current input as a move against player-known state."""
        known = self._known_session
        if known is None:
            self._set_status("Finish real-world setup first.")
            return
        try:
            move_id = _known_move_id_from_input(known.view, text)
            move = move_from_id(move_id)
            self._apply_known_move(move)
        except (PatiencePilotError, ValueError) as error:
            self._set_status(str(error))

    def _apply_known_move(self, move: Move) -> None:
        """Apply a visible-legal move to the player-known session."""
        known = self._known_session
        if known is None:
            self._set_status("Finish real-world setup first.")
            return
        legal_moves = visible_klondike_moves(known.view)
        if move not in legal_moves:
            self._set_status(f"{move_to_id(move)} is not legal from the visible state.")
            return

        if isinstance(move, DrawFromStock):
            count = min(known.view.draw_count, known.view.stock_count)
            self._real_world_prompt = RealWorldPrompt(
                kind="draw",
                message=_draw_prompt_message(count),
                move=move,
                before=known.view,
                count=count,
            )
            self.query_one("#move-input", Input).value = ""
            self._set_input_placeholder(_draw_input_placeholder(count))
            self._set_status(_draw_prompt_message(count))
            return

        before = known.view
        after, reveal_column = _apply_known_immediate_move(before, move)
        self.query_one("#move-input", Input).value = ""
        if reveal_column is not None:
            message = f"Enter the newly revealed card on T{reveal_column}."
            self._real_world_prompt = RealWorldPrompt(
                kind="reveal",
                message=message,
                move=move,
                before=before,
                interim=after,
            )
            self._set_input_placeholder(f"Revealed T{reveal_column} card, e.g. 2C")
            self._set_status(message)
            return
        self._commit_known_step(move, before, after, f"Applied {move_to_id(move)}.")

    def _apply_known_quick_draw(self) -> None:
        """Apply DRAW or RECYCLE in a player-known session when possible."""
        known = self._known_session
        if known is None:
            self._set_status("Finish real-world setup first.")
            return
        legal_moves = visible_klondike_moves(known.view)
        for wanted in (DrawFromStock(), RecycleWaste()):
            if wanted in legal_moves:
                self._apply_known_move(wanted)
                return
        self._set_status("No draw or recycle move is currently legal.")

    def _undo_known_move(self) -> None:
        """Undo the latest real-world mirror move."""
        if self._real_world_prompt is not None:
            self._set_status("Enter the requested card before undoing.")
            return
        known = self._known_session
        if known is None or not known.history:
            self._set_status("no moves to undo")
            return
        step = known.history.pop()
        known.redo.append(step)
        known.view = step.before
        self._last_effects = ()
        self._set_status(f"Undid {move_to_id(step.move)}.")

    def _redo_known_move(self) -> None:
        """Redo the latest undone real-world mirror move."""
        if self._real_world_prompt is not None:
            self._set_status("Enter the requested card before redoing.")
            return
        known = self._known_session
        if known is None or not known.redo:
            self._set_status("no moves to redo")
            return
        step = known.redo.pop()
        known.history.append(step)
        known.view = step.after
        self._last_effects = ()
        self._set_status(f"Redid {move_to_id(step.move)}.")

    def _commit_known_step(self, move: Move, before: PlayerView, after: PlayerView, status: str) -> None:
        """Record a completed real-world mirror move."""
        known = self._known_session
        if known is None:
            return
        known.view = after
        known.history.append(KnownStep(move=move, before=before, after=after))
        known.redo.clear()
        self._last_effects = ()
        self.query_one("#move-input", Input).value = ""
        self._set_input_placeholder("Move ID or number, e.g., DRAW or 2")
        self._set_status(status)

    def _request_known_advice(self) -> None:
        """Ask the advice provider for a move from player-known state."""
        if self._real_world_prompt is not None:
            self._set_status("Enter the requested card before asking for advice.")
            return
        known = self._known_session
        if known is None:
            self._set_status("Finish real-world setup first.")
            return
        if self.service.advice_provider is None:
            self._set_status("No advice provider configured.")
            return
        advice = self.service.advice_provider.suggest(known.view, limit=SearchLimit(depth_limit=1))
        best_move = advice.best_move
        if best_move is None:
            self._set_status("No advice available.")
            return
        self.query_one("#move-input", Input).value = move_to_id(best_move)
        self._set_status(f"Advice: try {move_to_id(best_move)}.")

    def _write_session(self, path: Path) -> None:
        """Write the current session to ``path``."""
        path.write_text(json.dumps(self.service.export_session(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _set_status(self, message: str) -> None:
        """Set status text and refresh the display."""
        self._status = message
        self._refresh()

    def _set_input_placeholder(self, placeholder: str) -> None:
        """Set the move input placeholder when the input is mounted."""
        self.query_one("#move-input", Input).placeholder = placeholder

    def _refresh(self) -> None:
        """Refresh all dynamic widgets."""
        if self._real_world_setup is not None:
            self.query_one("#board", Static).update(render_real_world_setup(self._real_world_setup))
            self.query_one("#legal-moves", Static).update("Legal moves\n\nFinish setup to see legal moves.")
            self.query_one("#history", Static).update("History\n\nNo moves yet.")
            self.query_one("#status", Static).update(render_status(self._status, self._last_effects))
            return
        if self._known_session is not None:
            self.query_one("#board", Static).update(render_player_view(self._known_session.view))
            self.query_one("#legal-moves", Static).update(render_known_legal_moves(self._known_session.view))
            self.query_one("#history", Static).update(render_known_history(self._known_session))
            self.query_one("#status", Static).update(render_status(self._status, self._last_effects))
            return
        session = self.session
        self.query_one("#board", Static).update(render_board(session))
        self.query_one("#legal-moves", Static).update(render_legal_moves(session))
        self.query_one("#history", Static).update(render_history(session))
        self.query_one("#status", Static).update(render_status(self._status, self._last_effects))


def build_parser() -> argparse.ArgumentParser:
    """Return the TUI argument parser."""
    parser = argparse.ArgumentParser(prog="patiencepilot-tui", description="Play Klondike in a Textual TUI.")
    parser.add_argument("--version", action="version", version=f"patiencepilot-tui {__version__}")
    parser.add_argument("--seed", metavar="VALUE", help="Seed for a reproducible deal.")
    parser.add_argument("--draw-count", type=int, default=1, metavar="N", help="Klondike draw count.")
    parser.add_argument("--redeals", metavar="N|none", help="Klondike redeal limit, or none for unlimited redeals.")
    parser.add_argument("--load", type=Path, metavar="PATH", help="Load a saved session JSON payload.")
    parser.add_argument("--save", type=Path, metavar="PATH", help="Save the session JSON payload from the TUI.")
    parser.add_argument(
        "--real-world",
        action="store_true",
        help="Mirror a physical Klondike game with guided visible-card entry.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the TUI."""
    options = options_from_args(build_parser().parse_args(argv))
    PatiencePilotTui(options).run()
    return 0


def options_from_args(args: argparse.Namespace) -> TuiOptions:
    """Return TUI options from parsed arguments."""
    return TuiOptions(
        seed=_parse_seed(args.seed),
        draw_count=args.draw_count,
        redeals=_parse_redeals(args.redeals),
        load_path=args.load,
        save_path=args.save,
        real_world=args.real_world,
    )


def render_board(session: GameSession) -> str:
    """Return a compact board rendering for the current session."""
    state = session.state
    foundation_text = "  ".join(f"{suit.code}:{_top_or_dash(state.foundation(suit))}" for suit in SUIT_ORDER)
    redeals = "*" if state.redeals_allowed is None else str(state.redeals_allowed)
    stock_line = (
        f"Stock: {len(state.stock):>2}   Waste: {_top_or_dash(state.waste):<2}   "
        f"Redeals: {state.redeals_used}/{redeals}"
    )
    lines = [
        stock_line,
        f"Foundations: {foundation_text}",
        "",
        " ".join(f"T{index}".center(6) for index in range(len(state.tableau))),
    ]
    rows = tuple(_tableau_rows(state.tableau))
    lines.extend(" ".join(card.center(6) for card in row) for row in rows)
    return "\n".join(lines)


def render_real_world_setup(setup: RealWorldSetup) -> str:
    """Return guided setup text for a real-world Klondike mirror."""
    lines = [
        "Real-world mirror setup",
        "",
        "Enter the visible top card for each tableau column.",
        "Hidden cards are tracked as unknown positions.",
        "",
    ]
    for column in range(7):
        value = setup.tableau_cards[column].code if column < len(setup.tableau_cards) else "--"
        lines.append(f"T{column}: {'## ' * column}{value}")
    lines.append("")
    lines.append(f"Progress: {len(setup.tableau_cards)}/7 visible tableau cards")
    return "\n".join(lines)


def render_player_view(view: PlayerView) -> str:
    """Return a compact player-known board rendering."""
    foundation_text = "  ".join(f"{suit.code}:{_top_or_dash(view.foundation(suit))}" for suit in SUIT_ORDER)
    redeals = "*" if view.redeals_allowed is None else str(view.redeals_allowed)
    stock_line = (
        f"Stock: {view.stock_count:>2}   Waste: {_top_or_dash(view.waste):<2}   Redeals: {view.redeals_used}/{redeals}"
    )
    lines = [
        "Real-world mirror",
        stock_line,
        f"Foundations: {foundation_text}",
        f"Unknown cards: {len(view.unknown.unseen_cards)}",
        "",
        " ".join(f"T{index}".center(6) for index in range(len(view.tableau))),
    ]
    rows = tuple(_player_tableau_rows(view.tableau))
    lines.extend(" ".join(card.center(6) for card in row) for row in rows)
    return "\n".join(lines)


def render_known_legal_moves(view: PlayerView) -> str:
    """Return player-visible legal moves formatted for display."""
    moves = visible_klondike_moves(view)
    if not moves:
        return "Legal moves\n\nNo legal moves."
    lines = ["Legal moves", ""]
    for index, move in enumerate(moves, start=1):
        lines.append(f"{index:>2}. {move_to_id(move)}")
    return "\n".join(lines)


def render_known_history(session: KnownGameSession) -> str:
    """Return recent move history for a real-world mirror session."""
    moves = session.move_history[-6:]
    if not moves:
        return "History\n\nNo moves yet."
    return "History\n\n" + "  ".join(move_to_id(move) for move in moves)


def render_legal_moves(session: GameSession) -> str:
    """Return legal moves formatted for display."""
    moves = session.legal_moves()
    if not moves:
        return "Legal moves\n\nNo legal moves."
    lines = ["Legal moves", ""]
    for index, move in enumerate(moves, start=1):
        lines.append(f"{index:>2}. {move_to_id(move)}")
    return "\n".join(lines)


def render_history(session: GameSession) -> str:
    """Return recent move history."""
    moves = session.move_history[-6:]
    if not moves:
        return "History\n\nNo moves yet."
    return "History\n\n" + "  ".join(move_to_id(move) for move in moves)


def render_status(status: str, effects: tuple[MoveEffect, ...]) -> str:
    """Return status and latest effects text."""
    if not effects:
        return status
    return status + "\n" + "\n".join(f"- {_format_effect(effect)}" for effect in effects)


def _move_id_from_input(session: GameSession, text: str) -> str:
    """Return a move ID from either a move ID or displayed list number."""
    move_input = text.strip()
    if not move_input.isdecimal():
        return move_input

    move_number = int(move_input)
    legal_moves = session.legal_moves()
    if 1 <= move_number <= len(legal_moves):
        return move_to_id(legal_moves[move_number - 1])

    msg = f"Move number {move_number} is not in the legal move list."
    raise ValueError(msg)


def _known_move_id_from_input(view: PlayerView, text: str) -> str:
    """Return a move ID from either a move ID or displayed known-move number."""
    move_input = text.strip()
    if not move_input.isdecimal():
        return move_input

    move_number = int(move_input)
    legal_moves = visible_klondike_moves(view)
    if 1 <= move_number <= len(legal_moves):
        return move_to_id(legal_moves[move_number - 1])

    msg = f"Move number {move_number} is not in the legal move list."
    raise ValueError(msg)


def _tableau_rows(tableau: tuple[tuple[StackCard, ...], ...]) -> list[tuple[str, ...]]:
    """Return tableau display rows."""
    height = max((len(column) for column in tableau), default=0)
    rows: list[tuple[str, ...]] = []
    for row_index in range(height):
        row = []
        for column in tableau:
            if row_index >= len(column):
                row.append("")
            else:
                row.append(_stack_card_text(column[row_index]))
        rows.append(tuple(row))
    return rows


def _player_tableau_rows(tableau: tuple[tuple[PlayerStackCard, ...], ...]) -> list[tuple[str, ...]]:
    """Return player-known tableau display rows."""
    height = max((len(column) for column in tableau), default=0)
    rows: list[tuple[str, ...]] = []
    for row_index in range(height):
        row = []
        for column in tableau:
            if row_index >= len(column):
                row.append("")
            else:
                row.append(_player_stack_card_text(column[row_index]))
        rows.append(tuple(row))
    return rows


def _stack_card_text(stack_card: StackCard) -> str:
    """Return display text for a tableau card."""
    return stack_card.card.code if stack_card.face_up else "##"


def _player_stack_card_text(stack_card: PlayerStackCard) -> str:
    """Return display text for a player-known tableau card."""
    card = stack_card.visible_card
    return "##" if card is None else card.code


def _top_or_dash(cards: tuple[Card, ...]) -> str:
    """Return top card text or a placeholder."""
    if not cards:
        return "--"
    return cards[-1].code


def _format_effect(effect: MoveEffect) -> str:
    """Return a readable move effect."""
    if isinstance(effect, (DrewStockCards, MovedCards)):
        cards = " ".join(card.code for card in effect.cards)
        return f"moved {cards}"
    if isinstance(effect, RecycledWaste):
        return f"recycled {effect.count} cards"
    if isinstance(effect, RevealedTableauCard):
        return f"revealed {effect.card.code}"
    return repr(effect)


def _new_real_world_view(cards: Sequence[Card], *, draw_count: int, redeals: int | None) -> PlayerView:
    """Return an initial player-known view from visible tableau cards."""
    if len(cards) != 7:
        msg = "real-world setup requires exactly 7 visible tableau cards"
        raise ValueError(msg)
    _validate_no_duplicate_cards(cards)
    tableau = tuple(
        (*tuple(PlayerStackCard.hidden() for _ in range(column)), PlayerStackCard.visible(card))
        for column, card in enumerate(cards)
    )
    return _replace_player_view(
        PlayerView(
            foundations=_empty_foundations(),
            tableau=tableau,
            waste=(),
            seen_cards=_standard_deck_ordered_unique(cards),
            unknown=UnknownCardConstraints(
                hidden_tableau_counts=tuple(range(7)),
                stock_count=24,
                unseen_cards=tuple(card for card in standard_deck() if card not in set(cards)),
            ),
            draw_count=draw_count,
            redeals_allowed=redeals,
        )
    )


def _apply_known_immediate_move(view: PlayerView, move: Move) -> tuple[PlayerView, int | None]:
    """Apply a non-draw move to player-known state."""
    if isinstance(move, RecycleWaste):
        return (
            _replace_player_view(
                view,
                stock_count=len(view.waste),
                waste=(),
                redeals_used=view.redeals_used + 1,
            ),
            None,
        )
    if isinstance(move, WasteToFoundation):
        card = view.waste[-1]
        foundations = _with_foundation_card(view.foundations, card)
        return _replace_player_view(view, foundations=foundations, waste=view.waste[:-1]), None
    if isinstance(move, WasteToTableau):
        card = view.waste[-1]
        tableau = [list(column) for column in view.tableau]
        tableau[move.destination].append(PlayerStackCard.visible(card))
        return _replace_player_view(view, tableau=_freeze_player_tableau(tableau), waste=view.waste[:-1]), None
    if isinstance(move, TableauToFoundation):
        tableau = [list(column) for column in view.tableau]
        card = _require_visible_top(tableau[move.source], move_to_id(move))
        tableau[move.source].pop()
        foundations = _with_foundation_card(view.foundations, card)
        frozen_tableau = _freeze_player_tableau(tableau)
        return _replace_player_view(view, foundations=foundations, tableau=frozen_tableau), _pending_reveal_column(
            frozen_tableau,
            move.source,
        )
    if isinstance(move, TableauToTableau):
        tableau = [list(column) for column in view.tableau]
        moving = tableau[move.source][-move.count :]
        tableau[move.source] = tableau[move.source][: -move.count]
        tableau[move.destination].extend(moving)
        frozen_tableau = _freeze_player_tableau(tableau)
        return _replace_player_view(view, tableau=frozen_tableau), _pending_reveal_column(frozen_tableau, move.source)

    msg = f"{move_to_id(move)} requires newly visible card input."
    raise ValueError(msg)


def _reveal_pending_tableau_card(view: PlayerView, move: Move, card: Card) -> PlayerView:
    """Reveal the top hidden tableau card exposed by ``move``."""
    source = _source_column_for_reveal(move)
    tableau = [list(column) for column in view.tableau]
    if source is None or not tableau[source] or tableau[source][-1].face_up:
        msg = "no hidden tableau card is waiting to be revealed"
        raise ValueError(msg)
    tableau[source][-1] = PlayerStackCard.visible(card)
    return _replace_player_view(view, tableau=_freeze_player_tableau(tableau), extra_seen=(card,))


def _replace_player_view(
    view: PlayerView,
    *,
    foundations: tuple[tuple[Card, ...], ...] | None = None,
    tableau: tuple[tuple[PlayerStackCard, ...], ...] | None = None,
    waste: tuple[Card, ...] | None = None,
    stock_count: int | None = None,
    redeals_used: int | None = None,
    extra_seen: Sequence[Card] = (),
) -> PlayerView:
    """Return ``view`` with updated parts and recomputed unknown constraints."""
    next_foundations = view.foundations if foundations is None else foundations
    next_tableau = view.tableau if tableau is None else tableau
    next_waste = view.waste if waste is None else waste
    next_stock_count = view.stock_count if stock_count is None else stock_count
    next_redeals_used = view.redeals_used if redeals_used is None else redeals_used
    seen_cards = _standard_deck_ordered_unique(
        (*view.seen_cards, *_visible_cards(next_foundations, next_tableau, next_waste), *extra_seen)
    )
    seen_set = set(seen_cards)
    return PlayerView(
        foundations=next_foundations,
        tableau=next_tableau,
        waste=next_waste,
        seen_cards=seen_cards,
        unknown=UnknownCardConstraints(
            hidden_tableau_counts=tuple(
                sum(1 for stack_card in column if not stack_card.face_up) for column in next_tableau
            ),
            stock_count=next_stock_count,
            unseen_cards=tuple(card for card in standard_deck() if card not in seen_set),
        ),
        variant=view.variant,
        draw_count=view.draw_count,
        redeals_allowed=view.redeals_allowed,
        redeals_used=next_redeals_used,
    )


def _empty_foundations() -> tuple[tuple[Card, ...], ...]:
    """Return empty foundation stacks."""
    return cast("tuple[tuple[Card, ...], ...]", tuple(() for _ in SUIT_ORDER))


def _with_foundation_card(foundations: tuple[tuple[Card, ...], ...], card: Card) -> tuple[tuple[Card, ...], ...]:
    """Return foundations with ``card`` appended to its suit stack."""
    foundation_list = [list(foundation) for foundation in foundations]
    foundation_list[SUIT_ORDER.index(card.suit)].append(card)
    return tuple(tuple(foundation) for foundation in foundation_list)


def _freeze_player_tableau(tableau: Sequence[Sequence[PlayerStackCard]]) -> tuple[tuple[PlayerStackCard, ...], ...]:
    """Return an immutable tableau from nested player stack-card sequences."""
    return tuple(tuple(column) for column in tableau)


def _require_visible_top(column: Sequence[PlayerStackCard], move_id: str) -> Card:
    """Return the top visible card or raise a validation error."""
    if not column:
        msg = f"{move_id} has no source card"
        raise ValueError(msg)
    card = column[-1].visible_card
    if card is None:
        msg = f"{move_id} source card is not visible"
        raise ValueError(msg)
    return card


def _pending_reveal_column(tableau: tuple[tuple[PlayerStackCard, ...], ...], source: int) -> int | None:
    """Return the source column if a hidden top card must be revealed."""
    if tableau[source] and not tableau[source][-1].face_up:
        return source
    return None


def _source_column_for_reveal(move: Move) -> int | None:
    """Return the tableau source column for moves that may reveal a card."""
    if isinstance(move, (TableauToFoundation, TableauToTableau)):
        return move.source
    return None


def _visible_cards(
    foundations: tuple[tuple[Card, ...], ...],
    tableau: tuple[tuple[PlayerStackCard, ...], ...],
    waste: tuple[Card, ...],
) -> tuple[Card, ...]:
    """Return all currently visible cards in a player-known state."""
    cards: list[Card] = []
    for foundation in foundations:
        cards.extend(foundation)
    for column in tableau:
        cards.extend(card for stack_card in column if (card := stack_card.visible_card) is not None)
    cards.extend(waste)
    return tuple(cards)


def _standard_deck_ordered_unique(cards: Sequence[Card]) -> tuple[Card, ...]:
    """Return unique cards in standard deck order."""
    card_set = set(cards)
    return tuple(card for card in standard_deck() if card in card_set)


def _parse_one_card(text: str) -> Card:
    """Parse exactly one card code from user input."""
    cards = _parse_card_list(text)
    if len(cards) != 1:
        msg = "Enter exactly one card code."
        raise ValueError(msg)
    return cards[0]


def _parse_card_list(text: str) -> tuple[Card, ...]:
    """Parse one or more whitespace- or comma-separated card codes."""
    parts = tuple(part for part in text.replace(",", " ").split() if part)
    if not parts:
        msg = "Enter at least one card code."
        raise ValueError(msg)
    try:
        return tuple(Card.from_code(part) for part in parts)
    except ValueError as error:
        msg = f"invalid card code: {error}"
        raise ValueError(msg) from error


def _validate_no_duplicate_cards(cards: Sequence[Card]) -> None:
    """Raise when ``cards`` contains a duplicate card."""
    seen: set[Card] = set()
    for card in cards:
        if card in seen:
            msg = f"card {card.code} is already visible."
            raise ValueError(msg)
        seen.add(card)


def _validate_new_visible_cards(cards: Sequence[Card], view: PlayerView) -> None:
    """Validate newly visible cards do not duplicate visible cards."""
    _validate_no_duplicate_cards(cards)
    visible = set(view.iter_visible_cards())
    for card in cards:
        if card in visible:
            msg = f"card {card.code} is already visible."
            raise ValueError(msg)


def _validate_revealed_tableau_card(card: Card, view: PlayerView) -> None:
    """Validate a newly revealed tableau card is still possible."""
    _validate_new_visible_cards((card,), view)
    if card not in set(view.unknown.unseen_cards):
        msg = f"card {card.code} has already been seen and cannot be hidden in the tableau."
        raise ValueError(msg)


def _draw_prompt_message(count: int) -> str:
    """Return draw prompt text for ``count`` newly visible cards."""
    if count == 1:
        return "Enter the drawn card."
    return f"Enter the {count} drawn cards from buried to topmost."


def _draw_input_placeholder(count: int) -> str:
    """Return draw input placeholder text."""
    if count == 1:
        return "Drawn card, e.g. 9S"
    return f"{count} drawn cards, e.g. 4D JS 9S"


def _read_json_object(path: Path) -> dict[str, object]:
    """Read a JSON object from ``path``."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = "session payload must be a JSON object"
        raise ValueError(msg)
    return data


def _parse_seed(text: str | None) -> Seed:
    """Return a seed from CLI text."""
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return text


def _parse_redeals(text: str | None) -> int | None:
    """Return a redeal limit from CLI text."""
    if text is None or text.casefold() in {"none", "null", "*"}:
        return None
    return int(text)


__all__ = [
    "PatiencePilotTui",
    "TuiOptions",
    "build_parser",
    "main",
    "options_from_args",
    "render_board",
    "render_history",
    "render_legal_moves",
    "render_status",
]
