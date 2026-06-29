"""Tests for public package exports and exception hierarchy."""

from __future__ import annotations

import pytest

import solitaire

pytestmark = pytest.mark.unit


def test_public_api_exports_expected_names() -> None:
    expected_exports = {
        "__version__",
        "SolitaireError",
    }

    assert set(solitaire.__all__) == expected_exports

    for name in solitaire.__all__:
        assert hasattr(solitaire, name)


def test_package_version_is_resolved() -> None:
    assert solitaire.__version__
    assert "unknown" not in solitaire.__version__
