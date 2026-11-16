"""The bundled string list: suggestions, materials and the TWU tension loss."""

from __future__ import annotations

from datetime import date

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.service import async_get_all_descriptions

from custom_components.racket_tracker.const import DOMAIN
from custom_components.racket_tracker.string_catalog import (
    CATALOG,
    NAMES,
    material,
    suggestions,
)
from custom_components.racket_tracker.tension import (
    STRING_TYPES,
    estimate,
    play_settings,
)


def test_catalog() -> None:
    assert len(CATALOG) > 750
    assert {kind for *_, kind in CATALOG} <= {*STRING_TYPES, None}
    assert "Solinco Hyper-G 17 (1.20)" in NAMES


def test_material() -> None:
    assert material("Hyper-G 1.25") == "polyester"
    assert material("solinco hyper-g") == "polyester"
    assert material("Babolat VS Touch 16") == "gut"
    assert material("Synthetic Gut 16") == "nylon"
    assert material("Something Unknown 17") is None
    assert material("") is None and material(None) is None


def test_suggestions() -> None:
    names = suggestions(["My String", "hyper-g", "My String"])
    assert names[:2] == ["My String", "hyper-g"]
    assert len(names) == len(NAMES) + 2


def test_string_type_from_the_string() -> None:
    options = {"play": {"hours_per_week": 4}}
    gut = {"date": "2026-01-01", "main_string": "VS Touch 1.30", "main_tension": 50}
    settings = play_settings(options, gut)
    assert settings.string_type == "gut"
    assert settings.string_type_source == "string"
    assert settings.rates == STRING_TYPES["gut"]

    unknown = {**gut, "main_string": "Mystery"}
    assert play_settings(options, unknown).string_type_source == "default"
    racket = {"play": {"hours_per_week": 4, "string_type": "nylon"}}
    assert play_settings(racket, gut).string_type == "nylon"

    # Gut loses less than the polyester default would
    poly = estimate(gut, play_settings(options), date(2026, 2, 1))
    real = estimate(gut, settings, date(2026, 2, 1))
    assert real.main_tension > poly.main_tension


def test_twu_tension_loss() -> None:
    # A polyester measured at 20.5 % in TWU's database loses half the default
    settings = play_settings({"play": {"hours_per_week": 4, "twu_tension_loss": 20.5}})
    assert settings.twu_tension_loss == 20.5
    assert settings.rates.initial == 5 and settings.rates.first_hour == 1.5
    assert settings.rates.relaxation == 2
    # A rate typed in (or from calibration) still wins
    settings = play_settings(
        {
            "play": {
                "hours_per_week": 4,
                "twu_tension_loss": 20.5,
                "initial_tension_loss": 9,
            }
        }
    )
    assert settings.rates.initial == 9 and settings.rates.relaxation == 2


async def test_action_forms_suggest_strings(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Aero", "tension_unit": "lbs", "play": {"hours_per_week": 4}},
    )
    entry_id = result["result"].entry_id
    await hass.async_block_till_done()

    def options(service: str, field: str) -> list[str]:
        selector = descriptions[DOMAIN][service]["fields"][field]["selector"]
        assert selector["select"]["custom_value"] is True
        return selector["select"]["options"]

    descriptions = await async_get_all_descriptions(hass)
    assert "Solinco Hyper-G 17 (1.20)" in options("add_restring", "main_string")
    assert "Solinco Hyper-G 17 (1.20)" in options("update_restring", "cross_string")
    # Other fields keep their services.yaml selectors
    fields = descriptions[DOMAIN]["add_restring"]["fields"]
    assert "number" in fields["main_tension"]["selector"]

    # A string you logged comes first next time
    await hass.services.async_call(
        DOMAIN,
        "add_restring",
        {
            "config_entry_id": entry_id,
            "main_string": "My Custom Poly",
            "main_tension": 50,
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    descriptions = await async_get_all_descriptions(hass)
    assert options("add_restring", "main_string")[0] == "My Custom Poly"

    # Unknown string: the estimate falls back to polyester and says so
    state = hass.states.get("sensor.aero_estimated_tension")
    assert state.attributes["string_type"] == "polyester"
    assert state.attributes["string_type_source"] == "default"
    await hass.services.async_call(
        DOMAIN,
        "update_restring",
        {"config_entry_id": entry_id, "main_string": "Babolat VS Touch 1.30"},
        blocking=True,
    )
    await hass.async_block_till_done()
    state = hass.states.get("sensor.aero_estimated_tension")
    assert state.attributes["string_type"] == "gut"
    assert state.attributes["string_type_source"] == "string"
