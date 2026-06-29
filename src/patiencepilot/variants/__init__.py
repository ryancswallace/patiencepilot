"""Solitaire variant implementations."""

from .base import Seed, Variant
from .klondike import KlondikeRules

__all__ = [
    "KlondikeRules",
    "Seed",
    "Variant",
]
