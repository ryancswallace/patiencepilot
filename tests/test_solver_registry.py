"""Tests for solver registry resolution."""

from __future__ import annotations

import pytest

from patiencepilot import (
    DEFAULT_SOLVER_REGISTRY,
    Advice,
    AdviceProvider,
    DrawFromStock,
    DummySolver,
    InvalidStateError,
    PlayerView,
    SearchLimit,
    SolverDefinition,
    SolverRegistry,
    UnsupportedSolverError,
    resolve_solver,
    solver_names,
)

pytestmark = pytest.mark.unit


def test_default_solver_registry_resolves_dummy_by_name_and_alias() -> None:
    assert isinstance(DEFAULT_SOLVER_REGISTRY, SolverRegistry)
    assert solver_names() == ("dummy",)
    assert isinstance(resolve_solver(), DummySolver)
    assert isinstance(resolve_solver("DUMMY"), DummySolver)
    assert isinstance(resolve_solver(" trivial "), DummySolver)
    assert DEFAULT_SOLVER_REGISTRY.definition_for("first").name == "dummy"


def test_solver_registry_registers_custom_solver_immutably() -> None:
    definition = SolverDefinition(name="recording", factory=RegistryRecordingSolver, aliases=("rec",))

    registry = DEFAULT_SOLVER_REGISTRY.register(definition)

    assert solver_names(registry=DEFAULT_SOLVER_REGISTRY) == ("dummy",)
    assert solver_names(registry=registry) == ("dummy", "recording")
    provider = resolve_solver("rec", registry=registry)
    assert isinstance(provider, RegistryRecordingSolver)
    assert _accepts_advice_provider(provider) is provider


def test_solver_registry_rejects_duplicate_names_and_aliases() -> None:
    duplicate = SolverDefinition(name="other", factory=RegistryRecordingSolver, aliases=("dummy",))

    with pytest.raises(InvalidStateError, match="duplicate solver registry name"):
        DEFAULT_SOLVER_REGISTRY.register(duplicate)


@pytest.mark.parametrize("name", ["missing", " "])
def test_solver_registry_rejects_unknown_or_empty_names(name: str) -> None:
    with pytest.raises(UnsupportedSolverError):
        resolve_solver(name)


class RegistryRecordingSolver:
    """Tiny advice provider used by registry tests."""

    name = "recording"

    def suggest(self, view: PlayerView, *, limit: SearchLimit | None = None) -> Advice:
        """Return a placeholder recommendation."""
        _ = view
        return Advice.from_move(DrawFromStock(), solver_name=self.name, limit=limit)


def _accepts_advice_provider(provider: AdviceProvider) -> AdviceProvider:
    """Return ``provider`` to exercise public protocol imports."""
    return provider
