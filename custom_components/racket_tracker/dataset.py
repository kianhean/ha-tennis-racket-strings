"""Look up known rackets in the Racqix Tennis Racquet Dataset.

https://www.racqix.com/en/tennis-racquet-dataset publishes specs for ~1,250
rackets as JSON (CC BY-NC-ND 4.0). The API has no search, so the whole list is
downloaded at most once a day: in the background after HA starts, or on the first
search after that. The download is kept in .storage/racket_tracker.dataset, so a
restart doesn't download it again. When there is no download yet and Racqix can't
be reached (its bot protection sometimes answers HA with a 429 challenge), the
copy bundled with the integration (racqix_dataset.json, unmodified, see
racqix_dataset.NOTICE.md) is used. The repairs check for linked rackets uses
the same list. Matched values go to `options["dataset_specs"]`, the base layer
under the user's own measurements (see specs.effective_specs).
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BRAND,
    CONF_HEAD_SIZE,
    CONF_MODEL,
    CONF_STRING_PATTERN,
    DOMAIN,
)
from .specs import CONF_DATASET_SPECS, SPECS

_LOGGER = logging.getLogger(__name__)

DATASET_URL = "https://www.racqix.com/api/racquets?mode=minimal"
DATASET_NAME = "Racqix Tennis Racquet Dataset"
ATTRIBUTION = f"Specs from the {DATASET_NAME} (racqix.com)"

CONF_DATASET_RACKET = "dataset_racket"

MAX_MATCHES = 50
# At most one download of the list a day, whether it worked or not
_REFRESH_INTERVAL = timedelta(days=1)
_TIMEOUT = aiohttp.ClientTimeout(total=20)
_DATA_KEY = "racket_tracker_dataset"
_STORE_KEY = f"{DOMAIN}.dataset"
_STORE_VERSION = 1
BUNDLED_FILE = Path(__file__).parent / "racqix_dataset.json"

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
    # When it was downloaded (ISO); None for the copy bundled with the integration
    downloaded: str | None = None


@dataclass
class _State:
    store: Store[dict[str, Any]]
    dataset: Dataset | None = None
    attempted: datetime | None = None
    lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)


def _parse(payload: Any, downloaded: str | None) -> Dataset | None:
    racquets = payload.get("racquets") if isinstance(payload, dict) else None
    if not isinstance(racquets, list):
        return None
    return Dataset(
        version=str(payload.get("dataset_version") or ""),
        racquets=[r for r in racquets if isinstance(r, dict) and r.get("slug")],
        downloaded=downloaded,
    )


def _read_bundled() -> Any:
    return json.loads(BUNDLED_FILE.read_text(encoding="utf-8"))


async def _async_state(hass: HomeAssistant) -> _State:
    """The dataset in memory: last download, else the bundled copy."""
    if (state := hass.data.get(_DATA_KEY)) is None:
        state = hass.data[_DATA_KEY] = _State(
            Store(hass, _STORE_VERSION, _STORE_KEY, private=True)
        )
    if state.dataset is None:
        async with state.lock:
            if state.dataset is None:
                stored = await state.store.async_load() or {}
                state.attempted = dt_util.parse_datetime(
                    str(stored.get("attempted") or "")
                )
                state.dataset = _parse(stored.get("payload"), stored.get("downloaded"))
                if state.dataset is None:
                    try:
                        bundled = await hass.async_add_executor_job(_read_bundled)
                    except (OSError, ValueError) as err:
                        _LOGGER.warning("Couldn't read %s: %r", BUNDLED_FILE, err)
                    else:
                        state.dataset = _parse(bundled, None)
    return state


async def _async_download(hass: HomeAssistant) -> Any:
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            DATASET_URL, timeout=_TIMEOUT, headers={"Accept": "application/json"}
        ) as resp:
            resp.raise_for_status()
            payload = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        _LOGGER.warning(
            "Couldn't fetch the racket dataset from %s: %r", DATASET_URL, err
        )
        return None
    if _parse(payload, None) is None:
        _LOGGER.warning("Unexpected response from %s", DATASET_URL)
        return None
    return payload


async def _async_refresh(hass: HomeAssistant, state: _State) -> None:
    """Download the list if it wasn't tried in the last day."""
    async with state.lock:
        now = dt_util.utcnow()
        if state.attempted and now - state.attempted < _REFRESH_INTERVAL:
            return
        state.attempted = now
        stored = await state.store.async_load() or {}
        if (payload := await _async_download(hass)) is not None:
            stored = {"payload": payload, "downloaded": now.isoformat()}
            state.dataset = _parse(payload, now.isoformat())
        elif state.dataset and state.dataset.downloaded is None:
            _LOGGER.info("Using the racket dataset bundled with the integration")
        await state.store.async_save({**stored, "attempted": now.isoformat()})


async def async_get_dataset(hass: HomeAssistant) -> Dataset:
    """The racket list: refreshed at most once a day, else the last copy we have.

    Raises DatasetError only when there is no copy at all.
    """
    state = await _async_state(hass)
    await _async_refresh(hass, state)
    if state.dataset is None:
        raise DatasetError("no copy of the racket dataset")
    return state.dataset


@callback
def async_schedule_refresh(hass: HomeAssistant) -> None:
    """Refresh the list in the background once HA has started (at most daily)."""

    async def _refresh(_: HomeAssistant) -> None:
        hass.async_create_background_task(
            async_get_dataset(hass), f"{DOMAIN} dataset refresh"
        )

    async_at_started(hass, _refresh)


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
