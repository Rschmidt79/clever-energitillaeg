"""Public charging (e.g. DC fast charging on a trip) entered by hand.

Clever counts the monthly kWh "både hjemme og ude på netværket", so public charging on Clever's
network gets the same energy surcharge as charging at home, and nothing else (the power is
included in the subscription). Each charge is entered with what was actually paid elsewhere
(e.g. at Tesla), so the month shows paid vs. what it would have cost with Clever.
Clever attributes a charge to the month in which it stopped, so the date is the stop date.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .calc import month_of, previous_month
from .const import DOMAIN

STORAGE_VERSION = 1
KEEP_MONTHS = 13  # this month and the 12 before; older charges are dropped on changes


@dataclass(frozen=True)
class PublicCharge:
    id: str
    dato: str  # ISO date (Danish) the charge stopped
    kwh: float
    pris: float  # kr. actually paid for the charge
    note: str | None = None

    @property
    def month(self) -> str:
        return date.fromisoformat(self.dato).strftime("%Y-%m")


class PublicCharging:
    """Charges entered by the user, persisted per config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.offentlig_ladning"
        )
        self.charges: list[PublicCharge] = []
        self._listeners: list[Callable[[], None]] = []

    async def async_load(self) -> None:
        raw = await self._store.async_load() or {}
        charges = []
        for item in raw.get("ladninger", []):
            try:
                charge = PublicCharge(
                    id=str(item["id"]),
                    dato=str(item["dato"]),
                    kwh=float(item["kwh"]),
                    pris=float(item["pris"]),
                    note=item.get("note"),
                )
                _ = charge.month  # validates the date
            except KeyError, TypeError, ValueError:
                continue
            charges.append(charge)
        self.charges = charges  # in the order they were added

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    async def _async_changed(self) -> None:
        await self._store.async_save({"ladninger": [asdict(c) for c in self.charges]})
        for listener in list(self._listeners):
            listener()

    async def async_add(
        self, kwh: float, pris: float, stopped: date, note: str | None
    ) -> PublicCharge:
        charge = PublicCharge(
            id=uuid.uuid4().hex[:8],
            dato=stopped.isoformat(),
            kwh=round(float(kwh), 3),
            pris=round(float(pris), 2),
            note=note or None,
        )
        oldest = month_of(dt_util.now())
        for _ in range(KEEP_MONTHS - 1):
            oldest = previous_month(oldest)
        self.charges = [c for c in self.charges if c.month >= oldest] + [charge]
        await self._async_changed()
        return charge

    async def async_remove(self, charge_id: str | None) -> PublicCharge | None:
        """Remove by id, or the most recently added charge without an id."""
        if not self.charges:
            return None
        if charge_id is None:
            removed = self.charges[-1]
        else:
            removed = next((c for c in self.charges if c.id == charge_id), None)
            if removed is None:
                return None
        self.charges = [c for c in self.charges if c is not removed]
        await self._async_changed()
        return removed

    def for_month(self, month: str) -> list[PublicCharge]:
        return sorted((c for c in self.charges if c.month == month), key=lambda c: c.dato)

    def kwh(self, month: str) -> float:
        return round(sum(c.kwh for c in self.for_month(month)), 3)

    def paid(self, month: str) -> float:
        return round(sum(c.pris for c in self.for_month(month)), 2)
