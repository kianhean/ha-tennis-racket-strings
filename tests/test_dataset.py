"""Looking a racket up in the Racqix dataset fills in its specs."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.racket_tracker.const import DOMAIN
from custom_components.racket_tracker.dataset import (
    ATTRIBUTION,
    DATASET_URL,
    RACQUET_URL,
    Dataset,
    async_get_dataset,
    async_schedule_refresh,
    dataset_specs,
    label,
    model_name,
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
    assert model_name({**PURE_AERO_2023, "slug": "babolat-pure-aero-lite-2023"}) == (
        "Pure Aero Lite"
    )
    assert model_name(
        {"slug": "yonex-vcore-100", "brand": "Yonex", "model": "VCore"}
    ) == ("VCore 100")
    assert (
        model_name(
            {
                "slug": "volkl-v-feel-8-315-g-2019",
                "brand": "Volkl",
                "model": "V-Feel",
                "year": "2019",
            }
        )
        == "V-Feel 8 315 G"
    )
    assert model_name(RACQUETS[2]) == "Blade 98 V9"
    assert dataset_specs(RACQUETS[2]) == {"unstrung_weight": 305, "stiffness": 62}


def _mock_api(aioclient_mock: AiohttpClientMocker) -> None:
    """The list, and each racket on its own (what the repairs check asks for)."""
    aioclient_mock.get(DATASET_URL, json=PAYLOAD)
    detail = {
        "weight": "specs_weight_unstrung_g",
        "balance_mm": "specs_balance_unstrung_mm",
        "swingweight": "advanced_swingweight",
        "ra": "specs_stiffness_ra",
        "head_size": "specs_head_size_in",
        "string_pattern": "specs_string_pattern",
    }
    for racquet in RACQUETS:
        aioclient_mock.get(
            RACQUET_URL.format(slug=racquet["slug"]),
            json={detail.get(k, k): v for k, v in racquet.items()},
        )


def _list_calls(aioclient_mock: AiohttpClientMocker) -> int:
    return sum(str(url) == DATASET_URL for _, url, *_ in aioclient_mock.mock_calls)


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
    _mock_api(aioclient_mock)
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
    assert _list_calls(aioclient_mock) == 1


async def test_lookup_skip_no_match_and_offline(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    # Racqix's bot protection: the bundled copy is searched instead
    aioclient_mock.get(DATASET_URL, status=429)
    result = await _start(hass, lookup="pure aero 2023")
    assert result["step_id"] == "pick"
    assert "(offline copy)" in result["description_placeholders"]["dataset"]
    assert _list_calls(aioclient_mock) == 1

    # No second download the same day, even after a failure
    aioclient_mock.clear_requests()
    _mock_api(aioclient_mock)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Aero", "tension_unit": "lbs", "lookup": "zzz"}
    )
    assert result["errors"] == {"lookup": "no_match"}
    assert _list_calls(aioclient_mock) == 0

    # Picking nothing adds the racket without dataset values
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Aero", "tension_unit": "lbs", "lookup": "aero"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    assert "dataset_specs" not in result["result"].options


async def test_bundled_copy() -> None:
    """The bundled file is an unmodified Racqix download (CC BY-NC-ND)."""
    from custom_components.racket_tracker.dataset import BUNDLED_FILE, _parse

    payload = json.loads(BUNDLED_FILE.read_text(encoding="utf-8"))
    dataset = _parse(payload, None)
    assert dataset is not None and dataset.downloaded is None
    assert len(dataset.racquets) == payload["total_racquets"] > 1000
    assert (BUNDLED_FILE.parent / "racqix_dataset.NOTICE.md").exists()


async def test_download_kept_across_restarts(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    _mock_api(aioclient_mock)
    dataset = await async_get_dataset(hass)
    assert dataset.downloaded and [r["slug"] for r in dataset.racquets] == [
        r["slug"] for r in RACQUETS
    ]
    await hass.async_block_till_done()
    stored = hass_storage["racket_tracker.dataset"]["data"]
    assert stored["payload"] == PAYLOAD and stored["attempted"]

    # A restart (empty memory) uses the stored download without asking again
    hass.data.pop("racket_tracker_dataset")
    assert (await async_get_dataset(hass)).racquets == RACQUETS
    assert _list_calls(aioclient_mock) == 1

    # A day later it downloads again; a failure keeps the last download
    freezer.tick(timedelta(days=1, seconds=1))
    aioclient_mock.clear_requests()
    aioclient_mock.get(DATASET_URL, status=429)
    dataset = await async_get_dataset(hass)
    assert _list_calls(aioclient_mock) == 1
    assert dataset.racquets == RACQUETS and dataset.downloaded


async def test_download_after_start(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    _mock_api(aioclient_mock)
    async_schedule_refresh(hass)  # HA is already running: refreshes now
    await hass.async_block_till_done(wait_background_tasks=True)
    assert _list_calls(aioclient_mock) == 1
    state = hass.data["racket_tracker_dataset"]
    assert state.dataset.downloaded
    assert dt_util.utcnow() - state.attempted < timedelta(minutes=1)


async def test_options_lookup_and_unlink(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    _mock_api(aioclient_mock)
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
