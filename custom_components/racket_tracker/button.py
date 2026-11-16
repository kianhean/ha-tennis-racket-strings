"""One-tap restring with the usual setup, and one-tap "my strings broke"."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RacketConfigEntry, async_log_restring, async_mark_broken, usual_setup
from .entity import racket_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RacketConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the racket's buttons."""
    async_add_entities([RepeatRestringButton(entry), StringsBrokeButton(entry)])


class RepeatRestringButton(ButtonEntity):
    """Log a restring today with the usual setup (or the same as last time)."""

    _attr_has_entity_name = True
    _attr_translation_key = "repeat_restring"

    def __init__(self, entry: RacketConfigEntry) -> None:
        """Initialize."""
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_repeat_restring"
        self._attr_device_info = racket_device_info(entry)

    async def async_press(self) -> None:
        """Log the restring."""
        await async_log_restring(self.hass, self._entry, usual_setup(self._entry))


class StringsBrokeButton(ButtonEntity):
    """Record that the current strings broke today."""

    _attr_has_entity_name = True
    _attr_translation_key = "strings_broke"

    def __init__(self, entry: RacketConfigEntry) -> None:
        """Initialize."""
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_strings_broke"
        self._attr_device_info = racket_device_info(entry)

    async def async_press(self) -> None:
        """Mark the latest restring as broken today."""
        await async_mark_broken(self.hass, self._entry)
