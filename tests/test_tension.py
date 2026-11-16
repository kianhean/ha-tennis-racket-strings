"""Estimated tension: the log-time / log-play model, string types, calibration."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.racket_tracker.const import DOMAIN
from custom_components.racket_tracker.tension import (
    PRESET_MINOR_VERSION,
    STRING_TYPES,
    LossRates,
    PlaySettings,
    calibrate,
    estimate,
    loss_percent,
    migrate_play_options,
    move_old_presets,
    play_settings,
    uses_old_presets,
)

POLY = STRING_TYPES["polyester"]
RECORD = {"date": "2026-01-01", "main_tension": 52, "cross_tension": 50}


def _on(days: int) -> date:
    return date(2026, 1, 1) + timedelta(days=days)


def test_loss_model() -> None:
    # Strung today: only the initial loss
    assert loss_percent(POLY, 0, 0) == 10
    # Relaxation: +4 % each time the age multiplies by 10, played or not
    assert loss_percent(POLY, 10, 0) == pytest.approx(14)
    assert loss_percent(POLY, 100, 0) == pytest.approx(18)
    # Play: 3 % in the first hour, 3 % more per doubling of (1 + hours)
    assert loss_percent(POLY, 1, 1) == pytest.approx(13)
    assert loss_percent(POLY, 1, 3) == pytest.approx(16)


def test_move_old_presets_keeps_user_rates() -> None:
    """Stored preset values move to the new presets; changed rates stay."""
    assert not uses_old_presets({"hours_per_week": 3})
    assert not uses_old_presets({"hours_per_week": 3, "string_type": "nylon"})
    stored = {
        "hours_per_week": 3,
        "string_type": "nylon",
        "initial_tension_loss": 6,
        "first_hour_loss": 1.5,
        "relaxation_loss": 2,
    }
    assert uses_old_presets(stored)
    assert move_old_presets(stored) == {
        "hours_per_week": 3,
        "string_type": "nylon",
        "initial_tension_loss": 6,
        "first_hour_loss": 1.5,
        "relaxation_loss": 4,
    }
    # Rates the user changed are their own: nothing moves
    custom = {**stored, "first_hour_loss": 2.5, "relaxation_loss": 3}
    assert not uses_old_presets(custom)
    assert move_old_presets(custom) == custom
    # No string type: the default type's preset is what moves. Polyester's did
    # not change, so there is nothing to move and a nylon value is left alone.
    assert not uses_old_presets({"initial_tension_loss": 6, "relaxation_loss": 4})
    assert move_old_presets({"initial_tension_loss": 6, "relaxation_loss": 4}) == {
        "initial_tension_loss": 6,
        "relaxation_loss": 4,
    }


def test_estimate() -> None:
    settings = PlaySettings(4, "polyester", POLY)
    est = estimate(RECORD, settings, _on(0))
    assert (est.hours_played, est.loss_percent, est.main_tension) == (0, 10, 46.8)
    # Two weeks, 8 h: 10 + 4·log10(14) + 3·log2(9) = 24.1 %
    est = estimate(RECORD, settings, _on(14))
    assert (est.hours_played, est.loss_percent) == (8, 24.1)
    assert (est.main_tension, est.cross_tension) == (39.5, 38)
    # Capped at 50 %
    assert estimate(RECORD, settings, _on(3 * 365)).loss_percent == 50
    assert estimate(None, settings, _on(0)) is None


def test_play_settings() -> None:
    assert play_settings({}) is None
    assert play_settings({"play": {"hours_per_week": 3}}) == PlaySettings(
        3, "polyester", POLY
    )
    # String type sets the defaults; set rates override them
    gut = play_settings({"play": {"hours_per_week": 3, "string_type": "gut"}})
    assert gut.rates == STRING_TYPES["gut"]
    custom = play_settings(
        {"play": {"hours_per_week": 3, "string_type": "nylon", "first_hour_loss": 2}}
    )
    assert custom.rates == LossRates(initial=6, first_hour=2, relaxation=4)
    # Materials keep the order the sources report: polyester > nylon > gut
    losses = [loss_percent(r, 30, 17) for r in STRING_TYPES.values()]
    assert losses == sorted(losses, reverse=True)


def test_presets_match_the_measured_totals() -> None:
    """The three terms together land near TWU's measured loss for each material.

    Two weeks at 4 h/week is about when most recreational string beds are restrung;
    TWU's medians are 41 % (polyester), 21 % (nylon) and 15 % (gut), with measured
    ranges of 27-55, 17-34 and 10-19 %. The split is TWU's: most of a polyester's
    loss is idle (its "stabilization"), most of nylon's is play.
    """
    for string_type, low, high in (
        ("polyester", 20, 30),
        ("nylon", 12, 20),
        ("gut", 8, 16),
    ):
        total = loss_percent(STRING_TYPES[string_type], 14, 8)
        assert low <= total <= high, (string_type, total)
    # Nylon's relaxation is the lab's ~4 % per tenfold, not a scaled polyester rate
    assert STRING_TYPES["nylon"].relaxation == pytest.approx(4)
    # Gut loses least of the three at every age
    assert (
        loss_percent(STRING_TYPES["gut"], 365, 200)
        < loss_percent(STRING_TYPES["nylon"], 365, 200)
        < loss_percent(STRING_TYPES["polyester"], 365, 200)
    )


def test_calibrate() -> None:
    settings = PlaySettings(4, "polyester", POLY)
    fitted = calibrate(RECORD, settings, 40, _on(14))
    assert estimate(RECORD, fitted, _on(14)).main_tension == 40
    assert fitted.rates.initial < POLY.initial  # Lost less than predicted
    for bad in (52, 60, 20):  # no loss, a gain, more than the cap
        with pytest.raises(ValueError):
            calibrate(RECORD, settings, bad, _on(14))


async def test_estimate_sensors_and_calibration(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "http", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Blade",
            "tension_unit": "kg",
            "play": {"hours_per_week": 7, "string_type": "nylon"},
        },
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.options["play"] == {"hours_per_week": 7, "string_type": "nylon"}

    # Calibrating needs a restring; no restring yet: no estimate
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "calibrate_tension",
            {"config_entry_id": entry.entry_id, "tension": 20},
            blocking=True,
        )
    assert hass.states.get("sensor.blade_estimated_tension").state == "unknown"

    ten_days_ago = (dt_util.now().date() - timedelta(days=10)).isoformat()
    await hass.services.async_call(
        DOMAIN,
        "add_restring",
        {
            "config_entry_id": entry.entry_id,
            "date": ten_days_ago,
            "main_string": "Synthetic gut",
            "cross_string": "VS Gut",
            "main_tension": 25,
            "cross_tension": 24,
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    # Nylon, 10 days, 10 h: 6 + 4·log10(10) + 1.5·log2(11) = 15.2 %
    tension = hass.states.get("sensor.blade_estimated_tension")
    assert float(tension.state) == 21.2
    assert tension.attributes["unit_of_measurement"] == "kg"
    assert tension.attributes["strung_tension"] == 25
    assert tension.attributes["estimated_cross_tension"] == 20.4
    assert tension.attributes["string_type"] == "nylon"
    assert tension.attributes["first_hour_loss"] == 1.5
    assert float(hass.states.get("sensor.blade_estimated_tension_loss").state) == 15.2
    assert float(hass.states.get("sensor.blade_hours_played").state) == 10

    # A measurement scales the rates to match it
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "calibrate_tension",
            {"config_entry_id": entry.entry_id, "tension": 26},
            blocking=True,
        )
    resp = await hass.services.async_call(
        DOMAIN,
        "calibrate_tension",
        {"config_entry_id": entry.entry_id, "tension": 20.5},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    assert resp["first_hour_loss"] > 1.5
    assert entry.options["play"]["string_type"] == "nylon"
    assert entry.options["play"]["first_hour_loss"] == resp["first_hour_loss"]
    assert float(hass.states.get("sensor.blade_estimated_tension").state) == 20.5

    # Clearing hours per week removes the estimates; calibrating then fails
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tension_unit": "kg", "play": {}}
    )
    await hass.async_block_till_done()
    assert "play" not in entry.options
    assert hass.states.get("sensor.blade_estimated_tension") is None
    assert er.async_get(hass).async_get("sensor.blade_hours_played") is None
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "calibrate_tension",
            {"config_entry_id": entry.entry_id, "tension": 20},
            blocking=True,
        )


async def test_migrate_linear_model(hass: HomeAssistant) -> None:
    """0.3 stored a loss per hour; it becomes the first-hour loss (1 %/h → 3 %)."""
    assert await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Old",
        version=1,
        minor_version=1,
        options={
            "tension_unit": "lbs",
            "play": {
                "hours_per_week": 4,
                "initial_tension_loss": 8,
                "tension_loss_per_hour": 0.5,
            },
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.minor_version == PRESET_MINOR_VERSION
    assert entry.options["play"] == {
        "hours_per_week": 4,
        "initial_tension_loss": 8,
        "first_hour_loss": 1.5,
    }
    assert hass.states.get("sensor.old_estimated_tension") is not None


async def test_migration_moves_old_preset_values(hass: HomeAssistant) -> None:
    """A rate saved from the old form is the old preset: it moves with the preset.

    Rackets at minor version 2 stored the suggested values (1.0 showed the preset
    and saving kept the number), so without this they would keep estimates about
    40 % too low after the presets changed (see tension.py).
    """
    entry = await _setup_old_entry(
        hass,
        minor_version=2,
        options={
            "tension_unit": "kg",
            "play": {
                "hours_per_week": 4,
                "string_type": "nylon",
                "initial_tension_loss": 6,
                "first_hour_loss": 1.5,
                "relaxation_loss": 2,
            },
        },
    )
    assert entry.minor_version == PRESET_MINOR_VERSION
    assert entry.options["play"] == {
        "hours_per_week": 4,
        "string_type": "nylon",
        "initial_tension_loss": 6,
        "first_hour_loss": 1.5,
        "relaxation_loss": 4,
    }
    # The estimate uses the new preset, not the old 0.6x one: the rates a
    # racket that left them empty would get
    settings = play_settings(entry.options)
    assert settings is not None
    assert settings.rates == STRING_TYPES["nylon"]


async def test_migration_keeps_a_custom_rate(hass: HomeAssistant) -> None:
    """A rate the user really changed (or calibrated) is theirs: it stays."""
    options = {
        "tension_unit": "kg",
        "play": {"hours_per_week": 4, "first_hour_loss": 2.5, "relaxation_loss": 2.5},
    }
    entry = await _setup_old_entry(hass, minor_version=2, options=options)
    assert entry.minor_version == PRESET_MINOR_VERSION
    assert entry.options == options


def test_migrate_play_options_keeps_what_it_did_not_convert() -> None:
    """Only the removed key changes: the rates and TWU value survive in proportion."""
    assert migrate_play_options({"hours_per_week": 4}) == {"hours_per_week": 4}
    assert migrate_play_options({}) == {}
    assert migrate_play_options(
        {
            "hours_per_week": 4,
            "string_type": "nylon",
            "tension_loss_per_hour": 1,  # the old default
            "twu_tension_loss": 30.5,
            "initial_tension_loss": 6,
            "relaxation_loss": 2,
        }
    ) == {
        "hours_per_week": 4,
        "string_type": "nylon",
        "first_hour_loss": 3,
        "twu_tension_loss": 30.5,
        "initial_tension_loss": 6,
        "relaxation_loss": 2,
    }
    # A linear model calibrated down to 0.2 %/h stays 0.6 % in the first hour
    assert (
        migrate_play_options({"tension_loss_per_hour": 0.2})["first_hour_loss"] == 0.6
    )


async def _setup_old_entry(
    hass: HomeAssistant,
    *,
    minor_version: int,
    options: dict,
    version: int = 1,
) -> MockConfigEntry:
    assert await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Old",
        version=version,
        minor_version=minor_version,
        options=options,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_migration_is_not_repeated(hass: HomeAssistant) -> None:
    """An entry already at minor version 2 keeps a customised first-hour loss.

    Running the migration again would replace it with the type default (or with
    3 × the old value, if that key were still there), so setup must not touch it.
    """
    options = {
        "tension_unit": "lbs",
        "play": {"hours_per_week": 6, "first_hour_loss": 2.25},
    }
    entry = await _setup_old_entry(hass, minor_version=2, options=options)
    assert entry.minor_version == PRESET_MINOR_VERSION
    assert entry.options == options
    assert hass.states.get("sensor.old_estimated_tension") is not None


async def test_migration_survives_a_restart(hass: HomeAssistant) -> None:
    """The entry is saved at the new minor version, so a restart doesn't migrate it.

    (Before the fix, strung.reload without closing the options flow asked for it
    twice, and the second run undid the first.)
    """
    entry = await _setup_old_entry(
        hass,
        minor_version=1,
        options={
            "tension_unit": "lbs",
            "play": {"hours_per_week": 3, "tension_loss_per_hour": 0.5},
        },
    )
    assert entry.minor_version == PRESET_MINOR_VERSION
    expected = dict(entry.options)

    # A restart: the entry is read back from its saved copies, migrated or not
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.options == expected
    assert "tension_loss_per_hour" not in entry.options["play"]


async def test_migration_without_play_section(hass: HomeAssistant) -> None:
    """Rackets without a play section just move to the new minor version."""
    entry = await _setup_old_entry(
        hass, minor_version=1, options={"tension_unit": "kg"}
    )
    assert entry.minor_version == PRESET_MINOR_VERSION
    assert entry.options == {"tension_unit": "kg"}
    assert hass.states.get("sensor.old_estimated_tension") is None


async def test_newer_entry_is_not_migrated(hass: HomeAssistant) -> None:
    """A downgraded install refuses the entry instead of damaging it."""
    assert await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(
        domain=DOMAIN, title="Newer", version=2, minor_version=1, options={}
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.version == 2 and entry.options == {}
