"""Restring due: on once the current strings reach the racket's restring rule."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import RacketConfigEntry
from .due import Due, due_rules
from .entity import DailyRacketEntity, async_remove_entity

KEY = "restring_due"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RacketConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the restring due sensor, if the racket has a restring rule."""
    if not due_rules(entry.options):
        async_remove_entity(hass, Platform.BINARY_SENSOR, entry, KEY)
        return
    async_add_entities([RestringDueSensor(entry, KEY)])


class RestringDueSensor(DailyRacketEntity, BinarySensorEntity):
    """On when the current strings are due to be replaced."""

    def _due(self) -> Due | None:
        return self._history.next_due(self._entry.options)

    @property
    def is_on(self) -> bool | None:
        """Whether the strings are due (unknown without a restring or a due date)."""
        if (due := self._due()) is None:
            return None
        return dt_util.now().date() >= due.date

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The due date and the rule that set it (days, hours_played, min_tension)."""
        due = self._due()
        return {
            "due_date": due.date.isoformat() if due else None,
            "days_until_due": (due.date - dt_util.now().date()).days if due else None,
            "reason": due.reason if due else None,
        }
