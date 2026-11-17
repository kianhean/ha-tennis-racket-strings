"""One-tap restring, "my strings broke" and (logged play) "I played"."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import (
    RacketConfigEntry,
    async_log_play,
    async_log_restring,
    async_mark_broken,
    usual_setup,
)
from .entity import async_remove_entity, racket_device_info
from .tension import logs_play, session_hours

LOG_PLAY_KEY = "log_play"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RacketConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the racket's buttons."""
    async_add_entities([RepeatRestringButton(entry), StringsBrokeButton(entry)])
    # Only for rackets that log play sessions instead of hours per week
    if logs_play(entry.options):
        async_add_entities([LogPlayButton(entry)])
    else:
        async_remove_entity(hass, Platform.BUTTON, entry, LOG_PLAY_KEY)


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


class LogPlayButton(ButtonEntity):
    """Log a play session today, of the racket's usual session length."""

    _attr_has_entity_name = True
    _attr_translation_key = LOG_PLAY_KEY

    def __init__(self, entry: RacketConfigEntry) -> None:
        """Initialize."""
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{LOG_PLAY_KEY}"
        self._attr_device_info = racket_device_info(entry)

    async def async_press(self) -> None:
        """Log the session."""
        await async_log_play(self._entry, session_hours(self._entry.options))
