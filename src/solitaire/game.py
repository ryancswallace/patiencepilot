"""Game logic.

Keep track of:
* Foundations: ordered list of cards (if no undo -> rank of top card in each suit's stack)
* Tableau: ordered list of cards in each pile, plus whether each card is face up or down
* Stock: ordered list of cards
* Waste: ordered list of cards

Operations:
* Deal: randomly shuffle the deck and deal cards to the tableau and stock
* Ask agent for move: given the current game state, ask the agent to choose a move
* Moves:
    * Move card(s) from one tableau pile to another
    * Move card from tableau to foundation
    * Move card from waste to tableau or foundation
    * Draw card from stock to waste
* Apply move to update game state
    * Validate move
    * Update tableau, foundations, stock, and waste as needed
    * Check for win condition: all cards in foundations
    * Check for lose conditions: no valid moves after full cycle through stock
    * Recycle stock if empty and waste is not empty
"""

import random
from enum import Enum, auto
from typing import LiteralString

N_TABLEAU_COLS: int = 7


class CardSuit(Enum):
    HEARTS = auto()
    DIAMONDS = auto()
    CLUBS = auto()
    SPADES = auto()


class CardRank(Enum):
    ACE = auto()
    TWO = auto()
    THREE = auto()
    FOUR = auto()
    FIVE = auto()
    SIX = auto()
    SEVEN = auto()
    EIGHT = auto()
    NINE = auto()
    TEN = auto()
    JACK = auto()
    QUEEN = auto()
    KING = auto()


class Card:
    def __init__(self, suit: CardSuit, rank: CardRank) -> None:
        self.suit: CardSuit = suit
        self.rank: CardRank = rank

    def __repr__(self) -> LiteralString:
        return f"{self.rank.name} of {self.suit.name}"


class Deck:
    def __init__(self) -> None:
        self.cards: list[Card] = [Card(suit, rank) for suit in CardSuit for rank in CardRank]

    def shuffle(self) -> None:
        random.shuffle(self.cards)


class GameState:
    def __init__(self) -> None:
        self.foundations: dict[CardSuit, list[Card]] = {suit: [] for suit in CardSuit}
        self.tableau: list[list[Card]] = [[] for _ in range(N_TABLEAU_COLS)]
        self.tableau_face_up: list[list[bool]] = [[] for _ in range(N_TABLEAU_COLS)]
        self.stock: list[Card] = []
        self.waste: list[Card] = []

    def __repr__(self) -> str:
        return f"Foundations: {self.foundations}\nTableau: {self.tableau}\nStock: {self.stock}\nWaste: {self.waste}"

    def deal(self, deck: Deck) -> None:
        for tableau_col in range(N_TABLEAU_COLS):
            for tableau_row in range(tableau_col + 1):
                self.tableau[tableau_col].append(deck.cards.pop())
                self.tableau_face_up[tableau_col].append(tableau_row == tableau_col)

        self.stock = deck.cards

    def random_deal(self) -> None:
        deck = Deck()
        deck.shuffle()

        self.deal(deck)


class MoveType(Enum):
    TABLEAU_TO_TABLEAU = auto()
    TABLEAU_TO_FOUNDATION = auto()
    WASTE_TO_TABLEAU = auto()
    WASTE_TO_FOUNDATION = auto()
    DRAW_FROM_STOCK = auto()


gs: GameState = GameState()
print(gs)
gs.random_deal()
print(gs)
