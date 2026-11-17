"""Strung (racket_tracker): keep a restring history for your tennis rackets."""

from __future__ import annotations

import asyncio
import copy
from datetime import date
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_set_service_schema
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util
from homeassistant.util.yaml import load_yaml_dict

from .backfill import async_backfill
from .const import (
    ATTR_BROKEN,
    ATTR_BROKEN_DATE,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_COST,
    ATTR_CROSS_STRING,
    ATTR_CROSS_TENSION,
    ATTR_DATE,
    ATTR_HOURS,
    ATTR_IMAGE,
    ATTR_MAIN_STRING,
    ATTR_MAIN_TENSION,
    ATTR_NOTES,
    ATTR_RATING,
    ATTR_REMOVE_IMAGE,
    ATTR_RESTRING_ID,
    ATTR_SESSION_ID,
    ATTR_STRINGER,
    CONF_CURRENT,
    CONF_SETUP,
    CONF_TENSION_UNIT,
    DOMAIN,
    EDITABLE_FIELDS,
    EVENT_RESTRUNG,
    SERVICE_ADD_RESTRING,
    SERVICE_CALIBRATE_TENSION,
    SERVICE_DELETE_PLAY,
    SERVICE_DELETE_RESTRING,
    SERVICE_EXPORT_HISTORY,
    SERVICE_GET_HISTORY,
    SERVICE_IMPORT_HISTORY,
    SERVICE_LOG_PLAY,
    SERVICE_REPEAT_RESTRING,
    SERVICE_UPDATE_RESTRING,
    SETUP_FIELDS,
    TENSION_UNIT_LBS,
)
from .dataset import async_schedule_refresh
from .history import RacketHistory, new_restring_id, with_image_url
from .history_io import (
    PLAY_COLUMNS,
    async_read_import,
    async_write_export,
    is_play_csv,
    parse_csv,
    parse_play_csv,
    to_csv,
)
from .images import (
    RacketImageView,
    async_delete_image,
    async_import_image,
    image_dir,
)
from .repairs import async_check_dataset, async_delete_racket_issues
from .specs import effective_specs
from .stats import summary
from .string_catalog import suggestions
from .tension import (
    CONF_FIRST_HOUR_LOSS,
    CONF_INITIAL_LOSS,
    CONF_PLAY,
    CONF_RELAXATION_LOSS,
    PRESET_MINOR_VERSION,
    calibrate,
    logs_play,
    migrate_play_options,
    move_old_presets,
    tracks_play,
    uses_old_presets,
)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CALENDAR,
    Platform.IMAGE,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.TEXT,
]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type RacketConfigEntry = ConfigEntry[RacketHistory]


def _whole(value: float) -> float | int:
    """Store 52.0 as 52 so it displays without a trailing .0."""
    return int(value) if value.is_integer() else value


_TENSION = vol.All(vol.Coerce(float), vol.Range(min=1, max=100), _whole)
_COST = vol.All(vol.Coerce(float), vol.Range(min=0), _whole)
_RATING = vol.All(vol.Coerce(int), vol.Range(min=1, max=5))

_RESTRING_FIELDS: dict[vol.Marker, Any] = {
    vol.Optional(ATTR_DATE): cv.date,
    vol.Optional(ATTR_CROSS_STRING): cv.string,
    vol.Optional(ATTR_CROSS_TENSION): _TENSION,
    vol.Optional(ATTR_COST): _COST,
    vol.Optional(ATTR_STRINGER): cv.string,
    vol.Optional(ATTR_RATING): _RATING,
    vol.Optional(ATTR_NOTES): cv.string,
    vol.Optional(ATTR_BROKEN_DATE): cv.date,
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
        vol.Optional(ATTR_BROKEN): cv.boolean,
        **_RESTRING_FIELDS,
    }
)

DELETE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_RESTRING_ID): cv.string,
    }
)

REPEAT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_RESTRING_ID): cv.string,
        vol.Optional(ATTR_DATE): cv.date,
        vol.Optional(ATTR_COST): _COST,
        vol.Optional(ATTR_STRINGER): cv.string,
        vol.Optional(ATTR_NOTES): cv.string,
        vol.Optional(ATTR_IMAGE): vol.Any(dict, cv.string),
    }
)

CALIBRATE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required("tension"): _TENSION,
        vol.Optional(ATTR_DATE): cv.date,
    }
)

LOG_PLAY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_HOURS): vol.All(
            vol.Coerce(float), vol.Range(min=0.1, max=24), _whole
        ),
        vol.Optional(ATTR_DATE): cv.date,
        vol.Optional(ATTR_NOTES): cv.string,
    }
)

DELETE_PLAY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_SESSION_ID): cv.string,
    }
)

HISTORY_SCHEMA = vol.Schema({vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string})

EXPORT_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string})

IMPORT_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
            vol.Exclusive("file", "source"): cv.string,
            vol.Exclusive("csv", "source"): cv.string,
        }
    ),
    cv.has_at_least_one_key("file", "csv"),
)

# Action fields that suggest string names (catalog + strings already used)
_STRING_FIELDS = {
    SERVICE_ADD_RESTRING: (ATTR_MAIN_STRING, ATTR_CROSS_STRING),
    SERVICE_UPDATE_RESTRING: (ATTR_MAIN_STRING, ATTR_CROSS_STRING),
}
_DESCRIPTIONS_KEY = f"{DOMAIN}_service_descriptions"


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


def _check_broken_date(record: dict[str, Any]) -> None:
    """Strings can't break before they were strung."""
    broken, strung = record.get(ATTR_BROKEN_DATE), record.get(ATTR_DATE)
    if broken and strung and broken < strung:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="broken_before_restring",
            translation_placeholders={"broken": broken, "date": strung},
        )


def used_strings(hass: HomeAssistant) -> list[str]:
    """Strings logged on any racket, most recent first."""
    records = [
        record
        for entry in hass.config_entries.async_loaded_entries(DOMAIN)
        for record in entry.runtime_data.restrings
    ]
    records.sort(key=lambda r: r.get(ATTR_DATE, ""), reverse=True)
    return [
        name
        for record in records
        for name in (record.get(ATTR_MAIN_STRING), record.get(ATTR_CROSS_STRING))
        if name
    ]


@callback
def async_update_string_suggestions(hass: HomeAssistant) -> None:
    """Offer catalog and used strings in the add/update restring forms."""
    if (base := hass.data.get(_DESCRIPTIONS_KEY)) is None:
        return
    selector = {
        "select": {
            "options": suggestions(used_strings(hass)),
            "custom_value": True,
            "mode": "dropdown",
            "sort": False,
        }
    }
    for service, fields in _STRING_FIELDS.items():
        description = copy.deepcopy(base[service])
        for field in fields:
            description["fields"][field]["selector"] = selector
        async_set_service_schema(hass, DOMAIN, service, description)


async def async_log_restring(
    hass: HomeAssistant, entry: RacketConfigEntry, fields: dict[str, Any]
) -> dict[str, Any]:
    """Store a new restring, fire the restrung event and return the record."""
    data = dict(fields)
    data["id"] = new_restring_id()
    if (image := data.pop(ATTR_IMAGE, None)) is not None:
        data[ATTR_IMAGE] = await async_import_image(hass, image, data["id"])
    data.setdefault(ATTR_DATE, dt_util.now().date())
    # Full bed of one string unless a hybrid is specified
    data.setdefault(ATTR_CROSS_STRING, data[ATTR_MAIN_STRING])
    data.setdefault(ATTR_CROSS_TENSION, data[ATTR_MAIN_TENSION])
    data.setdefault(
        "tension_unit", entry.options.get(CONF_TENSION_UNIT, TENSION_UNIT_LBS)
    )
    data = _serialize(data)
    _check_broken_date(data)

    record = await entry.runtime_data.async_add(data)
    record = with_image_url(hass, record)
    hass.bus.async_fire(
        EVENT_RESTRUNG,
        {"config_entry_id": entry.entry_id, "racket": entry.title, **record},
    )
    return record


def current_strings_change(
    latest: dict[str, Any] | None, current: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    """What saving the forms' Current strings section does.

    (True, changes) edits the latest restring: only its date moved, or only its
    strings/tensions changed. (False, fields) logs a new restring: there is none
    yet, or both changed. Empty changes: nothing to do.
    """
    fields: dict[str, Any] = {
        k: _whole(float(v)) if k in (ATTR_MAIN_TENSION, ATTR_CROSS_TENSION) else v
        for k, v in current.items()
        if v not in (None, "")
    }
    fields[ATTR_DATE] = str(fields.get(ATTR_DATE) or dt_util.now().date())
    fields.setdefault(ATTR_CROSS_STRING, fields[ATTR_MAIN_STRING])
    fields.setdefault(ATTR_CROSS_TENSION, fields[ATTR_MAIN_TENSION])
    if latest is None:
        return False, fields
    changes = {k: v for k, v in fields.items() if latest.get(k) != v}
    if ATTR_DATE not in changes or set(changes) == {ATTR_DATE}:
        return True, changes
    return False, fields


async def async_set_current_strings(
    hass: HomeAssistant,
    entry: RacketConfigEntry,
    current: dict[str, Any],
    tension_unit: str | None = None,
) -> dict[str, Any] | None:
    """Save the strings on the racket now (see current_strings_change).

    Returns the changed or new record, or None if nothing changed.
    """
    history = entry.runtime_data
    update, fields = current_strings_change(history.latest, current)
    if update:
        if not fields:
            return None
        assert history.latest is not None
        _check_broken_date({**history.latest, **fields})
        return await history.async_update(history.latest["id"], fields)
    if tension_unit:
        fields["tension_unit"] = tension_unit
    return await async_log_restring(hass, entry, fields)


async def async_mark_broken(
    hass: HomeAssistant, entry: RacketConfigEntry, on: date | None = None
) -> dict[str, Any]:
    """Record that the current strings broke (today unless given)."""
    history = entry.runtime_data
    if (latest := history.latest) is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_restrings",
            translation_placeholders={"racket": entry.title},
        )
    broken = (on or dt_util.now().date()).isoformat()
    _check_broken_date({**latest, ATTR_BROKEN_DATE: broken})
    record = await history.async_update(latest["id"], {ATTR_BROKEN_DATE: broken})
    return with_image_url(hass, record or {})


def usual_setup(
    entry: RacketConfigEntry, restring_id: str | None = None
) -> dict[str, Any]:
    """Strings, tensions, stringer and cost to repeat.

    From the given restring, else the racket's usual setup, else the latest restring.
    """
    history = entry.runtime_data
    if restring_id is not None:
        if (source := history.get(restring_id)) is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="restring_not_found",
                translation_placeholders={"restring_id": restring_id},
            )
    else:
        setup = entry.options.get(CONF_SETUP) or {}
        if setup.get(ATTR_MAIN_STRING) and setup.get(ATTR_MAIN_TENSION):
            source = setup
        elif (source := history.latest) is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_setup",
                translation_placeholders={"racket": entry.title},
            )
    return {
        k: _whole(v) if isinstance(v, float) else v
        for k in SETUP_FIELDS
        if (v := source.get(k)) not in (None, "")
    }


async def async_log_play(
    entry: RacketConfigEntry,
    hours: float,
    on: date | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Log a play session (log_play action, Log play session button)."""
    if not logs_play(entry.options):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="not_logging_play",
            translation_placeholders={"racket": entry.title},
        )
    session: dict[str, Any] = {
        ATTR_DATE: (on or dt_util.now().date()).isoformat(),
        ATTR_HOURS: _whole(float(hours)),
    }
    if notes:
        session[ATTR_NOTES] = notes
    return await entry.runtime_data.async_add_session(session)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions and the (login-only) photo view."""
    async_schedule_refresh(hass)
    folder = image_dir(hass)
    await hass.async_add_executor_job(lambda: folder.mkdir(parents=True, exist_ok=True))
    hass.http.register_view(RacketImageView(hass))

    async def add_restring(call: ServiceCall) -> ServiceResponse:
        entry = _get_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        data = dict(call.data)
        data.pop(ATTR_CONFIG_ENTRY_ID)
        record = await async_log_restring(hass, entry, data)
        return {"racket": entry.title, "restring": record}

    async def repeat_restring(call: ServiceCall) -> ServiceResponse:
        entry = _get_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        data = dict(call.data)
        data.pop(ATTR_CONFIG_ENTRY_ID)
        fields = usual_setup(entry, data.pop(ATTR_RESTRING_ID, None))
        record = await async_log_restring(hass, entry, {**fields, **data})
        return {"racket": entry.title, "restring": record}

    async def calibrate_tension(call: ServiceCall) -> ServiceResponse:
        entry = _get_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        if not tracks_play(entry.options):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_play_settings",
                translation_placeholders={"racket": entry.title},
            )
        if (latest := entry.runtime_data.latest) is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_restrings",
                translation_placeholders={"racket": entry.title},
            )
        settings = entry.runtime_data.play_settings(entry.options, latest)
        assert settings is not None
        measured = call.data["tension"]
        on = call.data.get(ATTR_DATE) or dt_util.now().date()
        try:
            fitted = calibrate(latest, settings, measured, on)
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="cannot_calibrate",
                translation_placeholders={
                    "tension": str(measured),
                    "strung": str(latest.get(ATTR_MAIN_TENSION)),
                },
            ) from err
        rates = {
            CONF_INITIAL_LOSS: fitted.rates.initial,
            CONF_FIRST_HOUR_LOSS: fitted.rates.first_hour,
            CONF_RELAXATION_LOSS: fitted.rates.relaxation,
        }
        play = {**entry.options[CONF_PLAY], **rates}
        # Saving the options reloads the racket with the new rates
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_PLAY: play}
        )
        return {"racket": entry.title, "measured_tension": measured, **rates}

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
        if (broken := call.data.get(ATTR_BROKEN)) is not None:
            changes[ATTR_BROKEN_DATE] = (
                changes.get(ATTR_BROKEN_DATE) or dt_util.now().date().isoformat()
                if broken
                else None
            )
        _check_broken_date({**existing, **changes})
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
        return {"racket": entry.title, "restring": with_image_url(hass, record or {})}

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
        response: dict[str, Any] = {
            "racket": entry.title,
            "specs": effective_specs(entry),
            "restring_count": history.count,
            "total_cost": history.total_cost,
            "stats": summary(
                history.restrings,
                history.play_settings(entry.options, history.latest),
                dt_util.now().date(),
            ),
            "restrings": history.newest_first(),
        }
        if history.sessions:
            response["play_sessions"] = list(reversed(history.sessions))
        return response

    async def log_play(call: ServiceCall) -> ServiceResponse:
        entry = _get_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        session = await async_log_play(
            entry,
            call.data[ATTR_HOURS],
            call.data.get(ATTR_DATE),
            call.data.get(ATTR_NOTES),
        )
        return {"racket": entry.title, "session": session}

    async def delete_play(call: ServiceCall) -> ServiceResponse:
        entry = _get_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        history = entry.runtime_data
        if (session_id := call.data.get(ATTR_SESSION_ID)) is None:
            if not history.sessions:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="no_sessions",
                    translation_placeholders={"racket": entry.title},
                )
            # The one logged last, not the one dated last
            session_id = max(history.sessions, key=lambda s: s["created"])["id"]
        if (session := await history.async_delete_session(session_id)) is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="session_not_found",
                translation_placeholders={"session_id": session_id},
            )
        return {"racket": entry.title, "session": session}

    async def export_history(call: ServiceCall) -> ServiceResponse:
        if entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID):
            entries = [_get_entry(hass, entry_id)]
            name = entries[0].title
        else:
            entries = list(hass.config_entries.async_loaded_entries(DOMAIN))
            name = "all rackets"
        rows = [
            (entry.title, record)
            for entry in entries
            for record in entry.runtime_data.restrings
        ]
        text = to_csv(rows)
        path = await async_write_export(hass, name, text)
        response: dict[str, Any] = {
            "file": str(path),
            "restrings": len(rows),
            "csv": text,
        }
        sessions = [
            (entry.title, session)
            for entry in entries
            for session in entry.runtime_data.sessions
        ]
        if sessions:
            play_text = to_csv(sessions, PLAY_COLUMNS)
            play_path = await async_write_export(hass, name, play_text, "-play")
            response |= {
                "play_file": str(play_path),
                "play_sessions": len(sessions),
                "play_csv": play_text,
            }
        return response

    async def import_history(call: ServiceCall) -> ServiceResponse:
        entry = _get_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        if file := call.data.get("file"):
            text = await async_read_import(hass, file)
        else:
            text = call.data["csv"]
        history = entry.runtime_data
        if is_play_csv(text):
            sessions, duplicates, other = parse_play_csv(
                text, entry.title, history.sessions
            )
            return {
                "racket": entry.title,
                "contents": "play_sessions",
                "imported": await history.async_add_sessions(sessions),
                "skipped_duplicates": duplicates,
                "skipped_other_rackets": other,
            }
        records, duplicates, other = parse_csv(
            text,
            entry.title,
            entry.options.get(CONF_TENSION_UNIT, TENSION_UNIT_LBS),
            history.restrings,
        )
        # No restrung events: these are old restrings, not new ones
        imported = await history.async_add_many(records)
        return {
            "racket": entry.title,
            "contents": "restrings",
            "imported": imported,
            "skipped_duplicates": duplicates,
            "skipped_other_rackets": other,
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
        SERVICE_REPEAT_RESTRING,
        repeat_restring,
        REPEAT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CALIBRATE_TENSION,
        calibrate_tension,
        CALIBRATE_SCHEMA,
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
        SERVICE_LOG_PLAY,
        log_play,
        LOG_PLAY_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_PLAY,
        delete_play,
        DELETE_PLAY_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_HISTORY,
        get_history,
        HISTORY_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_EXPORT_HISTORY,
        export_history,
        EXPORT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_HISTORY,
        import_history,
        IMPORT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    # services.yaml, kept to rebuild the forms with string suggestions
    integration = await async_get_integration(hass, DOMAIN)
    hass.data[_DESCRIPTIONS_KEY] = await hass.async_add_executor_job(
        load_yaml_dict, str(integration.file_path / "services.yaml")
    )
    async_update_string_suggestions(hass)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: RacketConfigEntry) -> bool:
    """Migrate options from older versions."""
    if entry.version > 1:
        return False  # Downgraded from a newer version
    if entry.minor_version < 2:
        # 1.2: the linear tension model's loss per hour became first_hour_loss
        options = dict(entry.options)
        if play := options.get(CONF_PLAY):
            options[CONF_PLAY] = migrate_play_options(play)
        hass.config_entries.async_update_entry(entry, options=options, minor_version=2)
    if entry.minor_version < PRESET_MINOR_VERSION:
        # 1.3: the nylon and gut presets were raised. A rate equal to an old
        # preset was most likely typed in from the form's "Default: ..." help
        # text, so it moves with the preset; any other rate, or a calibrated
        # one, is the user's own and stays.
        if uses_old_presets(play := entry.options.get(CONF_PLAY) or {}):
            hass.config_entries.async_update_entry(
                entry,
                options={**entry.options, CONF_PLAY: move_old_presets(play)},
                minor_version=PRESET_MINOR_VERSION,
            )
        else:
            hass.config_entries.async_update_entry(
                entry, minor_version=PRESET_MINOR_VERSION
            )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RacketConfigEntry) -> bool:
    """Set up a racket from a config entry."""
    history = RacketHistory(hass, entry.entry_id)
    await history.async_load()
    entry.runtime_data = history

    # Current strings entered when the racket was added
    if current := entry.data.get(CONF_CURRENT):
        await async_set_current_strings(hass, entry, current)
        hass.config_entries.async_update_entry(entry, data={})

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    loaded = _options_needing_reload(entry)

    async def _async_options_updated(
        hass: HomeAssistant, entry: RacketConfigEntry
    ) -> None:
        # The usual setup fields write their option and update themselves
        if _options_needing_reload(entry) != loaded:
            await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    # Keep the tension sensors' statistics in line with the (possibly backdated)
    # history, so statistics graphs show it from the first restring on
    # One at a time, each reading the history once it runs, so a slow earlier
    # run can't overwrite a newer one
    lock = asyncio.Lock()

    async def _run_backfill() -> None:
        async with lock:
            await async_backfill(hass, entry)

    @callback
    def _backfill() -> None:
        entry.async_create_background_task(
            hass, _run_backfill(), f"{DOMAIN} backfill {entry.entry_id}"
        )

    entry.async_on_unload(history.async_add_listener(_backfill))
    _backfill()

    @callback
    def _suggest() -> None:
        async_update_string_suggestions(hass)

    entry.async_on_unload(history.async_add_listener(_suggest))
    _suggest()

    # Has the looked-up racket changed or gone from the dataset? (repairs.py)
    entry.async_create_background_task(
        hass, async_check_dataset(hass, entry), f"{DOMAIN} dataset check"
    )
    return True


def _options_needing_reload(entry: RacketConfigEntry) -> dict[str, Any]:
    """Every option but the usual setup, which is read when it's used."""
    return {k: v for k, v in entry.options.items() if k != CONF_SETUP}


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
    async_delete_racket_issues(hass, entry.entry_id)
