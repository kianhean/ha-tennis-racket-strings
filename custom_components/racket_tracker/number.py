"""The usual setup's tensions and cost, editable on the device page."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RacketConfigEntry, _whole
from .const import (
    ATTR_COST,
    ATTR_CROSS_TENSION,
    ATTR_MAIN_TENSION,
    CONF_TENSION_UNIT,
    TENSION_UNIT_LBS,
)
from .entity import UsualSetupEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RacketConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the usual setup's number fields."""
    unit = entry.options.get(CONF_TENSION_UNIT, TENSION_UNIT_LBS)
    async_add_entities(
        [
            UsualSetupNumber(entry, ATTR_MAIN_TENSION, 1, 100, 0.5, unit),
            UsualSetupNumber(entry, ATTR_CROSS_TENSION, 1, 100, 0.5, unit),
            UsualSetupNumber(entry, ATTR_COST, 0, 10000, 0.01, hass.config.currency),
        ]
    )


class UsualSetupNumber(UsualSetupEntity, NumberEntity):
    """A number field of the usual setup (tension in the racket's unit, or cost)."""

    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        entry: RacketConfigEntry,
        field: str,
        minimum: float,
        maximum: float,
        step: float,
        unit: str,
    ) -> None:
        """Initialize."""
        super().__init__(entry, field)
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> float | None:
        """The stored value."""
        value = self._setup_value
        return None if value is None else float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Store the value (52.0 as 52, like the forms)."""
        self._async_store(_whole(float(value)))
