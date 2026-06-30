"""Solver contracts and implementations."""

from .base import Advice, AdviceProvider, RankedMove, SearchLimit, Solver
from .dummy import DummySolver, visible_klondike_moves
from .registry import (
    DEFAULT_SOLVER_REGISTRY,
    SolverDefinition,
    SolverFactory,
    SolverRegistry,
    resolve_solver,
    solver_names,
)

__all__ = [
    "DEFAULT_SOLVER_REGISTRY",
    "Advice",
    "AdviceProvider",
    "DummySolver",
    "RankedMove",
    "SearchLimit",
    "Solver",
    "SolverDefinition",
    "SolverFactory",
    "SolverRegistry",
    "resolve_solver",
    "solver_names",
    "visible_klondike_moves",
]
