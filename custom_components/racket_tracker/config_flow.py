"""Config flow for Racket String Tracker."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
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
from .specs import CONF_DATASET_SPECS, CONF_SPECS, SPECS

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

USER_SCHEMA = vol.Schema({vol.Required(CONF_NAME): TextSelector()}).extend(
    RACKET_DETAILS_SCHEMA.schema
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


class RacketTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a racket."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle adding a racket."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _clean(user_input, errors)
            name = data.pop(CONF_NAME).strip()
            if not name:
                errors[CONF_NAME] = "name_required"
            if not errors:
                return self.async_create_entry(title=name, data={}, options=data)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> RacketOptionsFlow:
        """Return the options flow."""
        return RacketOptionsFlow()


class RacketOptionsFlow(OptionsFlow):
    """Edit racket details."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage racket details."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _clean(user_input, errors)
            if not errors:
                # Keep dataset values; the user's own specs are layered on top.
                if dataset := self.config_entry.options.get(CONF_DATASET_SPECS):
                    data[CONF_DATASET_SPECS] = dataset
                return self.async_create_entry(data=data)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                RACKET_DETAILS_SCHEMA, user_input or self.config_entry.options
            ),
            errors=errors,
        )
