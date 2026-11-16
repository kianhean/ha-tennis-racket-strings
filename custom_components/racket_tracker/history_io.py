"""Export restring history to CSV, and import it from CSV (a backup or a spreadsheet).

Exports go to <config>/racket_tracker/exports/ (not served over HTTP) and are
also returned in the action's response. Imports read a file from the exports
folder or an allowed one (allowlist_external_dirs), or CSV text, check every row first and add
them in one go; rows already in the history are skipped, so importing the same
file twice adds nothing. Photos aren't part of the CSV.
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
    ATTR_MAIN_STRING,
    ATTR_MAIN_TENSION,
    ATTR_NOTES,
    ATTR_RATING,
    ATTR_STRINGER,
    DOMAIN,
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
# Spreadsheet headings we understand too
ALIASES = {
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


def to_csv(rows: list[tuple[str, dict[str, Any]]]) -> str:
    """CSV text for (racket name, restring) pairs."""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for racket, record in rows:
        row = {k: record.get(k) for k in COLUMNS}
        row["racket"] = racket
        row["id"] = record.get("id")
        writer.writerow({k: "" if v is None else v for k, v in row.items()})
    return out.getvalue()


async def async_write_export(hass: HomeAssistant, name: str, text: str) -> Path:
    """Save an export; returns its path."""
    stamp = dt_util.now().strftime("%Y%m%d-%H%M%S")
    slug = "-".join(re.findall(r"[a-z0-9]+", name.lower())) or "rackets"
    path = export_dir(hass) / f"strung-{slug}-{stamp}.csv"

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


def parse_csv(
    text: str, racket: str, racket_unit: str, existing: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int, int]:
    """Records to add, how many were already there, and rows for other rackets.

    A "racket" column naming several rackets (an export of all of them) keeps
    only this racket's rows; with one name, every row is taken.
    """
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    try:
        headings = [_column(h) for h in next(reader)]
    except StopIteration:
        raise _error("import_empty") from None
    missing = {ATTR_DATE, ATTR_MAIN_STRING, ATTR_MAIN_TENSION} - set(headings)
    if missing:
        raise _error("import_columns", columns=", ".join(sorted(missing)))

    rows = [
        (number, dict(zip(headings, values, strict=False)))
        for number, values in enumerate(reader, start=2)
        if any(v.strip() for v in values)
    ]
    names = {(r.get("racket") or "").strip().lower() for _, r in rows} - {""}
    other = 0
    if len(names) > 1:
        before = len(rows)
        rows = [
            (n, r)
            for n, r in rows
            if (r.get("racket") or "").strip().lower() == racket.strip().lower()
        ]
        other = before - len(rows)

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
