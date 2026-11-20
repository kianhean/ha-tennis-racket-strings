"""Export restring history to CSV, and import it from CSV (a backup or a spreadsheet).

Exports go to <config>/racket_tracker/exports/ (not served over HTTP) and are
also returned in the action's response. Imports read a file from the exports
folder or an allowed one (allowlist_external_dirs), or CSV text, check every row first and add
them in one go; rows already in the history are skipped, so importing the same
file twice adds nothing. Photos aren't part of the CSV.

Logged play sessions go to a CSV of their own (racket, id, date, hours, notes),
written next to the restrings' when there are any. Import tells the two apart
by their columns: an "hours" column and no main string means play sessions.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_BROKEN_DATE,
    ATTR_COST,
    ATTR_CROSS_STRING,
    ATTR_CROSS_TENSION,
    ATTR_DATE,
    ATTR_HOURS,
    ATTR_MAIN_STRING,
    ATTR_MAIN_TENSION,
    ATTR_NOTES,
    ATTR_RATING,
    ATTR_SESSION_TYPE,
    ATTR_STRINGER,
    ATTR_SURFACE,
    DOMAIN,
    SESSION_TYPES,
    SURFACES,
    TENSION_UNIT_KG,
    TENSION_UNIT_LBS,
)

COLUMNS = (
    "racket",
    "id",
    ATTR_DATE,
    ATTR_MAIN_STRING,
    ATTR_MAIN_TENSION,
    ATTR_CROSS_STRING,
    ATTR_CROSS_TENSION,
    "tension_unit",
    ATTR_COST,
    ATTR_STRINGER,
    ATTR_RATING,
    ATTR_BROKEN_DATE,
    ATTR_NOTES,
)
PLAY_COLUMNS = (
    "racket",
    "id",
    ATTR_DATE,
    ATTR_HOURS,
    ATTR_SESSION_TYPE,
    ATTR_SURFACE,
    ATTR_NOTES,
)
# Spreadsheet headings we understand too
ALIASES = {
    "duration": ATTR_HOURS,
    "hours_played": ATTR_HOURS,
    "session_id": "id",
    "restring_date": ATTR_DATE,
    "strung": ATTR_DATE,
    "string": ATTR_MAIN_STRING,
    "strings": ATTR_MAIN_STRING,
    "mains": ATTR_MAIN_STRING,
    "main": ATTR_MAIN_STRING,
    "tension": ATTR_MAIN_TENSION,
    "crosses": ATTR_CROSS_STRING,
    "cross": ATTR_CROSS_STRING,
    "unit": "tension_unit",
    "price": ATTR_COST,
    "comment": ATTR_NOTES,
    "comments": ATTR_NOTES,
    "broken": ATTR_BROKEN_DATE,
    "broke": ATTR_BROKEN_DATE,
    "restring_id": "id",
}
MAX_IMPORT_BYTES = 5 * 1024 * 1024
KG_TO_LBS = 2.20462
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def export_dir(hass: HomeAssistant) -> Path:
    """Folder for exports (<config>/racket_tracker/exports)."""
    return Path(hass.config.path(DOMAIN, "exports"))


def to_csv(
    rows: list[tuple[str, dict[str, Any]]], columns: tuple[str, ...] = COLUMNS
) -> str:
    """CSV text for (racket name, restring or play session) pairs."""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for racket, record in rows:
        row = {k: record.get(k) for k in columns}
        row["racket"] = racket
        row["id"] = record.get("id")
        writer.writerow({k: "" if v is None else v for k, v in row.items()})
    return out.getvalue()


async def async_write_export(
    hass: HomeAssistant, name: str, text: str, suffix: str = ""
) -> Path:
    """Save an export; returns its path. suffix: "-play" for play sessions."""
    stamp = dt_util.now().strftime("%Y%m%d-%H%M%S")
    slug = "-".join(re.findall(r"[a-z0-9]+", name.lower())) or "rackets"
    path = export_dir(hass) / f"strung-{slug}-{stamp}{suffix}.csv"

    def _write() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    await hass.async_add_executor_job(_write)
    return path


def _error(key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders,
    )


async def async_read_import(hass: HomeAssistant, file: str) -> str:
    """Read a CSV file from an allowed folder."""
    path = Path(file)
    exports = export_dir(hass).resolve()
    if not (
        path.resolve().is_relative_to(exports) or hass.config.is_allowed_path(str(path))
    ):
        raise _error("import_file", file=file, reason="not in an allowed folder")

    def _read() -> str:
        if not path.is_file():
            raise _error("import_file", file=file, reason="not found")
        if path.stat().st_size > MAX_IMPORT_BYTES:
            raise _error("import_file", file=file, reason="larger than 5 MB")
        # utf-8-sig drops the byte-order mark spreadsheets like to add
        return path.read_text(encoding="utf-8-sig")

    text: str = await hass.async_add_executor_job(_read)
    return text


def _column(heading: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", heading.strip().lower()).strip("_")
    return ALIASES.get(key, key)


def _number(value: str) -> float | None:
    value = value.strip().replace(" ", "")
    if not value:
        return None
    if "," in value and "." not in value:
        value = value.replace(",", ".")  # 52,5
    value = re.sub(r"[^0-9.\-]", "", value)  # "$35", "52 lbs"
    return float(value)


def _date(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value).date().isoformat()
    except ValueError as err:
        raise ValueError(f"date {value!r} is not YYYY-MM-DD") from err


def _whole(value: float) -> float | int:
    return int(value) if value.is_integer() else value


def _tension(value: str, unit: str, racket_unit: str) -> float | int | None:
    number = _number(value)
    if number is None:
        return None
    if unit == TENSION_UNIT_KG and racket_unit == TENSION_UNIT_LBS:
        number = round(number * KG_TO_LBS, 1)
    elif unit == TENSION_UNIT_LBS and racket_unit == TENSION_UNIT_KG:
        number = round(number / KG_TO_LBS, 1)
    if not 1 <= number <= 100:
        raise ValueError(f"tension {value!r} is out of range")
    return _whole(number)


def _row(row: dict[str, str], racket_unit: str) -> dict[str, Any]:
    """One CSV row as a restring record (raises ValueError if it's unusable)."""
    unit = (row.get("tension_unit") or "").strip().lower() or racket_unit
    if unit in ("lb", "pounds"):
        unit = TENSION_UNIT_LBS
    if unit not in (TENSION_UNIT_LBS, TENSION_UNIT_KG):
        raise ValueError(f"tension unit {unit!r} is not lbs or kg")
    record: dict[str, Any] = {"tension_unit": racket_unit}
    if not (day := _date(row.get(ATTR_DATE) or "")):
        raise ValueError("date is missing")
    record[ATTR_DATE] = day
    if not (main := (row.get(ATTR_MAIN_STRING) or "").strip()):
        raise ValueError("main_string is missing")
    record[ATTR_MAIN_STRING] = main
    tension = _tension(row.get(ATTR_MAIN_TENSION) or "", unit, racket_unit)
    if tension is None:
        raise ValueError("main_tension is missing")
    record[ATTR_MAIN_TENSION] = tension
    record[ATTR_CROSS_STRING] = (row.get(ATTR_CROSS_STRING) or "").strip() or main
    cross = _tension(row.get(ATTR_CROSS_TENSION) or "", unit, racket_unit)
    record[ATTR_CROSS_TENSION] = tension if cross is None else cross
    if (cost := _number(row.get(ATTR_COST) or "")) is not None:
        if cost < 0:
            raise ValueError("cost is negative")
        record[ATTR_COST] = _whole(round(cost, 2))
    if (rating := _number(row.get(ATTR_RATING) or "")) is not None:
        if not (rating.is_integer() and 1 <= rating <= 5):
            raise ValueError(f"rating {rating:g} is not 1-5")
        record[ATTR_RATING] = int(rating)
    for key in (ATTR_STRINGER, ATTR_NOTES):
        if value := (row.get(key) or "").strip():
            record[key] = value
    if broken := _date(row.get(ATTR_BROKEN_DATE) or ""):
        if broken < day:
            raise ValueError("broken_date is before the restring date")
        record[ATTR_BROKEN_DATE] = broken
    if _ID.match(restring_id := (row.get("id") or "").strip()):
        record["id"] = restring_id
    return record


def _read_rows(text: str) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    """Headings and the non-empty rows (with their line numbers)."""
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    try:
        headings = [_column(h) for h in next(reader)]
    except StopIteration:
        raise _error("import_empty") from None
    rows = [
        (number, dict(zip(headings, values, strict=False)))
        for number, values in enumerate(reader, start=2)
        if any(v.strip() for v in values)
    ]
    return headings, rows


def _this_racket(
    rows: list[tuple[int, dict[str, str]]], racket: str
) -> tuple[list[tuple[int, dict[str, str]]], int]:
    """A "racket" column naming several rackets (an export of all of them)
    keeps only this racket's rows; with one name, every row is taken."""
    names = {(r.get("racket") or "").strip().lower() for _, r in rows} - {""}
    if len(names) <= 1:
        return rows, 0
    mine = [
        (n, r)
        for n, r in rows
        if (r.get("racket") or "").strip().lower() == racket.strip().lower()
    ]
    return mine, len(rows) - len(mine)


def is_play_csv(text: str) -> bool:
    """Whether a CSV holds play sessions (an "hours" column, no main string)."""
    headings, _ = _read_rows(text)
    return ATTR_HOURS in headings and ATTR_MAIN_STRING not in headings


def parse_csv(
    text: str, racket: str, racket_unit: str, existing: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int, int]:
    """Records to add, how many were already there, and rows for other rackets."""
    headings, rows = _read_rows(text)
    missing = {ATTR_DATE, ATTR_MAIN_STRING, ATTR_MAIN_TENSION} - set(headings)
    if missing:
        raise _error("import_columns", columns=", ".join(sorted(missing)))
    rows, other = _this_racket(rows, racket)

    ids = {r["id"] for r in existing}
    seen = {
        (
            r.get(ATTR_DATE),
            str(r.get(ATTR_MAIN_STRING)).lower(),
            r.get(ATTR_MAIN_TENSION),
        )
        for r in existing
    }
    records: list[dict[str, Any]] = []
    duplicates = 0
    for number, row in rows:
        try:
            record = _row(row, racket_unit)
        except ValueError as err:
            raise _error("import_row", row=str(number), reason=str(err)) from err
        key = (
            record[ATTR_DATE],
            record[ATTR_MAIN_STRING].lower(),
            record[ATTR_MAIN_TENSION],
        )
        if record.get("id") in ids or key in seen:
            duplicates += 1
            continue
        if "id" in record:
            ids.add(record["id"])
        seen.add(key)
        records.append(record)
    return records, duplicates, other


def _session_row(row: dict[str, str]) -> dict[str, Any]:
    """One CSV row as a play session (raises ValueError if it's unusable)."""
    if not (day := _date(row.get(ATTR_DATE) or "")):
        raise ValueError("date is missing")
    if (hours := _number(row.get(ATTR_HOURS) or "")) is None:
        raise ValueError("hours is missing")
    if not 0.1 <= hours <= 24:
        raise ValueError(f"hours {hours:g} is not 0.1-24")
    session: dict[str, Any] = {ATTR_DATE: day, ATTR_HOURS: _whole(round(hours, 2))}
    if stype := (row.get(ATTR_SESSION_TYPE) or "").strip().lower():
        if stype not in SESSION_TYPES:
            raise ValueError(f"session_type {stype!r} is not valid")
        session[ATTR_SESSION_TYPE] = stype
    if surface := (row.get(ATTR_SURFACE) or "").strip().lower():
        if surface not in SURFACES:
            raise ValueError(f"surface {surface!r} is not valid")
        session[ATTR_SURFACE] = surface
    if notes := (row.get(ATTR_NOTES) or "").strip():
        session[ATTR_NOTES] = notes
    if _ID.match(session_id := (row.get("id") or "").strip()):
        session["id"] = session_id
    return session


def parse_play_csv(
    text: str, racket: str, existing: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int, int]:
    """Play sessions to add, how many were already there, rows for other rackets.

    A duplicate has the same id, or the same date, hours and notes.
    """
    headings, rows = _read_rows(text)
    missing = {ATTR_DATE, ATTR_HOURS} - set(headings)
    if missing:
        raise _error("import_columns", columns=", ".join(sorted(missing)))
    rows, other = _this_racket(rows, racket)

    def key(s: dict[str, Any]) -> tuple[Any, ...]:
        return (s[ATTR_DATE], float(s[ATTR_HOURS]), s.get(ATTR_NOTES) or "")

    ids = {s["id"] for s in existing}
    seen = {key(s) for s in existing}
    sessions: list[dict[str, Any]] = []
    duplicates = 0
    for number, row in rows:
        try:
            session = _session_row(row)
        except ValueError as err:
            raise _error("import_row", row=str(number), reason=str(err)) from err
        if session.get("id") in ids or key(session) in seen:
            duplicates += 1
            continue
        if "id" in session:
            ids.add(session["id"])
        seen.add(key(session))
        sessions.append(session)
    return sessions, duplicates, other
