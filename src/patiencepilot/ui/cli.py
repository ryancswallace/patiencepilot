"""Basic command line text interface."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO, cast

from patiencepilot import __version__
from patiencepilot.app import PatiencePilotApp
from patiencepilot.exceptions import PatiencePilotError
from patiencepilot.game import GameSession
from patiencepilot.moves import DrewStockCards, MovedCards, MoveEffect, RecycledWaste, RevealedTableauCard
from patiencepilot.notation import move_from_id, move_to_id, state_from_text, state_to_text
from patiencepilot.solvers import Advice, SearchLimit
from patiencepilot.variants.base import Seed


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line interface."""
    return run(argv)


def run(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the command line interface with injectable streams.

    Args:
        argv: Command line arguments without the executable name. Uses
            ``sys.argv`` when omitted.
        stdin: Input stream for state notation when ``--state -`` is used.
        stdout: Output stream for command results.
        stderr: Error and status stream.
    """
    input_stream = sys.stdin if stdin is None else stdin
    output_stream = sys.stdout if stdout is None else stdout
    error_stream = sys.stderr if stderr is None else stderr

    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return _dispatch(args, input_stream, output_stream, error_stream)
    except (PatiencePilotError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"patiencepilot-cli: {error}", file=error_stream)
        return 2


def build_parser() -> argparse.ArgumentParser:
    """Return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="patiencepilot-cli",
        description="Play and inspect Solitaire games from the command line.",
    )
    parser.add_argument("--version", action="version", version=f"patiencepilot-cli {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new", help="Deal a new game.")
    _add_variant_args(new_parser)
    new_parser.add_argument("--seed", metavar="VALUE", help="Seed for a reproducible deal.")
    _add_save_arg(new_parser)

    show_parser = subparsers.add_parser("show", help="Display the current state.")
    _add_source_args(show_parser)

    validate_parser = subparsers.add_parser("validate", help="Validate a saved session or state notation.")
    _add_source_args(validate_parser)

    moves_parser = subparsers.add_parser("moves", help="List legal moves.")
    _add_source_args(moves_parser)

    apply_parser = subparsers.add_parser("apply", help="Apply a move ID.")
    _add_source_args(apply_parser)
    apply_parser.add_argument("move", metavar="MOVE_ID", help="Move ID such as DRAW, W->F, or T0->T3:2.")
    _add_save_arg(apply_parser)

    undo_parser = subparsers.add_parser("undo", help="Undo the most recent saved-session move.")
    _add_source_args(undo_parser)
    _add_save_arg(undo_parser)

    advice_parser = subparsers.add_parser("advice", help="Ask the configured advice provider for a move.")
    _add_source_args(advice_parser)
    advice_parser.add_argument("--solver", default="dummy", metavar="NAME", help="Registered solver name or alias.")
    advice_parser.add_argument("--time-limit", type=float, metavar="SECONDS", help="Optional solver time limit.")
    advice_parser.add_argument("--node-limit", type=int, metavar="NODES", help="Optional solver node limit.")
    advice_parser.add_argument("--depth-limit", type=int, metavar="DEPTH", help="Optional solver depth limit.")

    return parser


def _dispatch(args: argparse.Namespace, stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
    """Dispatch parsed arguments to a command implementation."""
    command = cast("str", args.command)
    if command == "new":
        return _command_new(args, stdout, stderr)
    if command == "show":
        return _command_show(args, stdin, stdout)
    if command == "validate":
        return _command_validate(args, stdin, stdout)
    if command == "moves":
        return _command_moves(args, stdin, stdout)
    if command == "apply":
        return _command_apply(args, stdin, stdout, stderr)
    if command == "undo":
        return _command_undo(args, stdin, stdout, stderr)
    if command == "advice":
        return _command_advice(args, stdin, stdout)

    msg = f"unsupported command: {command}"
    raise ValueError(msg)


def _command_new(args: argparse.Namespace, stdout: TextIO, stderr: TextIO) -> int:
    """Deal, optionally save, and display a new session."""
    app = PatiencePilotApp()
    app.select_variant(_str_arg(args, "variant"), _variant_options_from_args(args))
    app.new_session(seed=_parse_seed(_optional_str_arg(args, "seed")))
    _save_if_requested(app, _optional_str_arg(args, "save"), stderr)
    _print_state(_require_session(app), stdout)
    return 0


def _command_show(args: argparse.Namespace, stdin: TextIO, stdout: TextIO) -> int:
    """Display a loaded session or entered state."""
    app = _load_app(args, stdin)
    _print_state(_require_session(app), stdout)
    return 0


def _command_validate(args: argparse.Namespace, stdin: TextIO, stdout: TextIO) -> int:
    """Validate a loaded session or entered state."""
    _load_app(args, stdin)
    print("OK", file=stdout)
    return 0


def _command_moves(args: argparse.Namespace, stdin: TextIO, stdout: TextIO) -> int:
    """List legal move IDs."""
    app = _load_app(args, stdin)
    moves = _require_session(app).legal_moves()
    if not moves:
        print("No legal moves.", file=stdout)
        return 0

    print("Legal moves:", file=stdout)
    for move in moves:
        print(move_to_id(move), file=stdout)
    return 0


def _command_apply(args: argparse.Namespace, stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
    """Apply a move to a loaded session or entered state."""
    app = _load_app(args, stdin)
    move = move_from_id(_str_arg(args, "move"))
    result = app.apply_move(move)
    _save_if_requested(app, _optional_str_arg(args, "save"), stderr)
    print(f"Applied {move_to_id(result.move)}", file=stdout)
    _print_effects(result.effects, stdout)
    print(file=stdout)
    _print_state(_require_session(app), stdout)
    return 0


def _command_undo(args: argparse.Namespace, stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
    """Undo the latest move from a loaded session."""
    if _optional_str_arg(args, "state") is not None:
        msg = "undo requires a saved session loaded with --load"
        raise ValueError(msg)

    app = _load_app(args, stdin)
    session = _require_session(app)
    move = session.move_history[-1] if session.move_history else None
    app.undo()
    _save_if_requested(app, _optional_str_arg(args, "save"), stderr)
    print(f"Undid {move_to_id(move)}" if move is not None else "Undid last move.", file=stdout)
    print(file=stdout)
    _print_state(_require_session(app), stdout)
    return 0


def _command_advice(args: argparse.Namespace, stdin: TextIO, stdout: TextIO) -> int:
    """Ask the configured advice provider for move advice."""
    app = _load_app(args, stdin)
    app.select_solver(_str_arg(args, "solver"))
    advice = app.request_advice(limit=_search_limit_from_args(args))
    _print_advice(advice, stdout)
    return 0


def _load_app(args: argparse.Namespace, stdin: TextIO) -> PatiencePilotApp:
    """Return an app containing a session from CLI source arguments."""
    app = PatiencePilotApp()
    load_path = _optional_str_arg(args, "load")
    state_path = _optional_str_arg(args, "state")
    if load_path is not None:
        app.import_session(_read_json_object(load_path))
        return app
    if state_path is not None:
        app.use_session(GameSession(state=state_from_text(_read_state_text(state_path, stdin))))
        return app

    msg = "provide --load or --state"
    raise ValueError(msg)


def _add_variant_args(parser: argparse.ArgumentParser) -> None:
    """Add variant selection arguments."""
    parser.add_argument("--variant", default="klondike", help="Registered variant name.")
    parser.add_argument("--draw-count", type=int, metavar="N", help="Klondike draw count.")
    parser.add_argument("--redeals", metavar="N|none", help="Klondike redeal limit, or none for unlimited redeals.")
    parser.add_argument(
        "--option",
        action="append",
        default=None,
        metavar="KEY=VALUE",
        help="Variant option. Values accept integers, true, false, none, null, or strings.",
    )


def _add_source_args(parser: argparse.ArgumentParser) -> None:
    """Add mutually exclusive session/state source arguments."""
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--load", metavar="PATH", help="Load a saved session JSON payload.")
    source.add_argument("--state", metavar="PATH", help="Read canonical state notation from PATH, or '-' for stdin.")


def _add_save_arg(parser: argparse.ArgumentParser) -> None:
    """Add a save destination argument."""
    parser.add_argument("--save", metavar="PATH", help="Write the resulting session JSON payload.")


def _variant_options_from_args(args: argparse.Namespace) -> dict[str, object]:
    """Return variant options from CLI arguments."""
    options = dict(_parse_option(item) for item in _option_args(args))
    draw_count = _optional_int_arg(args, "draw_count")
    redeals = _optional_str_arg(args, "redeals")
    if draw_count is not None:
        options["draw_count"] = draw_count
    if redeals is not None:
        options["redeals"] = _parse_redeals(redeals)
    return options


def _option_args(args: argparse.Namespace) -> tuple[str, ...]:
    """Return repeated ``--option`` values."""
    value = getattr(args, "option", ())
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return ()


def _parse_option(text: str) -> tuple[str, object]:
    """Return a variant option key-value pair."""
    key, separator, value = text.partition("=")
    if not separator or not key:
        msg = f"option must be KEY=VALUE: {text!r}"
        raise ValueError(msg)
    return key, _parse_scalar(value)


def _parse_redeals(text: str) -> int | None:
    """Return a redeal option from CLI text."""
    value = _parse_scalar(text)
    if value is None:
        return None
    if type(value) is int:
        return value
    msg = "--redeals must be an integer or none"
    raise ValueError(msg)


def _parse_scalar(text: str) -> object:
    """Parse a small JSON-like scalar from CLI text."""
    normalized = text.strip()
    lowered = normalized.lower()
    if lowered in {"none", "null"}:
        return None
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(normalized)
    except ValueError:
        return normalized


def _parse_seed(text: str | None) -> Seed:
    """Return a random seed from CLI text."""
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return text


def _search_limit_from_args(args: argparse.Namespace) -> SearchLimit | None:
    """Return solver search limits from CLI arguments."""
    time_limit = _optional_float_arg(args, "time_limit")
    node_limit = _optional_int_arg(args, "node_limit")
    depth_limit = _optional_int_arg(args, "depth_limit")
    if time_limit is None and node_limit is None and depth_limit is None:
        return None
    return SearchLimit(time_seconds=time_limit, node_limit=node_limit, depth_limit=depth_limit)


def _read_json_object(path_text: str) -> Mapping[str, object]:
    """Read a JSON object from ``path_text``."""
    data = json.loads(Path(path_text).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = "session payload must be a JSON object"
        raise ValueError(msg)
    return cast("Mapping[str, object]", data)


def _read_state_text(path_text: str, stdin: TextIO) -> str:
    """Read state notation from a path or stdin."""
    if path_text == "-":
        return stdin.read()
    return Path(path_text).read_text(encoding="utf-8")


def _save_if_requested(app: PatiencePilotApp, path_text: str | None, stderr: TextIO) -> None:
    """Save the current session when a destination is provided."""
    if path_text is None:
        return
    payload = app.export_session()
    Path(path_text).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Saved session to {path_text}", file=stderr)


def _print_state(session: GameSession, stdout: TextIO) -> None:
    """Print canonical state notation for a session."""
    print(state_to_text(session.state), file=stdout)


def _print_effects(effects: tuple[MoveEffect, ...], stdout: TextIO) -> None:
    """Print move-result effects."""
    if not effects:
        return
    print("Effects:", file=stdout)
    for effect in effects:
        print(f"- {_format_effect(effect)}", file=stdout)


def _print_advice(advice: Advice, stdout: TextIO) -> None:
    """Print solver advice."""
    if not advice.recommendations:
        print("No moves recommended.", file=stdout)
        return

    print("Advice:", file=stdout)
    for recommendation in advice.recommendations:
        details = _advice_details(recommendation.score, recommendation.confidence)
        suffix = "" if not details else f" ({', '.join(details)})"
        print(f"{recommendation.rank}. {move_to_id(recommendation.move)}{suffix}", file=stdout)
        if recommendation.reason is not None:
            print(f"   {recommendation.reason}", file=stdout)


def _advice_details(score: float | None, confidence: float | None) -> list[str]:
    """Return printable advice metadata."""
    details: list[str] = []
    if score is not None:
        details.append(f"score={score:g}")
    if confidence is not None:
        details.append(f"confidence={confidence:g}")
    return details


def _format_effect(effect: MoveEffect) -> str:
    """Return a readable move-effect description."""
    if isinstance(effect, DrewStockCards):
        return f"drew {_format_cards(effect.cards)}"
    if isinstance(effect, MovedCards):
        return f"moved {_format_cards(effect.cards)} from {effect.source} to {effect.destination}"
    if isinstance(effect, RecycledWaste):
        return f"recycled {effect.count} waste card(s)"
    if isinstance(effect, RevealedTableauCard):
        return f"revealed {effect.card.code} in T{effect.column}"
    return repr(effect)


def _format_cards(cards: tuple[object, ...]) -> str:
    """Return compact card text."""
    return " ".join(str(card) for card in cards) if cards else "(none)"


def _require_session(app: PatiencePilotApp) -> GameSession:
    """Return the active app session."""
    if app.session is None:
        msg = "no active session"
        raise ValueError(msg)
    return app.session


def _str_arg(args: argparse.Namespace, name: str) -> str:
    """Return a required string argument."""
    value = getattr(args, name)
    if not isinstance(value, str):
        msg = f"{name} must be a string"
        raise ValueError(msg)
    return value


def _optional_str_arg(args: argparse.Namespace, name: str) -> str | None:
    """Return an optional string argument."""
    value = getattr(args, name, None)
    if value is None or isinstance(value, str):
        return value
    msg = f"{name} must be a string"
    raise ValueError(msg)


def _optional_int_arg(args: argparse.Namespace, name: str) -> int | None:
    """Return an optional integer argument."""
    value = getattr(args, name, None)
    if value is None or type(value) is int:
        return value
    msg = f"{name} must be an integer"
    raise ValueError(msg)


def _optional_float_arg(args: argparse.Namespace, name: str) -> float | None:
    """Return an optional float argument."""
    value = getattr(args, name, None)
    if value is None or isinstance(value, float):
        return value
    msg = f"{name} must be a number"
    raise ValueError(msg)


__all__ = ["build_parser", "main", "run"]
