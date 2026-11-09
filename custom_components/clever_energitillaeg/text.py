"""Form note."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .form import FormEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([FormNote(entry.runtime_data, "form_note")])


class FormNote(FormEntity, TextEntity):
    _platform = "text"
    _attr_native_max = 200
    _attr_icon = "mdi:note-text"

    @property
    def native_value(self) -> str:
        return self._form.note

    async def async_set_value(self, value: str) -> None:
        self._form.note = value.strip()
        self.coordinator.public.async_form_changed()
