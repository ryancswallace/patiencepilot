"""Solver registry for resolving advice providers by name."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from patiencepilot.exceptions import InvalidStateError, UnsupportedSolverError
from patiencepilot.solvers.base import AdviceProvider
from patiencepilot.solvers.dummy import DummySolver


class SolverFactory(Protocol):
    """Callable that creates an advice provider."""

    def __call__(self) -> AdviceProvider:
        """Return an advice provider instance."""
        ...


@dataclass(frozen=True, slots=True)
class SolverDefinition:
    """Registered solver metadata and factory."""

    name: str
    factory: SolverFactory
    aliases: tuple[str, ...] = ()
    description: str | None = None

    def create(self) -> AdviceProvider:
        """Return a new advice provider instance."""
        return self.factory()


@dataclass(frozen=True, slots=True)
class SolverRegistry:
    """Small immutable registry of supported solvers."""

    definitions: tuple[SolverDefinition, ...]

    def __post_init__(self) -> None:
        """Validate registry keys."""
        keys: set[str] = set()
        for definition in self.definitions:
            for name in (definition.name, *definition.aliases):
                normalized = _normalize_solver_name(name)
                if normalized in keys:
                    msg = f"duplicate solver registry name: {name!r}"
                    raise InvalidStateError(msg)
                keys.add(normalized)

    @property
    def names(self) -> tuple[str, ...]:
        """Return canonical registered solver names."""
        return tuple(definition.name for definition in self.definitions)

    def register(self, definition: SolverDefinition) -> SolverRegistry:
        """Return a new registry that also contains ``definition``.

        Args:
            definition: Solver definition to add.
        """
        return SolverRegistry((*self.definitions, definition))

    def definition_for(self, name: str) -> SolverDefinition:
        """Return the registered definition for ``name`` or alias.

        Args:
            name: Solver name or alias.

        Raises:
            UnsupportedSolverError: If no solver is registered for ``name``.
        """
        normalized = _normalize_solver_name(name)
        for definition in self.definitions:
            if normalized == _normalize_solver_name(definition.name):
                return definition
            if any(normalized == _normalize_solver_name(alias) for alias in definition.aliases):
                return definition

        msg = f"unsupported solver: {name!r}"
        raise UnsupportedSolverError(msg)

    def create(self, name: str) -> AdviceProvider:
        """Return a new advice provider by solver name.

        Args:
            name: Solver name or alias.
        """
        return self.definition_for(name).create()


def resolve_solver(name: str = "dummy", *, registry: SolverRegistry | None = None) -> AdviceProvider:
    """Return an advice provider for a registered solver name.

    Args:
        name: Solver name or alias. Defaults to ``"dummy"``.
        registry: Registry to use. Defaults to the package registry.
    """
    return _registry_or_default(registry).create(name)


def solver_names(*, registry: SolverRegistry | None = None) -> tuple[str, ...]:
    """Return canonical names of registered solvers."""
    return _registry_or_default(registry).names


def _registry_or_default(registry: SolverRegistry | None) -> SolverRegistry:
    """Return ``registry`` or the package default registry."""
    if registry is not None:
        return registry
    return DEFAULT_SOLVER_REGISTRY


def _normalize_solver_name(name: str) -> str:
    """Normalize a solver registry key."""
    normalized = name.strip().casefold()
    if not normalized:
        msg = "solver name cannot be empty"
        raise UnsupportedSolverError(msg)
    return normalized


DEFAULT_SOLVER_REGISTRY = SolverRegistry(
    (
        SolverDefinition(
            name="dummy",
            factory=DummySolver,
            aliases=("first", "trivial"),
            description="Deterministic solver that recommends the first visible legal move.",
        ),
    )
)


__all__ = [
    "DEFAULT_SOLVER_REGISTRY",
    "SolverDefinition",
    "SolverFactory",
    "SolverRegistry",
    "resolve_solver",
    "solver_names",
]
