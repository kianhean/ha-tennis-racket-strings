"""Calendar of a racket's restrings, plus the next due date."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import RacketConfigEntry
from .const import (
    ATTR_COST,
    ATTR_CROSS_STRING,
    ATTR_CROSS_TENSION,
    ATTR_DATE,
    ATTR_MAIN_STRING,
    ATTR_MAIN_TENSION,
    ATTR_NOTES,
    ATTR_RATING,
    ATTR_STRINGER,
    CONF_TENSION_UNIT,
    TENSION_UNIT_LBS,
)
from .entity import DailyRacketEntity

DUE_SUMMARY = "Restring due"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RacketConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the restring calendar."""
    async_add_entities([RestringCalendar(entry, "restrings")])


def _strings(record: dict[str, Any]) -> str:
    cross = record.get(ATTR_CROSS_STRING)
    main = str(record.get(ATTR_MAIN_STRING) or "")
    if not cross or cross == main:
        return main
    return f"{main} / {cross}"


def _tension(record: dict[str, Any], unit: str) -> str | None:
    main, cross = record.get(ATTR_MAIN_TENSION), record.get(ATTR_CROSS_TENSION)
    if main is None:
        return None
    return f"{main} {unit}" if cross in (None, main) else f"{main}/{cross} {unit}"


def _day(start: date, summary: str, description: str | None, uid: str) -> CalendarEvent:
    return CalendarEvent(
        start=start,
        end=start + timedelta(days=1),
        summary=summary,
        description=description or None,
        uid=uid,
    )


class RestringCalendar(DailyRacketEntity, CalendarEntity):
    """All-day events: each restring, and when the current strings are due."""

    def _events(self) -> list[CalendarEvent]:
        unit = self._entry.options.get(CONF_TENSION_UNIT, TENSION_UNIT_LBS)
        events = []
        for record in self._history.restrings:
            if not record.get(ATTR_DATE):
                continue
            tension = _tension(record, unit)
            details = [
                f"Strung at {tension}" if tension else None,
                f"by {record[ATTR_STRINGER]}" if record.get(ATTR_STRINGER) else None,
                f"cost {record[ATTR_COST]}"
                if record.get(ATTR_COST) is not None
                else None,
                "★" * record[ATTR_RATING] if record.get(ATTR_RATING) else None,
            ]
            description = " · ".join(d for d in details if d)
            if notes := record.get(ATTR_NOTES):
                description = f"{description}\n\n{notes}" if description else notes
            events.append(
                _day(
                    date.fromisoformat(record[ATTR_DATE]),
                    f"Restrung: {_strings(record)}",
                    description,
                    record["id"],
                )
            )
        if (due := self._history.next_due(self._entry.options)) is not None:
            latest = self._history.latest or {}
            events.append(
                _day(
                    due.date,
                    DUE_SUMMARY,
                    f"{_strings(latest)}, strung {latest.get(ATTR_DATE)}",
                    f"{self._entry.entry_id}_due",
                )
            )
        events.sort(key=lambda e: e.start)
        return events

    @property
    def event(self) -> CalendarEvent | None:
        """Today's event, or the next one."""
        today = dt_util.now().date()
        return next((e for e in self._events() if e.end > today), None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Events that overlap the requested range."""
        return [
            e
            for e in self._events()
            if e.start_datetime_local < end_date and e.end_datetime_local > start_date
        ]
