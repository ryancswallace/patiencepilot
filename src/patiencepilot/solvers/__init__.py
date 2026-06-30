"""Solver contracts and implementations."""

from .base import Advice, AdviceProvider, RankedMove, SearchLimit, Solver
from .dummy import DummySolver, visible_klondike_moves

__all__ = [
    "Advice",
    "AdviceProvider",
    "DummySolver",
    "RankedMove",
    "SearchLimit",
    "Solver",
    "visible_klondike_moves",
]
