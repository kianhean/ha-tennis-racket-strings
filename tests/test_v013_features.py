"""Tests for v0.13.0 features: bundled cards, WebSocket API, bag summary,
duplicate racket flow, calibration history, play metadata, update_play,
kg script bounds, and full zip backup/restore.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from custom_components.racket_tracker.const import DOMAIN

from .test_integration import PNG, _add_racket


async def _call(hass: HomeAssistant, service: str, **data: Any) -> Any:
    return await hass.services.async_call(
        DOMAIN, service, data, blocking=True, return_response=True
    )


async def test_duplicate_racket_in_config_flow(hass: HomeAssistant) -> None:
    """Adding a second racket can copy specs, play, due and setup from an existing one."""
    assert await async_setup_component(hass, "http", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    res1 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Pure Aero #1",
            "brand": "Babolat",
            "model": "Pure Aero 98",
            "head_size": 98,
            "string_pattern": "16x20",
            "tension_unit": "kg",
            "play": {"tracking": "logged", "session_hours": 2},
            "due": {"days": 45},
            "setup": {"main_string": "Hyper-G 1.25", "main_tension": 23},
            "specs": {"strung_weight": 318, "swingweight": 320},
            "current": {"main_string": "Hyper-G 1.25", "main_tension": 23},
        },
    )
    entry1 = res1["result"]
    await hass.async_block_till_done()

    # Add matched pair #2 copying from #1
    result2 = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    res2 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        {
            "name": "Pure Aero #2",
            "copy_from": entry1.entry_id,
            "specs": {"strung_weight": 319},  # override one measured spec
        },
    )
    entry2 = res2["result"]
    await hass.async_block_till_done()

    assert entry2.options["brand"] == "Babolat"
    assert entry2.options["model"] == "Pure Aero 98"
    assert entry2.options["tension_unit"] == "kg"
    assert entry2.options["play"]["tracking"] == "logged"
    assert entry2.options["due"]["days"] == 45
    assert entry2.options["setup"]["main_string"] == "Hyper-G 1.25"
    assert entry2.options["specs"]["strung_weight"] == 319
    assert entry2.options["specs"]["swingweight"] == 320
    # Current strings are NOT copied from racket #1
    assert entry2.runtime_data.count == 0


async def test_bag_summary_and_setup_showdown(hass: HomeAssistant) -> None:
    """get_bag_summary aggregates totals, readiness ranking and setup comparison."""
    assert await async_setup_component(hass, "http", {})
    today = dt_util.now().date()

    # Racket 1: fresh match-ready racket
    r1 = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    aero = (
        await hass.config_entries.flow.async_configure(
            r1["flow_id"],
            {
                "name": "Pure Aero",
                "tension_unit": "lbs",
                "play": {"hours_per_week": 4},
                "due": {"days": 60},
            },
        )
    )["result"].entry_id

    # Racket 2: overdue racket
    r2 = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    blade = (
        await hass.config_entries.flow.async_configure(
            r2["flow_id"],
            {
                "name": "Blade",
                "tension_unit": "lbs",
                "play": {"hours_per_week": 3},
                "due": {"days": 30},
            },
        )
    )["result"].entry_id
    await hass.async_block_till_done()

    # Past + current restring on Pure Aero
    await _call(
        hass,
        "add_restring",
        config_entry_id=aero,
        date=(today - timedelta(days=30)).isoformat(),
        main_string="Hyper-G 1.25",
        main_tension=52,
        cost=35,
        rating=5,
        broken_date=(today - timedelta(days=5)).isoformat(),
    )
    await _call(
        hass,
        "add_restring",
        config_entry_id=aero,
        date=(today - timedelta(days=2)).isoformat(),
        main_string="Hyper-G 1.25",
        main_tension=52,
        cost=35,
        rating=5,
    )
    # Overdue restring on Blade
    await _call(
        hass,
        "add_restring",
        config_entry_id=blade,
        date=(today - timedelta(days=45)).isoformat(),
        main_string="ALU Power 1.25",
        main_tension=50,
        cost=40,
        rating=3,
    )

    bag = await _call(hass, "get_bag_summary")
    assert bag["totals"]["racket_count"] == 2
    assert bag["totals"]["restrings_total"] == 3
    assert bag["totals"]["due_count"] == 1
    assert bag["totals"]["ready_count"] == 1

    # Pure Aero (fresh) ranks before Blade (due)
    assert [r["name"] for r in bag["rackets"]] == ["Pure Aero", "Blade"]
    assert bag["rackets"][0]["status"] == "ready"
    assert bag["rackets"][0]["freshness"] >= 70
    assert bag["rackets"][1]["status"] == "due"
    assert bag["rackets"][1]["due"] is True

    # String Setup Showdown ranks Hyper-G (5.0★) above ALU Power (3.0★)
    setups = bag["setups"]
    assert [s["setup"] for s in setups] == ["Hyper-G 1.25", "ALU Power 1.25"]
    assert setups[0]["jobs"] == 2
    assert setups[0]["average_rating"] == 5.0
    assert setups[0]["breakages"] == 1
    assert setups[0]["breakage_rate"] == 100.0
    assert setups[0]["average_life_days"] == 25.0


async def test_update_play_and_session_metadata(hass: HomeAssistant) -> None:
    """log_play and update_play persist hours, date, session_type, surface and notes."""
    assert await async_setup_component(hass, "http", {})
    entry_id = await _add_racket(hass)
    opt = await hass.config_entries.options.async_init(entry_id)
    await hass.config_entries.options.async_configure(
        opt["flow_id"], {"tension_unit": "lbs", "play": {"tracking": "logged"}}
    )
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError):
        await _call(hass, "update_play", config_entry_id=entry_id, hours=2)

    logged = await _call(
        hass,
        "log_play",
        config_entry_id=entry_id,
        hours=1.5,
        date="2026-10-10",
        session_type="singles_match",
        surface="clay",
        notes="Club ladder",
    )
    sess_id = logged["session"]["id"]
    assert logged["session"]["session_type"] == "singles_match"
    assert logged["session"]["surface"] == "clay"

    # Update latest session (no session_id needed)
    updated = await _call(
        hass,
        "update_play",
        config_entry_id=entry_id,
        hours=2.5,
        surface="hard",
        notes="3-set match",
    )
    assert updated["session"]["id"] == sess_id
    assert updated["session"]["hours"] == 2.5
    assert updated["session"]["surface"] == "hard"
    assert updated["session"]["notes"] == "3-set match"

    with pytest.raises(ServiceValidationError):
        await _call(
            hass,
            "update_play",
            config_entry_id=entry_id,
            session_id="nonexistent",
            hours=1,
        )


async def test_calibration_history_stored(hass: HomeAssistant) -> None:
    """calibrate_tension stores each measurement with optional tool in history."""
    assert await async_setup_component(hass, "http", {})
    today = dt_util.now().date()
    r = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    entry_id = (
        await hass.config_entries.flow.async_configure(
            r["flow_id"],
            {"name": "Pure Aero", "tension_unit": "lbs", "play": {"hours_per_week": 4}},
        )
    )["result"].entry_id
    await hass.async_block_till_done()

    added = await _call(
        hass,
        "add_restring",
        config_entry_id=entry_id,
        date=(today - timedelta(days=10)).isoformat(),
        main_string="Hyper-G 1.25",
        main_tension=52,
    )
    res = await _call(
        hass,
        "calibrate_tension",
        config_entry_id=entry_id,
        tension=44.5,
        tool="ERT 300",
    )
    assert res["calibration"]["tension"] == 44.5
    assert res["calibration"]["tool"] == "ERT 300"
    assert res["calibration"]["restring_id"] == added["restring"]["id"]
    await hass.async_block_till_done()

    hist = await _call(hass, "get_history", config_entry_id=entry_id)
    assert len(hist["calibrations"]) == 1
    assert hist["calibrations"][0]["tool"] == "ERT 300"


async def test_zip_backup_and_restore(hass: HomeAssistant, tmp_path: Path) -> None:
    """export_backup and import_backup round-trip restrings, play sessions, calibrations and photos."""
    hass.config.media_dirs = {"local": str(tmp_path)}
    (tmp_path / "racket.png").write_bytes(PNG)
    assert await async_setup_component(hass, "http", {})

    r = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    aero = (
        await hass.config_entries.flow.async_configure(
            r["flow_id"],
            {
                "name": "Pure Aero",
                "tension_unit": "lbs",
                "play": {"tracking": "logged"},
            },
        )
    )["result"].entry_id
    await hass.async_block_till_done()

    await _call(
        hass,
        "add_restring",
        config_entry_id=aero,
        date="2026-10-01",
        main_string="Hyper-G 1.25",
        main_tension=52,
        image={
            "media_content_id": "media-source://media_source/local/racket.png",
            "media_content_type": "image/png",
        },
    )
    await _call(
        hass,
        "log_play",
        config_entry_id=aero,
        date="2026-10-05",
        hours=2,
        session_type="practice",
        surface="hard",
    )

    exported = await _call(hass, "export_backup", config_entry_id=aero)
    backup_file = Path(exported["file"])
    assert backup_file.is_file()
    assert exported["rackets"] == 1
    assert exported["restrings"] == 1
    assert exported["play_sessions"] == 1
    assert exported["photos"] == 1

    # Re-importing into the same racket skips duplicates
    reimp = await _call(hass, "import_backup", file=str(backup_file))
    assert reimp["rackets_matched"] == 1
    assert reimp["imported_restrings"] == 0
    assert reimp["skipped_restrings"] == 1
    assert reimp["imported_sessions"] == 0
    assert reimp["skipped_sessions"] == 1

    # Importing into a fresh racket restores everything
    r2 = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    clone = (
        await hass.config_entries.flow.async_configure(
            r2["flow_id"], {"name": "Restored Aero", "tension_unit": "lbs"}
        )
    )["result"].entry_id
    await hass.async_block_till_done()

    restored = await _call(
        hass, "import_backup", file=str(backup_file), config_entry_id=clone
    )
    assert restored["imported_restrings"] == 1
    assert restored["imported_sessions"] == 1

    # Reject bad zip files
    bad_zip = backup_file.parent / "bad.zip"
    bad_zip.write_bytes(b"not a zip")
    with pytest.raises(ServiceValidationError):
        await _call(hass, "import_backup", file=str(bad_zip))


async def test_websocket_api_and_static_card(
    hass: HomeAssistant, hass_ws_client: Any, hass_client: Any
) -> None:
    """Bundled JS card is served over HTTP and WebSocket commands return bag/racket/strings."""
    assert await async_setup_component(hass, "http", {})
    entry_id = await _add_racket(hass)
    await _call(
        hass,
        "add_restring",
        config_entry_id=entry_id,
        main_string="Hyper-G 1.25",
        main_tension=52,
    )

    # WebSocket commands (set up websocket_api before hass_client freezes router)
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": f"{DOMAIN}/bag"})
    msg = await ws.receive_json()
    assert msg["success"] is True
    assert msg["result"]["totals"]["racket_count"] == 1

    await ws.send_json(
        {"id": 2, "type": f"{DOMAIN}/racket", "config_entry_id": entry_id}
    )
    msg2 = await ws.receive_json()
    assert msg2["success"] is True
    assert msg2["result"]["racket"]["name"] == "Pure Aero"
    assert len(msg2["result"]["restrings"]) == 1

    await ws.send_json({"id": 3, "type": f"{DOMAIN}/strings"})
    msg3 = await ws.receive_json()
    assert msg3["success"] is True
    assert "Hyper-G 1.25" in msg3["result"]["strings"]

    await ws.send_json(
        {"id": 4, "type": f"{DOMAIN}/racket", "config_entry_id": "missing"}
    )
    msg4 = await ws.receive_json()
    assert msg4["success"] is False
    assert msg4["error"]["code"] == "not_found"

    # Static JS bundle served over HTTP
    http_client = await hass_client()
    resp = await http_client.get(f"/{DOMAIN}/strung-cards.js")
    assert resp.status == 200
    body = await resp.text()
    assert "strung-racket-card" in body
    assert "strung-bag-card" in body
