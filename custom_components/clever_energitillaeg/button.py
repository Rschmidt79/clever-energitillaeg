"""Form buttons: add the typed charge, undo the latest."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .form import FormEntity, async_submit, async_undo


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([AddButton(coordinator, "form_add"), UndoButton(coordinator, "form_undo")])


class AddButton(FormEntity, ButtonEntity):
    _platform = "button"
    _attr_icon = "mdi:plus-circle"

    async def async_press(self) -> None:
        await async_submit(self.coordinator)


class UndoButton(FormEntity, ButtonEntity):
    _platform = "button"
    _attr_icon = "mdi:undo"

    async def async_press(self) -> None:
        await async_undo(self.coordinator)
