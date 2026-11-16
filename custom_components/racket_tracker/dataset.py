"""Look up known rackets in the Racqix Tennis Racquet Dataset.

https://www.racqix.com/en/tennis-racquet-dataset publishes specs for ~1,250
rackets as JSON. The API has no search, so the list is fetched when someone
searches it, and kept in memory for a day. Checking an already linked racket
asks for that racket only (async_get_racquet). Matched values go to `options["dataset_specs"]`, the base layer
under the user's own measurements (see specs.effective_specs).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_BRAND, CONF_HEAD_SIZE, CONF_MODEL, CONF_STRING_PATTERN
from .specs import CONF_DATASET_SPECS, SPECS

_LOGGER = logging.getLogger(__name__)

DATASET_URL = "https://www.racqix.com/api/racquets?mode=minimal"
# One racket (~6 kB); 404 when it isn't in the dataset
RACQUET_URL = "https://www.racqix.com/api/racquets/{slug}"
DATASET_NAME = "Racqix Tennis Racquet Dataset"
ATTRIBUTION = f"Specs from the {DATASET_NAME} (racqix.com)"

CONF_DATASET_RACKET = "dataset_racket"

MAX_MATCHES = 50
_CACHE_SECONDS = 24 * 3600
_TIMEOUT = aiohttp.ClientTimeout(total=20)
_DATA_KEY = "racket_tracker_dataset"
_RACQUET_KEY = "racket_tracker_racquets"

# Single-racket field -> the list's (minimal) field, so both read the same way
_DETAIL_FIELDS = {
    "slug": "slug",
    "brand": "brand",
    "model": "model",
    "year": "year",
    "specs_weight_unstrung_g": "weight",
    "specs_balance_unstrung_mm": "balance_mm",
    "advanced_swingweight": "swingweight",
    "specs_stiffness_ra": "ra",
    "specs_head_size_in": "head_size",
    "specs_string_pattern": "string_pattern",
}

# Dataset field -> our spec key
_SPEC_FIELDS = {
    "weight": "unstrung_weight",
    "balance_mm": "balance",
    "swingweight": "swingweight",
    "ra": "stiffness",
}
_SPEC_BY_KEY = {spec.key: spec for spec in SPECS}
_PATTERN = re.compile(r"^\d{1,2}x\d{1,2}$")
_TOKEN = re.compile(r"[a-z0-9]+")


class DatasetError(Exception):
    """The dataset couldn't be fetched or read."""


@dataclass(frozen=True)
class Dataset:
    """The racket list and its version."""

    version: str
    racquets: list[dict[str, Any]]


async def async_get_dataset(hass: HomeAssistant) -> Dataset:
    """Return the dataset, fetching it if it isn't cached."""
    cached: tuple[float, Dataset] | None = hass.data.get(_DATA_KEY)
    if cached and time.monotonic() - cached[0] < _CACHE_SECONDS:
        return cached[1]
    session = async_get_clientsession(hass)
    try:
        async with session.get(DATASET_URL, timeout=_TIMEOUT) as resp:
            resp.raise_for_status()
            payload = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        _LOGGER.warning(
            "Couldn't fetch the racket dataset from %s: %r", DATASET_URL, err
        )
        raise DatasetError(str(err)) from err
    racquets = payload.get("racquets") if isinstance(payload, dict) else None
    if not isinstance(racquets, list):
        _LOGGER.warning("Unexpected response from %s", DATASET_URL)
        raise DatasetError("unexpected response")
    dataset = Dataset(
        version=str(payload.get("dataset_version") or ""),
        racquets=[r for r in racquets if isinstance(r, dict) and r.get("slug")],
    )
    hass.data[_DATA_KEY] = (time.monotonic(), dataset)
    return dataset


async def async_get_racquet(hass: HomeAssistant, slug: str) -> dict[str, Any] | None:
    """One racket from the dataset, or None if it was removed.

    Asks for that racket only, not the whole list (the repairs check uses it).
    The answer is kept for a day. Raises DatasetError if it can't be fetched.
    """
    cache: dict[str, tuple[float, dict[str, Any] | None]] = hass.data.setdefault(
        _RACQUET_KEY, {}
    )
    if (hit := cache.get(slug)) and time.monotonic() - hit[0] < _CACHE_SECONDS:
        return hit[1]
    url = RACQUET_URL.format(slug=quote(slug, safe=""))
    session = async_get_clientsession(hass)
    try:
        async with session.get(url, timeout=_TIMEOUT) as resp:
            if resp.status == 404:
                racquet = None
            else:
                resp.raise_for_status()
                payload = await resp.json(content_type=None)
                if not isinstance(payload, dict) or not payload.get("slug"):
                    raise ValueError("unexpected response")
                # Some keys come with a stray "\r"
                fields = {str(k).strip(): v for k, v in payload.items()}
                racquet = {
                    ours: fields.get(theirs) for theirs, ours in _DETAIL_FIELDS.items()
                }
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        _LOGGER.warning("Couldn't fetch %s: %r", url, err)
        raise DatasetError(str(err)) from err
    cache[slug] = (time.monotonic(), racquet)
    return racquet


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _year(racquet: dict[str, Any]) -> int:
    match = re.match(r"\d{4}", str(racquet.get("year") or ""))
    return int(match.group()) if match else 0


def search(dataset: Dataset, query: str) -> list[dict[str, Any]]:
    """Rackets matching every word of the query, newest first."""
    words = _tokens(query)
    if not words:
        return []
    matches = []
    for racquet in dataset.racquets:
        haystack = " ".join(
            str(racquet.get(k) or "")
            for k in ("slug", "brand", "model", "year", "head_size", "string_pattern")
        )
        tokens = set(_tokens(haystack))
        # Each word must start a word of the racket ("aer" matches "aero")
        if all(any(t.startswith(w) for t in tokens) for w in words):
            matches.append(racquet)
    matches.sort(key=lambda r: (-_year(r), r["slug"]))
    return matches[:MAX_MATCHES]


def _slugify(text: str) -> str:
    return "-".join(_tokens(text))


def model_name(racquet: dict[str, Any]) -> str:
    """Full model name, e.g. "Pure Aero Lite" from babolat-pure-aero-lite-2023.

    The dataset's `model` is often only the family ("Pure Aero"); the slug keeps
    the variant (98, Lite, Team, Plus...). The dataset's spelling is kept for the
    part of the slug it covers.
    """
    model = str(racquet.get("model") or "").strip()
    rest = str(racquet["slug"])
    brand = _slugify(str(racquet.get("brand") or ""))
    if brand and rest.startswith(brand + "-"):
        rest = rest[len(brand) + 1 :]
    year = str(racquet.get("year") or "")
    if year and rest.endswith("-" + year):
        rest = rest[: -len(year) - 1]
    words: list[str] = []
    if model and (rest == _slugify(model) or rest.startswith(_slugify(model) + "-")):
        words.append(model)
        rest = rest[len(_slugify(model)) + 1 :]
    words += [w if w.isdigit() else w.capitalize() for w in rest.split("-") if w]
    return " ".join(words) or model


def label(racquet: dict[str, Any]) -> str:
    """One line, e.g. "Babolat Pure Aero (2023) · 100 in² · 16x19 · 300 g"."""
    name = " ".join(
        part for part in (str(racquet.get("brand") or ""), model_name(racquet)) if part
    )
    if racquet.get("year"):
        name += f" ({racquet['year']})"
    details = [name or racquet["slug"]]
    if racquet.get("head_size"):
        details.append(f"{racquet['head_size']} in²")
    if racquet.get("string_pattern"):
        details.append(str(racquet["string_pattern"]))
    if racquet.get("weight"):
        details.append(f"{racquet['weight']} g")
    return " · ".join(details)


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def dataset_specs(racquet: dict[str, Any]) -> dict[str, int | float]:
    """Spec values from a dataset entry, skipping missing or implausible ones."""
    out: dict[str, int | float] = {}
    for field, key in _SPEC_FIELDS.items():
        value = _number(racquet.get(field))
        spec = _SPEC_BY_KEY[key]
        if value is not None and spec.min <= value <= spec.max:
            out[key] = value
    return out


def racket_details(racquet: dict[str, Any]) -> dict[str, Any]:
    """Brand, model, head size and string pattern from a dataset entry."""
    out: dict[str, Any] = {}
    if isinstance(racquet.get(CONF_BRAND), str) and racquet[CONF_BRAND].strip():
        out[CONF_BRAND] = racquet[CONF_BRAND].strip()
    if model := model_name(racquet):
        out[CONF_MODEL] = model
    head = _number(racquet.get("head_size"))
    if head is not None and 80 <= head <= 135:
        out[CONF_HEAD_SIZE] = head
    pattern = str(racquet.get("string_pattern") or "").strip().lower()
    if _PATTERN.match(pattern):
        out[CONF_STRING_PATTERN] = pattern
    return out


def apply(
    options: dict[str, Any], racquet: dict[str, Any], version: str
) -> dict[str, Any]:
    """Options linked to a dataset racket. Details the user typed are kept."""
    out = dict(options)
    for key, value in racket_details(racquet).items():
        if out.get(key) in (None, ""):
            out[key] = value
    out[CONF_DATASET_SPECS] = dataset_specs(racquet)
    out[CONF_DATASET_RACKET] = {
        "slug": racquet["slug"],
        "name": label(racquet),
        "version": version,
    }
    return out
