"""Variant registry for resolving Solitaire rules by name and options."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, TypeAlias

from patiencepilot.exceptions import InvalidStateError, UnsupportedVariantError
from patiencepilot.state import GameState
from patiencepilot.variants.base import Variant
from patiencepilot.variants.klondike import KlondikeRules

VariantOptions: TypeAlias = Mapping[str, object]


class VariantFactory(Protocol):
    """Callable that creates a variant rules object from option values."""

    def __call__(self, options: VariantOptions) -> Variant:
        """Return a variant rules object."""
        ...


class StateOptionsResolver(Protocol):
    """Callable that extracts variant options from a state."""

    def __call__(self, state: GameState) -> dict[str, object]:
        """Return JSON-compatible variant options for ``state``."""
        ...


@dataclass(frozen=True, slots=True)
class VariantDefinition:
    """Registered Solitaire variant plus its option conversion functions."""

    name: str
    factory: VariantFactory
    state_options: StateOptionsResolver
    aliases: tuple[str, ...] = ()

    def resolve(self, options: VariantOptions | None = None) -> Variant:
        """Return a rules object for this variant.

        Args:
            options: Variant-specific configuration values.
        """
        return self.factory({} if options is None else options)


@dataclass(frozen=True, slots=True)
class VariantRegistry:
    """Small immutable registry of supported Solitaire variants."""

    definitions: tuple[VariantDefinition, ...]

    def __post_init__(self) -> None:
        """Validate registry keys."""
        keys: set[str] = set()
        for definition in self.definitions:
            for name in (definition.name, *definition.aliases):
                normalized = _normalize_variant_name(name)
                if normalized in keys:
                    msg = f"duplicate variant registry name: {name!r}"
                    raise InvalidStateError(msg)
                keys.add(normalized)

    @property
    def names(self) -> tuple[str, ...]:
        """Return canonical registered variant names."""
        return tuple(definition.name for definition in self.definitions)

    def register(self, definition: VariantDefinition) -> VariantRegistry:
        """Return a new registry that also contains ``definition``.

        Args:
            definition: Variant definition to add.
        """
        return VariantRegistry((*self.definitions, definition))

    def definition_for(self, name: str) -> VariantDefinition:
        """Return the registered definition for ``name`` or alias.

        Args:
            name: Variant name or alias.

        Raises:
            UnsupportedVariantError: If no variant is registered for ``name``.
        """
        normalized = _normalize_variant_name(name)
        for definition in self.definitions:
            if normalized == _normalize_variant_name(definition.name):
                return definition
            if any(normalized == _normalize_variant_name(alias) for alias in definition.aliases):
                return definition

        msg = f"unsupported variant: {name!r}"
        raise UnsupportedVariantError(msg)

    def resolve(self, name: str, options: VariantOptions | None = None) -> Variant:
        """Return a rules object by variant name and options.

        Args:
            name: Variant name or alias.
            options: Variant-specific configuration values.
        """
        return self.definition_for(name).resolve(options)

    def options_from_state(self, state: GameState) -> dict[str, object]:
        """Return registry options that reproduce ``state`` rules.

        Args:
            state: State whose variant metadata should be converted.
        """
        return self.definition_for(state.variant).state_options(state)

    def resolve_state(self, state: GameState) -> Variant:
        """Return rules for the variant metadata stored in ``state``.

        Args:
            state: State containing variant name and option metadata.
        """
        return self.resolve(state.variant, self.options_from_state(state))


def resolve_variant(
    name: str = KlondikeRules.name,
    options: VariantOptions | None = None,
    *,
    registry: VariantRegistry | None = None,
) -> Variant:
    """Return rules for a registered variant name and options.

    Args:
        name: Variant name or alias. Defaults to ``"klondike"``.
        options: Variant-specific configuration values.
        registry: Registry to use. Defaults to the package registry.
    """
    return _registry_or_default(registry).resolve(name, options)


def resolve_state_variant(state: GameState, *, registry: VariantRegistry | None = None) -> Variant:
    """Return rules for the variant metadata stored in ``state``.

    Args:
        state: State containing variant name and option metadata.
        registry: Registry to use. Defaults to the package registry.
    """
    return _registry_or_default(registry).resolve_state(state)


def variant_options_from_state(state: GameState, *, registry: VariantRegistry | None = None) -> dict[str, object]:
    """Return registry options that reproduce ``state`` rules.

    Args:
        state: State containing variant name and option metadata.
        registry: Registry to use. Defaults to the package registry.
    """
    return _registry_or_default(registry).options_from_state(state)


def variant_names(*, registry: VariantRegistry | None = None) -> tuple[str, ...]:
    """Return canonical names of registered variants."""
    return _registry_or_default(registry).names


def _registry_or_default(registry: VariantRegistry | None) -> VariantRegistry:
    """Return ``registry`` or the package default registry."""
    if registry is not None:
        return registry
    return DEFAULT_VARIANT_REGISTRY


def _klondike_factory(options: VariantOptions) -> Variant:
    """Create Klondike rules from registry options."""
    _reject_unknown_options(KlondikeRules.name, options, allowed={"draw_count", "redeals"})
    return KlondikeRules(
        draw_count=_int_option(options, "draw_count", default=1),
        redeals=_optional_int_option(options, "redeals", default=None),
    )


def _klondike_options_from_state(state: GameState) -> dict[str, object]:
    """Return Klondike options from state metadata."""
    return {
        "draw_count": state.draw_count,
        "redeals": state.redeals_allowed,
    }


def _reject_unknown_options(variant_name: str, options: VariantOptions, *, allowed: set[str]) -> None:
    """Reject unsupported option names."""
    unknown = tuple(sorted(set(options) - allowed))
    if unknown:
        msg = f"unsupported {variant_name} option(s): {', '.join(unknown)}"
        raise InvalidStateError(msg)


def _int_option(options: VariantOptions, name: str, *, default: int) -> int:
    """Return an integer option value."""
    value = options.get(name, default)
    if type(value) is not int:
        msg = f"{name} must be an integer"
        raise InvalidStateError(msg)
    return value


def _optional_int_option(options: VariantOptions, name: str, *, default: int | None) -> int | None:
    """Return an optional integer option value."""
    value = options.get(name, default)
    if value is None:
        return None
    if type(value) is not int:
        msg = f"{name} must be an integer or None"
        raise InvalidStateError(msg)
    return value


def _normalize_variant_name(name: str) -> str:
    """Normalize a variant registry key."""
    normalized = name.strip().casefold()
    if not normalized:
        msg = "variant name cannot be empty"
        raise UnsupportedVariantError(msg)
    return normalized


DEFAULT_VARIANT_REGISTRY = VariantRegistry(
    (
        VariantDefinition(
            name=KlondikeRules.name,
            factory=_klondike_factory,
            state_options=_klondike_options_from_state,
        ),
    )
)
