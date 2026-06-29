"""Public solitaire API."""

from importlib.metadata import PackageNotFoundError, version

from .exceptions import SolitaireError

try:
    __version__ = version("solitaire")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"


__all__ = [
    "SolitaireError",
    "__version__",
]
