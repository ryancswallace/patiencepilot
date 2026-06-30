"""Reusable solver contract test harnesses."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from patiencepilot import Advice, AdviceProvider, PlayerView, SearchLimit, visible_klondike_moves
from patiencepilot.moves import Move


@dataclass(frozen=True, slots=True)
class SolverCase:
    """One reusable solver contract scenario."""

    name: str
    view: PlayerView
    expected_best: Move | None = None


class SolverHarness:
    """Assertions shared by concrete solver test suites."""

    def __init__(self, solver_factory: Callable[[], AdviceProvider]) -> None:
        """Initialize the harness with a fresh-solver factory."""
        self.solver_factory = solver_factory

    def assert_case(self, case: SolverCase, *, limit: SearchLimit | None = None) -> Advice:
        """Assert a solver returns well-formed visible-legal advice for ``case``."""
        solver = self.solver_factory()
        selected_limit = SearchLimit(depth_limit=1) if limit is None else limit

        advice = solver.suggest(case.view, limit=selected_limit)

        assert advice.limit == selected_limit
        self.assert_advice_is_well_formed(advice)
        self.assert_recommendations_are_visible_legal(case.view, advice)
        if case.expected_best is not None:
            assert advice.best_move == case.expected_best, case.name
        return advice

    @staticmethod
    def assert_advice_is_well_formed(advice: Advice) -> None:
        """Assert advice ranks and metadata are internally consistent."""
        ranks = tuple(recommendation.rank for recommendation in advice.recommendations)
        assert ranks == tuple(sorted(ranks))
        assert len(set(ranks)) == len(ranks)
        assert all(rank >= 1 for rank in ranks)
        assert advice.nodes_searched is None or advice.nodes_searched >= 0
        assert advice.depth_reached is None or advice.depth_reached >= 0
        assert advice.elapsed_seconds is None or advice.elapsed_seconds >= 0

    @staticmethod
    def assert_recommendations_are_visible_legal(view: PlayerView, advice: Advice) -> None:
        """Assert recommended moves are legal from player-visible information only."""
        visible_moves = set(visible_klondike_moves(view))
        for recommendation in advice.recommendations:
            assert recommendation.move in visible_moves

    @staticmethod
    def assert_view_hides_unknown_tableau_cards(view: PlayerView) -> None:
        """Assert the supplied fixture does not expose hidden tableau card identities."""
        assert all(
            stack_card.card is None for column in view.tableau for stack_card in column if not stack_card.face_up
        )


__all__ = ["SolverCase", "SolverHarness"]
