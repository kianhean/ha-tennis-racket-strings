"""Run the shipped automation blueprints in a real Home Assistant.

Each blueprint is copied into a temporary config dir, instantiated with
`use_blueprint`, and driven through the integration's own actions, so it is
checked on every HA version in the CI matrix.
"""

from __future__ import annotations

import shutil
from datetime import timedelta
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.racket_tracker.const import DOMAIN

from .test_integration import _add_racket

BLUEPRINTS = Path(__file__).parents[1] / "blueprints" / "automation" / "racket_tracker"


@pytest.fixture
async def notify_calls(hass: HomeAssistant, tmp_path: Path) -> list[ServiceCall]:
    """Point HA at a config dir holding the blueprints; mock notify.notify."""
    hass.config.config_dir = str(tmp_path)
    shutil.copytree(
        BLUEPRINTS, tmp_path / "blueprints" / "automation" / "racket_tracker"
    )
    assert await async_setup_component(hass, "http", {})
    return async_mock_service(hass, "notify", "notify")


async def _automation(hass: HomeAssistant, blueprint: str, inputs: dict) -> None:
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "alias": "test",
                "use_blueprint": {
                    "path": f"racket_tracker/{blueprint}",
                    "input": inputs,
                },
            }
        },
    )
    await hass.async_block_till_done()
    # An invalid blueprint leaves the automation unavailable instead of "on".
    assert hass.states.get("automation.test").state == "on"


async def _restring(hass: HomeAssistant, entry_id: str, **data) -> None:
    await hass.services.async_call(
        DOMAIN,
        "add_restring",
        {
            "config_entry_id": entry_id,
            "main_string": "RPM Blast",
            "main_tension": 52,
            **data,
        },
        blocking=True,
    )
    await hass.async_block_till_done()


def test_every_blueprint_is_tested() -> None:
    tested = {
        "restring_reminder.yaml",
        "restring_due.yaml",
        "racket_picker.yaml",
        "racket_picker.yaml",
        "restring_logged.yaml",
        "rate_strings.yaml",
    }
    assert {p.name for p in BLUEPRINTS.glob("*.yaml")} == tested


async def test_restring_reminder(hass: HomeAssistant, notify_calls) -> None:
    entry_id = await _add_racket(hass)
    await _automation(
        hass,
        "restring_reminder.yaml",
        {"age_sensor": "sensor.pure_aero_days_since_restring", "days": 60},
    )
    await _restring(
        hass, entry_id, date=(dt_util.now().date() - timedelta(days=30)).isoformat()
    )
    assert notify_calls == []

    await _restring(
        hass, entry_id, date=(dt_util.now().date() - timedelta(days=60)).isoformat()
    )
    # Back-dated restring is older than the current one, so nothing changes yet
    assert notify_calls == []

    # Delete the newer one: the 60-day-old strings are now current
    history = hass.states.get("sensor.pure_aero_restrings").attributes["history"]
    await hass.services.async_call(
        DOMAIN,
        "delete_restring",
        {"config_entry_id": entry_id, "restring_id": history[0]["id"]},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert len(notify_calls) == 1
    assert notify_calls[0].data["message"] == "Pure Aero's strings are 60 days old."


async def test_restring_due(hass: HomeAssistant, notify_calls) -> None:
    entry_id = await _add_racket(hass)
    result = await hass.config_entries.options.async_init(entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "tension_unit": "lbs",
            "play": {"hours_per_week": 7},
            "due": {"days": 90, "min_tension": 40},
        },
    )
    await hass.async_block_till_done()
    await _automation(
        hass,
        "restring_due.yaml",
        {"due_sensor": "binary_sensor.pure_aero_restring_due"},
    )
    await _restring(
        hass, entry_id, date=(dt_util.now().date() - timedelta(days=5)).isoformat()
    )
    assert notify_calls == []

    # 52 → 40 lbs is 23.1 % loss: 10 % + 4 % × log10(8) + 3 % × log2(1 + 8 h) on day 8
    await hass.services.async_call(
        DOMAIN,
        "update_restring",
        {
            "config_entry_id": entry_id,
            "date": (dt_util.now().date() - timedelta(days=8)).isoformat(),
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    assert len(notify_calls) == 1
    assert notify_calls[0].data["message"] == (
        "Pure Aero's strings are estimated to be down to the tension you set."
    )


async def test_restring_logged(hass: HomeAssistant, notify_calls) -> None:
    entry_id = await _add_racket(hass)
    await _automation(hass, "restring_logged.yaml", {"racket": entry_id})
    await _restring(hass, entry_id, cross_string="VS Touch", cross_tension=50, cost=900)
    assert len(notify_calls) == 1
    call = notify_calls[0].data
    assert call["title"] == "Restrung: Pure Aero"
    assert call["message"] == "RPM Blast / VS Touch @ 52/50 lbs · 900"
    assert call["data"] == {"image": ""}


async def test_restring_logged_other_racket_ignored(
    hass: HomeAssistant, notify_calls
) -> None:
    entry_id = await _add_racket(hass)
    await _automation(hass, "restring_logged.yaml", {"racket": "some_other_entry"})
    await _restring(hass, entry_id)
    assert notify_calls == []


async def test_rate_strings(hass: HomeAssistant, notify_calls) -> None:
    entry_id = await _add_racket(hass)
    await _automation(
        hass,
        "rate_strings.yaml",
        {"strings_sensor": "sensor.pure_aero_strings", "days": 3},
    )
    await _restring(
        hass, entry_id, date=(dt_util.now().date() - timedelta(days=1)).isoformat()
    )
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=2))
    await hass.async_block_till_done()
    assert notify_calls == []

    await hass.services.async_call(
        DOMAIN,
        "update_restring",
        {
            "config_entry_id": entry_id,
            "date": (dt_util.now().date() - timedelta(days=3)).isoformat(),
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    assert len(notify_calls) == 1
    assert "Rate RPM Blast on Pure Aero" in notify_calls[0].data["message"]


async def test_racket_picker(hass: HomeAssistant, notify_calls) -> None:
    from homeassistant import config_entries

    assert await async_setup_component(
        hass, "input_select", {"input_select": {"racket": {"options": ["—"]}}}
    )
    first = await _add_racket(hass)
    await _automation(hass, "racket_picker.yaml", {"picker": "input_select.racket"})

    async def add(name: str) -> str:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"name": name, "tension_unit": "lbs"}
        )
        await hass.async_block_till_done()
        return result["result"].entry_id

    def options() -> list[str]:
        return hass.states.get("input_select.racket").attributes["options"]

    # Adding a racket fills the dropdown with every racket, sorted
    blade = await add("Blade")
    assert options() == ["Blade", "Pure Aero"]

    # Renaming follows
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": first},
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Match racket"}
    )
    await hass.async_block_till_done()
    assert options() == ["Blade", "Match racket"]

    # Removing one drops it
    await hass.config_entries.async_remove(blade)
    await hass.async_block_till_done()
    assert options() == ["Match racket"]
