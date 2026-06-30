"""Tests for player-known state projections."""

from __future__ import annotations

import pytest

from patiencepilot import (
    Card,
    DrawFromStock,
    InvalidStateError,
    PlayerStackCard,
    PlayerView,
    UnknownCardConstraints,
    apply_move,
    new_game,
)

pytestmark = pytest.mark.unit


def test_player_view_hides_face_down_tableau_identities() -> None:
    state = new_game(seed=123)

    view = PlayerView.from_state(state)

    assert view.stock_count == 24
    assert view.unknown.hidden_tableau_counts == (0, 1, 2, 3, 4, 5, 6)
    assert view.unknown.hidden_position_count == 45

    hidden_cards: set[Card] = set()
    for state_column, view_column in zip(state.tableau, view.tableau, strict=True):
        for state_card, view_card in zip(state_column, view_column, strict=True):
            if state_card.face_up:
                assert view_card == PlayerStackCard.visible(state_card.card)
            else:
                hidden_cards.add(state_card.card)
                assert view_card == PlayerStackCard.hidden()

    assert hidden_cards.isdisjoint(view.iter_visible_cards())
    assert hidden_cards.isdisjoint(view.seen_cards)
    assert hidden_cards.issubset(view.unknown.unseen_cards)


def test_player_view_keeps_seen_card_history_without_revealing_positions() -> None:
    state = new_game(seed=123)
    previously_seen_card = state.tableau[3][0].card

    view = PlayerView.from_state(state, seen_cards=(previously_seen_card,))

    assert previously_seen_card in view.seen_cards
    assert previously_seen_card not in view.unknown.unseen_cards
    assert view.tableau[3][0] == PlayerStackCard.hidden()


def test_player_view_marks_drawn_waste_cards_as_seen() -> None:
    state = apply_move(new_game(seed=7), DrawFromStock()).state

    view = PlayerView.from_state(state)

    assert view.waste == state.waste
    assert set(view.waste).issubset(view.seen_cards)
    assert view.stock_count == len(state.stock)


def test_player_view_rejects_visibility_invariant_violations() -> None:
    with pytest.raises(InvalidStateError, match="face-up"):
        PlayerStackCard(card=None, face_up=True)

    with pytest.raises(InvalidStateError, match="face-down"):
        PlayerStackCard(card=Card.from_code("AS"), face_up=False)


def test_unknown_card_constraints_validate_counts() -> None:
    with pytest.raises(InvalidStateError, match="7 entries"):
        UnknownCardConstraints(hidden_tableau_counts=(0, 1), stock_count=24, unseen_cards=())

    with pytest.raises(InvalidStateError, match="non-negative"):
        UnknownCardConstraints(hidden_tableau_counts=(0, 1, 2, 3, 4, 5, 6), stock_count=-1, unseen_cards=())
