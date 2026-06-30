"""Tests for solver visibility and advice contracts."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from patiencepilot import (
    Advice,
    DrawFromStock,
    InvalidStateError,
    PatiencePilotApp,
    PlayerView,
    RankedMove,
    SearchLimit,
    WasteToFoundation,
)

pytestmark = pytest.mark.unit


def test_search_limit_accepts_time_node_and_depth_limits() -> None:
    limit = SearchLimit(time_seconds=0.5, node_limit=10, depth_limit=0)

    assert limit.time_seconds == 0.5
    assert limit.node_limit == 10
    assert limit.depth_limit == 0


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: SearchLimit(time_seconds=0.0), "time_seconds must be positive"),
        (lambda: SearchLimit(node_limit=0), "node_limit must be at least 1"),
        (lambda: SearchLimit(depth_limit=-1), "depth_limit must be non-negative"),
    ],
)
def test_search_limit_rejects_invalid_limits(factory: Callable[[], SearchLimit], message: str) -> None:
    with pytest.raises(InvalidStateError, match=message):
        factory()


def test_advice_can_wrap_a_single_recommended_move() -> None:
    limit = SearchLimit(node_limit=25)

    advice = Advice.from_move(
        DrawFromStock(),
        solver_name="single",
        limit=limit,
        score=1.25,
        confidence=0.75,
        reason="Open a new waste card.",
    )

    assert advice.solver_name == "single"
    assert advice.limit == limit
    assert advice.best_move == DrawFromStock()
    assert advice.best == RankedMove(
        move=DrawFromStock(),
        rank=1,
        score=1.25,
        confidence=0.75,
        reason="Open a new waste card.",
    )
    assert advice.alternatives == ()


def test_advice_sorts_ranked_alternatives() -> None:
    lower_ranked = RankedMove(move=WasteToFoundation(), rank=2, score=0.4)
    higher_ranked = RankedMove(move=DrawFromStock(), rank=1, score=0.7)

    advice = Advice(recommendations=(lower_ranked, higher_ranked), solver_name="ranked")

    assert advice.best_move == DrawFromStock()
    assert advice.recommendations == (higher_ranked, lower_ranked)
    assert advice.alternatives == (lower_ranked,)


def test_empty_advice_has_no_best_move() -> None:
    advice = Advice(recommendations=())

    assert advice.best is None
    assert advice.best_move is None
    assert advice.alternatives == ()


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: RankedMove(move=DrawFromStock(), rank=0), "rank must be at least 1"),
        (lambda: RankedMove(move=DrawFromStock(), confidence=1.1), "confidence must be between 0 and 1"),
        (lambda: Advice(recommendations=(), nodes_searched=-1), "nodes_searched must be non-negative"),
        (lambda: Advice(recommendations=(), depth_reached=-1), "depth_reached must be non-negative"),
        (lambda: Advice(recommendations=(), elapsed_seconds=-0.1), "elapsed_seconds must be non-negative"),
    ],
)
def test_advice_rejects_invalid_metadata(factory: Callable[[], object], message: str) -> None:
    with pytest.raises(InvalidStateError, match=message):
        factory()


def test_app_passes_player_view_to_advice_providers_without_hidden_cards() -> None:
    app = PatiencePilotApp()
    session = app.new_session(seed=21)
    seen_card = session.state.stock[0]
    provider = RecordingProvider()
    limit = SearchLimit(depth_limit=1)

    advice = app.request_advice(provider=provider, limit=limit, seen_cards=(seen_card,))

    assert advice.best_move == DrawFromStock()
    assert provider.seen_view is not None
    assert provider.seen_limit == limit
    assert provider.seen_view.stock_count == len(session.state.stock)
    assert seen_card in provider.seen_view.seen_cards
    assert all(card.card is None for column in provider.seen_view.tableau for card in column if not card.face_up)


class RecordingProvider:
    """Advice provider that records its player-known input."""

    seen_limit: SearchLimit | None = None
    seen_view: PlayerView | None = None

    def suggest(self, view: PlayerView, *, limit: SearchLimit | None = None) -> Advice:
        """Record the view and return one legal-shaped recommendation."""
        self.seen_view = view
        self.seen_limit = limit
        return Advice.from_move(DrawFromStock(), solver_name="recording", limit=limit)
