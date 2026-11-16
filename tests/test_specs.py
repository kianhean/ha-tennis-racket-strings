"""Racket specs: user-measured values override dataset values."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from custom_components.racket_tracker.const import DOMAIN


async def _add(hass: HomeAssistant, specs: dict | None = None) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    data = {"name": "Blade", "tension_unit": "lbs"}
    if specs is not None:
        data["specs"] = specs
    result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
    assert result["type"] == "create_entry", result
    await hass.async_block_till_done()
    return result["result"].entry_id


async def test_specs_from_config_flow(hass: HomeAssistant) -> None:
    await _add(
        hass,
        {
            "strung_weight": 321.5,
            "balance": 320,
            "swingweight": 325,
            "stiffness": 62,
            "tension_min": 50,
            "tension_max": 60,
        },
    )
    weight = hass.states.get("sensor.blade_strung_weight")
    assert float(weight.state) == 321.5
    assert weight.attributes["unit_of_measurement"] == "g"
    assert weight.attributes["source"] == "measured"
    # The number selector makes 325 a float; it still shows as 325
    assert hass.states.get("sensor.blade_swingweight").state == "325"
    assert (
        hass.states.get("sensor.blade_stiffness").attributes["unit_of_measurement"]
        == "RA"
    )
    assert (
        hass.states.get("sensor.blade_recommended_tension_min").attributes[
            "unit_of_measurement"
        ]
        == "lbs"
    )
    # Specs that weren't entered don't create entities
    assert hass.states.get("sensor.blade_length") is None


async def test_no_specs_section(hass: HomeAssistant) -> None:
    await _add(hass)
    assert hass.states.get("sensor.blade_balance") is None


async def test_tension_range_validated(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Blade",
            "tension_unit": "lbs",
            "specs": {"tension_min": 60, "tension_max": 50},
        },
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "tension_range"}


async def test_measured_overrides_dataset_and_clearing(hass: HomeAssistant) -> None:
    entry_id = await _add(hass, {"balance": 322})
    entry = hass.config_entries.async_get_entry(entry_id)

    # Simulate a dataset lookup filling base values
    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            "dataset_specs": {"balance": 315, "length": 27, "stiffness": 65},
        },
    )
    await hass.async_block_till_done()
    balance = hass.states.get("sensor.blade_balance")
    assert float(balance.state) == 322 and balance.attributes["source"] == "measured"
    length = hass.states.get("sensor.blade_length")
    assert float(length.state) == 27 and length.attributes["source"] == "dataset"

    # Options flow: the user measures stiffness too, and clears balance
    result = await hass.config_entries.options.async_init(entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tension_unit": "lbs", "specs": {"stiffness": 63}}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    entry = hass.config_entries.async_get_entry(entry_id)
    assert entry.options["dataset_specs"]["stiffness"] == 65  # dataset kept
    stiff = hass.states.get("sensor.blade_stiffness")
    assert float(stiff.state) == 63 and stiff.attributes["source"] == "measured"
    # Balance falls back to the dataset value
    assert hass.states.get("sensor.blade_balance").attributes["source"] == "dataset"

    # Remove the dataset too: the balance sensor goes away entirely
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, "dataset_specs": {"length": 27}}
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.blade_balance") is None
    assert er.async_get(hass).async_get("sensor.blade_balance") is None

    resp = await hass.services.async_call(
        DOMAIN,
        "get_history",
        {"config_entry_id": entry_id},
        blocking=True,
        return_response=True,
    )
    assert resp["specs"]["stiffness"] == {"value": 63, "source": "measured"}


async def test_flows_serialize_over_http(hass: HomeAssistant, hass_client) -> None:
    """The forms (with the collapsible specs section) render for the frontend."""
    # Load the integration (and its http/media_source dependencies) before the
    # test client starts the web server: routes can't be added after that.
    assert await async_setup_component(hass, "config", {})
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    client = await hass_client()
    resp = await client.post(
        "/api/config/config_entries/flow", json={"handler": DOMAIN}
    )
    assert resp.status == 200
    form = await resp.json()
    section = next(f for f in form["data_schema"] if f["name"] == "specs")
    assert section["type"] == "expandable"
    assert {f["name"] for f in section["schema"]} >= {"balance", "swingweight"}

    resp = await client.post(
        f"/api/config/config_entries/flow/{form['flow_id']}",
        json={"name": "Speed", "tension_unit": "kg", "specs": {"strung_weight": 315}},
    )
    assert (await resp.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    entry_id = hass.config_entries.async_entries(DOMAIN)[0].entry_id

    resp = await client.post(
        "/api/config/config_entries/options/flow", json={"handler": entry_id}
    )
    assert resp.status == 200
    form = await resp.json()
    assert any(f["name"] == "specs" for f in form["data_schema"])
