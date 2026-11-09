"""Form date (the day the charge stopped)."""

from __future__ import annotations

from datetime import date

from homeassistant.components.date import DateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .form import FormEntity, today


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([FormDate(entry.runtime_data, "form_date")])


class FormDate(FormEntity, DateEntity):
    _platform = "date"
    _attr_icon = "mdi:calendar"

    @property
    def native_value(self) -> date:
        return self._form.dato or today()

    async def async_set_value(self, value: date) -> None:
        self._form.dato = None if value == today() else value
        self.coordinator.public.async_form_changed()
