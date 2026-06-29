"""Tests for public package exports and exception hierarchy."""

from __future__ import annotations

import pytest

import patiencepilot

pytestmark = pytest.mark.unit


def test_public_api_exports_expected_names() -> None:
    expected_exports = {
        "__version__",
        "PatiencePilotError",
    }

    assert set(patiencepilot.__all__) == expected_exports

    for name in patiencepilot.__all__:
        assert hasattr(patiencepilot, name)


def test_package_version_is_resolved() -> None:
    assert patiencepilot.__version__
    assert "unknown" not in patiencepilot.__version__
