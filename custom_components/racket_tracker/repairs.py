"""Repair issues for rackets linked to the Racqix dataset.

When a racket with looked-up specs is set up, its dataset entry is checked
(using the day-long cache in dataset.py, so a restart with several rackets
fetches the list at most once):

- dataset_unreachable: the list couldn't be fetched. Nothing breaks: the
  specs are kept in the racket's options. Removed once a check succeeds.
- dataset_racket_missing (fixable): the racket is no longer in the dataset.
  Fixing it unlinks the racket and keeps the specs.
- dataset_specs_changed (fixable): the dataset now has other values for the
  racket. Fixing it takes the new values; your own measurements still win.
"""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .dataset import (
    CONF_DATASET_RACKET,
    DatasetError,
    async_get_dataset,
    dataset_specs,
    label,
)
from .specs import CONF_DATASET_SPECS, SPECS

ISSUE_UNREACHABLE = "dataset_unreachable"
ISSUE_MISSING = "dataset_racket_missing"
ISSUE_CHANGED = "dataset_specs_changed"
_ENTRY_ISSUES = (ISSUE_MISSING, ISSUE_CHANGED)

# Don't ask again for an hour after a failed fetch
_RETRY = timedelta(hours=1)
_STATE_KEY = f"{DOMAIN}_dataset_check"
_UNITS = {spec.key: spec.unit or "" for spec in SPECS}


def _issue_id(kind: str, entry_id: str) -> str:
    return f"{kind}_{entry_id}"


@callback
def async_delete_racket_issues(hass: HomeAssistant, entry_id: str) -> None:
    """Remove a racket's dataset issues (unlinked or removed)."""
    for kind in _ENTRY_ISSUES:
        ir.async_delete_issue(hass, DOMAIN, _issue_id(kind, entry_id))


def _format(key: str, value: Any) -> str:
    if value is None:
        return "—"
    unit = _UNITS.get(key, "")
    return f"{value} {unit}".strip()


def describe_changes(old: dict[str, Any], new: dict[str, Any]) -> str:
    """One line per changed spec, e.g. "stiffness: 68 RA → 66 RA"."""
    return "\n".join(
        f"- {key.replace('_', ' ')}: {_format(key, old.get(key))} → "
        f"{_format(key, new.get(key))}"
        for key in sorted(set(old) | set(new))
        if old.get(key) != new.get(key)
    )


async def async_check_dataset(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Check a linked racket against the current dataset."""
    linked = entry.options.get(CONF_DATASET_RACKET)
    if not linked:
        async_delete_racket_issues(hass, entry.entry_id)
        return
    state: dict[str, Any] = hass.data.setdefault(
        _STATE_KEY, {"lock": asyncio.Lock(), "failed": None}
    )
    async with state["lock"]:
        failed = state["failed"]
        if failed is not None and dt_util.utcnow() - failed < _RETRY:
            return
        try:
            dataset = await async_get_dataset(hass)
        except DatasetError:
            state["failed"] = dt_util.utcnow()
            ir.async_create_issue(
                hass,
                DOMAIN,
                ISSUE_UNREACHABLE,
                is_fixable=False,
                is_persistent=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_UNREACHABLE,
            )
            return
        state["failed"] = None
        ir.async_delete_issue(hass, DOMAIN, ISSUE_UNREACHABLE)

    racquet = next(
        (r for r in dataset.racquets if r["slug"] == linked.get("slug")), None
    )
    missing_id = _issue_id(ISSUE_MISSING, entry.entry_id)
    changed_id = _issue_id(ISSUE_CHANGED, entry.entry_id)
    if racquet is None:
        ir.async_delete_issue(hass, DOMAIN, changed_id)
        ir.async_create_issue(
            hass,
            DOMAIN,
            missing_id,
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_MISSING,
            translation_placeholders={
                "racket": entry.title,
                "dataset_racket": linked.get("name") or linked.get("slug", ""),
            },
            data={"entry_id": entry.entry_id},
        )
        return
    ir.async_delete_issue(hass, DOMAIN, missing_id)

    old = dict(entry.options.get(CONF_DATASET_SPECS) or {})
    new = dataset_specs(racquet)
    if new == old:
        ir.async_delete_issue(hass, DOMAIN, changed_id)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        changed_id,
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_CHANGED,
        translation_placeholders={
            "racket": entry.title,
            "dataset_racket": label(racquet),
            "changes": describe_changes(old, new),
        },
        data={
            "entry_id": entry.entry_id,
            "specs": json.dumps(new),
            "name": label(racquet),
            "version": dataset.version,
        },
    )


class DatasetRepairFlow(RepairsFlow):
    """Confirm, then unlink the racket or take the dataset's new values."""

    def __init__(self, kind: str, data: dict[str, Any]) -> None:
        """Initialize."""
        self._kind = kind
        self._data = data

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Start with the confirmation."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Show what will change; apply it on submit."""
        entry = self.hass.config_entries.async_get_entry(self._data["entry_id"])
        if entry is None:
            return self.async_abort(reason="racket_removed")
        if user_input is not None:
            options = dict(entry.options)
            if self._kind == ISSUE_MISSING:
                options.pop(CONF_DATASET_RACKET, None)
            else:
                options[CONF_DATASET_SPECS] = json.loads(self._data["specs"])
                options[CONF_DATASET_RACKET] = {
                    **(options.get(CONF_DATASET_RACKET) or {}),
                    "name": self._data["name"],
                    "version": self._data["version"],
                }
            # Saving the options reloads the racket, which checks it again
            self.hass.config_entries.async_update_entry(entry, options=options)
            return self.async_create_entry(data={})
        issue = ir.async_get(self.hass).async_get_issue(DOMAIN, self.issue_id)
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders=issue.translation_placeholders if issue else None,
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Create the fix flow for a racket's dataset issue."""
    kind = ISSUE_MISSING if issue_id.startswith(ISSUE_MISSING) else ISSUE_CHANGED
    return DatasetRepairFlow(kind, dict(data or {}))
