"""Repair issues for rackets linked to the Racqix dataset."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.racket_tracker.const import DOMAIN
from custom_components.racket_tracker.dataset import DATASET_URL, RACQUET_URL
from custom_components.racket_tracker.repairs import describe_changes

URL = RACQUET_URL.format(slug="babolat-pure-aero-2023")


def _detail(**changes: str) -> dict:
    """The single-racket API's answer: other field names, numbers as text."""
    return {
        "slug": "babolat-pure-aero-2023",
        "brand": "Babolat",
        "model": "Pure Aero",
        "year": "2023",
        "specs_weight_unstrung_g": "300",
        "specs_balance_unstrung_mm": "320",
        "advanced_swingweight": "320",
        "specs_stiffness_ra": "68",
        "specs_head_size_in": "100",
        "specs_string_pattern": "16x19",
        "scores_spin": "100",
        "updated_at\r": "2025-12-23\r",  # sic
        **changes,
    }


LINKED = {
    "tension_unit": "lbs",
    "dataset_specs": {
        "unstrung_weight": 300,
        "balance": 320,
        "swingweight": 320,
        "stiffness": 68,
    },
    "dataset_racket": {
        "slug": "babolat-pure-aero-2023",
        "name": "Babolat Pure Aero (2023)",
        "version": "2026.1",
    },
}


async def _setup(hass: HomeAssistant, options: dict) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, title="Aero", options=options, version=1, minor_version=2
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _fix(hass: HomeAssistant, hass_client, issue_id: str) -> dict:
    assert await async_setup_component(hass, "repairs", {})
    client = await hass_client()
    resp = await client.post(
        "/api/repairs/issues/fix", json={"handler": DOMAIN, "issue_id": issue_id}
    )
    assert resp.status == 200
    flow = await resp.json()
    assert flow["step_id"] == "confirm"
    resp = await client.post(f"/api/repairs/issues/fix/{flow['flow_id']}")
    assert resp.status == 200
    await hass.async_block_till_done()
    return flow


def test_describe_changes() -> None:
    assert describe_changes(
        {"stiffness": 68, "balance": 320}, {"stiffness": 66, "swingweight": 318}
    ) == (
        "- balance: 320 mm → —\n"
        "- stiffness: 68 RA → 66 RA\n"
        "- swingweight: — → 318 kg·cm²"
    )


async def test_up_to_date_racket_has_no_issue(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(URL, json=_detail())
    await _setup(hass, LINKED)
    assert not ir.async_get(hass).issues
    # Not linked: no request at all
    await _setup(hass, {"tension_unit": "lbs"})
    assert aioclient_mock.call_count == 1
    # Only that racket was asked for, never the whole list
    assert all(str(url) != DATASET_URL for _, url, *_ in aioclient_mock.mock_calls)


async def test_specs_changed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, hass_client
) -> None:
    aioclient_mock.get(URL, json=_detail(specs_stiffness_ra="66"))
    entry = await _setup(hass, {**LINKED, "specs": {"stiffness": 70}})
    issue_id = f"dataset_specs_changed_{entry.entry_id}"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue is not None and issue.is_fixable
    assert issue.translation_placeholders["changes"] == "- stiffness: 68 RA → 66 RA"

    flow = await _fix(hass, hass_client, issue_id)
    assert "68 RA → 66 RA" in flow["description_placeholders"]["changes"]
    assert entry.options["dataset_specs"]["stiffness"] == 66
    assert entry.options["specs"] == {"stiffness": 70}  # measured still wins
    assert float(hass.states.get("sensor.aero_stiffness").state) == 70
    assert float(hass.states.get("sensor.aero_balance").state) == 320
    # Reloaded and checked again: up to date now
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_racket_missing(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, hass_client
) -> None:
    aioclient_mock.get(URL, status=404, json={"error": "Racquet not found"})
    entry = await _setup(hass, LINKED)
    issue_id = f"dataset_racket_missing_{entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id)

    await _fix(hass, hass_client, issue_id)
    assert "dataset_racket" not in entry.options
    assert entry.options["dataset_specs"]["stiffness"] == 68  # kept
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None

    # The options flow still offers to drop the kept specs
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "use_dataset" in result["data_schema"].schema


async def test_removing_racket_removes_its_issues(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(URL, status=404, json={"error": "Racquet not found"})
    entry = await _setup(hass, LINKED)
    assert ir.async_get(hass).issues
    await hass.config_entries.async_remove(entry.entry_id)
    assert not ir.async_get(hass).issues


async def test_unreachable(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    aioclient_mock.get(URL, status=503)
    entry = await _setup(hass, LINKED)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "dataset_unreachable")
    # Specs keep working
    assert float(hass.states.get("sensor.aero_stiffness").state) == 68

    # A reload within the hour doesn't ask again
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 1

    # Later, it's back
    freezer.tick(3700)
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, json=_detail())
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 1
    assert not ir.async_get(hass).issues
