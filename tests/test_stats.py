"""String life, breakages, costs and favourite setups."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.racket_tracker.const import DOMAIN
from custom_components.racket_tracker.stats import (
    average_days_to_break,
    average_life_days,
    best_rated_string,
    breakage_rate,
    breakages,
    cost_in_year,
    cost_per_hour,
    most_used_string,
    string_counts,
    string_lives,
    summary,
)
from custom_components.racket_tracker.tension import play_settings

RECORDS = [
    {
        "id": "a",
        "date": "2026-01-01",
        "main_string": "RPM Blast",
        "cost": 30,
        "rating": 3,
        "broken_date": "2026-01-21",
    },
    {"id": "b", "date": "2026-02-01", "main_string": "RPM Blast", "rating": 5},
    {
        "id": "c",
        "date": "2026-03-01",
        "main_string": "Hyper-G",
        "cross_string": "VS Touch",
        "cost": 45,
        "rating": 5,
    },
    {"id": "d", "date": "2025-12-01", "main_string": "Hyper-G", "cost": 25},
]
RECORDS.sort(key=lambda r: r["date"])


def test_string_life_and_breakages() -> None:
    lives = string_lives(RECORDS)
    # d ends at a (31 d), a broke after 20 d, b ends at c (28 d); c is current
    assert [(life.record["id"], life.days, life.broken) for life in lives] == [
        ("d", 31, False),
        ("a", 20, True),
        ("b", 28, False),
    ]
    assert average_life_days(RECORDS) == 26.3
    assert average_days_to_break(RECORDS) == 20
    assert breakages(RECORDS) == 1
    assert breakage_rate(RECORDS) == 33.3
    assert average_life_days([]) is None and breakage_rate([]) is None

    # The current strings count once they break
    current = [*RECORDS[:-1], {**RECORDS[-1], "broken_date": "2026-03-11"}]
    assert string_lives(current)[-1].days == 10


def test_costs_and_favourites() -> None:
    assert cost_in_year(RECORDS, 2026) == 75
    assert cost_in_year(RECORDS, 2025) == 25
    settings = play_settings({"play": {"hours_per_week": 7}})
    # 100 € over 98 days at 1 h/day
    assert cost_per_hour(RECORDS, settings, date(2026, 3, 9)) == 1.02
    assert cost_per_hour([], settings, date(2026, 3, 9)) is None

    assert string_counts(RECORDS) == {
        "RPM Blast": 2,
        "Hyper-G": 1,
        "Hyper-G / VS Touch": 1,
    }
    assert most_used_string(RECORDS) == ("RPM Blast", 2)
    # RPM Blast averages 4; the hybrid's single 5 wins
    assert best_rated_string(RECORDS) == ("Hyper-G / VS Touch", 5, 1)
    assert best_rated_string([{"main_string": "X"}]) is None

    stats = summary(RECORDS, settings, date(2026, 3, 9))
    assert stats["breakages"] == 1 and stats["average_string_life_hours"] == 26.3
    assert "cost_per_hour" not in summary(RECORDS, None, date(2026, 3, 9))


async def test_stats_sensors_and_broken_strings(hass: HomeAssistant) -> None:
    hass.config.currency = "EUR"
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Aero", "tension_unit": "lbs", "play": {"hours_per_week": 7}},
    )
    entry_id = result["result"].entry_id
    await hass.async_block_till_done()
    today = dt_util.now().date()

    async def add(days_ago: int, **data) -> None:
        await hass.services.async_call(
            DOMAIN,
            "add_restring",
            {
                "config_entry_id": entry_id,
                "date": (today - timedelta(days=days_ago)).isoformat(),
                "main_tension": 52,
                **data,
            },
            blocking=True,
        )

    assert hass.states.get("sensor.aero_average_string_life").state == "unknown"
    assert hass.states.get("button.aero_strings_broke") is not None

    await add(40, main_string="RPM Blast", cost=30, rating=3)
    await add(10, main_string="RPM Blast", cost=30, rating=5)
    await hass.async_block_till_done()

    life = hass.states.get("sensor.aero_average_string_life")
    assert float(life.state) == 30
    assert life.attributes["average_hours_played"] == 30
    assert hass.states.get("sensor.aero_string_breakages").state == "0"
    year = hass.states.get("sensor.aero_string_cost_this_year")
    assert year.attributes["unit_of_measurement"] == "EUR"
    assert float(year.state) == sum(
        30 for d in (40, 10) if (today - timedelta(days=d)).year == today.year
    )
    per_hour = hass.states.get("sensor.aero_string_cost_per_hour")
    assert per_hour.attributes["unit_of_measurement"] == "EUR/h"
    assert float(per_hour.state) == 1.5  # 60 EUR over 40 h
    used = hass.states.get("sensor.aero_most_used_setup")
    assert used.state == "RPM Blast"
    assert used.attributes["string_counts"] == {"RPM Blast": 2}
    best = hass.states.get("sensor.aero_best_rated_setup")
    assert best.state == "RPM Blast" and best.attributes["average_rating"] == 4

    # The strings broke: the button marks the current restring
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.aero_strings_broke"}, blocking=True
    )
    await hass.async_block_till_done()
    breaks = hass.states.get("sensor.aero_string_breakages")
    assert breaks.state == "1"
    assert breaks.attributes["last_broken"] == today.isoformat()
    assert breaks.attributes["breakage_rate"] == 50
    strings = hass.states.get("sensor.aero_strings")
    assert strings.attributes["broken_date"] == today.isoformat()
    assert float(hass.states.get("sensor.aero_average_string_life").state) == 20

    # Un-break it with update_restring, then break it on a given date
    await hass.services.async_call(
        DOMAIN,
        "update_restring",
        {"config_entry_id": entry_id, "broken": False},
        blocking=True,
    )
    assert hass.states.get("sensor.aero_string_breakages").state == "0"
    when = (today - timedelta(days=2)).isoformat()
    resp = await hass.services.async_call(
        DOMAIN,
        "update_restring",
        {"config_entry_id": entry_id, "broken": True, "broken_date": when},
        blocking=True,
        return_response=True,
    )
    assert resp["restring"]["broken_date"] == when

    # Breaking before the restring is refused
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "update_restring",
            {
                "config_entry_id": entry_id,
                "broken_date": (today - timedelta(days=30)).isoformat(),
            },
            blocking=True,
        )
    assert err.value.translation_key == "broken_before_restring"

    history = await hass.services.async_call(
        DOMAIN,
        "get_history",
        {"config_entry_id": entry_id},
        blocking=True,
        return_response=True,
    )
    assert history["stats"]["breakages"] == 1
    assert history["stats"]["most_used_string"] == "RPM Blast"


async def test_broke_button_without_restrings(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Aero", "tension_unit": "lbs"}
    )
    await hass.async_block_till_done()
    # Without hours per week there is no cost per hour
    assert hass.states.get("sensor.aero_string_cost_per_hour") is None
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.aero_strings_broke"},
            blocking=True,
        )
