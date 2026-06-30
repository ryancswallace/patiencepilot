"""Solitaire variant implementations."""

from .base import Seed, Variant
from .klondike import KlondikeRules
from .registry import (
    DEFAULT_VARIANT_REGISTRY,
    VariantDefinition,
    VariantOptions,
    VariantRegistry,
    resolve_state_variant,
    resolve_variant,
    variant_names,
    variant_options_from_state,
)

__all__ = [
    "DEFAULT_VARIANT_REGISTRY",
    "KlondikeRules",
    "Seed",
    "Variant",
    "VariantDefinition",
    "VariantOptions",
    "VariantRegistry",
    "resolve_state_variant",
    "resolve_variant",
    "variant_names",
    "variant_options_from_state",
]
