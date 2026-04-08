from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass


SUITS = ("♠", "♥", "♦", "♣")
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
BLACKJACK_VALUES = {
    "A": 11,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "J": 10,
    "Q": 10,
    "K": 10,
}
RANK_ORDER = {rank: index for index, rank in enumerate(RANKS, start=1)}


@dataclass(frozen=True, slots=True)
class Card:
    rank: str
    suit: str

    @property
    def label(self) -> str:
        return f"{self.suit}{self.rank}"


def new_deck() -> list[Card]:
    deck = [Card(rank, suit) for suit in SUITS for rank in RANKS]
    random.shuffle(deck)
    return deck


def format_cards(cards: list[Card]) -> str:
    return " ".join(card.label for card in cards)


def blackjack_value(cards: list[Card]) -> int:
    total = sum(BLACKJACK_VALUES[card.rank] for card in cards)
    aces = sum(1 for card in cards if card.rank == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def evaluate_video_poker(cards: list[Card]) -> tuple[str, int]:
    ranks = [card.rank for card in cards]
    suits = [card.suit for card in cards]
    rank_counts = sorted(Counter(ranks).values(), reverse=True)
    ordered = sorted(RANK_ORDER[rank] for rank in ranks)
    is_flush = len(set(suits)) == 1
    is_straight = len(set(ordered)) == 5 and ordered[-1] - ordered[0] == 4
    royal = set(ranks) == {"10", "J", "Q", "K", "A"}

    if royal and is_flush:
        return ("ロイヤルフラッシュ", 250)
    if is_straight and is_flush:
        return ("ストレートフラッシュ", 50)
    if rank_counts == [4, 1]:
        return ("フォーカード", 25)
    if rank_counts == [3, 2]:
        return ("フルハウス", 9)
    if is_flush:
        return ("フラッシュ", 6)
    if is_straight:
        return ("ストレート", 4)
    if rank_counts == [3, 1, 1]:
        return ("スリーカード", 3)
    if rank_counts == [2, 2, 1]:
        return ("ツーペア", 2)
    if rank_counts == [2, 1, 1, 1]:
        pair_rank = next(rank for rank, count in Counter(ranks).items() if count == 2)
        if pair_rank in {"J", "Q", "K", "A"}:
            return ("Jacks or Better", 1)
    return ("役なし", 0)
