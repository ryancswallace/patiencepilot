"""Console script entry point for the Patience Pilot CLI."""

from __future__ import annotations

from .ui.cli import main

__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
