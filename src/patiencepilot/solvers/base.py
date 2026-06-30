"""Solver visibility and advice contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from patiencepilot.exceptions import InvalidStateError
from patiencepilot.moves import Move
from patiencepilot.view import PlayerView


@dataclass(frozen=True, slots=True)
class SearchLimit:
    """Optional limits for bounded solver work."""

    time_seconds: float | None = None
    node_limit: int | None = None
    depth_limit: int | None = None

    def __post_init__(self) -> None:
        """Validate search-limit values."""
        if self.time_seconds is not None and self.time_seconds <= 0:
            msg = "time_seconds must be positive when provided"
            raise InvalidStateError(msg)
        if self.node_limit is not None and self.node_limit < 1:
            msg = "node_limit must be at least 1 when provided"
            raise InvalidStateError(msg)
        if self.depth_limit is not None and self.depth_limit < 0:
            msg = "depth_limit must be non-negative when provided"
            raise InvalidStateError(msg)


@dataclass(frozen=True, slots=True)
class RankedMove:
    """One ranked solver move recommendation."""

    move: Move
    rank: int = 1
    score: float | None = None
    confidence: float | None = None
    reason: str | None = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate ranked-move metadata."""
        if self.rank < 1:
            msg = "rank must be at least 1"
            raise InvalidStateError(msg)
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            msg = "confidence must be between 0 and 1"
            raise InvalidStateError(msg)


@dataclass(frozen=True, slots=True)
class Advice:
    """Solver advice containing zero or more ranked move alternatives."""

    recommendations: tuple[RankedMove, ...]
    solver_name: str | None = None
    limit: SearchLimit | None = None
    nodes_searched: int | None = None
    depth_reached: int | None = None
    elapsed_seconds: float | None = None
    assumptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Sort and validate advice metadata."""
        object.__setattr__(self, "recommendations", tuple(sorted(self.recommendations, key=lambda item: item.rank)))
        if self.nodes_searched is not None and self.nodes_searched < 0:
            msg = "nodes_searched must be non-negative"
            raise InvalidStateError(msg)
        if self.depth_reached is not None and self.depth_reached < 0:
            msg = "depth_reached must be non-negative"
            raise InvalidStateError(msg)
        if self.elapsed_seconds is not None and self.elapsed_seconds < 0:
            msg = "elapsed_seconds must be non-negative"
            raise InvalidStateError(msg)

    @classmethod
    def from_move(
        cls,
        move: Move,
        *,
        solver_name: str | None = None,
        limit: SearchLimit | None = None,
        score: float | None = None,
        confidence: float | None = None,
        reason: str | None = None,
    ) -> Advice:
        """Return advice with a single recommended move.

        Args:
            move: Recommended move.
            solver_name: Optional solver identifier.
            limit: Optional search limits used for the recommendation.
            score: Optional solver-specific move score.
            confidence: Optional confidence from 0 to 1.
            reason: Optional human-readable reason.
        """
        return cls(
            recommendations=(RankedMove(move=move, rank=1, score=score, confidence=confidence, reason=reason),),
            solver_name=solver_name,
            limit=limit,
        )

    @property
    def best(self) -> RankedMove | None:
        """Return the highest-ranked recommendation, if any."""
        if not self.recommendations:
            return None
        return self.recommendations[0]

    @property
    def best_move(self) -> Move | None:
        """Return the highest-ranked move, if any."""
        best = self.best
        if best is None:
            return None
        return best.move

    @property
    def alternatives(self) -> tuple[RankedMove, ...]:
        """Return recommendations after the best move."""
        return self.recommendations[1:]


class AdviceProvider(Protocol):
    """Protocol for components that produce advice from player-known state."""

    def suggest(self, view: PlayerView, *, limit: SearchLimit | None = None) -> Advice:
        """Return move advice using only the supplied player-known view."""
        ...


class Solver(AdviceProvider, Protocol):
    """Protocol for pluggable Solitaire solvers."""

    name: str
