"""Public patiencepilot API."""

from importlib.metadata import PackageNotFoundError, version

from .cards import Card, Color, Rank, Suit, standard_deck
from .engine import apply_move, is_won, legal_moves, new_game, validate_state
from .exceptions import (
    InvalidMoveError,
    InvalidStateError,
    NotationError,
    PatiencePilotError,
    SolverLimitError,
    UnsupportedVariantError,
)
from .moves import (
    DrawFromStock,
    DrewStockCards,
    MovedCards,
    MoveResult,
    RecycledWaste,
    RecycleWaste,
    RevealedTableauCard,
    TableauToFoundation,
    TableauToTableau,
    WasteToFoundation,
    WasteToTableau,
)
from .state import GameState, StackCard, UnknownCard
from .variants import KlondikeRules, Variant

try:
    __version__ = version("patiencepilot")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"


__all__ = [
    "Card",
    "Color",
    "DrawFromStock",
    "DrewStockCards",
    "GameState",
    "InvalidMoveError",
    "InvalidStateError",
    "KlondikeRules",
    "MoveResult",
    "MovedCards",
    "NotationError",
    "PatiencePilotError",
    "Rank",
    "RecycleWaste",
    "RecycledWaste",
    "RevealedTableauCard",
    "SolverLimitError",
    "StackCard",
    "Suit",
    "TableauToFoundation",
    "TableauToTableau",
    "UnknownCard",
    "UnsupportedVariantError",
    "Variant",
    "WasteToFoundation",
    "WasteToTableau",
    "__version__",
    "apply_move",
    "is_won",
    "legal_moves",
    "new_game",
    "standard_deck",
    "validate_state",
]
