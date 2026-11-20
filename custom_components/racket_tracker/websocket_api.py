"""WebSocket API for the bundled Strung Lovelace cards."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.websocket_api import (  # type: ignore[attr-defined]
    ActiveConnection,
    async_register_command,
    websocket_command,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .const import ATTR_CONFIG_ENTRY_ID, CONF_TENSION_UNIT, DOMAIN, TENSION_UNIT_LBS
from .history import with_image_url
from .specs import effective_specs
from .stats import RacketSnapshot, bag_summary, summary
from .string_catalog import suggestions


def build_bag_summary(hass: HomeAssistant) -> dict[str, Any]:
    """Build the cross-racket bag summary across all loaded rackets."""
    today = dt_util.now().date()
    snapshots: list[RacketSnapshot] = []
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        history = entry.runtime_data
        latest = history.latest
        img_url = with_image_url(hass, latest).get("image_url") if latest else None
        snapshots.append(
            RacketSnapshot(
                entry_id=entry.entry_id,
                name=entry.title,
                options=entry.options,
                restrings=history.restrings,
                sessions=history.sessions,
                play_settings=history.play_settings(entry.options, latest),
                due=history.next_due(entry.options),
                image_url=img_url,
            )
        )
    data = bag_summary(snapshots, today)
    data["currency"] = hass.config.currency
    return data


@callback
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register Strung WebSocket commands."""
    async_register_command(hass, ws_get_bag)
    async_register_command(hass, ws_get_racket)
    async_register_command(hass, ws_get_strings)


@websocket_command({vol.Required("type"): f"{DOMAIN}/bag"})
@callback
def ws_get_bag(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the cross-racket bag summary."""
    connection.send_result(msg["id"], build_bag_summary(hass))


@websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/racket",
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
    }
)
@callback
def ws_get_racket(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return detailed state, history, play sessions and specs for one racket."""
    entry_id = msg[ATTR_CONFIG_ENTRY_ID]
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
        connection.send_error(msg["id"], "not_found", f"Racket {entry_id} not found")
        return

    history = entry.runtime_data
    today = dt_util.now().date()
    latest = history.latest
    img_url = with_image_url(hass, latest).get("image_url") if latest else None
    snap = RacketSnapshot(
        entry_id=entry.entry_id,
        name=entry.title,
        options=entry.options,
        restrings=history.restrings,
        sessions=history.sessions,
        play_settings=history.play_settings(entry.options, latest),
        due=history.next_due(entry.options),
        image_url=img_url,
    )
    single_bag = bag_summary([snap], today)
    racket_info = single_bag["rackets"][0]
    connection.send_result(
        msg["id"],
        {
            "racket": racket_info,
            "currency": hass.config.currency,
            "tension_unit": entry.options.get(CONF_TENSION_UNIT, TENSION_UNIT_LBS),
            "specs": effective_specs(entry),
            "stats": summary(history.restrings, snap.play_settings, today),
            "restrings": history.newest_first(),
            "play_sessions": list(reversed(history.sessions)),
            "calibrations": list(reversed(history.calibrations)),
        },
    )


@websocket_command({vol.Required("type"): f"{DOMAIN}/strings"})
@callback
def ws_get_strings(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return string autocomplete suggestions (used strings first, then catalog)."""
    records = [
        record
        for entry in hass.config_entries.async_loaded_entries(DOMAIN)
        for record in entry.runtime_data.restrings
    ]
    records.sort(key=lambda r: r.get("date", ""), reverse=True)
    used = [
        name
        for record in records
        for name in (record.get("main_string"), record.get("cross_string"))
        if name
    ]
    connection.send_result(msg["id"], {"strings": suggestions(used)})
