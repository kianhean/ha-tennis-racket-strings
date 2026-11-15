"""Persistent restring history for a single racket."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_COST,
    ATTR_DATE,
    ATTR_IMAGE,
    ATTR_IMAGE_URL,
    DOMAIN,
    STORAGE_VERSION,
)
from .images import image_url


def with_image_url(record: dict[str, Any]) -> dict[str, Any]:
    """Copy of a record with a browser-usable image URL added."""
    out = dict(record)
    out[ATTR_IMAGE_URL] = image_url(record.get(ATTR_IMAGE))
    if out[ATTR_IMAGE_URL] and (
        stamp := record.get("updated") or record.get("created")
    ):
        # Cache-buster so a replaced photo shows up immediately
        out[ATTR_IMAGE_URL] += f"?v={stamp[:19].replace(':', '')}"
    return out


def new_restring_id() -> str:
    """Generate a short unique restring id."""
    return uuid.uuid4().hex[:12]


class RacketHistory:
    """Holds and persists the restring history of one racket."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the history store."""
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )
        self.restrings: list[dict[str, Any]] = []
        self._listeners: list[Callable[[], None]] = []

    async def async_load(self) -> None:
        """Load history from disk."""
        data = await self._store.async_load()
        self.restrings = list((data or {}).get("restrings", []))
        self._sort()

    async def async_remove(self) -> None:
        """Delete the history file (racket removed)."""
        await self._store.async_remove()

    # ------------------------------------------------------------------ queries

    @property
    def latest(self) -> dict[str, Any] | None:
        """Return the most recent restring, if any."""
        return self.restrings[-1] if self.restrings else None

    @property
    def count(self) -> int:
        """Return number of restrings."""
        return len(self.restrings)

    @property
    def total_cost(self) -> float:
        """Return the summed cost of all restrings."""
        return round(sum(r.get(ATTR_COST) or 0 for r in self.restrings), 2)

    @property
    def average_cost(self) -> float | None:
        """Return the average cost of restrings that have a cost."""
        costs = [r[ATTR_COST] for r in self.restrings if r.get(ATTR_COST) is not None]
        return round(sum(costs) / len(costs), 2) if costs else None

    def get(self, restring_id: str) -> dict[str, Any] | None:
        """Return a restring by id."""
        return next((r for r in self.restrings if r["id"] == restring_id), None)

    def newest_first(self) -> list[dict[str, Any]]:
        """Return a copy of the history, most recent first (with photo URLs)."""
        return [with_image_url(r) for r in reversed(self.restrings)]

    # ---------------------------------------------------------------- mutations

    async def async_add(self, record: dict[str, Any]) -> dict[str, Any]:
        """Add a restring and persist."""
        new = {
            "id": record.pop("id", None) or new_restring_id(),
            "created": dt_util.utcnow().isoformat(),
            **record,
        }
        self.restrings.append(new)
        await self._async_commit()
        return new

    async def async_update(
        self, restring_id: str, changes: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update fields of an existing restring and persist."""
        if (record := self.get(restring_id)) is None:
            return None
        record.update(changes)
        record["updated"] = dt_util.utcnow().isoformat()
        await self._async_commit()
        return record

    async def async_delete(self, restring_id: str) -> bool:
        """Delete a restring and persist."""
        before = len(self.restrings)
        self.restrings = [r for r in self.restrings if r["id"] != restring_id]
        if len(self.restrings) == before:
            return False
        await self._async_commit()
        return True

    async def _async_commit(self) -> None:
        self._sort()
        await self._store.async_save({"restrings": self.restrings})
        for listener in list(self._listeners):
            listener()

    def _sort(self) -> None:
        self.restrings.sort(key=lambda r: (r.get(ATTR_DATE, ""), r.get("created", "")))

    # ---------------------------------------------------------------- listeners

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a callback for history changes; returns an unsubscribe fn."""
        self._listeners.append(listener)

        @callback
        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove
