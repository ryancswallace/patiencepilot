"""Tests for playing card primitives."""

from __future__ import annotations

import pytest

from patiencepilot import Card, Color, Rank, Suit, standard_deck

pytestmark = pytest.mark.unit


def test_standard_deck_contains_unique_cards() -> None:
    deck = standard_deck()

    assert len(deck) == 52
    assert len(set(deck)) == 52
    assert {card.suit for card in deck} == set(Suit)
    assert {card.rank for card in deck} == set(Rank)


def test_card_codes_round_trip() -> None:
    assert Card.from_code("AS") == Card(rank=Rank.ACE, suit=Suit.SPADES)
    assert Card.from_code("10h") == Card(rank=Rank.TEN, suit=Suit.HEARTS)
    assert Card.from_code("TD").code == "TD"


def test_card_colors_follow_suits() -> None:
    assert Card.from_code("AH").color == Color.RED
    assert Card.from_code("QD").color == Color.RED
    assert Card.from_code("KC").color == Color.BLACK
    assert Card.from_code("2S").color == Color.BLACK
