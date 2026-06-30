"""Tests for the Klondike game engine."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from typing import cast, get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st

from patiencepilot import (
    Card,
    DrawFromStock,
    DrewStockCards,
    GameState,
    InvalidMoveError,
    InvalidStateError,
    KlondikeRules,
    MovedCards,
    Rank,
    RecycledWaste,
    RecycleWaste,
    RevealedTableauCard,
    StackCard,
    Suit,
    TableauToFoundation,
    TableauToTableau,
    UnsupportedVariantError,
    WasteToFoundation,
    WasteToTableau,
    apply_move,
    is_won,
    legal_moves,
    new_game,
    standard_deck,
    validate_state,
)
from patiencepilot.moves import Move
from patiencepilot.state import N_TABLEAU_COLUMNS, empty_foundations, empty_tableau

pytestmark = pytest.mark.unit


def c(code: str) -> Card:
    """Return a card from compact test notation."""
    return Card.from_code(code)


def state_with(
    *,
    foundations: tuple[tuple[Card, ...], ...] | None = None,
    tableau: tuple[tuple[StackCard, ...], ...] | None = None,
    stock: tuple[Card, ...] = (),
    waste: tuple[Card, ...] = (),
    draw_count: int = 1,
    redeals_allowed: int | None = None,
    redeals_used: int = 0,
) -> GameState:
    """Return a Klondike state with test-friendly defaults."""
    return GameState(
        foundations=foundations if foundations is not None else empty_foundations(),
        tableau=tableau if tableau is not None else empty_tableau(),
        stock=stock,
        waste=waste,
        draw_count=draw_count,
        redeals_allowed=redeals_allowed,
        redeals_used=redeals_used,
    )


def with_foundation(suit: Suit, cards: tuple[Card, ...]) -> tuple[tuple[Card, ...], ...]:
    """Return foundations with one suit populated."""
    foundations = list(empty_foundations())
    foundations[tuple(Suit).index(suit)] = cards
    return tuple(foundations)


def known_cards(state: GameState) -> tuple[Card, ...]:
    """Return all exact cards in a state."""
    return tuple(state.iter_known_cards())


def test_reveal_is_an_engine_effect_not_a_requested_move() -> None:
    move_types = get_args(Move)

    assert RevealedTableauCard not in move_types
    assert all("Reveal" not in move_type.__name__ for move_type in move_types)


def test_klondike_rules_are_immutable_configuration_objects() -> None:
    rules = KlondikeRules(draw_count=3, redeals=1)

    assert rules.draw_count == 3
    assert rules.redeals == 1
    assert hash(rules) == hash(KlondikeRules(draw_count=3, redeals=1))

    with pytest.raises(FrozenInstanceError):
        rules.__setattr__("draw_count", 1)


def test_klondike_rules_reject_invalid_configuration_and_deals() -> None:
    with pytest.raises(InvalidStateError, match="draw_count"):
        KlondikeRules(draw_count=0)

    with pytest.raises(InvalidStateError, match="redeals"):
        KlondikeRules(redeals=-1)

    rules = KlondikeRules()
    deck = standard_deck()
    with pytest.raises(InvalidStateError, match="unique 52-card deck"):
        rules.deal(deck[:-1])

    with pytest.raises(InvalidStateError, match="unique 52-card deck"):
        rules.deal((*deck[:-1], deck[0]))


def test_new_game_is_seeded_and_has_klondike_deal_shape() -> None:
    rules = KlondikeRules(draw_count=3, redeals=1)

    state = new_game(rules, seed=123)
    matching_state = new_game(rules, seed=123)
    different_state = new_game(rules, seed=456)

    assert state == matching_state
    assert state != different_state
    assert state.draw_count == 3
    assert state.redeals_allowed == 1
    assert len(state.stock) == 24
    assert state.waste == ()
    assert [len(column) for column in state.tableau] == list(range(1, N_TABLEAU_COLUMNS + 1))
    assert all(column[-1].face_up for column in state.tableau)
    assert all(not stack_card.face_up for column in state.tableau for stack_card in column[:-1])
    assert all(
        type(stack_card.card) is Card for column in state.tableau for stack_card in column if not stack_card.face_up
    )
    assert len(known_cards(state)) == 52
    assert len(set(known_cards(state))) == 52


@pytest.mark.parametrize(
    ("rules", "state", "message"),
    [
        (KlondikeRules(), replace(state_with(), variant="spider"), "expected variant"),
        (KlondikeRules(), state_with(draw_count=3), "draw_count"),
        (KlondikeRules(), state_with(redeals_allowed=1), "redeals_allowed"),
        (KlondikeRules(), state_with(redeals_used=-1), "redeals_used must be non-negative"),
        (KlondikeRules(redeals=1), state_with(redeals_allowed=1, redeals_used=2), "cannot exceed"),
        (KlondikeRules(), replace(state_with(), foundations=()), "foundations"),
        (KlondikeRules(), replace(state_with(), tableau=empty_tableau()[:-1]), "tableau"),
        (
            KlondikeRules(),
            state_with(foundations=with_foundation(Suit.HEARTS, (c("2H"),))),
            "foundation H",
        ),
    ],
)
def test_validate_state_rejects_rule_and_shape_mismatches(
    rules: KlondikeRules,
    state: GameState,
    message: str,
) -> None:
    with pytest.raises((InvalidStateError, UnsupportedVariantError), match=message):
        rules.validate_state(state)


def test_draw_from_stock_returns_new_state_and_effect() -> None:
    state = new_game(KlondikeRules(draw_count=3), seed=7)

    result = apply_move(state, DrawFromStock())
    draw_effect = result.effects[0]

    assert len(state.stock) == 24
    assert len(result.state.stock) == 21
    assert len(result.state.waste) == 3
    assert isinstance(draw_effect, DrewStockCards)
    assert result.state.waste[-3:] == draw_effect.cards
    assert len(known_cards(result.state)) == 52
    assert len(set(known_cards(result.state))) == 52


def test_drawing_from_empty_stock_is_invalid() -> None:
    with pytest.raises(InvalidMoveError, match="empty stock"):
        apply_move(state_with(stock=()), DrawFromStock())


def test_recycle_waste_reverses_waste_into_stock_and_tracks_redeal_limit() -> None:
    state = new_game(KlondikeRules(redeals=1), seed=1)
    while state.stock:
        state = apply_move(state, DrawFromStock()).state

    waste_before_recycle = state.waste
    result = apply_move(state, RecycleWaste())

    assert result.state.stock == tuple(reversed(waste_before_recycle))
    assert result.state.waste == ()
    assert result.state.redeals_used == 1
    assert result.effects == (RecycledWaste(count=len(waste_before_recycle)),)

    while result.state.stock:
        result = apply_move(result.state, DrawFromStock())

    with pytest.raises(InvalidMoveError, match="redeal limit"):
        apply_move(result.state, RecycleWaste())


@pytest.mark.parametrize(
    ("state", "message"),
    [
        (state_with(stock=(c("2C"),), waste=(c("3D"),)), "while stock is not empty"),
        (state_with(stock=(), waste=()), "empty waste pile"),
    ],
)
def test_invalid_recycle_moves_report_clear_errors(state: GameState, message: str) -> None:
    with pytest.raises(InvalidMoveError, match=message):
        apply_move(state, RecycleWaste())


def test_tableau_to_foundation_reveals_hidden_source_card() -> None:
    hidden_card = c("2C")
    moving_card = c("AH")
    state = state_with(
        tableau=(
            (StackCard.hidden(hidden_card), StackCard.visible(moving_card)),
            *empty_tableau()[1:],
        ),
    )

    assert TableauToFoundation(source=0) in legal_moves(state)

    result = apply_move(state, TableauToFoundation(source=0))

    assert result.move == TableauToFoundation(source=0)
    assert result.state.foundation(Suit.HEARTS) == (moving_card,)
    assert result.state.tableau[0] == (StackCard.visible(hidden_card),)
    assert result.effects == (
        MovedCards(cards=(moving_card,), source="tableau[0]", destination="foundation[H]"),
        RevealedTableauCard(column=0, card=hidden_card),
    )


def test_tableau_to_tableau_moves_visible_sequence() -> None:
    state = state_with(
        tableau=(
            (StackCard.hidden(c("AH")), StackCard.visible(c("7C")), StackCard.visible(c("6H"))),
            (StackCard.visible(c("8D")),),
            *empty_tableau()[2:],
        ),
    )

    move = TableauToTableau(source=0, destination=1, count=2)
    result = apply_move(state, move)

    assert result.move == move
    assert result.state.tableau[0] == (StackCard.visible(c("AH")),)
    assert result.state.tableau[1] == (
        StackCard.visible(c("8D")),
        StackCard.visible(c("7C")),
        StackCard.visible(c("6H")),
    )
    assert result.effects == (
        MovedCards(cards=(c("7C"), c("6H")), source="tableau[0]", destination="tableau[1]"),
        RevealedTableauCard(column=0, card=c("AH")),
    )


def test_invalid_tableau_move_raises_clear_error() -> None:
    state = state_with(
        tableau=(
            (StackCard.visible(c("5H")),),
            (StackCard.visible(c("7S")),),
            *empty_tableau()[2:],
        ),
    )

    with pytest.raises(InvalidMoveError, match="cannot move 5H"):
        apply_move(state, TableauToTableau(source=0, destination=1))


@pytest.mark.parametrize(
    ("move", "state", "message"),
    [
        (WasteToFoundation(), state_with(waste=()), "empty waste pile"),
        (WasteToFoundation(), state_with(waste=(c("5H"),)), "cannot move 5H to foundation"),
        (WasteToTableau(destination=9), state_with(waste=(c("KH"),)), "out of range"),
        (WasteToTableau(destination=0), state_with(waste=()), "empty waste pile"),
        (
            WasteToTableau(destination=0),
            state_with(waste=(c("5H"),), tableau=((StackCard.visible(c("7S")),), *empty_tableau()[1:])),
            "cannot move 5H",
        ),
        (TableauToFoundation(source=9), state_with(), "out of range"),
        (
            TableauToFoundation(source=0),
            state_with(tableau=((StackCard.hidden(c("AH")),), *empty_tableau()[1:])),
            "no visible top card",
        ),
        (
            TableauToFoundation(source=0),
            state_with(tableau=((StackCard.visible(c("5H")),), *empty_tableau()[1:])),
            "cannot move 5H to foundation",
        ),
        (
            TableauToTableau(source=0, destination=0),
            state_with(tableau=((StackCard.visible(c("KH")),), *empty_tableau()[1:])),
            "must differ",
        ),
        (
            TableauToTableau(source=0, destination=1, count=0),
            state_with(tableau=((StackCard.visible(c("KH")),), *empty_tableau()[1:])),
            "count must be at least 1",
        ),
        (
            TableauToTableau(source=0, destination=1, count=2),
            state_with(tableau=((StackCard.visible(c("KH")),), *empty_tableau()[1:])),
            "does not contain 2 cards",
        ),
        (
            TableauToTableau(source=0, destination=1, count=2),
            state_with(
                tableau=(
                    (StackCard.hidden(c("QH")), StackCard.visible(c("KH"))),
                    *empty_tableau()[1:],
                ),
            ),
            "face-up descending",
        ),
        (
            TableauToTableau(source=0, destination=1),
            state_with(
                tableau=(
                    (StackCard.visible(c("5H")),),
                    (StackCard.visible(c("7S")),),
                    *empty_tableau()[2:],
                ),
            ),
            "cannot move 5H",
        ),
    ],
)
def test_invalid_foundation_waste_and_tableau_moves_report_clear_errors(
    move: Move,
    state: GameState,
    message: str,
) -> None:
    with pytest.raises(InvalidMoveError, match=message):
        apply_move(state, move)


def test_unsupported_runtime_move_is_rejected() -> None:
    with pytest.raises(InvalidMoveError, match="unsupported Klondike move"):
        apply_move(state_with(), cast("Move", object()))


def test_waste_moves_to_foundation_and_tableau() -> None:
    foundation_state = state_with(waste=(c("AS"),))
    foundation_result = apply_move(foundation_state, WasteToFoundation())

    assert foundation_result.state.foundation(Suit.SPADES) == (c("AS"),)
    assert foundation_result.state.waste == ()

    tableau_state = state_with(waste=(c("KS"),))
    tableau_result = apply_move(tableau_state, WasteToTableau(destination=0))

    assert tableau_result.state.tableau[0] == (StackCard.visible(c("KS")),)
    assert tableau_result.state.waste == ()


def test_legal_moves_include_recycle_and_waste_destinations_when_available() -> None:
    recycle_state = state_with(stock=(), waste=(c("3D"),), redeals_allowed=1, redeals_used=0)
    waste_state = state_with(waste=(c("AS"),))
    king_state = state_with(waste=(c("KH"),))

    assert RecycleWaste() in legal_moves(recycle_state)
    assert WasteToFoundation() in legal_moves(waste_state)
    assert WasteToTableau(destination=0) in legal_moves(king_state)


def test_legal_moves_do_not_place_on_hidden_tableau_cards() -> None:
    state = state_with(
        tableau=((StackCard.hidden(c("QS")),), *empty_tableau()[1:]),
        waste=(c("KH"),),
    )

    assert WasteToTableau(destination=0) not in legal_moves(state)


def test_win_detection_requires_complete_foundations() -> None:
    complete_foundations = tuple(tuple(Card(rank=rank, suit=suit) for rank in Rank) for suit in Suit)
    won_state = state_with(foundations=complete_foundations)
    partial_state = state_with(foundations=with_foundation(Suit.HEARTS, (c("AH"),)))

    assert is_won(won_state)
    assert not is_won(partial_state)


def test_validate_state_rejects_duplicate_known_cards() -> None:
    state = state_with(
        tableau=(
            (StackCard.visible(c("AS")),),
            (StackCard.visible(c("AS")),),
            *empty_tableau()[2:],
        ),
    )

    with pytest.raises(InvalidStateError, match="duplicate known cards"):
        validate_state(state)


def test_validate_state_rejects_non_card_tableau_entries() -> None:
    not_a_card = cast(Card, "unknown")
    state = state_with(
        tableau=(
            (StackCard(card=not_a_card, face_up=False),),
            *empty_tableau()[1:],
        ),
    )

    with pytest.raises(InvalidStateError, match="non-card value"):
        validate_state(state)


@given(seed=st.integers(min_value=0, max_value=10_000))
def test_first_legal_move_preserves_known_card_identities(seed: int) -> None:
    state = new_game(seed=seed)
    moves = legal_moves(state)

    assert moves

    result = apply_move(state, moves[0])

    assert sorted(card.code for card in known_cards(result.state)) == sorted(card.code for card in known_cards(state))
