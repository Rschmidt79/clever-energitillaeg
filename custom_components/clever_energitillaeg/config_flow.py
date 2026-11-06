"""UI setup: optional monthly energy sensor, threshold and VAT."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_ENERGY_ENTITY,
    CONF_THRESHOLD,
    CONF_VAT,
    DEFAULT_THRESHOLD,
    DEFAULT_VAT,
    DOMAIN,
    NAME,
)

SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENERGY_ENTITY): EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.ENERGY)
        ),
        vol.Required(CONF_THRESHOLD, default=DEFAULT_THRESHOLD): NumberSelector(
            NumberSelectorConfig(
                min=0, max=10, step=0.01, mode=NumberSelectorMode.BOX, unit_of_measurement="DKK/kWh"
            )
        ),
        vol.Required(CONF_VAT, default=DEFAULT_VAT): NumberSelector(
            NumberSelectorConfig(
                min=0, max=100, step=0.1, mode=NumberSelectorMode.BOX, unit_of_measurement="%"
            )
        ),
    }
)


class CleverConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title=NAME, data={}, options=user_input)
        return self.async_show_form(step_id="user", data_schema=SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return CleverOptionsFlow()


class CleverOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(SCHEMA, self.config_entry.options),
        )
