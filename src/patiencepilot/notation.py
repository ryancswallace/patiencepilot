"""Canonical notation and JSON-compatible serialization."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import NotRequired, TypedDict, cast

from .cards import Card, Suit
from .exceptions import NotationError, PatiencePilotError
from .moves import (
    DrawFromStock,
    Move,
    RecycleWaste,
    TableauToFoundation,
    TableauToTableau,
    WasteToFoundation,
    WasteToTableau,
)
from .state import SUIT_ORDER, GameState, StackCard
from .variants.registry import resolve_variant, variant_options_from_state
from .view import PlayerStackCard, PlayerView, UnknownCardConstraints

SCHEMA_VERSION = 1

_TABLEAU_TO_TABLEAU_RE = re.compile(r"^T(?P<source>\d+)->T(?P<destination>\d+)(?::(?P<count>\d+))?$")
_TABLEAU_TO_FOUNDATION_RE = re.compile(r"^T(?P<source>\d+)->F$")
_WASTE_TO_TABLEAU_RE = re.compile(r"^W->T(?P<destination>\d+)$")
_HIDDEN_CARD_RE = re.compile(r"^\[(?P<card>[^\]]+)\]$")


class SerializedMove(TypedDict):
    """JSON-compatible serialized move payload."""

    id: str
    schema_version: NotRequired[int]


class SerializedStackCard(TypedDict):
    """JSON-compatible authoritative tableau card payload."""

    card: str
    face_up: bool


class SerializedGameState(TypedDict):
    """JSON-compatible authoritative game-state payload."""

    schema_version: int
    variant: str
    options: dict[str, object]
    foundations: list[list[str]]
    tableau: list[list[SerializedStackCard]]
    stock: list[str]
    waste: list[str]
    redeals_used: int


class SerializedPlayerStackCard(TypedDict):
    """JSON-compatible player-view tableau card payload."""

    card: str | None
    face_up: bool


class SerializedUnknownCardConstraints(TypedDict):
    """JSON-compatible unknown-card constraint payload."""

    hidden_tableau_counts: list[int]
    stock_count: int
    unseen_cards: list[str]


class SerializedPlayerView(TypedDict):
    """JSON-compatible player-known state payload."""

    schema_version: int
    variant: str
    options: dict[str, object]
    foundations: list[list[str]]
    tableau: list[list[SerializedPlayerStackCard]]
    waste: list[str]
    seen_cards: list[str]
    unknown: SerializedUnknownCardConstraints
    redeals_used: int


@dataclass(frozen=True, slots=True)
class ValidationDiagnostic:
    """A validation diagnostic suitable for UI display."""

    path: str
    message: str
    error_type: str


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Structured validation result for notation and payload checks."""

    diagnostics: tuple[ValidationDiagnostic, ...] = ()

    @property
    def ok(self) -> bool:
        """Return whether validation succeeded."""
        return not self.diagnostics

    @property
    def message(self) -> str | None:
        """Return the first validation message, if any."""
        if not self.diagnostics:
            return None
        return self.diagnostics[0].message


def move_to_id(move: Move) -> str:
    """Return the canonical compact identifier for ``move``.

    Args:
        move: Structured move to identify.

    Raises:
        NotationError: If the move contains invalid notation values.
    """
    if isinstance(move, DrawFromStock):
        return "DRAW"
    if isinstance(move, RecycleWaste):
        return "RECYCLE"
    if isinstance(move, WasteToFoundation):
        return "W->F"
    if isinstance(move, WasteToTableau):
        _require_non_negative(move.destination, "destination")
        return f"W->T{move.destination}"
    if isinstance(move, TableauToFoundation):
        _require_non_negative(move.source, "source")
        return f"T{move.source}->F"
    if isinstance(move, TableauToTableau):
        _require_non_negative(move.source, "source")
        _require_non_negative(move.destination, "destination")
        if move.count < 1:
            msg = "tableau move count must be at least 1"
            raise NotationError(msg)
        suffix = "" if move.count == 1 else f":{move.count}"
        return f"T{move.source}->T{move.destination}{suffix}"

    msg = f"unsupported move: {move!r}"
    raise NotationError(msg)


def move_from_id(move_id: str) -> Move:
    """Parse a canonical compact move identifier.

    Args:
        move_id: Identifier such as ``DRAW``, ``W->F``, ``W->T3``,
            ``T0->F``, or ``T0->T3:2``.

    Raises:
        NotationError: If the identifier cannot be parsed.
    """
    normalized = _normalize_move_id(move_id)
    if normalized == "DRAW":
        return DrawFromStock()
    if normalized == "RECYCLE":
        return RecycleWaste()
    if normalized == "W->F":
        return WasteToFoundation()

    waste_to_tableau_match = _WASTE_TO_TABLEAU_RE.fullmatch(normalized)
    if waste_to_tableau_match is not None:
        return WasteToTableau(destination=int(waste_to_tableau_match.group("destination")))

    tableau_to_foundation_match = _TABLEAU_TO_FOUNDATION_RE.fullmatch(normalized)
    if tableau_to_foundation_match is not None:
        return TableauToFoundation(source=int(tableau_to_foundation_match.group("source")))

    tableau_to_tableau_match = _TABLEAU_TO_TABLEAU_RE.fullmatch(normalized)
    if tableau_to_tableau_match is not None:
        count_text = tableau_to_tableau_match.group("count")
        count = 1 if count_text is None else int(count_text)
        if count < 1:
            msg = f"tableau move count must be at least 1: {move_id!r}"
            raise NotationError(msg)
        return TableauToTableau(
            source=int(tableau_to_tableau_match.group("source")),
            destination=int(tableau_to_tableau_match.group("destination")),
            count=count,
        )

    msg = f"invalid move id: {move_id!r}"
    raise NotationError(msg)


def serialize_move(move: Move) -> SerializedMove:
    """Return a JSON-compatible serialized move payload."""
    return {"id": move_to_id(move)}


def deserialize_move(data: Mapping[str, object]) -> Move:
    """Return a move from a JSON-compatible serialized payload.

    Args:
        data: Mapping with an ``id`` string.

    Raises:
        NotationError: If the payload is missing or has an invalid ``id``.
    """
    schema_version = data.get("schema_version", SCHEMA_VERSION)
    if schema_version != SCHEMA_VERSION:
        msg = f"unsupported move schema_version: {schema_version!r}"
        raise NotationError(msg)
    move_id = data.get("id")
    if not isinstance(move_id, str):
        msg = "serialized move must contain an 'id' string"
        raise NotationError(msg)
    return move_from_id(move_id)


def state_to_text(state: GameState) -> str:
    """Return canonical text notation for an authoritative state."""
    redeals = "none" if state.redeals_allowed is None else str(state.redeals_allowed)
    lines = [
        f"VARIANT {state.variant} draw_count={state.draw_count} redeals={redeals} redeals_used={state.redeals_used}",
        "FOUNDATIONS " + " ".join(f"{suit.code}={_format_card_codes(state.foundation(suit))}" for suit in SUIT_ORDER),
        f"STOCK: {_format_card_sequence(state.stock)}",
        f"WASTE: {_format_card_sequence(state.waste)}",
    ]
    lines.extend(
        f"T{column_index}: {_format_tableau_column(column)}" for column_index, column in enumerate(state.tableau)
    )
    return "\n".join(lines)


def state_from_text(text: str) -> GameState:
    """Return a state parsed from canonical text notation.

    Args:
        text: State notation produced by :func:`state_to_text`.

    Raises:
        NotationError: If the notation cannot be parsed or validated.
    """
    lines = _normalized_state_lines(text)
    if len(lines) < 4:
        msg = "state notation must contain variant, foundations, stock, waste, and tableau lines"
        raise NotationError(msg)

    variant, options, redeals_used = _parse_variant_line(lines[0])
    foundations = _parse_foundations_line(lines[1])
    stock = _parse_card_sequence_line(lines[2], "STOCK")
    waste = _parse_card_sequence_line(lines[3], "WASTE")
    tableau = tuple(_parse_tableau_line(line, expected_index=index) for index, line in enumerate(lines[4:]))

    state = GameState(
        foundations=foundations,
        tableau=tableau,
        stock=stock,
        waste=waste,
        variant=variant,
        draw_count=_int_option(options, "draw_count", default=1),
        redeals_allowed=_optional_int_option(options, "redeals"),
        redeals_used=redeals_used,
    )
    _validate_state_with_options(state, options)
    return state


def serialize_state(state: GameState) -> SerializedGameState:
    """Return a JSON-compatible authoritative state payload."""
    return {
        "schema_version": SCHEMA_VERSION,
        "variant": state.variant,
        "options": variant_options_from_state(state),
        "foundations": [[card.code for card in foundation] for foundation in state.foundations],
        "tableau": [
            [{"card": stack_card.card.code, "face_up": stack_card.face_up} for stack_card in column]
            for column in state.tableau
        ],
        "stock": [card.code for card in state.stock],
        "waste": [card.code for card in state.waste],
        "redeals_used": state.redeals_used,
    }


def deserialize_state(data: Mapping[str, object]) -> GameState:
    """Return a state from a JSON-compatible payload.

    Args:
        data: State payload created by :func:`serialize_state`.

    Raises:
        NotationError: If the payload cannot be parsed or validated.
    """
    migrated = migrate_state_payload(data)
    variant = _str_value(migrated, "variant")
    options = _dict_value(migrated, "options")
    state = GameState(
        foundations=_deserialize_foundations(migrated),
        tableau=_deserialize_tableau(migrated),
        stock=tuple(_deserialize_cards(migrated, "stock")),
        waste=tuple(_deserialize_cards(migrated, "waste")),
        variant=variant,
        draw_count=_int_option(options, "draw_count", default=1),
        redeals_allowed=_optional_int_option(options, "redeals"),
        redeals_used=_int_value(migrated, "redeals_used"),
    )
    _validate_state_with_options(state, options)
    return state


def migrate_state_payload(data: Mapping[str, object]) -> dict[str, object]:
    """Return a best-effort alpha migration to schema version 1."""
    migrated = dict(data)
    schema_version = migrated.get("schema_version", SCHEMA_VERSION)
    if schema_version != SCHEMA_VERSION:
        msg = f"unsupported state schema_version: {schema_version!r}"
        raise NotationError(msg)
    migrated["schema_version"] = SCHEMA_VERSION
    migrated.setdefault("variant", "klondike")
    migrated.setdefault("options", {})
    migrated.setdefault("foundations", [[], [], [], []])
    migrated.setdefault("tableau", [])
    migrated.setdefault("stock", [])
    migrated.setdefault("waste", [])
    migrated.setdefault("redeals_used", 0)
    return migrated


def serialize_player_view(view: PlayerView) -> SerializedPlayerView:
    """Return a JSON-compatible player-known state payload."""
    return {
        "schema_version": SCHEMA_VERSION,
        "variant": view.variant,
        "options": {
            "draw_count": view.draw_count,
            "redeals": view.redeals_allowed,
        },
        "foundations": [[card.code for card in foundation] for foundation in view.foundations],
        "tableau": [
            [
                {
                    "card": None if stack_card.card is None else stack_card.card.code,
                    "face_up": stack_card.face_up,
                }
                for stack_card in column
            ]
            for column in view.tableau
        ],
        "waste": [card.code for card in view.waste],
        "seen_cards": [card.code for card in view.seen_cards],
        "unknown": {
            "hidden_tableau_counts": list(view.unknown.hidden_tableau_counts),
            "stock_count": view.unknown.stock_count,
            "unseen_cards": [card.code for card in view.unknown.unseen_cards],
        },
        "redeals_used": view.redeals_used,
    }


def deserialize_player_view(data: Mapping[str, object]) -> PlayerView:
    """Return a player-known view from a JSON-compatible payload."""
    schema_version = data.get("schema_version", SCHEMA_VERSION)
    if schema_version != SCHEMA_VERSION:
        msg = f"unsupported player-view schema_version: {schema_version!r}"
        raise NotationError(msg)

    options = _dict_value(data, "options")
    unknown = _mapping_value(data, "unknown")
    return PlayerView(
        foundations=_deserialize_foundations(data),
        tableau=_deserialize_player_tableau(data),
        waste=tuple(_deserialize_cards(data, "waste")),
        seen_cards=tuple(_deserialize_cards(data, "seen_cards")),
        unknown=UnknownCardConstraints(
            hidden_tableau_counts=tuple(_int_list_value(unknown, "hidden_tableau_counts")),
            stock_count=_int_value(unknown, "stock_count"),
            unseen_cards=tuple(_deserialize_cards(unknown, "unseen_cards")),
        ),
        variant=_str_value(data, "variant"),
        draw_count=_int_option(options, "draw_count", default=1),
        redeals_allowed=_optional_int_option(options, "redeals"),
        redeals_used=_int_value(data, "redeals_used"),
    )


def validate_move_id(move_id: str) -> ValidationResult:
    """Validate a move identifier without raising."""
    try:
        move_from_id(move_id)
    except PatiencePilotError as error:
        return _validation_result("move_id", error)
    return ValidationResult()


def validate_serialized_move(data: Mapping[str, object]) -> ValidationResult:
    """Validate a serialized move payload without raising."""
    try:
        deserialize_move(data)
    except PatiencePilotError as error:
        return _validation_result("move", error)
    return ValidationResult()


def validate_serialized_state(data: Mapping[str, object]) -> ValidationResult:
    """Validate a serialized state payload without raising."""
    try:
        deserialize_state(data)
    except PatiencePilotError as error:
        return _validation_result("state", error)
    return ValidationResult()


def validate_state_text(text: str) -> ValidationResult:
    """Validate state text notation without raising."""
    try:
        state_from_text(text)
    except PatiencePilotError as error:
        return _validation_result("state_text", error)
    return ValidationResult()


def _format_card_codes(cards: tuple[Card, ...]) -> str:
    """Return comma-separated card codes, or ``-`` for empty."""
    if not cards:
        return "-"
    return ",".join(card.code for card in cards)


def _format_card_sequence(cards: tuple[Card, ...]) -> str:
    """Return space-separated card codes, or ``-`` for empty."""
    if not cards:
        return "-"
    return " ".join(card.code for card in cards)


def _format_tableau_column(column: tuple[StackCard, ...]) -> str:
    """Return text notation for one tableau column."""
    if not column:
        return "-"
    return " ".join(
        stack_card.card.code if stack_card.face_up else f"[{stack_card.card.code}]" for stack_card in column
    )


def _normalized_state_lines(text: str) -> list[str]:
    """Return meaningful state notation lines."""
    return [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]


def _parse_variant_line(line: str) -> tuple[str, dict[str, object], int]:
    """Parse the variant metadata line."""
    parts = line.split()
    if len(parts) < 2 or parts[0].upper() != "VARIANT":
        msg = "state notation must start with 'VARIANT <name>'"
        raise NotationError(msg)

    options: dict[str, object] = {}
    redeals_used = 0
    for token in parts[2:]:
        if "=" not in token:
            msg = f"invalid variant option token: {token!r}"
            raise NotationError(msg)
        key, value = token.split("=", 1)
        if key == "draw_count":
            options[key] = _parse_int_text(value, "draw_count")
        elif key == "redeals":
            options[key] = _parse_optional_int_text(value, "redeals")
        elif key == "redeals_used":
            redeals_used = _parse_int_text(value, "redeals_used")
        else:
            options[key] = value
    options.setdefault("draw_count", 1)
    options.setdefault("redeals", None)
    return parts[1], options, redeals_used


def _parse_foundations_line(line: str) -> tuple[tuple[Card, ...], ...]:
    """Parse the foundations line."""
    if not line.upper().startswith("FOUNDATIONS "):
        msg = "state notation must contain a FOUNDATIONS line"
        raise NotationError(msg)
    foundations_by_suit: dict[Suit, tuple[Card, ...]] = {}
    for token in line.split()[1:]:
        if "=" not in token:
            msg = f"invalid foundation token: {token!r}"
            raise NotationError(msg)
        suit_code, cards_text = token.split("=", 1)
        try:
            suit = Suit.from_code(suit_code)
        except ValueError as error:
            raise NotationError(str(error)) from error
        foundations_by_suit[suit] = _parse_card_codes(cards_text, f"foundation[{suit.code}]")
    return tuple(foundations_by_suit.get(suit, ()) for suit in SUIT_ORDER)


def _parse_card_sequence_line(line: str, label: str) -> tuple[Card, ...]:
    """Parse a labelled card sequence line."""
    prefix = f"{label}:"
    if not line.upper().startswith(prefix):
        msg = f"state notation must contain a {label} line"
        raise NotationError(msg)
    return _parse_card_tokens(line[len(prefix) :].strip(), label.lower())


def _parse_tableau_line(line: str, *, expected_index: int) -> tuple[StackCard, ...]:
    """Parse one tableau line."""
    prefix = f"T{expected_index}:"
    if not line.upper().startswith(prefix):
        msg = f"expected tableau line {prefix}"
        raise NotationError(msg)

    body = line[len(prefix) :].strip()
    if body == "-":
        return ()

    cards: list[StackCard] = []
    for token_index, token in enumerate(body.split()):
        hidden_match = _HIDDEN_CARD_RE.fullmatch(token)
        path = f"tableau[{expected_index}][{token_index}]"
        if hidden_match is not None:
            cards.append(StackCard.hidden(_card_from_code(hidden_match.group("card"), path)))
        else:
            cards.append(StackCard.visible(_card_from_code(token, path)))
    return tuple(cards)


def _parse_card_codes(cards_text: str, path: str) -> tuple[Card, ...]:
    """Parse comma-separated card codes."""
    if cards_text == "-":
        return ()
    return tuple(_card_from_code(token, f"{path}[{index}]") for index, token in enumerate(cards_text.split(",")))


def _parse_card_tokens(cards_text: str, path: str) -> tuple[Card, ...]:
    """Parse space-separated card codes."""
    if not cards_text or cards_text == "-":
        return ()
    return tuple(_card_from_code(token, f"{path}[{index}]") for index, token in enumerate(cards_text.split()))


def _parse_int_text(value: str, name: str) -> int:
    """Parse an integer text value."""
    try:
        parsed = int(value)
    except ValueError as error:
        msg = f"{name} must be an integer: {value!r}"
        raise NotationError(msg) from error
    return parsed


def _parse_optional_int_text(value: str, name: str) -> int | None:
    """Parse an optional integer text value."""
    if value.casefold() in {"none", "null", "*"}:
        return None
    return _parse_int_text(value, name)


def _validate_state_with_options(state: GameState, options: Mapping[str, object]) -> None:
    """Validate ``state`` with explicitly supplied options."""
    resolve_variant(state.variant, options).validate_state(state)


def _deserialize_foundations(data: Mapping[str, object]) -> tuple[tuple[Card, ...], ...]:
    """Return deserialized foundation stacks."""
    foundations: list[tuple[Card, ...]] = []
    for foundation_index, foundation in enumerate(_list_value(data, "foundations")):
        if not isinstance(foundation, list):
            msg = f"foundations[{foundation_index}] must be a list"
            raise NotationError(msg)
        foundations.append(
            tuple(
                _card_from_code(card_code, f"foundations[{foundation_index}][{index}]")
                for index, card_code in enumerate(foundation)
            )
        )
    return tuple(foundations)


def _deserialize_tableau(data: Mapping[str, object]) -> tuple[tuple[StackCard, ...], ...]:
    """Return deserialized authoritative tableau columns."""
    tableau: list[tuple[StackCard, ...]] = []
    for column_index, column in enumerate(_list_value(data, "tableau")):
        if not isinstance(column, list):
            msg = f"tableau[{column_index}] must be a list"
            raise NotationError(msg)
        cards: list[StackCard] = []
        for card_index, item in enumerate(column):
            path = f"tableau[{column_index}][{card_index}]"
            if not isinstance(item, Mapping):
                msg = f"{path} must be a mapping"
                raise NotationError(msg)
            stack_card = cast("Mapping[str, object]", item)
            card = _card_from_code(stack_card.get("card"), f"{path}.card")
            face_up = stack_card.get("face_up")
            if not isinstance(face_up, bool):
                msg = f"{path}.face_up must be a boolean"
                raise NotationError(msg)
            cards.append(StackCard(card=card, face_up=face_up))
        tableau.append(tuple(cards))
    return tuple(tableau)


def _deserialize_player_tableau(data: Mapping[str, object]) -> tuple[tuple[PlayerStackCard, ...], ...]:
    """Return deserialized player-view tableau columns."""
    tableau: list[tuple[PlayerStackCard, ...]] = []
    for column_index, column in enumerate(_list_value(data, "tableau")):
        if not isinstance(column, list):
            msg = f"tableau[{column_index}] must be a list"
            raise NotationError(msg)
        cards: list[PlayerStackCard] = []
        for card_index, item in enumerate(column):
            path = f"tableau[{column_index}][{card_index}]"
            if not isinstance(item, Mapping):
                msg = f"{path} must be a mapping"
                raise NotationError(msg)
            stack_card = cast("Mapping[str, object]", item)
            face_up = stack_card.get("face_up")
            if not isinstance(face_up, bool):
                msg = f"{path}.face_up must be a boolean"
                raise NotationError(msg)
            card_value = stack_card.get("card")
            card = None if card_value is None else _card_from_code(card_value, f"{path}.card")
            cards.append(PlayerStackCard(card=card, face_up=face_up))
        tableau.append(tuple(cards))
    return tuple(tableau)


def _deserialize_cards(data: Mapping[str, object], key: str) -> tuple[Card, ...]:
    """Return deserialized card list from ``key``."""
    return tuple(
        _card_from_code(card_code, f"{key}[{index}]") for index, card_code in enumerate(_list_value(data, key))
    )


def _card_from_code(value: object, path: str) -> Card:
    """Return a card parsed from a serialized code."""
    if not isinstance(value, str):
        msg = f"{path} must be a card-code string"
        raise NotationError(msg)
    try:
        return Card.from_code(value)
    except ValueError as error:
        raise NotationError(f"{path}: {error}") from error


def _mapping_value(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    """Return a mapping payload value."""
    value = data.get(key)
    if not isinstance(value, Mapping):
        msg = f"{key} must be a mapping"
        raise NotationError(msg)
    return cast("Mapping[str, object]", value)


def _dict_value(data: Mapping[str, object], key: str) -> dict[str, object]:
    """Return a dictionary payload value."""
    return dict(_mapping_value(data, key))


def _list_value(data: Mapping[str, object], key: str) -> list[object]:
    """Return a list payload value."""
    value = data.get(key)
    if not isinstance(value, list):
        msg = f"{key} must be a list"
        raise NotationError(msg)
    return value


def _int_list_value(data: Mapping[str, object], key: str) -> tuple[int, ...]:
    """Return an integer list payload value."""
    values = _list_value(data, key)
    parsed: list[int] = []
    for index, value in enumerate(values):
        if type(value) is not int:
            msg = f"{key}[{index}] must be an integer"
            raise NotationError(msg)
        parsed.append(value)
    return tuple(parsed)


def _str_value(data: Mapping[str, object], key: str) -> str:
    """Return a string payload value."""
    value = data.get(key)
    if not isinstance(value, str):
        msg = f"{key} must be a string"
        raise NotationError(msg)
    return value


def _int_value(data: Mapping[str, object], key: str) -> int:
    """Return an integer payload value."""
    value = data.get(key)
    if type(value) is not int:
        msg = f"{key} must be an integer"
        raise NotationError(msg)
    return value


def _int_option(options: Mapping[str, object], key: str, *, default: int) -> int:
    """Return an integer option value."""
    value = options.get(key, default)
    if type(value) is not int:
        msg = f"{key} must be an integer"
        raise NotationError(msg)
    return value


def _optional_int_option(options: Mapping[str, object], key: str) -> int | None:
    """Return an optional integer option value."""
    value = options.get(key)
    if value is None:
        return None
    if type(value) is not int:
        msg = f"{key} must be an integer or None"
        raise NotationError(msg)
    return value


def _normalize_move_id(move_id: str) -> str:
    """Normalize move-id whitespace and casing."""
    normalized = "".join(move_id.split()).upper()
    if not normalized:
        msg = "move id cannot be empty"
        raise NotationError(msg)
    return normalized


def _require_non_negative(value: int, name: str) -> None:
    """Raise when ``value`` is negative."""
    if value < 0:
        msg = f"{name} must be non-negative"
        raise NotationError(msg)


def _validation_result(path: str, error: PatiencePilotError) -> ValidationResult:
    """Return a validation result from an exception."""
    return ValidationResult(
        diagnostics=(ValidationDiagnostic(path=path, message=str(error), error_type=type(error).__name__),)
    )


__all__ = [
    "SCHEMA_VERSION",
    "SerializedGameState",
    "SerializedMove",
    "SerializedPlayerStackCard",
    "SerializedPlayerView",
    "SerializedStackCard",
    "SerializedUnknownCardConstraints",
    "ValidationDiagnostic",
    "ValidationResult",
    "deserialize_move",
    "deserialize_player_view",
    "deserialize_state",
    "migrate_state_payload",
    "move_from_id",
    "move_to_id",
    "serialize_move",
    "serialize_player_view",
    "serialize_state",
    "state_from_text",
    "state_to_text",
    "validate_move_id",
    "validate_serialized_move",
    "validate_serialized_state",
    "validate_state_text",
]
