"""Strung (racket_tracker): keep a restring history for your tennis rackets."""

from __future__ import annotations

from datetime import date
from typing import Any

import voluptuous as vol
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_COST,
    ATTR_CROSS_STRING,
    ATTR_CROSS_TENSION,
    ATTR_DATE,
    ATTR_IMAGE,
    ATTR_MAIN_STRING,
    ATTR_MAIN_TENSION,
    ATTR_NOTES,
    ATTR_RATING,
    ATTR_REMOVE_IMAGE,
    ATTR_RESTRING_ID,
    ATTR_STRINGER,
    CONF_TENSION_UNIT,
    DOMAIN,
    EDITABLE_FIELDS,
    EVENT_RESTRUNG,
    SERVICE_ADD_RESTRING,
    SERVICE_DELETE_RESTRING,
    SERVICE_GET_HISTORY,
    SERVICE_UPDATE_RESTRING,
    TENSION_UNIT_LBS,
)
from .history import RacketHistory, new_restring_id, with_image_url
from .images import (
    IMAGE_URL_PREFIX,
    async_delete_image,
    async_import_image,
    image_dir,
)
from .specs import effective_specs

PLATFORMS: list[Platform] = [Platform.IMAGE, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type RacketConfigEntry = ConfigEntry[RacketHistory]


def _whole(value: float) -> float | int:
    """Store 52.0 as 52 so it displays without a trailing .0."""
    return int(value) if value.is_integer() else value


_TENSION = vol.All(vol.Coerce(float), vol.Range(min=1, max=100), _whole)
_COST = vol.All(vol.Coerce(float), vol.Range(min=0), _whole)
_RATING = vol.All(vol.Coerce(int), vol.Range(min=1, max=5))

_RESTRING_FIELDS = {
    vol.Optional(ATTR_DATE): cv.date,
    vol.Optional(ATTR_CROSS_STRING): cv.string,
    vol.Optional(ATTR_CROSS_TENSION): _TENSION,
    vol.Optional(ATTR_COST): _COST,
    vol.Optional(ATTR_STRINGER): cv.string,
    vol.Optional(ATTR_RATING): _RATING,
    vol.Optional(ATTR_NOTES): cv.string,
    # Media selector value ({media_content_id, ...}), media-source ID or file path
    vol.Optional(ATTR_IMAGE): vol.Any(dict, cv.string),
}

ADD_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_MAIN_STRING): cv.string,
        vol.Required(ATTR_MAIN_TENSION): _TENSION,
        **_RESTRING_FIELDS,
    }
)

UPDATE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_RESTRING_ID): cv.string,
        vol.Optional(ATTR_MAIN_STRING): cv.string,
        vol.Optional(ATTR_MAIN_TENSION): _TENSION,
        vol.Optional(ATTR_REMOVE_IMAGE, default=False): cv.boolean,
        **_RESTRING_FIELDS,
    }
)

DELETE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_RESTRING_ID): cv.string,
    }
)

HISTORY_SCHEMA = vol.Schema({vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string})


def _get_entry(hass: HomeAssistant, entry_id: str) -> RacketConfigEntry:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="racket_not_found",
            translation_placeholders={"entry_id": entry_id},
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="racket_not_loaded",
            translation_placeholders={"racket": entry.title},
        )
    return entry


def _serialize(data: dict[str, Any]) -> dict[str, Any]:
    """Convert date objects to ISO strings for storage."""
    return {k: v.isoformat() if isinstance(v, date) else v for k, v in data.items()}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions and the photo URL path."""
    folder = image_dir(hass)
    await hass.async_add_executor_job(lambda: folder.mkdir(parents=True, exist_ok=True))
    await hass.http.async_register_static_paths(
        [StaticPathConfig(IMAGE_URL_PREFIX, str(folder), False)]
    )

    async def add_restring(call: ServiceCall) -> ServiceResponse:
        entry = _get_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        data = dict(call.data)
        data.pop(ATTR_CONFIG_ENTRY_ID)
        data["id"] = new_restring_id()
        if (image := data.pop(ATTR_IMAGE, None)) is not None:
            data[ATTR_IMAGE] = await async_import_image(hass, image, data["id"])
        data.setdefault(ATTR_DATE, dt_util.now().date())
        # Full bed of one string unless a hybrid is specified
        data.setdefault(ATTR_CROSS_STRING, data[ATTR_MAIN_STRING])
        data.setdefault(ATTR_CROSS_TENSION, data[ATTR_MAIN_TENSION])
        data["tension_unit"] = entry.options.get(CONF_TENSION_UNIT, TENSION_UNIT_LBS)

        record = await entry.runtime_data.async_add(_serialize(data))
        record = with_image_url(record)
        hass.bus.async_fire(
            EVENT_RESTRUNG,
            {"config_entry_id": entry.entry_id, "racket": entry.title, **record},
        )
        return {"racket": entry.title, "restring": record}

    async def update_restring(call: ServiceCall) -> ServiceResponse:
        entry = _get_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        history = entry.runtime_data
        restring_id = call.data.get(ATTR_RESTRING_ID)
        if restring_id is None:
            if history.latest is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="no_restrings",
                    translation_placeholders={"racket": entry.title},
                )
            restring_id = history.latest["id"]

        if (existing := history.get(restring_id)) is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="restring_not_found",
                translation_placeholders={"restring_id": restring_id},
            )
        changes = _serialize(
            {k: v for k, v in call.data.items() if k in EDITABLE_FIELDS}
        )
        if ATTR_IMAGE in call.data:
            changes[ATTR_IMAGE] = await async_import_image(
                hass, call.data[ATTR_IMAGE], restring_id
            )
            if existing.get(ATTR_IMAGE) not in (None, changes[ATTR_IMAGE]):
                await async_delete_image(hass, existing[ATTR_IMAGE])
        elif call.data[ATTR_REMOVE_IMAGE] and existing.get(ATTR_IMAGE):
            await async_delete_image(hass, existing[ATTR_IMAGE])
            changes[ATTR_IMAGE] = None
        record = await history.async_update(restring_id, changes)
        return {"racket": entry.title, "restring": with_image_url(record or {})}

    async def delete_restring(call: ServiceCall) -> None:
        entry = _get_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        restring_id = call.data[ATTR_RESTRING_ID]
        record = entry.runtime_data.get(restring_id)
        if record is not None:
            await async_delete_image(hass, record.get(ATTR_IMAGE))
        if not await entry.runtime_data.async_delete(restring_id):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="restring_not_found",
                translation_placeholders={"restring_id": restring_id},
            )

    async def get_history(call: ServiceCall) -> ServiceResponse:
        entry = _get_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        history = entry.runtime_data
        return {
            "racket": entry.title,
            "specs": effective_specs(entry),
            "restring_count": history.count,
            "total_cost": history.total_cost,
            "restrings": history.newest_first(),
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_RESTRING,
        add_restring,
        ADD_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_RESTRING,
        update_restring,
        UPDATE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_RESTRING, delete_restring, DELETE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_HISTORY,
        get_history,
        HISTORY_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RacketConfigEntry) -> bool:
    """Set up a racket from a config entry."""
    history = RacketHistory(hass, entry.entry_id)
    await history.async_load()
    entry.runtime_data = history

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: RacketConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: RacketConfigEntry) -> bool:
    """Unload a racket."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: RacketConfigEntry) -> None:
    """Delete stored history and photos when a racket is removed."""
    history = RacketHistory(hass, entry.entry_id)
    await history.async_load()
    for record in history.restrings:
        await async_delete_image(hass, record.get(ATTR_IMAGE))
    await history.async_remove()
