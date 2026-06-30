"""Textual terminal user interface."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Static

from patiencepilot import __version__
from patiencepilot.app import PatiencePilotApp
from patiencepilot.cards import Card
from patiencepilot.exceptions import PatiencePilotError
from patiencepilot.game import GameSession
from patiencepilot.moves import DrewStockCards, MovedCards, MoveEffect, RecycledWaste, RevealedTableauCard
from patiencepilot.notation import move_from_id, move_to_id
from patiencepilot.solvers import SearchLimit
from patiencepilot.state import SUIT_ORDER, StackCard
from patiencepilot.variants.base import Seed


@dataclass(frozen=True, slots=True)
class TuiOptions:
    """Configuration for launching the TUI."""

    seed: Seed = None
    draw_count: int = 1
    redeals: int | None = None
    load_path: Path | None = None
    save_path: Path | None = None


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
        width: 2fr;
        min-width: 58;
        padding: 1 2;
        border: round #2f81f7;
        background: #111827;
    }

    #side-panel {
        width: 34;
        min-width: 30;
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
        margin: 1 0;
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
        min-width: 9;
        margin: 0 1 1 0;
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
        self._last_effects: tuple[MoveEffect, ...] = ()
        self._status = "Ready."

    def compose(self) -> ComposeResult:
        """Compose the terminal layout."""
        yield Header(show_clock=True)
        with Horizontal(id="layout"):
            with Vertical(id="board-panel"):
                yield Static("Patience Pilot", classes="panel-title")
                yield Static("", id="board")
            with Vertical(id="side-panel"):
                yield Static("Controls", classes="panel-title")
                with Container(id="buttons"):
                    yield Button("Apply", id="apply", variant="success", classes="primary")
                    yield Button("Draw", id="draw")
                    yield Button("Undo", id="undo")
                    yield Button("Redo", id="redo")
                    yield Button("New", id="new", variant="primary")
                    yield Button("Save", id="save")
                    yield Button("Load", id="load")
                    yield Button("Advice", id="advice", classes="warning")
                yield Input(placeholder="Move ID, e.g. DRAW", id="move-input")
                yield Static("", id="legal-moves")
                yield Static("", id="history")
                yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        """Start or load a game when the TUI mounts."""
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
        legal_ids = tuple(move_to_id(move) for move in self.session.legal_moves())
        if "DRAW" in legal_ids:
            self._apply_move_id("DRAW")
        elif "RECYCLE" in legal_ids:
            self._apply_move_id("RECYCLE")
        else:
            self._set_status("No draw or recycle move is currently legal.")

    def action_undo(self) -> None:
        """Undo the latest move."""
        try:
            step = self.session.undo()
        except PatiencePilotError as error:
            self._set_status(str(error))
            return
        self._last_effects = ()
        self._set_status(f"Undid {move_to_id(step.move)}.")

    def action_redo(self) -> None:
        """Redo the latest undone move."""
        try:
            result = self.session.redo()
        except PatiencePilotError as error:
            self._set_status(str(error))
            return
        self._last_effects = result.effects
        self._set_status(f"Redid {move_to_id(result.move)}.")

    def action_new_game(self) -> None:
        """Start a new game."""
        self._start_new_session()
        self._last_effects = ()
        self._set_status("Started a new game.")

    def action_save(self) -> None:
        """Save the active session."""
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

    def _apply_entered_move(self) -> None:
        """Apply the current move input value."""
        move_id = self.query_one("#move-input", Input).value.strip()
        if not move_id:
            self._set_status("Enter a move ID first.")
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

    def _write_session(self, path: Path) -> None:
        """Write the current session to ``path``."""
        path.write_text(json.dumps(self.service.export_session(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _set_status(self, message: str) -> None:
        """Set status text and refresh the display."""
        self._status = message
        self._refresh()

    def _refresh(self) -> None:
        """Refresh all dynamic widgets."""
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


def _stack_card_text(stack_card: StackCard) -> str:
    """Return display text for a tableau card."""
    return stack_card.card.code if stack_card.face_up else "##"


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
