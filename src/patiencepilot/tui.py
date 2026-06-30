"""Console script entry point for the Patience Pilot TUI."""

from __future__ import annotations

from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Textual terminal user interface."""
    try:
        from .ui.tui import main as tui_main
    except ModuleNotFoundError as error:
        if error.name == "textual":
            print("patiencepilot-tui requires Textual. Install with: patiencepilot[tui]")
            return 2
        raise
    return tui_main(argv)


__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
