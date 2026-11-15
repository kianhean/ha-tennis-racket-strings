"""Restring due rules, the due/next restring entities, calendar, repeat and rename."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.racket_tracker.const import DOMAIN, EVENT_RESTRUNG
from custom_components.racket_tracker.due import next_due

from .test_integration import _add_racket

D = date(2026, 1, 1)
REC = {"date": D.isoformat(), "main_tension": 50}


def _days_ago(days: int) -> str:
    return (dt_util.now().date() - timedelta(days=days)).isoformat()


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({}, None),
        ({"due": {"days": 60}}, (60, "days")),
        # Hours and tension rules need hours per week
        ({"due": {"hours_played": 10}}, None),
        (
            {"due": {"hours_played": 10}, "play": {"hours_per_week": 4}},
            (18, "hours_played"),
        ),
        # 50 lbs → 45: 10 % loss = the initial loss, due on the day
        (
            {"due": {"min_tension": 45}, "play": {"hours_per_week": 4}},
            (0, "min_tension"),
        ),
        # 50 → 40 lbs: 20 % = 10 % initial + 10 h at 1 %/h = 17.5 days
        (
            {"due": {"min_tension": 40}, "play": {"hours_per_week": 4}},
            (18, "min_tension"),
        ),
        # Never that low (the estimate is capped at 50 % loss)
        ({"due": {"min_tension": 20}, "play": {"hours_per_week": 4}}, None),
        # Earliest rule wins
        (
            {"due": {"days": 10, "hours_played": 10}, "play": {"hours_per_week": 4}},
            (10, "days"),
        ),
        (
            {"due": {"days": 90, "hours_played": 8}, "play": {"hours_per_week": 8}},
            (7, "hours_played"),
        ),
        # Nobody plays: only the days rule can fire
        ({"due": {"hours_played": 8}, "play": {"hours_per_week": 0}}, None),
    ],
)
def test_next_due(options, expected) -> None:
    due = next_due(REC, options)
    if expected is None:
        assert due is None
    else:
        assert ((due.date - D).days, due.reason) == expected


def test_next_due_without_restring() -> None:
    assert next_due(None, {"due": {"days": 1}}) is None
    assert next_due({"date": D.isoformat()}, {"due": {"min_tension": 40}}) is None


async def _configure(hass: HomeAssistant, entry_id: str, **options) -> dict:
    result = await hass.config_entries.options.async_init(entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tension_unit": "lbs", **options}
    )
    await hass.async_block_till_done()
    return result


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


async def test_due_entities(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "http", {})
    entry_id = await _add_racket(hass)
    # No rule: no due entities
    assert hass.states.get("binary_sensor.pure_aero_restring_due") is None
    assert hass.states.get("sensor.pure_aero_next_restring") is None

    # Hours rule without hours per week is refused
    result = await _configure(hass, entry_id, due={"hours_played": 20})
    assert result["errors"] == {"base": "due_needs_play"}

    await _configure(hass, entry_id, due={"days": 30})
    due = hass.states.get("binary_sensor.pure_aero_restring_due")
    assert due.state == "unknown"  # nothing strung yet
    assert hass.states.get("sensor.pure_aero_next_restring").state == "unknown"

    await _restring(hass, entry_id, date=_days_ago(10))
    due = hass.states.get("binary_sensor.pure_aero_restring_due")
    assert due.state == "off"
    assert due.attributes["days_until_due"] == 20
    assert due.attributes["reason"] == "days"
    assert (
        hass.states.get("sensor.pure_aero_next_restring").state
        == (dt_util.now().date() + timedelta(days=20)).isoformat()
    )

    await hass.services.async_call(
        DOMAIN,
        "update_restring",
        {"config_entry_id": entry_id, "date": _days_ago(30)},
        blocking=True,
    )
    await hass.async_block_till_done()
    due = hass.states.get("binary_sensor.pure_aero_restring_due")
    assert due.state == "on" and due.attributes["days_until_due"] == 0

    # Clearing the rule removes the entities
    await _configure(hass, entry_id)
    registry = er.async_get(hass)
    assert registry.async_get("binary_sensor.pure_aero_restring_due") is None
    assert registry.async_get("sensor.pure_aero_next_restring") is None


async def test_calendar(hass: HomeAssistant, hass_client) -> None:
    assert await async_setup_component(hass, "http", {})
    entry_id = await _add_racket(hass)
    await _configure(hass, entry_id, due={"days": 30})
    await _restring(
        hass,
        entry_id,
        date=_days_ago(40),
        main_string="Hyper-G",
        cross_string="VS Touch",
        main_tension=50,
        cross_tension=48,
        stringer="Pro shop",
        cost=900,
        rating=4,
        notes="Great spin",
    )
    await _restring(hass, entry_id, date=_days_ago(5))

    cal = hass.states.get("calendar.pure_aero_restrings")
    # Next event: the restring due date
    assert cal.attributes["message"] == "Restring due"
    assert cal.attributes["start_time"].startswith(
        (dt_util.now().date() + timedelta(days=25)).isoformat()
    )

    client = await hass_client()
    start = (dt_util.now() - timedelta(days=60)).isoformat()
    end = (dt_util.now() + timedelta(days=60)).isoformat()
    r = await client.get(
        "/api/calendars/calendar.pure_aero_restrings",
        params={"start": start, "end": end},
    )
    assert r.status == 200
    events = await r.json()
    assert [e["summary"] for e in events] == [
        "Restrung: Hyper-G / VS Touch",
        "Restrung: RPM Blast",
        "Restring due",
    ]
    assert events[0]["start"] == {"date": _days_ago(40)}
    assert events[0]["description"] == (
        "Strung at 50/48 lbs · by Pro shop · cost 900 · ★★★★\n\nGreat spin"
    )
    assert events[1]["description"] == "Strung at 52 lbs"

    # A range with nothing in it
    r = await client.get(
        "/api/calendars/calendar.pure_aero_restrings",
        params={
            "start": (dt_util.now() - timedelta(days=400)).isoformat(),
            "end": (dt_util.now() - timedelta(days=300)).isoformat(),
        },
    )
    assert await r.json() == []


async def test_repeat_restring(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "http", {})
    entry_id = await _add_racket(hass)
    events = async_capture_events(hass, EVENT_RESTRUNG)

    # Nothing to repeat yet
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "repeat_restring", {"config_entry_id": entry_id}, blocking=True
        )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.pure_aero_restring_with_usual_setup"},
            blocking=True,
        )

    # Without a usual setup the latest restring is repeated
    await _restring(
        hass,
        entry_id,
        date=_days_ago(30),
        main_string="Hyper-G",
        cross_string="VS Touch",
        main_tension=50,
        cross_tension=48,
        stringer="Shop",
        cost=900,
        rating=5,
        notes="Great",
    )
    first = hass.states.get("sensor.pure_aero_strings").attributes["restring_id"]
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.pure_aero_restring_with_usual_setup"},
        blocking=True,
    )
    await hass.async_block_till_done()
    a = hass.states.get("sensor.pure_aero_strings").attributes
    assert a["date"] == dt_util.now().date().isoformat()
    assert (a["main_string"], a["cross_string"]) == ("Hyper-G", "VS Touch")
    assert (a["main_tension"], a["cross_tension"]) == (50, 48)
    assert (a["stringer"], a["cost"]) == ("Shop", 900)
    # Rating and notes belong to the old strings
    assert a["rating"] is None and a["notes"] is None
    assert len(events) == 2

    # A usual setup takes precedence; floats from the form are stored as ints
    result = await _configure(hass, entry_id, setup={"main_tension": 52.0})
    assert result["errors"] == {"base": "setup_incomplete"}
    await _configure(
        hass, entry_id, setup={"main_string": " RPM Blast ", "main_tension": 52.0}
    )
    resp = await hass.services.async_call(
        DOMAIN,
        "repeat_restring",
        {"config_entry_id": entry_id, "date": "2030-01-01", "cost": 700},
        blocking=True,
        return_response=True,
    )
    r = resp["restring"]
    assert (r["main_string"], r["cross_string"]) == ("RPM Blast", "RPM Blast")
    assert (r["main_tension"], r["cross_tension"]) == (52, 52)
    assert isinstance(r["main_tension"], int)
    assert r["cost"] == 700 and "stringer" not in r

    # Or copy a past restring
    resp = await hass.services.async_call(
        DOMAIN,
        "repeat_restring",
        {"config_entry_id": entry_id, "restring_id": first},
        blocking=True,
        return_response=True,
    )
    assert resp["restring"]["cross_string"] == "VS Touch"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "repeat_restring",
            {"config_entry_id": entry_id, "restring_id": "nope"},
            blocking=True,
        )


async def test_rename(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "http", {})
    entry_id = await _add_racket(hass)
    entry = hass.config_entries.async_get_entry(entry_id)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry_id},
    )
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "  "}
    )
    assert result["errors"] == {"name": "name_required"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Match racket"}
    )
    assert result["type"] == "abort" and result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.title == "Match racket"
    # Entity IDs stay; the device takes the new name
    state = hass.states.get("sensor.pure_aero_strings")
    assert state.attributes["friendly_name"] == "Match racket Strings"


async def test_new_flow_sections(hass: HomeAssistant) -> None:
    """The add flow takes the same sections as the options flow."""
    assert await async_setup_component(hass, "http", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Blade",
            "tension_unit": "kg",
            "play": {"hours_per_week": 3},
            "due": {"min_tension": 20},
            "setup": {"main_string": "", "stringer": " "},
        },
    )
    assert result["type"] == "create_entry"
    assert result["options"]["due"] == {"min_tension": 20}
    assert "setup" not in result["options"]
