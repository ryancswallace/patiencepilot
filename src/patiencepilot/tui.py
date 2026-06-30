"""Console script entry point for the Patience Pilot TUI."""

from __future__ import annotations

from collections.abc import Sequence
from importlib import import_module


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Textual terminal user interface."""
    try:
        tui_module = import_module("patiencepilot.ui.tui")
    except ModuleNotFoundError as error:
        if error.name == "textual":
            print("patiencepilot-tui and patp-tui require Textual. Install with: patiencepilot[tui]")
            return 2
        raise
    return tui_module.main(argv)


__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
