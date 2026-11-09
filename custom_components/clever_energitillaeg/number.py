"""Form kWh and price."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .form import FormEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([FormKwh(coordinator, "form_kwh"), FormPrice(coordinator, "form_price")])


class FormNumber(FormEntity, NumberEntity):
    _platform = "number"
    _attr_mode = NumberMode.BOX
    _field: str

    @property
    def native_value(self) -> float:
        return getattr(self._form, self._field)

    async def async_set_native_value(self, value: float) -> None:
        setattr(self._form, self._field, float(value))
        self.coordinator.public.async_form_changed()


class FormKwh(FormNumber):
    _field = "kwh"
    _attr_native_min_value = 0
    _attr_native_max_value = 1000
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = NumberDeviceClass.ENERGY
    _attr_icon = "mdi:ev-station"


class FormPrice(FormNumber):
    _field = "pris"
    _attr_native_min_value = 0
    _attr_native_max_value = 100_000
    _attr_native_step = 0.01
    _attr_native_unit_of_measurement = "kr."
    _attr_icon = "mdi:receipt-text"
