"""Application orchestration between UI adapters and core game modules."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TypedDict, cast

from .cards import Card
from .exceptions import InvalidStateError, NotationError, PatiencePilotError
from .game import GameSession
from .moves import Move, MoveResult
from .notation import (
    SCHEMA_VERSION,
    SerializedGameState,
    SerializedMove,
    SerializedPlayerView,
    ValidationDiagnostic,
    deserialize_move,
    deserialize_state,
    serialize_move,
    serialize_player_view,
    serialize_state,
    state_from_text,
    state_to_text,
    validate_serialized_state,
)
from .solvers import Advice, AdviceProvider, SearchLimit
from .state import GameState
from .variants.base import Seed, Variant
from .variants.registry import VariantOptions, resolve_variant, variant_options_from_state
from .view import PlayerView


class SerializedSession(TypedDict):
    """JSON-compatible game-session payload."""

    schema_version: int
    variant: str
    options: dict[str, object]
    seed: object
    initial_state: SerializedGameState
    current_state: SerializedGameState
    state_notation: str
    history: list[SerializedMove]
    redo: list[SerializedMove]
    seen_cards: list[str]
    player_view: SerializedPlayerView
    metadata: dict[str, object]
    ui_state: dict[str, object]


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Validation result suitable for UI display."""

    ok: bool
    message: str | None = None
    error_type: str | None = None
    diagnostics: tuple[ValidationDiagnostic, ...] = ()


@dataclass(slots=True)
class PatiencePilotApp:
    """Small application service for UI and adapter workflows."""

    variant: str = "klondike"
    options: dict[str, object] = field(default_factory=dict)
    session: GameSession | None = None
    advice_provider: AdviceProvider | None = None

    def select_variant(self, name: str, options: VariantOptions | None = None) -> Variant:
        """Select the variant used for newly created sessions.

        Args:
            name: Registered variant name.
            options: Variant-specific option values.
        """
        rules = resolve_variant(name, options)
        self.variant = rules.name
        self.options = {} if options is None else dict(options)
        return rules

    def new_session(
        self,
        *,
        seed: Seed = None,
        metadata: Mapping[str, object] | None = None,
        ui_state: Mapping[str, object] | None = None,
    ) -> GameSession:
        """Create, store, and return a new session for the selected variant."""
        self.session = GameSession.new(
            self.variant,
            seed=seed,
            options=self.options,
            metadata=metadata,
            ui_state=ui_state,
        )
        return self.session

    def use_session(self, session: GameSession) -> GameSession:
        """Store an existing session and sync selected variant metadata."""
        session.validate_state()
        self.session = session
        self.variant = session.state.variant
        self.options = variant_options_from_state(session.state)
        return session

    def validate(self, state: GameState | None = None) -> ValidationReport:
        """Validate a state or the active session state without raising."""
        try:
            if state is not None:
                resolve_variant(state.variant, variant_options_from_state(state)).validate_state(state)
            else:
                self._require_session().validate_state()
        except PatiencePilotError as error:
            return _validation_report("state", error)
        return ValidationReport(ok=True)

    def apply_move(self, move: Move) -> MoveResult:
        """Apply ``move`` to the active session."""
        return self._require_session().apply_move(move)

    def undo(self) -> GameSession:
        """Undo the active session's most recent move and return the session."""
        session = self._require_session()
        session.undo()
        return session

    def redo(self) -> MoveResult:
        """Redo the active session's most recently undone move."""
        return self._require_session().redo()

    def export_session(
        self,
        session: GameSession | None = None,
        *,
        seen_cards: Iterable[Card] | None = None,
    ) -> SerializedSession:
        """Return a serialized payload for ``session`` or the active session."""
        return export_session(self._require_session() if session is None else session, seen_cards=seen_cards)

    def import_session(self, data: Mapping[str, object]) -> GameSession:
        """Import, store, and return a session payload."""
        session = import_session(data)
        self.use_session(session)
        return session

    def request_advice(
        self,
        *,
        provider: AdviceProvider | None = None,
        limit: SearchLimit | None = None,
        seen_cards: Iterable[Card] | None = None,
    ) -> Advice:
        """Request advice for the active session from an advice provider.

        Args:
            provider: Optional provider to use for this request. When omitted,
                the configured ``advice_provider`` is used.
            limit: Optional solver search limits.
            seen_cards: Optional cards known from earlier observation history.
        """
        selected_provider = self.advice_provider if provider is None else provider
        if selected_provider is None:
            msg = "no advice provider configured"
            raise InvalidStateError(msg)
        session = self._require_session()
        view = PlayerView.from_state(session.state, seen_cards=_seen_cards_for_session(session, seen_cards))
        return selected_provider.suggest(view, limit=limit)

    def _require_session(self) -> GameSession:
        """Return the active session or raise a package error."""
        if self.session is None:
            msg = "no active session"
            raise InvalidStateError(msg)
        return self.session


def export_session(session: GameSession, *, seen_cards: Iterable[Card] | None = None) -> SerializedSession:
    """Return a JSON-compatible session payload.

    Args:
        session: Session to export.
        seen_cards: Cards known to the player from earlier observation history.
            When omitted, ``session.metadata["seen_cards"]`` is used if present.
    """
    initial_state = session.history[0].before if session.history else session.state
    known_seen_cards = _seen_cards_for_session(session, seen_cards)
    player_view = PlayerView.from_state(session.state, seen_cards=known_seen_cards)
    return {
        "schema_version": SCHEMA_VERSION,
        "variant": session.state.variant,
        "options": variant_options_from_state(session.state),
        "seed": session.seed,
        "initial_state": serialize_state(initial_state),
        "current_state": serialize_state(session.state),
        "state_notation": state_to_text(session.state),
        "history": [serialize_move(move) for move in session.move_history],
        "redo": [serialize_move(step.move) for step in session.redo_history],
        "seen_cards": [card.code for card in known_seen_cards],
        "player_view": serialize_player_view(player_view),
        "metadata": dict(session.metadata),
        "ui_state": dict(session.ui_state),
    }


def import_session(data: Mapping[str, object]) -> GameSession:
    """Return a session from a serialized payload.

    Args:
        data: Session payload created by :func:`export_session`.

    Raises:
        NotationError: If the payload cannot be imported.
    """
    migrated = migrate_session_payload(data)
    variant = _str_value(migrated, "variant")
    options = _dict_value(migrated, "options")
    initial_state = deserialize_state(_mapping_value(migrated, "initial_state"))
    current_state = deserialize_state(_mapping_value(migrated, "current_state"))
    state_notation = migrated.get("state_notation")
    if isinstance(state_notation, str) and state_from_text(state_notation) != current_state:
        msg = "state_notation does not match current_state"
        raise NotationError(msg)

    history = _deserialize_move_list(migrated, "history")
    redo = _deserialize_move_list(migrated, "redo")
    metadata = _dict_value(migrated, "metadata")
    ui_state = _dict_value(migrated, "ui_state")
    seen_cards = _cards_from_codes(_list_value(migrated, "seen_cards"), "seen_cards")
    if seen_cards and "seen_cards" not in metadata:
        metadata["seen_cards"] = [card.code for card in seen_cards]

    resolve_variant(variant, options).validate_state(initial_state)
    session = GameSession(
        state=initial_state,
        variant=variant,
        seed=_seed_value(migrated.get("seed")),
        metadata=metadata,
        ui_state=ui_state,
    )
    for move in history:
        session.apply_move(move)

    if session.state != current_state:
        msg = "session history does not reproduce current_state"
        raise NotationError(msg)

    for move in redo:
        session.apply_move(move)
    for _ in redo:
        session.undo()

    return session


def migrate_session_payload(data: Mapping[str, object]) -> dict[str, object]:
    """Return a best-effort alpha migration to session schema version 1."""
    migrated = dict(data)
    schema_version = migrated.get("schema_version", SCHEMA_VERSION)
    if schema_version != SCHEMA_VERSION:
        msg = f"unsupported session schema_version: {schema_version!r}"
        raise NotationError(msg)

    if "current_state" not in migrated and "state" in migrated:
        migrated["current_state"] = migrated["state"]
    if "initial_state" not in migrated and "current_state" in migrated:
        migrated["initial_state"] = migrated["current_state"]

    current_state = migrated.get("current_state")
    if isinstance(current_state, Mapping):
        migrated.setdefault("variant", current_state.get("variant", "klondike"))
        migrated.setdefault("options", current_state.get("options", {}))
    else:
        migrated.setdefault("variant", "klondike")
        migrated.setdefault("options", {})

    migrated["schema_version"] = SCHEMA_VERSION
    migrated.setdefault("seed", None)
    migrated.setdefault("history", [])
    migrated.setdefault("redo", [])
    migrated.setdefault("metadata", {})
    migrated.setdefault("ui_state", {})
    migrated.setdefault("seen_cards", [])
    return migrated


def validate_session_payload(data: Mapping[str, object]) -> ValidationReport:
    """Validate a serialized session payload without raising."""
    try:
        import_session(data)
    except PatiencePilotError as error:
        return _validation_report("session", error)
    return ValidationReport(ok=True)


def validate_state_payload(data: Mapping[str, object]) -> ValidationReport:
    """Validate a serialized state payload without raising."""
    result = validate_serialized_state(data)
    if result.ok:
        return ValidationReport(ok=True)
    diagnostic = result.diagnostics[0]
    return ValidationReport(
        ok=False,
        message=diagnostic.message,
        error_type=diagnostic.error_type,
        diagnostics=result.diagnostics,
    )


def _deserialize_move_list(data: Mapping[str, object], key: str) -> tuple[Move, ...]:
    """Return deserialized moves from ``key``."""
    moves: list[Move] = []
    for item in _list_value(data, key):
        if not isinstance(item, Mapping):
            msg = f"{key} items must be mappings"
            raise NotationError(msg)
        moves.append(deserialize_move(cast("Mapping[str, object]", item)))
    return tuple(moves)


def _seen_cards_for_session(session: GameSession, seen_cards: Iterable[Card] | None) -> tuple[Card, ...]:
    """Return seen cards from an argument or session metadata."""
    if seen_cards is not None:
        return tuple(seen_cards)

    value = session.metadata.get("seen_cards", ())
    if isinstance(value, list | tuple):
        return _cards_from_codes(value, "metadata.seen_cards")
    return ()


def _cards_from_codes(values: Iterable[object], path: str) -> tuple[Card, ...]:
    """Return cards from serialized card codes."""
    cards: list[Card] = []
    for index, value in enumerate(values):
        if isinstance(value, Card):
            cards.append(value)
            continue
        if not isinstance(value, str):
            msg = f"{path}[{index}] must be a card-code string"
            raise NotationError(msg)
        try:
            cards.append(Card.from_code(value))
        except ValueError as error:
            raise NotationError(f"{path}[{index}]: {error}") from error
    return tuple(cards)


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


def _str_value(data: Mapping[str, object], key: str) -> str:
    """Return a string payload value."""
    value = data.get(key)
    if not isinstance(value, str):
        msg = f"{key} must be a string"
        raise NotationError(msg)
    return value


def _seed_value(value: object) -> Seed:
    """Return a seed payload value."""
    if value is None:
        return None
    if type(value) is int:
        return value
    if isinstance(value, str | bytes | bytearray):
        return value
    msg = "seed must be an integer, string, bytes, bytearray, or None"
    raise NotationError(msg)


def _validation_report(path: str, error: PatiencePilotError) -> ValidationReport:
    """Return a validation report from an exception."""
    diagnostic = ValidationDiagnostic(path=path, message=str(error), error_type=type(error).__name__)
    return ValidationReport(
        ok=False,
        message=diagnostic.message,
        error_type=diagnostic.error_type,
        diagnostics=(diagnostic,),
    )


__all__ = [
    "SCHEMA_VERSION",
    "AdviceProvider",
    "PatiencePilotApp",
    "SerializedSession",
    "ValidationReport",
    "export_session",
    "import_session",
    "migrate_session_payload",
    "validate_session_payload",
    "validate_state_payload",
]
