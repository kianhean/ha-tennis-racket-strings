"""Estimated tension from hours of play per week."""

from __future__ import annotations

from datetime import date, timedelta

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.racket_tracker.const import DOMAIN
from custom_components.racket_tracker.tension import (
    PlaySettings,
    estimate,
    play_settings,
)


def test_estimate_model() -> None:
    settings = PlaySettings(hours_per_week=4, initial_loss=10, loss_per_hour=1)
    record = {"date": "2026-01-01", "main_tension": 52, "cross_tension": 50}
    # Strung today: only the initial loss
    est = estimate(record, settings, date(2026, 1, 1))
    assert (est.hours_played, est.loss_percent, est.main_tension) == (0, 10, 46.8)
    # Two weeks later: 8 hours played, 18 % lost
    est = estimate(record, settings, date(2026, 1, 15))
    assert est.hours_played == 8
    assert est.loss_percent == 18
    assert est.main_tension == 42.6
    assert est.cross_tension == 41
    # Capped at 50 %
    assert estimate(record, settings, date(2027, 1, 1)).loss_percent == 50
    assert estimate(None, settings, date(2026, 1, 1)) is None

    assert play_settings({}) is None
    assert play_settings({"play": {"hours_per_week": 3}}) == PlaySettings(3, 10, 1)


async def test_estimate_sensors(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Blade",
            "tension_unit": "kg",
            "play": {"hours_per_week": 7, "tension_loss_per_hour": 0.5},
        },
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.options["play"] == {"hours_per_week": 7, "tension_loss_per_hour": 0.5}

    # No restring yet: no estimate
    assert hass.states.get("sensor.blade_estimated_tension").state == "unknown"

    ten_days_ago = (dt_util.now().date() - timedelta(days=10)).isoformat()
    await hass.services.async_call(
        DOMAIN,
        "add_restring",
        {
            "config_entry_id": entry.entry_id,
            "date": ten_days_ago,
            "main_string": "RPM Blast",
            "cross_string": "VS Gut",
            "main_tension": 25,
            "cross_tension": 24,
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    # 10 h played: 10 % + 0.5 % × 10 = 15 %
    tension = hass.states.get("sensor.blade_estimated_tension")
    assert float(tension.state) == 21.2
    assert tension.attributes["unit_of_measurement"] == "kg"
    assert tension.attributes["strung_tension"] == 25
    assert tension.attributes["estimated_cross_tension"] == 20.4
    assert float(hass.states.get("sensor.blade_estimated_tension_loss").state) == 15
    assert float(hass.states.get("sensor.blade_hours_played").state) == 10

    # Clearing hours per week removes the estimates
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tension_unit": "kg", "play": {}}
    )
    await hass.async_block_till_done()
    assert "play" not in entry.options
    assert hass.states.get("sensor.blade_estimated_tension") is None
    assert er.async_get(hass).async_get("sensor.blade_hours_played") is None
