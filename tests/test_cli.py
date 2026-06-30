"""Tests for the command line text interface."""

from __future__ import annotations

import json
import tomllib
from argparse import Namespace
from collections.abc import Callable
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

import patiencepilot.cli as cli_entry
import patiencepilot.ui.cli as cli
from patiencepilot import (
    Advice,
    Card,
    DrawFromStock,
    DrewStockCards,
    GameSession,
    GameState,
    MovedCards,
    Rank,
    RankedMove,
    RecycledWaste,
    RevealedTableauCard,
    StackCard,
    Suit,
    deserialize_move,
    state_to_text,
)
from patiencepilot.ui.cli import run

pytestmark = pytest.mark.unit


def test_cli_packaging_declares_script_and_optional_ui_extras() -> None:
    config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]

    assert project["scripts"]["patiencepilot-cli"] == "patiencepilot.cli:main"
    assert project["scripts"]["patp-cli"] == "patiencepilot.cli:main"
    assert "patiencepilot" not in project["scripts"]
    assert project["optional-dependencies"]["cli"] == []
    assert project["optional-dependencies"]["webui"] == []


def test_cli_new_saves_session_and_prints_state(tmp_path: Path) -> None:
    save_path = tmp_path / "game.json"
    stdout = StringIO()
    stderr = StringIO()

    code = run(
        ["new", "--seed", "7", "--draw-count", "3", "--redeals", "1", "--save", str(save_path)],
        stdout=stdout,
        stderr=stderr,
    )

    payload = _read_json(save_path)

    assert code == 0
    assert payload["seed"] == 7
    assert payload["options"] == {"draw_count": 3, "redeals": 1}
    assert "VARIANT klondike draw_count=3 redeals=1 redeals_used=0" in stdout.getvalue()
    assert f"Saved session to {save_path}" in stderr.getvalue()


def test_cli_entry_point_main_displays_state_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    state_path = tmp_path / "state.txt"
    state_path.write_text(state_to_text(GameSession.new(seed=7).state), encoding="utf-8")

    code = cli_entry.main(["show", "--state", str(state_path)])

    captured = capsys.readouterr()
    assert code == 0
    assert "VARIANT klondike" in captured.out


def test_cli_show_and_validate_saved_session(tmp_path: Path) -> None:
    save_path = tmp_path / "game.json"
    run(["new", "--seed", "8", "--save", str(save_path)])
    show_stdout = StringIO()
    validate_stdout = StringIO()

    show_code = run(["show", "--load", str(save_path)], stdout=show_stdout)
    validate_code = run(["validate", "--load", str(save_path)], stdout=validate_stdout)

    assert show_code == 0
    assert "VARIANT klondike" in show_stdout.getvalue()
    assert validate_code == 0
    assert validate_stdout.getvalue() == "OK\n"


def test_cli_lists_and_applies_moves_from_saved_session(tmp_path: Path) -> None:
    save_path = tmp_path / "game.json"
    run(["new", "--seed", "8", "--save", str(save_path)])
    moves_stdout = StringIO()
    apply_stdout = StringIO()

    moves_code = run(["moves", "--load", str(save_path)], stdout=moves_stdout)
    apply_code = run(["apply", "--load", str(save_path), "--save", str(save_path), "DRAW"], stdout=apply_stdout)
    payload = _read_json(save_path)

    assert moves_code == 0
    assert "Legal moves:\nDRAW\n" in moves_stdout.getvalue()
    assert apply_code == 0
    assert "Applied DRAW" in apply_stdout.getvalue()
    assert payload["history"] == [{"id": "DRAW"}]
    assert deserialize_move(payload["history"][0]) == DrawFromStock()


def test_cli_apply_without_save_leaves_saved_session_unchanged(tmp_path: Path) -> None:
    save_path = tmp_path / "game.json"
    run(["new", "--seed", "8", "--save", str(save_path)])
    before = _read_json(save_path)

    code = run(["apply", "--load", str(save_path), "DRAW"])

    assert code == 0
    assert _read_json(save_path) == before


def test_cli_undo_uses_saved_session_history(tmp_path: Path) -> None:
    save_path = tmp_path / "game.json"
    run(["new", "--seed", "9", "--save", str(save_path)])
    run(["apply", "--load", str(save_path), "--save", str(save_path), "DRAW"])
    stdout = StringIO()

    code = run(["undo", "--load", str(save_path), "--save", str(save_path)], stdout=stdout)
    payload = _read_json(save_path)

    assert code == 0
    assert "Undid DRAW" in stdout.getvalue()
    assert payload["history"] == []
    assert payload["redo"] == [{"id": "DRAW"}]


def test_cli_undo_rejects_raw_state_notation() -> None:
    stderr = StringIO()

    code = run(["undo", "--state", "-"], stdin=StringIO(state_to_text(GameSession.new(seed=9).state)), stderr=stderr)

    assert code == 2
    assert "undo requires a saved session" in stderr.getvalue()


def test_cli_accepts_state_notation_from_stdin() -> None:
    state_text = state_to_text(GameSession.new(seed=10).state)
    stdout = StringIO()

    code = run(["moves", "--state", "-"], stdin=StringIO(state_text), stdout=stdout)

    assert code == 0
    assert "DRAW" in stdout.getvalue()


def test_cli_reports_no_legal_moves_for_won_state() -> None:
    complete_foundations = tuple(tuple(Card(rank=rank, suit=suit) for rank in Rank) for suit in Suit)
    state = GameState(foundations=complete_foundations, tableau=((), (), (), (), (), (), ()), stock=(), waste=())
    stdout = StringIO()

    code = run(["moves", "--state", "-"], stdin=StringIO(state_to_text(state)), stdout=stdout)

    assert code == 0
    assert stdout.getvalue() == "No legal moves.\n"


def test_cli_validate_reports_ok_for_state_file(tmp_path: Path) -> None:
    state_path = tmp_path / "state.txt"
    state_path.write_text(state_to_text(GameSession.new(seed=11).state), encoding="utf-8")
    stdout = StringIO()

    code = run(["validate", "--state", str(state_path)], stdout=stdout)

    assert code == 0
    assert stdout.getvalue() == "OK\n"


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["new", "--option", "broken"], "option must be KEY=VALUE"),
        (["new", "--redeals", "many"], "--redeals must be an integer or none"),
        (["show", "--load", "missing.json"], "No such file"),
    ],
)
def test_cli_reports_command_errors(argv: list[str], message: str) -> None:
    stderr = StringIO()

    code = run(argv, stderr=stderr)

    assert code == 2
    assert message in stderr.getvalue()


def test_cli_advice_command_is_wired_to_provider_boundary(tmp_path: Path) -> None:
    save_path = tmp_path / "game.json"
    run(["new", "--seed", "12", "--save", str(save_path)])
    stdout = StringIO()

    code = run(["advice", "--load", str(save_path), "--depth-limit", "1"], stdout=stdout)

    assert code == 0
    assert stdout.getvalue() == "Advice:\n1. DRAW\n"


def test_cli_advice_accepts_all_search_limit_options(tmp_path: Path) -> None:
    save_path = tmp_path / "game.json"
    run(["new", "--seed", "12", "--save", str(save_path)])
    stdout = StringIO()

    code = run(
        ["advice", "--load", str(save_path), "--time-limit", "0.1", "--node-limit", "10", "--depth-limit", "2"],
        stdout=stdout,
    )

    assert code == 0
    assert stdout.getvalue() == "Advice:\n1. DRAW\n"


def test_cli_rejects_non_object_session_json(tmp_path: Path) -> None:
    session_path = tmp_path / "game.json"
    session_path.write_text("[]", encoding="utf-8")
    stderr = StringIO()

    code = run(["show", "--load", str(session_path)], stderr=stderr)

    assert code == 2
    assert "session payload must be a JSON object" in stderr.getvalue()


def test_cli_dispatch_rejects_unknown_internal_command() -> None:
    with pytest.raises(ValueError, match="unsupported command"):
        cli._dispatch(Namespace(command="missing"), StringIO(), StringIO(), StringIO())


def test_cli_load_app_requires_a_source_argument() -> None:
    with pytest.raises(ValueError, match="provide --load or --state"):
        cli._load_app(Namespace(), StringIO())


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("none", None),
        ("null", None),
        ("true", True),
        ("false", False),
        ("42", 42),
        ("plain", "plain"),
    ],
)
def test_cli_scalar_parser_handles_json_like_values(text: str, expected: object) -> None:
    assert cli._parse_scalar(text) == expected


def test_cli_variant_options_accept_repeated_key_value_options() -> None:
    args = Namespace(option=["draw_count=3", "redeals=none"], draw_count=None, redeals=None)

    assert cli._variant_options_from_args(args) == {"draw_count": 3, "redeals": None}


def test_cli_formats_effects_and_advice_for_display() -> None:
    stdout = StringIO()
    advice_stdout = StringIO()

    cli._print_effects(
        (
            DrewStockCards(cards=(Card.from_code("AS"),)),
            MovedCards(cards=(Card.from_code("KH"),), source="waste", destination="tableau[0]"),
            RecycledWaste(count=3),
            RevealedTableauCard(column=1, card=Card.from_code("2C")),
        ),
        stdout,
    )
    cli._print_advice(
        Advice(
            recommendations=(
                RankedMove(
                    move=DrawFromStock(),
                    rank=1,
                    score=2.5,
                    confidence=0.75,
                    reason="Open a new waste card.",
                ),
            ),
        ),
        advice_stdout,
    )

    assert "drew AS" in stdout.getvalue()
    assert "moved KH from waste to tableau[0]" in stdout.getvalue()
    assert "recycled 3 waste card(s)" in stdout.getvalue()
    assert "revealed 2C in T1" in stdout.getvalue()
    assert "1. DRAW (score=2.5, confidence=0.75)" in advice_stdout.getvalue()
    assert "Open a new waste card." in advice_stdout.getvalue()


def test_cli_formats_empty_advice_and_empty_card_lists() -> None:
    stdout = StringIO()

    cli._print_advice(Advice(recommendations=()), stdout)

    assert stdout.getvalue() == "No moves recommended.\n"
    assert cli._format_cards(()) == "(none)"


@pytest.mark.parametrize(
    ("args", "helper", "message"),
    [
        (Namespace(move=3), cli._str_arg, "move must be a string"),
        (Namespace(load=3), cli._optional_str_arg, "load must be a string"),
        (Namespace(node_limit="3"), cli._optional_int_arg, "node_limit must be an integer"),
        (Namespace(time_limit="3"), cli._optional_float_arg, "time_limit must be a number"),
    ],
)
def test_cli_argument_helpers_reject_unexpected_types(
    args: Namespace,
    helper: Callable[[Namespace, str], object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        helper(args, next(iter(vars(args))))


def test_cli_can_represent_hidden_tableau_destinations_without_moves() -> None:
    state = GameState(
        foundations=((), (), (), ()),
        tableau=((StackCard.hidden(Card.from_code("QS")),), (), (), (), (), (), ()),
        stock=(),
        waste=(Card.from_code("KH"),),
    )
    stdout = StringIO()

    code = run(["moves", "--state", "-"], stdin=StringIO(state_to_text(state)), stdout=stdout)

    assert code == 0
    assert "W->T0" not in stdout.getvalue()


def _read_json(path: Path) -> dict[str, Any]:
    """Return a JSON object from ``path``."""
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data
