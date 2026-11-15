"""Shared entity helpers."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_BRAND, CONF_HEAD_SIZE, CONF_MODEL, CONF_STRING_PATTERN, DOMAIN


def racket_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Device info describing a racket."""
    opts = entry.options
    model_bits = [opts.get(CONF_MODEL)]
    if opts.get(CONF_HEAD_SIZE):
        model_bits.append(f"{int(opts[CONF_HEAD_SIZE])} sq in")
    if opts.get(CONF_STRING_PATTERN):
        model_bits.append(opts[CONF_STRING_PATTERN])
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer=opts.get(CONF_BRAND),
        model=" · ".join(b for b in model_bits if b) or None,
    )
