"""Errors raised by patiencepilot."""


class PatiencePilotError(Exception):
    """Base class for patiencepilot errors."""


class InvalidStateError(PatiencePilotError):
    """Raised when a game state is malformed or inconsistent."""


class InvalidMoveError(PatiencePilotError):
    """Raised when a move is not legal from the current state."""


class UnsupportedVariantError(PatiencePilotError):
    """Raised when a Solitaire variant is not supported."""


class UnsupportedSolverError(PatiencePilotError):
    """Raised when a solver is not supported."""


class SolverLimitError(PatiencePilotError):
    """Raised when a solver cannot continue within configured limits."""


class NotationError(PatiencePilotError):
    """Raised when state notation cannot be parsed or serialized."""
