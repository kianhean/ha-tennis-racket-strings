"""Diagnostics for Racket String Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import RacketConfigEntry
from .specs import effective_specs


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: RacketConfigEntry
) -> dict[str, Any]:
    """Return the racket's options and full restring history."""
    history = entry.runtime_data
    return {
        "title": entry.title,
        "options": dict(entry.options),
        "specs": effective_specs(entry),
        "restring_count": history.count,
        "total_cost": history.total_cost,
        "restrings": history.newest_first(),
    }
