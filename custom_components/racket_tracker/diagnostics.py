"""Diagnostics for Strung."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import RacketConfigEntry
from .specs import effective_specs
from .stats import summary
from .tension import play_settings


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
        "stats": summary(
            history.restrings,
            play_settings(entry.options, history.latest),
            dt_util.now().date(),
        ),
        "restrings": history.newest_first(),
    }
