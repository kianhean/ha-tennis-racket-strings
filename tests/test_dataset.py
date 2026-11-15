"""Looking a racket up in the Racqix dataset fills in its specs."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.racket_tracker.const import DOMAIN
from custom_components.racket_tracker.dataset import (
    ATTRIBUTION,
    DATASET_URL,
    Dataset,
    dataset_specs,
    label,
    search,
)

PURE_AERO_2023 = {
    "slug": "babolat-pure-aero-2023",
    "brand": "Babolat",
    "model": "Pure Aero",
    "year": "2023",
    "weight": 300,
    "swingweight": 320,
    "ra": 68,
    "balance_mm": 320,
    "head_size": 100,
    "string_pattern": "16x19",
}
RACQUETS = [
    {**PURE_AERO_2023, "slug": "babolat-pure-aero-2019", "year": "2019", "ra": 69},
    PURE_AERO_2023,
    {
        "slug": "wilson-blade-98-v9",
        "brand": "Wilson",
        "model": "Blade 98",
        "year": None,
        "weight": 305,
        "swingweight": None,
        "ra": 62,
        "balance_mm": 9999,  # implausible: skipped
        "head_size": 98,
        "string_pattern": "16x19",
    },
]
PAYLOAD = {
    "dataset_version": "2026.1",
    "source": "Racqix Tennis Racquet Dataset",
    "racquets": RACQUETS,
}


def test_search_and_label() -> None:
    dataset = Dataset("2026.1", RACQUETS)
    assert [r["slug"] for r in search(dataset, "Pure Aero")] == [
        "babolat-pure-aero-2023",  # newest first
        "babolat-pure-aero-2019",
    ]
    assert [r["slug"] for r in search(dataset, "aero 2019")] == [
        "babolat-pure-aero-2019"
    ]
    assert [r["slug"] for r in search(dataset, "blade 16x19")] == ["wilson-blade-98-v9"]
    assert search(dataset, "prince") == []
    assert search(dataset, "  ") == []
    assert label(PURE_AERO_2023) == "Babolat Pure Aero (2023) · 100 in² · 16x19 · 300 g"
    assert dataset_specs(RACQUETS[2]) == {"unstrung_weight": 305, "stiffness": 62}


async def _start(hass: HomeAssistant, **extra) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Aero", "tension_unit": "lbs", **extra}
    )


async def test_lookup_fills_specs(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(DATASET_URL, json=PAYLOAD)
    result = await _start(
        hass, lookup="pure aero", model="Pure Aero 2023", specs={"balance": 322}
    )
    assert result["type"] == "form" and result["step_id"] == "pick"
    assert result["description_placeholders"]["count"] == "2"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"racquet": "babolat-pure-aero-2023"}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    options = result["result"].options
    assert options["brand"] == "Babolat"  # filled from the dataset
    assert options["model"] == "Pure Aero 2023"  # what the user typed wins
    assert options["head_size"] == 100
    assert options["dataset_racket"]["slug"] == "babolat-pure-aero-2023"
    assert options["dataset_racket"]["version"] == "2026.1"

    stiffness = hass.states.get("sensor.aero_stiffness")
    assert float(stiffness.state) == 68
    assert stiffness.attributes["source"] == "dataset"
    assert stiffness.attributes["attribution"] == ATTRIBUTION
    balance = hass.states.get("sensor.aero_balance")
    assert float(balance.state) == 322  # measured beats the dataset
    assert balance.attributes["source"] == "measured"
    assert "attribution" not in balance.attributes
    assert float(hass.states.get("sensor.aero_unstrung_weight").state) == 300

    # The list is cached: a second lookup doesn't fetch again
    result = await _start(hass, lookup="blade")
    assert result["step_id"] == "pick"
    assert aioclient_mock.call_count == 1


async def test_lookup_skip_no_match_and_offline(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(DATASET_URL, status=503)
    result = await _start(hass, lookup="pure aero")
    assert result["type"] == "form"
    assert result["errors"] == {"lookup": "cannot_connect"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(DATASET_URL, json=PAYLOAD)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Aero", "tension_unit": "lbs", "lookup": "zzz"}
    )
    assert result["errors"] == {"lookup": "no_match"}

    # Picking nothing adds the racket without dataset values
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Aero", "tension_unit": "lbs", "lookup": "aero"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    assert "dataset_specs" not in result["result"].options


async def test_options_lookup_and_unlink(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(DATASET_URL, json=PAYLOAD)
    result = await _start(hass)
    await hass.async_block_till_done()
    entry = result["result"]
    assert hass.states.get("sensor.aero_stiffness") is None

    # Look the racket up later, from Configure
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["description_placeholders"]["dataset_racket"] == "—"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tension_unit": "lbs", "lookup": "blade"}
    )
    assert result["step_id"] == "pick"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"racquet": "wilson-blade-98-v9"}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["brand"] == "Wilson"
    assert float(hass.states.get("sensor.aero_stiffness").state) == 62

    # Saving again keeps the link
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "Wilson Blade 98" in result["description_placeholders"]["dataset_racket"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tension_unit": "lbs", "use_dataset": True}
    )
    await hass.async_block_till_done()
    assert entry.options["dataset_specs"]["stiffness"] == 62

    # Turning it off removes the dataset values and their sensors
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tension_unit": "lbs", "use_dataset": False}
    )
    await hass.async_block_till_done()
    assert "dataset_specs" not in entry.options
    assert "dataset_racket" not in entry.options
    assert hass.states.get("sensor.aero_stiffness") is None
