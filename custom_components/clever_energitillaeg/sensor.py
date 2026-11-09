"""Rate, averages, last fetch and one preliminary surcharge per selected energy sensor."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, EntityCategory, UnitOfEnergy
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change
from homeassistant.util import dt as dt_util

from . import (
    last_month_surcharge_key,
    last_month_surcharge_object_id,
    surcharge_key,
    surcharge_object_id,
)
from .calc import MonthResult, month_of, previous_month
from .const import CONF_ENERGY_ENTITIES, DK_TZ, DOMAIN
from .coordinator import CleverCoordinator
from .entity import CleverEntity

PRICE_UNIT = "kr./kWh"
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
        LastMonthRateSensor(coordinator),
    ]
    energy_entities = list(dict.fromkeys(entry.options.get(CONF_ENERGY_ENTITIES) or []))
    entities.extend(SurchargeSensor(coordinator, e) for e in energy_entities)
    entities.extend(LastMonthSurchargeSensor(coordinator, e) for e in energy_entities)
    for last in (False, True):
        entities.append(PublicEnergySensor(coordinator, last))
        entities.append(PublicSurchargeSensor(coordinator, last))
        entities.append(PublicPaidSensor(coordinator, last))
        entities.append(PublicSavingSensor(coordinator, last))
        entities.append(TotalSurchargeSensor(coordinator, energy_entities, last))
        entities.extend(
            ComparisonSensor(coordinator, energy_entities, kind, last)
            for kind in ("with", "without", "difference")
        )
    # Surcharges for sensors no longer selected are removed, not left as orphans.
    registry = er.async_get(hass)
    wanted = {e.unique_id for e in entities}
    for ent in er.async_entries_for_config_entry(registry, entry.entry_id):
        if "surcharge" in ent.unique_id and ent.unique_id not in wanted:
            registry.async_remove(ent.entity_id)
    async_add_entities(entities)


def energy_name(hass: HomeAssistant, entity_id: str) -> str:
    """The energy sensor's display name, for naming its surcharge."""
    if state := hass.states.get(entity_id):
        if name := state.attributes.get("friendly_name"):
            return str(name)
    if ent := er.async_get(hass).async_get(entity_id):
        if name := ent.name or ent.original_name:
            return name
    return entity_id.split(".", 1)[-1]


def current_kwh(hass: HomeAssistant, entity_id: str) -> tuple[float | None, str | None]:
    """This month's energy in kWh, or None with the reason it cannot be used."""
    state: State | None = hass.states.get(entity_id)
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None, "energi_utilgaengelig"
    factor = ENERGY_FACTOR.get(state.attributes.get("unit_of_measurement"))
    if factor is None:
        return None, "energi_enhed"
    try:
        value = float(state.state) * factor
    except ValueError:
        return None, "energi_utilgaengelig"
    last_reset = dt_util.parse_datetime(str(state.attributes.get("last_reset") or ""))
    if last_reset is None or month_of(last_reset) != month_of(dt_util.now()):
        return None, "energi_ikke_nulstillet_denne_maaned"
    return value, None


def last_month_kwh(hass: HomeAssistant, entity_id: str) -> float | None:
    """Last month's energy from a utility meter's last_period, if it is last month's."""
    state = hass.states.get(entity_id)
    if state is None:
        return None
    factor = ENERGY_FACTOR.get(state.attributes.get("unit_of_measurement"))
    last_reset = dt_util.parse_datetime(str(state.attributes.get("last_reset") or ""))
    try:
        kwh = float(state.attributes["last_period"]) * factor  # type: ignore[operator]
    except KeyError, TypeError, ValueError:
        return None
    if last_reset is None or month_of(last_reset) != month_of(dt_util.now()):
        return None
    return kwh


class RateSensor(CleverEntity, SensorEntity):
    """Preliminary rate; unknown (never 0) without a valid calculation."""

    _attr_native_unit_of_measurement = PRICE_UNIT
    _attr_state_class = SensorStateClass.MEASUREMENT
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
            "maaned": data.month,
            "status": data.status,
            "fejl": data.error,
            "http_status": data.http_status,
            "hentet": data.fetched.isoformat() if data.fetched else None,
            "sidste_forsoeg": data.last_attempt.isoformat(),
            "grundsats": self.coordinator.threshold,
            "moms_procent": self.coordinator.vat,
            "note": NOTE,
        }
        if res is not None:
            attrs.update(
                dage_i_maaned=res.days_in_month,
                antal_dage_indgaar=len(res.included_days),
                dage_indgaar=res.included_days,
                manglende_dage=res.missing_days,
                afventer_dage=res.pending_days,
                medtager_dage_efter_i_dag=res.includes_future_days,
                intervaller_dk1=res.intervals.get("DK1"),
                intervaller_dk2=res.intervals.get("DK2"),
                sats_raa=res.raw_rate,
                dage=res.days,
            )
        return attrs


class AverageSensor(CleverEntity, SensorEntity):
    """Month-to-date spot average incl. VAT (national = DK1/DK2 50/50)."""

    _attr_native_unit_of_measurement = PRICE_UNIT
    _attr_state_class = SensorStateClass.MEASUREMENT
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
        return {"maaned": data.month, "status": data.status} if data else None


def month_attributes(res: MonthResult) -> dict[str, Any]:
    return {
        "maaned": res.month,
        "sats_raa": res.raw_rate,
        "landsgennemsnit": res.national_average,
        "gennemsnit_dk1": res.average.get("DK1"),
        "gennemsnit_dk2": res.average.get("DK2"),
        "antal_dage_indgaar": len(res.included_days),
        "dage_i_maaned": res.days_in_month,
        "manglende_dage": res.missing_days,
        "dage": res.days,
    }


class LastMonthRateSensor(CleverEntity, SensorEntity):
    """Last month's rate recalculated from Energinet; Clever's published rate is the official one."""

    _attr_native_unit_of_measurement = PRICE_UNIT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:cash-check"

    def __init__(self, coordinator: CleverCoordinator) -> None:
        super().__init__(coordinator, "last_month_rate")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # At midnight on the 1st "last month" changes before the next fetch.
        self.async_on_remove(async_track_time_change(self.hass, self._tick, minute=0, second=1))

    @callback
    def _tick(self, _now: datetime) -> None:
        self.async_write_ha_state()

    def _result(self) -> MonthResult | None:
        data = self.coordinator.data
        if not data or not data.previous:
            return None
        # Only while it is still "last month".
        if data.previous.month != previous_month(month_of(dt_util.now())):
            return None
        return data.previous

    @property
    def native_value(self) -> float | None:
        res = self._result()
        return res.rate if res else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        res = self._result()
        attrs = month_attributes(res) if res else {}
        attrs["grundsats"] = self.coordinator.threshold
        attrs["note"] = (
            "Beregnet af integrationen ud fra Energinets priser for hele måneden. "
            "Clevers offentliggjorte sats er den officielle."
        )
        return attrs


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

    _attr_native_unit_of_measurement = "kr."
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:cash-plus"

    def __init__(self, coordinator: CleverCoordinator, energy_entity: str) -> None:
        super().__init__(
            coordinator, surcharge_key(energy_entity), surcharge_object_id(energy_entity)
        )
        self._energy_entity = energy_entity
        self._attr_name = (
            f"Foreløbigt energitillæg – {energy_name(coordinator.hass, energy_entity)}"
        )

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

    def _value(self) -> tuple[float | None, str | None, float | None]:
        data = self.coordinator.data
        if not data or not data.result or data.result.rate is None:
            return None, "ingen_sats", None
        if data.month != month_of(dt_util.now()):
            return None, "sats_fra_anden_maaned", None
        kwh, reason = current_kwh(self.hass, self._energy_entity)
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
            "energisensor": self._energy_entity,
            "energi_kwh": kwh,
            "sats": data.result.rate if data and data.result else None,
            "maaned": data.month if data else None,
            "note": "Foreløbigt: sats × energisensorens månedsforbrug. Clever henfører en opladning "
            "til den måned, hvor den stopper, og bruger egne målinger.",
        }


class LastMonthSurchargeSensor(CleverEntity, SensorEntity):
    """Last month's rate × the energy sensor's last_period (utility meter).

    Only available while the energy sensor's last_reset is in the current month, so
    last_period is last month's consumption.
    """

    _attr_native_unit_of_measurement = "kr."
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:cash-check"

    def __init__(self, coordinator: CleverCoordinator, energy_entity: str) -> None:
        super().__init__(
            coordinator,
            last_month_surcharge_key(energy_entity),
            last_month_surcharge_object_id(energy_entity),
        )
        self._energy_entity = energy_entity
        self._attr_name = (
            f"Energitillæg sidste måned – {energy_name(coordinator.hass, energy_entity)}"
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(self.hass, [self._energy_entity], self._changed)
        )
        self.async_on_remove(async_track_time_change(self.hass, self._changed, minute=0, second=1))

    @callback
    def _changed(self, _event: Any) -> None:
        self.async_write_ha_state()

    def _value(self) -> tuple[float | None, float | None, MonthResult | None]:
        data = self.coordinator.data
        now_month = month_of(dt_util.now())
        prev = data.previous if data else None
        if prev is None or prev.rate is None or prev.month != previous_month(now_month):
            return None, None, None
        kwh = last_month_kwh(self.hass, self._energy_entity)
        if kwh is None:
            return None, None, prev
        return round(prev.rate * kwh, 2), kwh, prev

    @property
    def available(self) -> bool:
        return self._value()[0] is not None

    @property
    def native_value(self) -> float | None:
        return self._value()[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        _, kwh, prev = self._value()
        return {
            "energisensor": self._energy_entity,
            "energi_kwh": kwh,
            "sats": prev.rate if prev else None,
            "maaned": prev.month if prev else None,
            "note": "Sidste måneds beregnede sats × energisensorens last_period (utility meter).",
        }


PUBLIC_NOTE = (
    "Offentlig ladning (fx DC-lynladning) tilføjet med handlingen "
    "clever_energitillaeg.tilfoej_offentlig_ladning med kWh og evt. den pris, du har betalt. "
    "Med Clever er strømmen inkluderet i abonnementet; kWh tæller kun med i energitillægget "
    "(sats × kWh). Clever henfører en opladning til den måned, hvor den stopper."
)


class PublicEntity(CleverEntity, SensorEntity):
    """Updates when a public charge is added or removed, and hourly for the month change."""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.public.async_add_listener(self.async_write_ha_state))
        self.async_on_remove(async_track_time_change(self.hass, self._tick, minute=0, second=1))

    @callback
    def _tick(self, _now: Any) -> None:
        self.async_write_ha_state()

    def _month(self, last: bool) -> str:
        month = month_of(dt_util.now())
        return previous_month(month) if last else month

    def _charges(self, month: str) -> list[dict[str, Any]]:
        return [
            {"id": c.id, "dato": c.dato, "kwh": c.kwh, "pris": c.pris, "note": c.note}
            for c in self.coordinator.public.for_month(month)
        ]


class PublicEnergySensor(PublicEntity):
    """kWh of public charging entered for this (or last) month. 0 when nothing is entered."""

    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator: CleverCoordinator, last: bool) -> None:
        super().__init__(coordinator, "public_energy_last_month" if last else "public_energy")
        self._last = last
        if not last:
            # Resets on the 1st like a monthly utility meter.
            self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> float:
        return self.coordinator.public.kwh(self._month(self._last))

    @property
    def last_reset(self) -> datetime | None:
        if self._last:
            return None
        now = dt_util.now().astimezone(DK_TZ)
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        month = self._month(self._last)
        return {"maaned": month, "ladninger": self._charges(month), "note": PUBLIC_NOTE}


class PublicSurchargeSensor(PublicEntity):
    """Rate × the public charging kWh of the month."""

    _attr_native_unit_of_measurement = "kr."
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: CleverCoordinator, last: bool) -> None:
        super().__init__(coordinator, "public_last_month_surcharge" if last else "public_surcharge")
        self._last = last
        self._attr_icon = "mdi:cash-check" if last else "mdi:cash-plus"

    def _value(self) -> tuple[float | None, float | None, float]:
        month = self._month(self._last)
        kwh = self.coordinator.public.kwh(month)
        rate = month_rate(self.coordinator, month)
        return (None if rate is None else round(rate * kwh, 2)), rate, kwh

    @property
    def available(self) -> bool:
        return self._value()[0] is not None

    @property
    def native_value(self) -> float | None:
        return self._value()[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        value, rate, kwh = self._value()
        month = self._month(self._last)
        without = self.coordinator.public.cost_without(month, self.coordinator.public_price)
        return {
            "energi_kwh": kwh,
            "sats": rate,
            "maaned": month,
            "betalt": self.coordinator.public.paid(month),
            "uden_clever": without,
            "besparelse_med_clever": (
                None if value is None or without is None else round(without - value, 2)
            ),
        }


class PublicPaidSensor(PublicEntity):
    """What was actually paid for the month's public charging (entered by the user)."""

    _attr_native_unit_of_measurement = "kr."
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:receipt-text"

    def __init__(self, coordinator: CleverCoordinator, last: bool) -> None:
        super().__init__(coordinator, "public_paid_last_month" if last else "public_paid")
        self._last = last

    @property
    def native_value(self) -> float:
        return self.coordinator.public.paid(self._month(self._last))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        month = self._month(self._last)
        public = self.coordinator.public
        priced = round(public.kwh(month) - public.unpriced_kwh(month), 3)
        paid = public.paid(month)
        return {
            "maaned": month,
            "energi_kwh": public.kwh(month),
            "energi_kwh_med_kvittering": priced,
            "energi_kwh_uden_pris": public.unpriced_kwh(month),
            "pris_pr_kwh": round(paid / priced, 2) if priced else None,
        }


class PublicSavingSensor(PublicEntity):
    """Paid minus what Clever would have charged (rate × kWh). Positive: Clever is cheaper.

    The subscription itself is not included; it is paid whether or not you charge away.
    """

    _attr_native_unit_of_measurement = "kr."
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:scale-balance"

    def __init__(self, coordinator: CleverCoordinator, last: bool) -> None:
        super().__init__(coordinator, "public_saving_last_month" if last else "public_saving")
        self._last = last

    def _value(self) -> tuple[float | None, dict[str, Any]]:
        month = self._month(self._last)
        public = self.coordinator.public
        kwh = public.kwh(month)
        without = public.cost_without(month, self.coordinator.public_price)
        rate = month_rate(self.coordinator, month)
        clever = None if rate is None else round(rate * kwh, 2)
        info = {
            "maaned": month,
            "energi_kwh": kwh,
            "betalt": public.paid(month),
            "uden_clever": without,
            "alternativ_pris_pr_kwh": self.coordinator.public_price,
            "med_clever": clever,
            "sats": rate,
            "note": "Uden Clever (kvitteringer, ellers kWh × alternativ pris) − energitillæg "
            "(sats × kWh). Positiv: Clever havde været billigst. Abonnementet er ikke medregnet.",
        }
        if clever is None or without is None:
            return None, info
        return round(without - clever, 2), info

    @property
    def available(self) -> bool:
        return self._value()[0] is not None

    @property
    def native_value(self) -> float | None:
        return self._value()[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._value()[1]


class TotalSurchargeSensor(PublicEntity):
    """Rate × (all selected energy sensors + public charging), as Clever bills it.

    Unavailable if any selected energy sensor cannot be used, so a part is never counted as 0.
    """

    _attr_native_unit_of_measurement = "kr."
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: CleverCoordinator,
        energy_entities: list[str],
        last: bool,
        key: str | None = None,
    ) -> None:
        if key is None:
            key = "total_last_month_surcharge" if last else "total_surcharge"
        super().__init__(coordinator, key)
        self._last = last
        self._attr_icon = "mdi:cash-check" if last else "mdi:cash-multiple"
        # Our own public charging sensor, if selected as an energy sensor, is counted once.
        self._energy_entities = [
            e for e in energy_entities if not e.startswith(f"sensor.{DOMAIN}_")
        ]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._energy_entities:
            self.async_on_remove(
                async_track_state_change_event(self.hass, self._energy_entities, self._tick)
            )

    def _value(self) -> tuple[float | None, dict[str, Any]]:
        month = self._month(self._last)
        rate = month_rate(self.coordinator, month)
        parts: dict[str, float | None] = {}
        for entity_id in self._energy_entities:
            if self._last:
                parts[entity_id] = last_month_kwh(self.hass, entity_id)
            else:
                parts[entity_id] = current_kwh(self.hass, entity_id)[0]
        parts["offentlig_ladning"] = self.coordinator.public.kwh(month)
        info: dict[str, Any] = {"maaned": month, "sats": rate, "energi_kwh_dele": parts}
        if rate is None or any(v is None for v in parts.values()):
            return None, info
        kwh = sum(v for v in parts.values() if v is not None)
        info["energi_kwh"] = round(kwh, 3)
        return round(rate * kwh, 2), info

    @property
    def available(self) -> bool:
        return self._value()[0] is not None

    @property
    def native_value(self) -> float | None:
        return self._value()[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._value()[1]


COMPARISON_NOTE = (
    "Med Clever (Clever One + Clever Power) = abonnement + energitillæg (sats × alle kWh hjemme "
    "og ude); hjemmeladningens strøm dækkes 1:1. Uden Clever = det hjemmeladningen koster dig + "
    "offentlig ladning (kvitteringens pris, ellers kWh × alternativ DC-pris). Forskel = uden − med; positiv: Clever havde været "
    "billigst. Indeværende måneds sats er foreløbig."
)
MONEY_UNITS = ("kr", "kr.", "DKK")


def money_value(hass: HomeAssistant, entity_id: str, last: bool) -> tuple[float | None, str | None]:
    """A monthly cost sensor in kr.: this month's state, or last month's last_period."""
    state = hass.states.get(entity_id)
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None, "hjemmepris_utilgaengelig"
    if state.attributes.get("unit_of_measurement") not in MONEY_UNITS:
        return None, "hjemmepris_enhed"
    last_reset = dt_util.parse_datetime(str(state.attributes.get("last_reset") or ""))
    if last_reset is None or month_of(last_reset) != month_of(dt_util.now()):
        return None, "hjemmepris_ikke_nulstillet_denne_maaned"
    try:
        return float(state.attributes["last_period"] if last else state.state), None
    except KeyError, TypeError, ValueError:
        return None, "hjemmepris_utilgaengelig"


class ComparisonSensor(TotalSurchargeSensor):
    """The month with Clever vs. without Clever, and the difference."""

    def __init__(
        self,
        coordinator: CleverCoordinator,
        energy_entities: list[str],
        kind: str,
        last: bool,
    ) -> None:
        key = f"comparison_{kind}" + ("_last_month" if last else "")
        super().__init__(coordinator, energy_entities, last, key)
        self._kind = kind
        self._attr_icon = {
            "with": "mdi:lightning-bolt-circle",
            "without": "mdi:receipt-text",
            "difference": "mdi:scale-balance",
        }[kind]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if cost := self.coordinator.home_cost_entity:
            self.async_on_remove(async_track_state_change_event(self.hass, [cost], self._tick))

    def _home_cost(self, home_kwh: float | None) -> tuple[float | None, str | None]:
        """What home charging costs without Clever."""
        coordinator = self.coordinator
        if coordinator.home_cost_entity:
            return money_value(self.hass, coordinator.home_cost_entity, self._last)
        if not self._energy_entities:
            return 0.0, None  # no home charging is tracked
        if coordinator.home_price is None:
            return None, "hjemmepris_mangler"
        if home_kwh is None:
            return None, "energi_utilgaengelig"
        return round(coordinator.home_price * home_kwh, 2), None

    def _comparison(self) -> tuple[float | None, dict[str, Any]]:
        surcharge, info = TotalSurchargeSensor._value(self)
        month = self._month(self._last)
        subscription = self.coordinator.subscription
        public = self.coordinator.public
        paid = public.cost_without(month, self.coordinator.public_price)
        parts = info.get("energi_kwh_dele") or {}
        home_values = [v for k, v in parts.items() if k != "offentlig_ladning"]
        home_kwh = None if None in home_values else round(sum(home_values), 3)
        home_cost, reason = self._home_cost(home_kwh)
        with_clever = None if surcharge is None else round(subscription + surcharge, 2)
        if paid is None and reason is None:
            reason = "dc_pris_mangler"
        without = None if home_cost is None or paid is None else round(home_cost + paid, 2)
        diff = None if with_clever is None or without is None else round(without - with_clever, 2)
        attrs: dict[str, Any] = {
            "maaned": month,
            "med_clever": with_clever,
            "uden_clever": without,
            "forskel": diff,
            "billigst": None if diff is None else ("Clever" if diff > 0 else "Uden Clever"),
            "abonnement": subscription,
            "energitillaeg": surcharge,
            "sats": info.get("sats"),
            "energi_kwh": info.get("energi_kwh"),
            "energi_kwh_dele": parts,
            "hjemme_kwh": home_kwh,
            "hjemmeladning_pris": home_cost,
            "hjemmeladning_kilde": self.coordinator.home_cost_entity
            or (None if self.coordinator.home_price is None else "fast kr./kWh"),
            "offentlig_ladning_uden_clever": paid,
            "offentlig_ladning_betalt": public.paid(month),
            "alternativ_dc_pris_pr_kwh": self.coordinator.public_price,
            "mangler": reason,
            "note": COMPARISON_NOTE,
        }
        value = {"with": with_clever, "without": without, "difference": diff}[self._kind]
        return value, attrs

    def _value(self) -> tuple[float | None, dict[str, Any]]:
        return self._comparison()


def month_rate(coordinator: CleverCoordinator, month: str) -> float | None:
    """The calculated rate for this or last month; None unless it belongs to that month."""
    data = coordinator.data
    if data is None:
        return None
    # Last month only from the recalculation of the whole month (as LastMonthRateSensor).
    res = data.result if month == month_of(dt_util.now()) else data.previous
    if res is None or res.month != month:
        return None
    return res.rate
