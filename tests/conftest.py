"""Fixtures."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations in all tests."""
    return


@pytest.fixture(autouse=True)
def no_dataset_refresh_on_start():
    """No background download of the racket list (test_dataset tests it on its own)."""
    with patch("custom_components.racket_tracker.async_schedule_refresh"):
        yield
