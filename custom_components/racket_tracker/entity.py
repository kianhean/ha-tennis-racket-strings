"""Shared entity helpers."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_change

from .const import CONF_BRAND, CONF_HEAD_SIZE, CONF_MODEL, CONF_STRING_PATTERN, DOMAIN

if TYPE_CHECKING:
    from . import RacketConfigEntry


def racket_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Device info describing a racket."""
    opts = entry.options
    model_bits = [opts.get(CONF_MODEL)]
    if opts.get(CONF_HEAD_SIZE):
        model_bits.append(f"{int(opts[CONF_HEAD_SIZE])} sq in")
    if opts.get(CONF_STRING_PATTERN):
        model_bits.append(opts[CONF_STRING_PATTERN])
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer=opts.get(CONF_BRAND),
        model=" · ".join(b for b in model_bits if b) or None,
    )


class DailyRacketEntity(Entity):
    """An entity that changes with the history and with the date."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: RacketConfigEntry, key: str) -> None:
        """Initialize."""
        self._entry = entry
        self._history = entry.runtime_data
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = racket_device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Update on history changes and just after midnight."""
        self.async_on_remove(
            self._history.async_add_listener(self.async_write_ha_state)
        )
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._handle_midnight, hour=0, minute=0, second=5
            )
        )

    @callback
    def _handle_midnight(self, _now: datetime) -> None:
        self.async_write_ha_state()


@callback
def async_remove_entity(
    hass: HomeAssistant, platform: str, entry: ConfigEntry, key: str
) -> None:
    """Drop an entity that no longer applies (e.g. its option was cleared)."""
    registry = er.async_get(hass)
    unique_id = f"{entry.entry_id}_{key}"
    if entity_id := registry.async_get_entity_id(platform, DOMAIN, unique_id):
        registry.async_remove(entity_id)
