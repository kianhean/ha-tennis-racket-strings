"""Sensors for Racket String Tracker."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
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
    DOMAIN,
    TENSION_UNIT_LBS,
)
from .entity import racket_device_info
from .history import RacketHistory, with_image_url
from .specs import SPECS, Spec, effective_specs, spec_unit


def _latest(history: RacketHistory, key: str) -> Any:
    return history.latest.get(key) if history.latest else None


def _last_date(history: RacketHistory) -> date | None:
    value = _latest(history, ATTR_DATE)
    return date.fromisoformat(value) if value else None


def _strings_label(history: RacketHistory) -> str | None:
    main = _latest(history, ATTR_MAIN_STRING)
    cross = _latest(history, ATTR_CROSS_STRING)
    if main is None:
        return None
    return main if not cross or cross == main else f"{main} / {cross}"


def _days_since(history: RacketHistory) -> int | None:
    last = _last_date(history)
    return (dt_util.now().date() - last).days if last else None


def _latest_attrs(history: RacketHistory) -> dict[str, Any]:
    if not (latest := history.latest):
        return {}
    r = with_image_url(latest)
    return {
        "restring_id": r["id"],
        ATTR_DATE: r.get(ATTR_DATE),
        ATTR_MAIN_STRING: r.get(ATTR_MAIN_STRING),
        ATTR_CROSS_STRING: r.get(ATTR_CROSS_STRING),
        ATTR_MAIN_TENSION: r.get(ATTR_MAIN_TENSION),
        ATTR_CROSS_TENSION: r.get(ATTR_CROSS_TENSION),
        ATTR_STRINGER: r.get(ATTR_STRINGER),
        ATTR_RATING: r.get(ATTR_RATING),
        ATTR_COST: r.get(ATTR_COST),
        ATTR_NOTES: r.get(ATTR_NOTES),
        "image_url": r.get("image_url"),
    }


@dataclass(frozen=True, kw_only=True)
class RacketSensorDescription(SensorEntityDescription):
    """Describes a racket sensor."""

    value_fn: Callable[[RacketHistory], Any]
    attrs_fn: Callable[[RacketHistory], dict[str, Any]] | None = None
    unit_fn: Callable[[HomeAssistant, RacketConfigEntry], str | None] | None = None
    daily_refresh: bool = False


SENSORS: tuple[RacketSensorDescription, ...] = (
    RacketSensorDescription(
        key="strings",
        translation_key="strings",
        value_fn=_strings_label,
        attrs_fn=_latest_attrs,
    ),
    RacketSensorDescription(
        key="tension",
        translation_key="tension",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda h: _latest(h, ATTR_MAIN_TENSION),
        attrs_fn=lambda h: {ATTR_CROSS_TENSION: _latest(h, ATTR_CROSS_TENSION)},
        unit_fn=lambda hass, entry: entry.options.get(
            CONF_TENSION_UNIT, TENSION_UNIT_LBS
        ),
    ),
    RacketSensorDescription(
        key="last_restrung",
        translation_key="last_restrung",
        device_class=SensorDeviceClass.DATE,
        value_fn=_last_date,
    ),
    RacketSensorDescription(
        key="days_since_restring",
        translation_key="days_since_restring",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_days_since,
        daily_refresh=True,
    ),
    RacketSensorDescription(
        key="restrings",
        translation_key="restrings",
        value_fn=lambda h: h.count,
        attrs_fn=lambda h: {"history": h.newest_first()},
    ),
    RacketSensorDescription(
        key="total_cost",
        translation_key="total_cost",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda h: h.total_cost,
        attrs_fn=lambda h: {"average_cost": h.average_cost},
        unit_fn=lambda hass, entry: hass.config.currency,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RacketConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up racket sensors."""
    async_add_entities(RacketSensor(hass, entry, desc) for desc in SENSORS)

    # One sensor per spec that has a value; drop sensors for specs since cleared.
    specs = effective_specs(entry)
    registry = er.async_get(hass)
    for spec in SPECS:
        if spec.key in specs:
            continue
        unique_id = f"{entry.entry_id}_spec_{spec.key}"
        if entity_id := registry.async_get_entity_id("sensor", DOMAIN, unique_id):
            registry.async_remove(entity_id)
    async_add_entities(
        RacketSpecSensor(entry, spec, specs[spec.key])
        for spec in SPECS
        if spec.key in specs
    )


class RacketSensor(SensorEntity):
    """A sensor derived from a racket's restring history."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    # Keep the (potentially long) history list out of the recorder database
    _unrecorded_attributes = frozenset({"history"})
    entity_description: RacketSensorDescription

    def __init__(
        self,
        hass: HomeAssistant,
        entry: RacketConfigEntry,
        description: RacketSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        self._history = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        if description.unit_fn:
            self._attr_native_unit_of_measurement = description.unit_fn(hass, entry)

        self._attr_device_info = racket_device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Subscribe to history changes."""
        self.async_on_remove(
            self._history.async_add_listener(self.async_write_ha_state)
        )
        if self.entity_description.daily_refresh:
            self.async_on_remove(
                async_track_time_change(
                    self.hass, self._handle_midnight, hour=0, minute=0, second=5
                )
            )

    @callback
    def _handle_midnight(self, _now: datetime) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.entity_description.value_fn(self._history)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self._history)


class RacketSpecSensor(SensorEntity):
    """A racket spec: measured by the user, or from a dataset."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self, entry: RacketConfigEntry, spec: Spec, value: dict[str, Any]
    ) -> None:
        """Initialize the sensor."""
        self._attr_translation_key = spec.key
        self._attr_unique_id = f"{entry.entry_id}_spec_{spec.key}"
        self._attr_device_info = racket_device_info(entry)
        self._attr_device_class = spec.device_class
        self._attr_native_unit_of_measurement = spec_unit(entry, spec)
        # Keep tennis units (27 in, 320 mm) instead of HA's unit-system conversion
        if spec.device_class is not None:
            self._attr_suggested_unit_of_measurement = (
                self._attr_native_unit_of_measurement
            )
        self._attr_native_value = value["value"]
        self._attr_extra_state_attributes = {"source": value["source"]}
