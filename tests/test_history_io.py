"""Export history to CSV and import it back (or from a spreadsheet)."""

from __future__ import annotations

from pathlib import Path

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.racket_tracker.const import DOMAIN, EVENT_RESTRUNG


async def _racket(hass: HomeAssistant, name: str, unit: str = "lbs") -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": name, "tension_unit": unit}
    )
    await hass.async_block_till_done()
    return result["result"].entry_id


async def _call(hass: HomeAssistant, service: str, **data):
    return await hass.services.async_call(
        DOMAIN, service, data, blocking=True, return_response=True
    )


async def test_export_and_import_round_trip(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    hass.config.allowlist_external_dirs = set()  # exports are always readable
    aero = await _racket(hass, "Aero")
    blade = await _racket(hass, "Blade", "kg")
    await _call(
        hass,
        "add_restring",
        config_entry_id=aero,
        date="2026-01-10",
        main_string="RPM Blast, 1.25",
        main_tension=52,
        cost=30,
        rating=4,
        notes='Said "great"\nnew line',
        broken_date="2026-02-01",
    )
    await _call(
        hass,
        "add_restring",
        config_entry_id=blade,
        date="2026-01-12",
        main_string="ALU Power",
        main_tension=24,
    )

    one = await _call(hass, "export_history", config_entry_id=aero)
    assert one["restrings"] == 1
    assert Path(one["file"]).is_file()
    assert Path(one["file"]).parent == Path(hass.config.path(DOMAIN, "exports"))
    assert one["csv"].splitlines()[0].startswith("racket,id,date,main_string")
    assert '"RPM Blast, 1.25"' in one["csv"]

    both = await _call(hass, "export_history")
    assert both["restrings"] == 2 and "Blade" in both["csv"]

    # Importing into the same racket adds nothing
    resp = await _call(hass, "import_history", config_entry_id=aero, file=one["file"])
    assert resp["imported"] == 0 and resp["skipped_duplicates"] == 1

    # A new racket gets Aero's rows from the all-rackets export, by name
    events = async_capture_events(hass, EVENT_RESTRUNG)
    entry = hass.config_entries.async_get_entry(aero)
    await hass.config_entries.async_remove(aero)
    aero2 = await _racket(hass, "Aero")
    resp = await _call(hass, "import_history", config_entry_id=aero2, csv=both["csv"])
    assert resp == {
        "racket": "Aero",
        "contents": "restrings",
        "imported": 1,
        "skipped_duplicates": 0,
        "skipped_other_rackets": 1,
    }
    assert not events  # Old restrings don't fire restrung events
    await hass.async_block_till_done()
    record = hass.states.get("sensor.aero_strings").attributes
    assert record["main_string"] == "RPM Blast, 1.25"
    assert record["notes"] == 'Said "great"\nnew line'
    assert record["broken_date"] == "2026-02-01"
    assert record["rating"] == 4 and record["cost"] == 30
    assert entry is not None


async def test_import_spreadsheet(hass: HomeAssistant, tmp_path: Path) -> None:
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    racket = await _racket(hass, "Aero")
    sheet = tmp_path / "strings.csv"
    # Semicolons, decimal commas, kg, a byte-order mark and spreadsheet headings
    sheet.write_text(
        "﻿Date;String;Tension;Unit;Price;Comments\n"
        "2025-05-01;Hyper-G 1.25;23,5;kg;€35;Nice\n"
        ";;;;;\n"
        "2025-06-01T10:00:00;4G;52;;;\n",
        encoding="utf-8",
    )
    resp = await _call(hass, "import_history", config_entry_id=racket, file=str(sheet))
    assert resp["imported"] == 2
    hist = await _call(hass, "get_history", config_entry_id=racket)
    first, second = reversed(hist["restrings"])
    assert first["main_tension"] == 51.8 and first["cross_tension"] == 51.8
    assert first["cost"] == 35 and first["notes"] == "Nice"
    assert first["cross_string"] == "Hyper-G 1.25"
    assert second["date"] == "2025-06-01" and second["main_tension"] == 52


@pytest.mark.parametrize(
    ("data", "key"),
    [
        ({"csv": ""}, "import_empty"),
        ({"csv": "date,notes\n2026-01-01,x"}, "import_columns"),
        ({"csv": "date,main_string,main_tension\n01/02/2026,X,52"}, "import_row"),
        ({"csv": "date,main_string,main_tension\n2026-01-01,X,520"}, "import_row"),
        (
            {"csv": "date,main_string,main_tension,rating\n2026-01-01,X,52,9"},
            "import_row",
        ),
        (
            {
                "csv": "date,main_string,main_tension,broken_date\n2026-01-05,X,52,2026-01-01"
            },
            "import_row",
        ),
        ({"file": "/etc/passwd"}, "import_file"),
        ({"file": "/nope/missing.csv"}, "import_file"),
    ],
)
async def test_import_errors(
    hass: HomeAssistant, tmp_path: Path, data: dict, key: str
) -> None:
    hass.config.allowlist_external_dirs = {"/nope"}
    racket = await _racket(hass, "Aero")
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "import_history", config_entry_id=racket, **data)
    assert err.value.translation_key == key
    hist = await _call(hass, "get_history", config_entry_id=racket)
    assert hist["restring_count"] == 0


async def test_play_sessions_round_trip(hass: HomeAssistant) -> None:
    aero = await _racket(hass, "Aero")
    blade = await _racket(hass, "Blade")
    one = await _call(hass, "export_history", config_entry_id=aero)
    assert "play_file" not in one  # No sessions, no second file

    for entry_id in (aero, blade):
        result = await hass.config_entries.options.async_init(entry_id)
        await hass.config_entries.options.async_configure(
            result["flow_id"], {"tension_unit": "lbs", "play": {"tracking": "logged"}}
        )
        await hass.async_block_till_done()
    await _call(hass, "log_play", config_entry_id=aero, hours=1.5, date="2026-03-01")
    await _call(
        hass,
        "log_play",
        config_entry_id=aero,
        hours=2,
        date="2026-03-03",
        notes="Match, 3 sets",
    )
    await _call(hass, "log_play", config_entry_id=blade, hours=1, date="2026-03-02")

    both = await _call(hass, "export_history")
    assert both["play_sessions"] == 3
    assert Path(both["play_file"]).name.endswith("-play.csv")
    assert (
        both["play_csv"].splitlines()[0]
        == "racket,id,date,hours,session_type,surface,notes"
    )
    assert '"Match, 3 sets"' in both["play_csv"]

    # Back into the same racket: all duplicates
    resp = await _call(
        hass, "import_history", config_entry_id=aero, file=both["play_file"]
    )
    assert resp == {
        "racket": "Aero",
        "contents": "play_sessions",
        "imported": 0,
        "skipped_duplicates": 2,
        "skipped_other_rackets": 1,
    }

    # A spreadsheet: "Duration" heading, no IDs; the same session twice is one
    sheet = "Date;Duration;Notes\n2026-03-01;1,5;\n2026-03-05;1;Drills\n2026-03-05;1;Drills\n"
    resp = await _call(hass, "import_history", config_entry_id=aero, csv=sheet)
    assert resp["imported"] == 1 and resp["skipped_duplicates"] == 2
    entry = hass.config_entries.async_get_entry(aero)
    assert [(s["date"], s["hours"]) for s in entry.runtime_data.sessions] == [
        ("2026-03-01", 1.5),
        ("2026-03-03", 2),
        ("2026-03-05", 1),
    ]

    with pytest.raises(ServiceValidationError, match="Row 2"):
        await _call(
            hass,
            "import_history",
            config_entry_id=aero,
            csv="date,hours\n2026-03-01,30\n",
        )
