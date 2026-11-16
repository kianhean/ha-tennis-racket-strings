"""Backfill the tension sensors' long-term statistics from the restring history.

Home Assistant only records a sensor's values from the moment it writes them,
so a backdated restring would show as a jump on the day it was logged. After
every change to the history (and on setup) this writes one hourly statistic
per hour, from the first restring (at most MAX_DAYS back) up to the last full
hour, for:

- the Tension sensor: the strung mains tension of the restring in effect then
- the Estimated tension sensor: the model's estimate for that day

Statistics graph cards then show the whole history. The recorder compiles the
hours after that from the sensors' own states, which give the same values.
"""

from __future__ import annotations

import bisect
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DATE,
    ATTR_MAIN_TENSION,
    CONF_TENSION_UNIT,
    DOMAIN,
    TENSION_UNIT_LBS,
)
from .tension import PlaySettings, estimate, play_settings

if TYPE_CHECKING:
    from . import RacketConfigEntry

MAX_DAYS = 3 * 365


def _hourly(
    records: list[dict[str, Any]],
    settings: PlaySettings | None,
    start: datetime,
    end: datetime,
) -> tuple[list[tuple[datetime, float]], list[tuple[datetime, float]]]:
    """(hour, strung tension) and (hour, estimated tension) from start to end."""
    dates = [r[ATTR_DATE] for r in records]
    strung: list[tuple[datetime, float]] = []
    estimated: list[tuple[datetime, float]] = []
    per_day: dict[date, tuple[float | None, float | None]] = {}
    hour = start
    while hour < end:
        day = dt_util.as_local(hour).date()
        if day not in per_day:
            # The restring in effect that day: the last one on or before it
            index = bisect.bisect_right(dates, day.isoformat()) - 1
            record = records[index] if index >= 0 else None
            value = record.get(ATTR_MAIN_TENSION) if record else None
            est = estimate(record, settings, day) if record and settings else None
            per_day[day] = (
                value if isinstance(value, (int, float)) else None,
                est.main_tension if est else None,
            )
        value, est_value = per_day[day]
        if value is not None:
            strung.append((hour, float(value)))
        if est_value is not None:
            estimated.append((hour, est_value))
        hour += timedelta(hours=1)
    return strung, estimated


async def async_backfill(hass: HomeAssistant, entry: RacketConfigEntry) -> None:
    """Write the hourly statistics for this racket's tension sensors."""
    if "recorder" not in hass.config.components:
        return
    # Imported here: the recorder is optional (after_dependencies)
    from homeassistant.components.recorder.models import (
        StatisticData,
        StatisticMeanType,
        StatisticMetaData,
    )
    from homeassistant.components.recorder.statistics import async_import_statistics

    records = [r for r in entry.runtime_data.restrings if r.get(ATTR_DATE)]
    if not records:
        return
    end = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    first = dt_util.start_of_local_day(date.fromisoformat(records[0][ATTR_DATE]))
    start = max(dt_util.as_utc(first), end - timedelta(days=MAX_DAYS))
    settings = play_settings(entry.options)
    strung, estimated = await hass.async_add_executor_job(
        _hourly, records, settings, start, end
    )

    registry = er.async_get(hass)
    unit = entry.options.get(CONF_TENSION_UNIT, TENSION_UNIT_LBS)
    for key, rows in (("tension", strung), ("estimated_tension", estimated)):
        entity_id = registry.async_get_entity_id(
            Platform.SENSOR, DOMAIN, f"{entry.entry_id}_{key}"
        )
        if entity_id is None or not rows:
            continue
        metadata: dict[str, Any] = {
            "mean_type": StatisticMeanType.ARITHMETIC,
            "has_sum": False,
            "name": None,
            "source": "recorder",
            "statistic_id": entity_id,
            "unit_of_measurement": unit,
        }
        # Newer recorders need unit_class; older ones reject unknown keys
        if "unit_class" in StatisticMetaData.__annotations__:
            metadata["unit_class"] = None
        async_import_statistics(
            hass,
            StatisticMetaData(**metadata),  # type: ignore[typeddict-item]
            [
                StatisticData(start=hour, mean=value, min=value, max=value)
                for hour, value in rows
            ],
        )
