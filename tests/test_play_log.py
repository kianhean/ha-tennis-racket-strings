"""Logged play sessions: tracking "logged" instead of hours per week."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from custom_components.racket_tracker.const import DOMAIN
from custom_components.racket_tracker.due import next_due
from custom_components.racket_tracker.stats import average_life_hours, summary
from custom_components.racket_tracker.tension import (
    STRING_TYPES,
    estimate,
    hours_played,
    logged_pace,
    loss_percent,
    play_settings,
)

from .test_due import _configure, _restring
from .test_integration import _add_racket

D = date(2026, 1, 1)
REC = {"date": D.isoformat(), "main_tension": 50}
LOGGED = {"play": {"tracking": "logged"}}


def _on(days: int) -> date:
    return D + timedelta(days=days)


def test_weekly_is_unchanged() -> None:
    settings = play_settings({"play": {"hours_per_week": 7}})
    assert settings.tracking == "weekly"
    assert hours_played(settings, D, _on(10)) == 10
    # Sessions are ignored when counting hours per week
    with_sessions = play_settings(
        {"play": {"hours_per_week": 7}}, REC, ((_on(1), 5.0),), _on(3)
    )
    assert hours_played(with_sessions, D, _on(10)) == 10


def test_logged_hours() -> None:
    sessions = ((_on(-1), 9.0), (_on(0), 1.5), (_on(3), 2.0), (_on(9), 4.0))
    settings = play_settings(LOGGED, REC, sessions, today=_on(5))
    assert settings.tracking == "logged"
    # Only sessions from stringing on, up to the day asked for
    assert hours_played(settings, D, _on(0)) == 1.5
    assert hours_played(settings, D, _on(5)) == 3.5
    # The session dated after today isn't counted; the forecast pace is the last
    # four weeks' (3.5 h logged up to today, 9 h the day before stringing)
    assert settings.hours_per_week == logged_pace(sessions, _on(5))
    assert settings.hours_per_week == round(12.5 * 7 / 28, 2)
    assert hours_played(settings, D, _on(12)) == 3.5 + settings.hours_per_week

    est = estimate(REC, settings, _on(5))
    assert est.hours_played == 3.5
    rates = STRING_TYPES["polyester"]
    assert est.loss_percent == round(loss_percent(rates, 5, 3.5), 1)


def test_logged_with_hours_per_week_forecast() -> None:
    options = {"play": {"tracking": "logged", "hours_per_week": 14}}
    settings = play_settings(options, REC, ((_on(1), 1.0),), today=_on(2))
    assert settings.hours_per_week == 14
    assert hours_played(settings, D, _on(2)) == 1
    assert hours_played(settings, D, _on(4)) == 5
    # Without today (backfill), only what was logged
    past = play_settings(options, REC, ((_on(1), 1.0),))
    assert hours_played(past, D, _on(30)) == 1


def test_logged_without_sessions() -> None:
    settings = play_settings(LOGGED, REC, (), today=_on(3))
    assert settings is not None
    assert settings.hours_per_week == 0
    assert estimate(REC, settings, _on(3)).hours_played == 0


def test_next_due_logged() -> None:
    rules = {**LOGGED, "due": {"hours_played": 5}}
    # Reached on a session's day: that day
    sessions = ((_on(2), 3.0), (_on(6), 2.5))
    assert next_due(REC, rules, sessions, _on(8)).date == _on(6)
    # Not reached: forecast at the last four weeks' pace (3 h → 0.75 h/week)
    due = next_due(REC, rules, sessions[:1], _on(8))
    assert due.reason == "hours_played"
    assert due.date == _on(8) + timedelta(days=19)
    # Nothing logged and no hours per week: no forecast
    assert next_due(REC, rules, (), _on(8)) is None
    # The tension rule forecasts too
    tension = next_due(REC, {**LOGGED, "due": {"min_tension": 40}}, sessions, _on(8))
    assert tension is not None
    assert tension.reason == "min_tension"


def test_stats_logged() -> None:
    records = [
        {"date": D.isoformat(), "main_string": "A", "cost": 20},
        {"date": _on(10).isoformat(), "main_string": "B", "cost": 20},
        {"date": _on(20).isoformat(), "main_string": "C", "broken_date": _on(25)},
    ]
    records[2]["broken_date"] = _on(25).isoformat()
    sessions = (
        (_on(0), 1.0),
        (_on(9), 2.0),
        (_on(10), 4.0),  # The new strings' first hit
        (_on(25), 1.0),  # Broke during this one
        (_on(26), 3.0),
    )
    settings = play_settings(LOGGED, records[-1], sessions, _on(30))
    # Beds: 3 h, 4 h, 1 h
    assert average_life_hours(records, settings) == round(8 / 3, 1)
    stats = summary(records, settings, _on(30))
    assert stats["cost_per_hour"] == round(40 / 11, 2)


async def test_log_play(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "http", {})
    entry_id = await _add_racket(hass)
    await _restring(hass, entry_id)
    today = dt_util.now().date()

    # Counting hours per week: logging play is refused, no button
    await _configure(hass, entry_id, play={"hours_per_week": 3})
    with pytest.raises(ServiceValidationError, match="Logged sessions"):
        await hass.services.async_call(
            DOMAIN,
            "log_play",
            {"config_entry_id": entry_id, "hours": 1},
            blocking=True,
        )
    assert hass.states.get("button.pure_aero_log_play_session") is None

    # Logged sessions: no hours per week needed, even for a play-based rule
    result = await _configure(
        hass,
        entry_id,
        play={"tracking": "logged", "session_hours": 2},
        due={"hours_played": 6},
    )
    assert result["type"] == "create_entry"
    assert float(hass.states.get("sensor.pure_aero_hours_played").state) == 0

    response = await hass.services.async_call(
        DOMAIN,
        "log_play",
        {"config_entry_id": entry_id, "hours": 1.5, "notes": "Doubles"},
        blocking=True,
        return_response=True,
    )
    assert response["session"]["hours"] == 1.5
    assert response["session"]["date"] == today.isoformat()
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.pure_aero_log_play_session"},
        blocking=True,
    )
    await hass.async_block_till_done()
    hours = hass.states.get("sensor.pure_aero_hours_played")
    assert float(hours.state) == 3.5
    assert hours.attributes["sessions"] == 2
    assert hours.attributes["tracking"] == "logged"
    assert hass.states.get("binary_sensor.pure_aero_restring_due").state == "off"

    # A third session reaches the 6 h rule: due today
    await hass.services.async_call(
        DOMAIN,
        "log_play",
        {"config_entry_id": entry_id, "hours": 3},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.pure_aero_restring_due").state == "on"
    assert hass.states.get("sensor.pure_aero_next_restring").state == today.isoformat()

    # Delete the session logged last: not due any more
    response = await hass.services.async_call(
        DOMAIN,
        "delete_play",
        {"config_entry_id": entry_id},
        blocking=True,
        return_response=True,
    )
    assert response["session"]["hours"] == 3
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.pure_aero_hours_played").state) == 3.5
    assert hass.states.get("binary_sensor.pure_aero_restring_due").state == "off"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "delete_play",
            {"config_entry_id": entry_id, "session_id": "nope"},
            blocking=True,
        )

    history = await hass.services.async_call(
        DOMAIN,
        "get_history",
        {"config_entry_id": entry_id},
        blocking=True,
        return_response=True,
    )
    assert [s["hours"] for s in history["play_sessions"]] == [2, 1.5]
    assert history["stats"]["cost_per_hour"] is None  # No cost logged

    # Sessions survive a reload
    await hass.config_entries.async_reload(entry_id)
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.pure_aero_hours_played").state) == 3.5

    # Back to hours per week: the button goes
    await _configure(hass, entry_id, play={"hours_per_week": 3})
    assert hass.states.get("button.pure_aero_log_play_session") is None

    # All sessions deleted, then nothing to delete
    entry = hass.config_entries.async_get_entry(entry_id)
    for session in list(entry.runtime_data.sessions):
        await entry.runtime_data.async_delete_session(session["id"])
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "delete_play", {"config_entry_id": entry_id}, blocking=True
        )
