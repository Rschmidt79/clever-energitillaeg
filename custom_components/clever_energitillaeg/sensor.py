"""Rate, averages, last fetch and the optional preliminary surcharge."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, EntityCategory, UnitOfEnergy
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change
from homeassistant.util import dt as dt_util

from .calc import month_of
from .const import CONF_ENERGY_ENTITY
from .coordinator import CleverCoordinator
from .entity import CleverEntity

PRICE_UNIT = "DKK/kWh"
NOTE = (
    "Foreløbig sats ud fra de dage, der indgår. Den kan ændre sig frem til månedens afslutning; "
    "Clever fastsætter den endelige sats efter månedens udløb."
)
ENERGY_FACTOR = {
    UnitOfEnergy.WATT_HOUR: 0.001,
    UnitOfEnergy.KILO_WATT_HOUR: 1.0,
    UnitOfEnergy.MEGA_WATT_HOUR: 1000.0,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator: CleverCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        RateSensor(coordinator),
        AverageSensor(coordinator, "national_average", None),
        AverageSensor(coordinator, "average_dk1", "DK1"),
        AverageSensor(coordinator, "average_dk2", "DK2"),
        LastFetchSensor(coordinator),
    ]
    energy_entity = entry.options.get(CONF_ENERGY_ENTITY, entry.data.get(CONF_ENERGY_ENTITY))
    if energy_entity:
        entities.append(SurchargeSensor(coordinator, energy_entity))
    async_add_entities(entities)


class RateSensor(CleverEntity, SensorEntity):
    """Preliminary rate; unknown (never 0) without a valid calculation."""

    _attr_native_unit_of_measurement = PRICE_UNIT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:cash-plus"

    def __init__(self, coordinator: CleverCoordinator) -> None:
        super().__init__(coordinator, "rate")

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        return data.result.rate if data and data.result else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if data is None:
            return {"note": NOTE}
        res = data.result
        attrs: dict[str, Any] = {
            "month": data.month,
            "status": data.status,
            "error": data.error,
            "http_status": data.http_status,
            "fetched": data.fetched.isoformat() if data.fetched else None,
            "last_attempt": data.last_attempt.isoformat(),
            "threshold": self.coordinator.threshold,
            "vat_percent": self.coordinator.vat,
            "note": NOTE,
        }
        if res is not None:
            attrs.update(
                days_in_month=res.days_in_month,
                included_day_count=len(res.included_days),
                included_days=res.included_days,
                missing_days=res.missing_days,
                pending_days=res.pending_days,
                includes_future_days=res.includes_future_days,
                intervals_dk1=res.intervals.get("DK1"),
                intervals_dk2=res.intervals.get("DK2"),
                raw_rate=res.raw_rate,
            )
        return attrs


class AverageSensor(CleverEntity, SensorEntity):
    """Month-to-date spot average incl. VAT (national = DK1/DK2 50/50)."""

    _attr_native_unit_of_measurement = PRICE_UNIT
    _attr_suggested_display_precision = 4
    _attr_icon = "mdi:chart-line"

    def __init__(self, coordinator: CleverCoordinator, key: str, area: str | None) -> None:
        super().__init__(coordinator, key)
        self._area = area

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if not data or not data.result:
            return None
        if self._area is None:
            return data.result.national_average
        return data.result.average.get(self._area)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        return {"month": data.month, "status": data.status} if data else None


class LastFetchSensor(CleverEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CleverCoordinator) -> None:
        super().__init__(coordinator, "last_fetch")

    @property
    def native_value(self) -> datetime | None:
        data = self.coordinator.data
        return data.fetched if data else None


class SurchargeSensor(CleverEntity, SensorEntity):
    """rate × the month's energy. Unavailable unless both belong to the current month."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "DKK"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:cash-plus"

    def __init__(self, coordinator: CleverCoordinator, energy_entity: str) -> None:
        super().__init__(coordinator, "surcharge")
        self._energy_entity = energy_entity

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(self.hass, [self._energy_entity], self._energy_changed)
        )
        # Month change at midnight must make the value unavailable without a state change.
        self.async_on_remove(async_track_time_change(self.hass, self._tick, minute=0, second=1))

    @callback
    def _energy_changed(self, _event: Event[EventStateChangedData]) -> None:
        self.async_write_ha_state()

    @callback
    def _tick(self, _now: datetime) -> None:
        self.async_write_ha_state()

    def _energy_kwh(self) -> tuple[float | None, str | None]:
        """Energy in kWh, or None with the reason it cannot be used."""
        state: State | None = self.hass.states.get(self._energy_entity)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None, "energy_unavailable"
        factor = ENERGY_FACTOR.get(state.attributes.get("unit_of_measurement"))
        if factor is None:
            return None, "energy_unit"
        try:
            value = float(state.state) * factor
        except ValueError:
            return None, "energy_unavailable"
        last_reset = dt_util.parse_datetime(str(state.attributes.get("last_reset") or ""))
        if last_reset is None or month_of(last_reset) != month_of(dt_util.now()):
            return None, "energy_not_reset_this_month"
        return value, None

    def _value(self) -> tuple[float | None, str | None, float | None]:
        data = self.coordinator.data
        if not data or not data.result or data.result.rate is None:
            return None, "no_rate", None
        if data.month != month_of(dt_util.now()):
            return None, "rate_from_other_month", None
        kwh, reason = self._energy_kwh()
        if kwh is None:
            return None, reason, None
        return round(data.result.rate * kwh, 2), None, kwh

    @property
    def available(self) -> bool:
        return self._value()[0] is not None

    @property
    def unavailable_reason(self) -> str | None:
        """Shown in diagnostics (HA drops attributes of unavailable entities)."""
        return self._value()[1]

    @property
    def native_value(self) -> float | None:
        return self._value()[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        _, _, kwh = self._value()
        return {
            "energy_entity": self._energy_entity,
            "energy_kwh": kwh,
            "rate": data.result.rate if data and data.result else None,
            "month": data.month if data else None,
            "note": "Foreløbigt: sats × energisensorens månedsforbrug. Clever henfører en opladning "
            "til den måned, hvor den stopper, og bruger egne målinger.",
        }
