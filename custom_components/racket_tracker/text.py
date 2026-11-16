"""The usual setup's strings and stringer, editable on the device page."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RacketConfigEntry
from .const import ATTR_CROSS_STRING, ATTR_MAIN_STRING, ATTR_STRINGER
from .entity import UsualSetupEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RacketConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the usual setup's text fields."""
    async_add_entities(
        UsualSetupText(entry, field)
        for field in (ATTR_MAIN_STRING, ATTR_CROSS_STRING, ATTR_STRINGER)
    )


class UsualSetupText(UsualSetupEntity, TextEntity):
    """A text field of the usual setup. Empty clears it."""

    _attr_native_max = 100

    @property
    def native_value(self) -> str:
        """The stored value ("" when unset)."""
        return str(self._setup_value or "")

    async def async_set_value(self, value: str) -> None:
        """Store the value."""
        self._async_store(value.strip())
