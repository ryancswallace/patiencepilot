"""Tests for solver visibility and advice contracts."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from patiencepilot import (
    Advice,
    Card,
    DrawFromStock,
    DummySolver,
    GameSession,
    GameState,
    InvalidStateError,
    PatiencePilotApp,
    PlayerView,
    Rank,
    RankedMove,
    RecycleWaste,
    SearchLimit,
    StackCard,
    Suit,
    TableauToFoundation,
    TableauToTableau,
    UnsupportedVariantError,
    WasteToFoundation,
    WasteToTableau,
    legal_moves,
    visible_klondike_moves,
)
from solver_harness import SolverCase, SolverHarness

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


def test_dummy_solver_returns_the_first_player_visible_legal_move() -> None:
    session = GameSession.new(seed=1)
    view = PlayerView.from_state(session.state)

    advice = DummySolver().suggest(view, limit=SearchLimit(depth_limit=1))

    assert advice.solver_name == "dummy"
    assert advice.best_move == legal_moves(session.state)[0]
    assert advice.nodes_searched == len(legal_moves(session.state))
    assert advice.depth_reached == 0
    assert visible_klondike_moves(view) == legal_moves(session.state)


def test_dummy_solver_satisfies_shared_solver_harness() -> None:
    harness = SolverHarness(DummySolver)
    hidden_state = GameState(
        foundations=((), (), (), ()),
        tableau=(
            (StackCard.hidden(Card.from_code("5C")), StackCard.visible(Card.from_code("4H"))),
            (),
            (),
            (),
            (),
            (),
            (),
        ),
        stock=(Card.from_code("AS"),),
        waste=(),
    )
    hidden_view = PlayerView.from_state(hidden_state)

    harness.assert_view_hides_unknown_tableau_cards(hidden_view)
    harness.assert_case(
        SolverCase(
            name="initial deal",
            view=PlayerView.from_state(GameSession.new(seed=1).state),
            expected_best=DrawFromStock(),
        )
    )
    harness.assert_case(SolverCase(name="hidden tableau identities", view=hidden_view, expected_best=DrawFromStock()))

    complete_foundations = tuple(tuple(Card(rank=rank, suit=suit) for rank in Rank) for suit in Suit)
    no_move_view = PlayerView.from_state(
        GameState(foundations=complete_foundations, tableau=((), (), (), (), (), (), ()), stock=(), waste=())
    )
    advice = harness.assert_case(SolverCase(name="no visible legal moves", view=no_move_view))
    assert advice.recommendations == ()


def test_dummy_solver_returns_empty_advice_when_no_visible_moves_exist() -> None:
    complete_foundations = tuple(tuple(Card(rank=rank, suit=suit) for rank in Rank) for suit in Suit)
    state = GameState(foundations=complete_foundations, tableau=((), (), (), (), (), (), ()), stock=(), waste=())

    advice = DummySolver().suggest(PlayerView.from_state(state))

    assert advice.recommendations == ()
    assert advice.solver_name == "dummy"


def test_dummy_solver_finds_visible_waste_moves_and_recycles() -> None:
    state = GameState(
        foundations=((), (), (), (Card.from_code("AS"),)),
        tableau=((), (), (), (), (), (), ()),
        stock=(),
        waste=(Card.from_code("2S"),),
    )

    moves = visible_klondike_moves(PlayerView.from_state(state))

    assert moves[:2] == (RecycleWaste(), WasteToFoundation())

    king_state = GameState.empty()
    king_state = GameState(
        foundations=king_state.foundations,
        tableau=king_state.tableau,
        stock=(),
        waste=(Card.from_code("KH"),),
    )

    assert WasteToTableau(destination=0) in visible_klondike_moves(PlayerView.from_state(king_state))


def test_dummy_solver_finds_visible_tableau_moves() -> None:
    state = GameState(
        foundations=((), (), (), ()),
        tableau=(
            (StackCard.visible(Card.from_code("AS")),),
            (StackCard.visible(Card.from_code("5C")),),
            (StackCard.visible(Card.from_code("4H")), StackCard.visible(Card.from_code("3C"))),
            (),
            (),
            (),
            (),
        ),
        stock=(),
        waste=(),
    )

    moves = visible_klondike_moves(PlayerView.from_state(state))

    assert TableauToFoundation(source=0) in moves
    assert TableauToTableau(source=2, destination=1, count=2) in moves


def test_dummy_solver_does_not_place_cards_on_hidden_tableau_tops() -> None:
    state = GameState(
        foundations=((), (), (), ()),
        tableau=((StackCard.hidden(Card.from_code("5C")),), (), (), (), (), (), ()),
        stock=(),
        waste=(Card.from_code("4H"),),
    )

    moves = visible_klondike_moves(PlayerView.from_state(state))

    assert WasteToTableau(destination=0) not in moves


def test_dummy_solver_rejects_unsupported_variants() -> None:
    view = PlayerView.from_state(GameState.empty(variant="spider"))

    with pytest.raises(UnsupportedVariantError, match="only supports 'klondike'"):
        DummySolver().suggest(view)


class RecordingProvider:
    """Advice provider that records its player-known input."""

    seen_limit: SearchLimit | None = None
    seen_view: PlayerView | None = None

    def suggest(self, view: PlayerView, *, limit: SearchLimit | None = None) -> Advice:
        """Record the view and return one legal-shaped recommendation."""
        self.seen_view = view
        self.seen_limit = limit
        return Advice.from_move(DrawFromStock(), solver_name="recording", limit=limit)
