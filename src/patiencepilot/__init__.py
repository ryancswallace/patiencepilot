"""Public patiencepilot API."""

from importlib.metadata import PackageNotFoundError, version

from .exceptions import PatiencePilotError

try:
    __version__ = version("patiencepilot")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"


__all__ = [
    "PatiencePilotError",
    "__version__",
]
