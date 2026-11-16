"""Backdated restrings backfill the tension sensors' long-term statistics."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from homeassistant import config_entries
from homeassistant.components.recorder import Recorder, get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.racket_tracker.const import DOMAIN
from custom_components.racket_tracker.tension import estimate, play_settings


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    recorder_mock: Recorder, enable_custom_integrations: None
) -> None:
    """The recorder must start before hass (overrides conftest's fixture)."""


IDS = {"sensor.blade_tension", "sensor.blade_estimated_tension"}


async def _stats(hass: HomeAssistant) -> dict[str, list[dict]]:
    # The backfill runs as a background task, then queues a recorder job
    await hass.async_block_till_done(wait_background_tasks=True)
    await async_wait_recording_done(hass)
    start = dt_util.utcnow() - timedelta(days=400)
    return await get_instance(hass).async_add_executor_job(
        statistics_during_period, hass, start, None, IDS, "hour", None, {"mean"}
    )


def _days_ago(days: int) -> str:
    return (dt_util.now().date() - timedelta(days=days)).isoformat()


async def test_backfill(recorder_mock: Recorder, hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "http", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Blade", "tension_unit": "lbs", "play": {"hours_per_week": 4}},
    )
    entry = result["result"]
    await hass.async_block_till_done()
    assert await _stats(hass) == {}  # Nothing strung yet

    async def restring(**data) -> None:
        await hass.services.async_call(
            DOMAIN,
            "add_restring",
            {"config_entry_id": entry.entry_id, "main_string": "ALU", **data},
            blocking=True,
        )
        await hass.async_block_till_done()

    # Two backdated restrings: 60 days ago at 52, 20 days ago at 50
    await restring(main_tension=52, date=_days_ago(60))
    await restring(main_tension=50, date=_days_ago(20))
    stats = await _stats(hass)
    strung, est = stats["sensor.blade_tension"], stats["sensor.blade_estimated_tension"]

    # Hourly from local midnight on the first restring day to the last full hour
    first = dt_util.as_utc(
        dt_util.start_of_local_day(date.fromisoformat(_days_ago(60)))
    )
    assert dt_util.utc_from_timestamp(strung[0]["start"]) == first
    last_full_hour = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    assert dt_util.utc_from_timestamp(
        strung[-1]["start"]
    ) >= last_full_hour - timedelta(hours=1)
    assert len(est) == len(strung)

    def at(rows: list[dict], days_ago: int) -> float:
        """The value at local noon that many days ago."""
        noon = dt_util.start_of_local_day(
            date.fromisoformat(_days_ago(days_ago))
        ) + timedelta(hours=12)
        stamp = dt_util.as_utc(noon).timestamp()
        return next(r["mean"] for r in rows if r["start"] == stamp)

    # The restring in effect that day, and the model's estimate for it
    assert at(strung, 40) == 52 and at(strung, 10) == 50
    settings = play_settings(entry.options)
    for days_ago, record in (
        (59, {"date": _days_ago(60), "main_tension": 52}),
        (40, {"date": _days_ago(60), "main_tension": 52}),
        (10, {"date": _days_ago(20), "main_tension": 50}),
    ):
        expected = estimate(record, settings, date.fromisoformat(_days_ago(days_ago)))
        assert at(est, days_ago) == expected.main_tension
    # Strings lose tension until the next restring resets it
    assert at(est, 40) < at(est, 59)
    assert at(est, 19) > at(est, 21)

    # Without hours per week only the strung tension is backfilled
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"tension_unit": "lbs", "play": {}}
    )
    await hass.async_block_till_done()
    await restring(main_tension=48, date=_days_ago(5))
    stats = await _stats(hass)
    assert at(stats["sensor.blade_tension"], 2) == 48
