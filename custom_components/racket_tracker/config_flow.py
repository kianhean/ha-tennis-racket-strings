"""Config flow for Strung (racket_tracker)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    CONF_BRAND,
    CONF_HEAD_SIZE,
    CONF_MODEL,
    CONF_STRING_PATTERN,
    CONF_TENSION_UNIT,
    DOMAIN,
    TENSION_UNIT_LBS,
    TENSION_UNITS,
)
from .dataset import (
    CONF_DATASET_RACKET,
    DATASET_NAME,
    DatasetError,
    apply,
    async_get_dataset,
    label,
    search,
)
from .specs import CONF_DATASET_SPECS, CONF_SPECS, SPECS

CONF_LOOKUP = "lookup"
CONF_RACQUET = "racquet"
CONF_USE_DATASET = "use_dataset"

# Specs the user measured themselves (they override dataset values). Units are
# shown for lbs; tension fields use the racket's own tension unit.
SPECS_SCHEMA = vol.Schema(
    {
        vol.Optional(spec.key): NumberSelector(
            NumberSelectorConfig(
                min=spec.min,
                max=spec.max,
                step=spec.step,
                mode=NumberSelectorMode.BOX,
                **({"unit_of_measurement": spec.unit} if spec.unit else {}),
            )
        )
        for spec in SPECS
    }
)

RACKET_DETAILS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_BRAND): TextSelector(),
        vol.Optional(CONF_MODEL): TextSelector(),
        vol.Optional(CONF_HEAD_SIZE): NumberSelector(
            NumberSelectorConfig(
                min=80,
                max=135,
                step=1,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="sq in",
            )
        ),
        vol.Optional(CONF_STRING_PATTERN): TextSelector(),
        vol.Required(CONF_TENSION_UNIT, default=TENSION_UNIT_LBS): SelectSelector(
            SelectSelectorConfig(
                options=TENSION_UNITS,
                mode=SelectSelectorMode.LIST,
                translation_key=CONF_TENSION_UNIT,
            )
        ),
    }
)

RACKET_DETAILS_SCHEMA = RACKET_DETAILS_SCHEMA.extend(
    {vol.Optional(CONF_SPECS): section(SPECS_SCHEMA, {"collapsed": True})}
)

LOOKUP_SCHEMA = vol.Schema({vol.Optional(CONF_LOOKUP): TextSelector()})

USER_SCHEMA = (
    vol.Schema({vol.Required(CONF_NAME): TextSelector()})
    .extend(LOOKUP_SCHEMA.schema)
    .extend(RACKET_DETAILS_SCHEMA.schema)
)


def _clean(user_input: dict[str, Any], errors: dict[str, str]) -> dict[str, Any]:
    """Drop empty specs and check the tension range."""
    data = dict(user_input)
    specs = {k: v for k, v in (data.get(CONF_SPECS) or {}).items() if v is not None}
    data[CONF_SPECS] = specs
    low, high = specs.get("tension_min"), specs.get("tension_max")
    if low is not None and high is not None and low > high:
        errors["base"] = "tension_range"
    return data


class _LookupMixin:
    """Search the racket dataset and let the user pick a match."""

    _options: dict[str, Any]
    _matches: list[dict[str, Any]]
    _query: str
    _version: str

    async def _async_lookup(self, query: str, errors: dict[str, str]) -> bool:
        """Search for the query; True if there is something to pick from."""
        try:
            dataset = await async_get_dataset(self.hass)  # type: ignore[attr-defined]
        except DatasetError:
            errors[CONF_LOOKUP] = "cannot_connect"
            return False
        self._query, self._version = query, dataset.version
        self._matches = search(dataset, query)
        if not self._matches:
            errors[CONF_LOOKUP] = "no_match"
        return bool(self._matches)

    def _pick_form(self, step_id: str) -> ConfigFlowResult:
        options = [
            {"value": racquet["slug"], "label": label(racquet)}
            for racquet in self._matches
        ]
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_RACQUET): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST
                            if len(options) <= 8
                            else SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            description_placeholders={
                "count": str(len(options)),
                "query": self._query,
                "dataset": f"{DATASET_NAME} v{self._version}"
                if self._version
                else DATASET_NAME,
            },
        )

    def _picked(self, user_input: dict[str, Any]) -> dict[str, Any] | None:
        """Options with the picked racket applied, or None if nothing was picked."""
        slug = user_input.get(CONF_RACQUET)
        racquet = next((r for r in self._matches if r["slug"] == slug), None)
        if racquet is None:
            return None
        return apply(self._options, racquet, self._version)


class RacketTrackerConfigFlow(_LookupMixin, ConfigFlow, domain=DOMAIN):
    """Add a racket."""

    VERSION = 1

    _name: str

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle adding a racket."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _clean(user_input, errors)
            name = data.pop(CONF_NAME).strip()
            query = (data.pop(CONF_LOOKUP, None) or "").strip()
            if not name:
                errors[CONF_NAME] = "name_required"
            if not errors:
                self._name, self._options = name, data
                if not query:
                    return self.async_create_entry(title=name, data={}, options=data)
                if await self._async_lookup(query, errors):
                    return await self.async_step_pick()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the racket from the dataset matches (or none)."""
        if user_input is None:
            return self._pick_form("pick")
        options = self._picked(user_input) or self._options
        return self.async_create_entry(title=self._name, data={}, options=options)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> RacketOptionsFlow:
        """Return the options flow."""
        return RacketOptionsFlow()


class RacketOptionsFlow(_LookupMixin, OptionsFlow):
    """Edit racket details."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage racket details."""
        errors: dict[str, str] = {}
        linked = self.config_entry.options.get(CONF_DATASET_RACKET)
        if user_input is not None:
            data = _clean(user_input, errors)
            query = (data.pop(CONF_LOOKUP, None) or "").strip()
            keep = data.pop(CONF_USE_DATASET, True)
            if not errors:
                # Keep dataset values unless unlinked; the user's own specs are
                # layered on top.
                if keep:
                    for key in (CONF_DATASET_SPECS, CONF_DATASET_RACKET):
                        if value := self.config_entry.options.get(key):
                            data[key] = value
                self._options = data
                if not query:
                    return self.async_create_entry(data=data)
                if await self._async_lookup(query, errors):
                    return await self.async_step_pick()

        schema = LOOKUP_SCHEMA.extend(RACKET_DETAILS_SCHEMA.schema)
        if linked:
            schema = schema.extend(
                {vol.Optional(CONF_USE_DATASET, default=True): BooleanSelector()}
            )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or self.config_entry.options
            ),
            errors=errors,
            description_placeholders={
                "dataset_racket": linked["name"] if linked else "—"
            },
        )

    async def async_step_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the racket from the dataset matches (or keep things as they are)."""
        if user_input is None:
            return self._pick_form("pick")
        return self.async_create_entry(data=self._picked(user_input) or self._options)
