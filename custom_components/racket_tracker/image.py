"""Photo entity showing the most recent restring photo of a racket."""

from __future__ import annotations

from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import RacketConfigEntry
from .const import ATTR_DATE, ATTR_IMAGE
from .entity import racket_device_info
from .images import async_read_image, image_content_type


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RacketConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the photo entity."""
    async_add_entities([RacketPhoto(hass, entry)])


class RacketPhoto(ImageEntity):
    """Latest restring photo."""

    _attr_has_entity_name = True
    _attr_translation_key = "photo"

    def __init__(self, hass: HomeAssistant, entry: RacketConfigEntry) -> None:
        """Initialize."""
        super().__init__(hass)
        self._history = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_photo"
        self._attr_device_info = racket_device_info(entry)
        self._record: dict[str, Any] | None = None
        self._refresh()

    def _refresh(self) -> None:
        record = next(
            (r for r in reversed(self._history.restrings) if r.get(ATTR_IMAGE)), None
        )
        stamp = (record or {}).get("updated") or (record or {}).get("created")
        if record is None:
            self._attr_image_last_updated = None
        elif (
            self._record is None
            or record["id"] != self._record["id"]
            or record[ATTR_IMAGE] != self._record.get(ATTR_IMAGE)
            or self._attr_image_last_updated is None
        ):
            self._attr_image_last_updated = (
                dt_util.parse_datetime(stamp) if stamp else dt_util.utcnow()
            )
            self._attr_content_type = image_content_type(record[ATTR_IMAGE])
        self._record = dict(record) if record else None

    async def async_added_to_hass(self) -> None:
        """Subscribe to history changes."""
        self.async_on_remove(self._history.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self._refresh()
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Which restring the photo belongs to."""
        if not self._record:
            return None
        return {
            "restring_id": self._record["id"],
            ATTR_DATE: self._record.get(ATTR_DATE),
        }

    async def async_image(self) -> bytes | None:
        """Return the photo bytes."""
        if not self._record:
            return None
        return await async_read_image(self.hass, self._record[ATTR_IMAGE])
