"""Sensors for Strung."""

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
from homeassistant.const import PERCENTAGE, Platform, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from . import RacketConfigEntry
from .const import (
    ATTR_BROKEN_DATE,
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
from .dataset import ATTRIBUTION
from .due import due_rules, next_due
from .entity import DailyRacketEntity, async_remove_entity, racket_device_info
from .history import RacketHistory, with_image_url
from .specs import SOURCE_DATASET, SPECS, Spec, effective_specs, spec_unit
from .stats import (
    average_days_to_break,
    average_life_days,
    best_rated_string,
    breakage_rate,
    breakages,
    cost_in_year,
    cost_per_hour,
    last_broken,
    most_used_string,
    restrings_in_year,
    string_counts,
    strings_label,
)
from .tension import Estimate, PlaySettings, estimate, play_settings


def _latest(history: RacketHistory, key: str) -> Any:
    return history.latest.get(key) if history.latest else None


def _last_date(history: RacketHistory) -> date | None:
    value = _latest(history, ATTR_DATE)
    return date.fromisoformat(value) if value else None


def _strings_label(history: RacketHistory) -> str | None:
    return strings_label(history.latest) if history.latest else None


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
        ATTR_BROKEN_DATE: r.get(ATTR_BROKEN_DATE),
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


@dataclass(frozen=True, kw_only=True)
class PlaySensorDescription(SensorEntityDescription):
    """A sensor estimated from play time; exists only with hours per week set."""

    value_fn: Callable[[Estimate], Any]
    racket_unit: bool = False


PLAY_SENSORS: tuple[PlaySensorDescription, ...] = (
    PlaySensorDescription(
        key="estimated_tension",
        translation_key="estimated_tension",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda e: e.main_tension,
        racket_unit=True,
    ),
    PlaySensorDescription(
        key="estimated_tension_loss",
        translation_key="estimated_tension_loss",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda e: e.loss_percent,
    ),
    PlaySensorDescription(
        key="hours_played",
        translation_key="hours_played",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda e: e.hours_played,
    ),
)


@dataclass(frozen=True, kw_only=True)
class StatsSensorDescription(SensorEntityDescription):
    """A statistic over the whole history; may need hours of play per week."""

    value_fn: Callable[[list[dict[str, Any]], PlaySettings | None, date], Any]
    attrs_fn: (
        Callable[[list[dict[str, Any]], PlaySettings | None, date], dict[str, Any]]
        | None
    ) = None
    currency_unit: str | None = None  # "" for the currency, "/h" per hour
    needs_play: bool = False


def _life_attrs(
    records: list[dict[str, Any]], settings: PlaySettings | None, _today: date
) -> dict[str, Any]:
    life = average_life_days(records)
    return {
        "average_hours_played": round(life * settings.hours_per_week / 7, 1)
        if settings is not None and life is not None
        else None,
        "average_days_to_break": average_days_to_break(records),
    }


def _most_used(records: list[dict[str, Any]], *_: Any) -> str | None:
    most = most_used_string(records)
    return most[0] if most else None


def _best_rated(records: list[dict[str, Any]], *_: Any) -> str | None:
    best = best_rated_string(records)
    return best[0] if best else None


def _best_rated_attrs(records: list[dict[str, Any]], *_: Any) -> dict[str, Any]:
    best = best_rated_string(records)
    return {
        "average_rating": best[1] if best else None,
        "ratings": best[2] if best else 0,
    }


STATS_SENSORS: tuple[StatsSensorDescription, ...] = (
    StatsSensorDescription(
        key="string_life",
        translation_key="string_life",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        suggested_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda r, *_: average_life_days(r),
        attrs_fn=_life_attrs,
    ),
    StatsSensorDescription(
        key="breakages",
        translation_key="breakages",
        value_fn=lambda r, *_: breakages(r),
        attrs_fn=lambda r, *_: {
            "breakage_rate": breakage_rate(r),
            "last_broken": last_broken(r),
        },
    ),
    StatsSensorDescription(
        key="cost_this_year",
        translation_key="cost_this_year",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        currency_unit="",
        value_fn=lambda r, _s, today: cost_in_year(r, today.year),
        attrs_fn=lambda r, _s, today: {
            "restrings_this_year": restrings_in_year(r, today.year)
        },
    ),
    StatsSensorDescription(
        key="cost_per_hour",
        translation_key="cost_per_hour",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        currency_unit="/h",
        needs_play=True,
        value_fn=lambda r, s, today: cost_per_hour(r, s, today) if s else None,
    ),
    StatsSensorDescription(
        key="most_used_string",
        translation_key="most_used_string",
        value_fn=_most_used,
        attrs_fn=lambda r, *_: {"string_counts": string_counts(r)},
    ),
    StatsSensorDescription(
        key="best_rated_string",
        translation_key="best_rated_string",
        value_fn=_best_rated,
        attrs_fn=_best_rated_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RacketConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up racket sensors."""
    async_add_entities(RacketSensor(hass, entry, desc) for desc in SENSORS)

    registry = er.async_get(hass)

    if due_rules(entry.options):
        async_add_entities([NextRestringSensor(entry, "next_restring")])
    else:
        async_remove_entity(hass, Platform.SENSOR, entry, "next_restring")

    # Estimates need hours of play per week; drop them when that's cleared.
    if play_settings(entry.options) is None:
        for desc in PLAY_SENSORS:
            unique_id = f"{entry.entry_id}_{desc.key}"
            if entity_id := registry.async_get_entity_id("sensor", DOMAIN, unique_id):
                registry.async_remove(entity_id)
    else:
        async_add_entities(PlaySensor(entry, desc) for desc in PLAY_SENSORS)

    has_play = play_settings(entry.options) is not None
    for stat in STATS_SENSORS:
        if stat.needs_play and not has_play:
            async_remove_entity(hass, Platform.SENSOR, entry, stat.key)
        else:
            async_add_entities([StatsSensor(hass, entry, stat)])

    # One sensor per spec that has a value; drop sensors for specs since cleared.
    specs = effective_specs(entry)
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
        if value["source"] == SOURCE_DATASET:
            self._attr_attribution = ATTRIBUTION


class PlaySensor(SensorEntity):
    """Estimated tension, tension loss or hours played since the last restring."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    entity_description: PlaySensorDescription

    def __init__(
        self, entry: RacketConfigEntry, description: PlaySensorDescription
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        self._history = entry.runtime_data
        self._options = entry.options
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = racket_device_info(entry)
        if description.racket_unit:
            self._attr_native_unit_of_measurement = entry.options.get(
                CONF_TENSION_UNIT, TENSION_UNIT_LBS
            )

    async def async_added_to_hass(self) -> None:
        """Update on history changes and every day."""
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

    @property
    def _settings(self) -> PlaySettings:
        """Settings for the current strings (their material may differ)."""
        settings = play_settings(self._options, self._history.latest)
        assert settings is not None
        return settings

    def _estimate(self) -> Estimate | None:
        return estimate(self._history.latest, self._settings, dt_util.now().date())

    @property
    def native_value(self) -> Any:
        """Return the estimate."""
        if (est := self._estimate()) is None:
            return None
        return self.entity_description.value_fn(est)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Show the inputs, so the estimate can be checked."""
        settings = self._settings
        attrs: dict[str, Any] = {
            "hours_per_week": settings.hours_per_week,
            "string_type": settings.string_type,
            "string_type_source": settings.string_type_source,
            "twu_tension_loss": settings.twu_tension_loss,
            "initial_tension_loss": settings.rates.initial,
            "first_hour_loss": settings.rates.first_hour,
            "relaxation_loss": settings.rates.relaxation,
        }
        if self.entity_description.key == "estimated_tension":
            est = self._estimate()
            attrs["strung_tension"] = _latest(self._history, ATTR_MAIN_TENSION)
            attrs["strung_cross_tension"] = _latest(self._history, ATTR_CROSS_TENSION)
            attrs["estimated_cross_tension"] = est.cross_tension if est else None
            attrs[ATTR_DATE] = _latest(self._history, ATTR_DATE)
        return attrs


class NextRestringSensor(DailyRacketEntity, SensorEntity):
    """The date the current strings are due, from the racket's restring rules."""

    _attr_device_class = SensorDeviceClass.DATE

    @property
    def native_value(self) -> date | None:
        """Return the due date."""
        due = next_due(self._history.latest, self._entry.options)
        return due.date if due else None


class StatsSensor(DailyRacketEntity, SensorEntity):
    """String life, breakages, costs and favourite strings over the history."""

    entity_description: StatsSensorDescription
    # Per-string counts can grow long; keep them out of the database
    _unrecorded_attributes = frozenset({"string_counts"})

    def __init__(
        self,
        hass: HomeAssistant,
        entry: RacketConfigEntry,
        description: StatsSensorDescription,
    ) -> None:
        """Initialize."""
        super().__init__(entry, description.key)
        self.entity_description = description
        if description.currency_unit is not None:
            self._attr_native_unit_of_measurement = (
                f"{hass.config.currency}{description.currency_unit}"
            )

    def _args(self) -> tuple[list[dict[str, Any]], PlaySettings | None, date]:
        return (
            self._history.restrings,
            play_settings(self._entry.options, self._history.latest),
            dt_util.now().date(),
        )

    @property
    def native_value(self) -> Any:
        """Return the statistic."""
        return self.entity_description.value_fn(*self._args())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the details."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(*self._args())
