"""Daily fetch; every refresh recalculates the whole month from source data."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .api import EnergiDataServiceApi, PriceApiError
from .calc import MonthResult, calculate, month_of, next_month
from .const import (
    CONF_THRESHOLD,
    CONF_VAT,
    DEFAULT_THRESHOLD,
    DEFAULT_VAT,
    DK_TZ,
    DOMAIN,
    FETCH_TIME,
    MONTH_START_TIME,
    RETRY_TIME,
)

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1


@dataclass(frozen=True)
class CleverData:
    """What the entities show. result is None when there is no valid calculation."""

    month: str
    status: str  # ok | error | no_data
    result: MonthResult | None
    fetched: datetime | None  # last successful fetch
    last_attempt: datetime
    error: str | None = None
    http_status: int | None = None


def option(entry: ConfigEntry, key: str, default: Any) -> Any:
    return entry.options.get(key, entry.data.get(key, default))


class CleverCoordinator(DataUpdateCoordinator[CleverData]):
    """No update_interval: refreshes are scheduled at fixed local times."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: EnergiDataServiceApi):
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=None)
        self.api = api
        self.threshold = float(option(entry, CONF_THRESHOLD, DEFAULT_THRESHOLD))
        self.vat = float(option(entry, CONF_VAT, DEFAULT_VAT))
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._stored: CleverData | None = None

    async def async_load_stored(self) -> None:
        """Last successful calculation, so a failed fetch after restart keeps the month's value."""
        raw = await self._store.async_load()
        if not raw or raw.get("threshold") != self.threshold or raw.get("vat") != self.vat:
            return
        try:
            self._stored = CleverData(
                month=raw["month"],
                status="ok",
                result=MonthResult.from_dict(raw["result"]),
                fetched=dt_util.parse_datetime(raw["fetched"]),
                last_attempt=dt_util.parse_datetime(raw["fetched"]),
            )
        except KeyError, TypeError, ValueError:
            _LOGGER.debug("Ignoring unreadable stored calculation")

    def _previous(self, month: str) -> CleverData | None:
        for candidate in (self.data, self._stored):
            if candidate and candidate.result is not None and candidate.month == month:
                return candidate
        return None

    async def _async_update_data(self) -> CleverData:
        now = dt_util.now()
        month = month_of(now)
        try:
            records = await self.api.async_month_records(month, next_month(month))
        except PriceApiError as err:
            _LOGGER.warning("Energinet DayAheadPrices: %s", err)
            prev = self._previous(month)
            if prev is not None:
                return replace(
                    prev, status="error", error=str(err), http_status=err.status, last_attempt=now
                )
            return CleverData(
                month=month,
                status="error",
                result=None,
                fetched=None,
                last_attempt=now,
                error=str(err),
                http_status=err.status,
            )
        result = calculate(records, month, now.astimezone(DK_TZ).date(), self.threshold, self.vat)
        if not result.included_days:
            return CleverData(
                month=month,
                status="no_data",
                result=None,
                fetched=now,
                last_attempt=now,
                error="Ingen komplette dage",
                http_status=200,
            )
        await self._store.async_save(
            {
                "month": month,
                "result": result.as_dict(),
                "fetched": now.isoformat(),
                "threshold": self.threshold,
                "vat": self.vat,
            }
        )
        return CleverData(
            month=month, status="ok", result=result, fetched=now, last_attempt=now, http_status=200
        )

    @callback
    def async_schedule(self) -> None:
        """Daily fetch, evening retry only after a failure, and the first of the month."""
        jitter = sum(map(ord, self.config_entry.entry_id)) % 60  # spread installs over a minute

        @callback
        def daily(_now: datetime) -> None:
            self.hass.async_create_task(self.async_refresh())

        @callback
        def retry(_now: datetime) -> None:
            today = dt_util.now().astimezone(DK_TZ).date()
            fetched = self.data.fetched if self.data else None
            if (
                self.data is None
                or self.data.status != "ok"
                or fetched is None
                or (fetched.astimezone(DK_TZ).date() != today)
            ):
                self.hass.async_create_task(self.async_refresh())

        @callback
        def month_start(_now: datetime) -> None:
            if dt_util.now().astimezone(DK_TZ).day == 1:
                self.hass.async_create_task(self.async_refresh())

        for (hour, minute), action in (
            (FETCH_TIME, daily),
            (RETRY_TIME, retry),
            (MONTH_START_TIME, month_start),
        ):
            self.config_entry.async_on_unload(
                async_track_time_change(self.hass, action, hour=hour, minute=minute, second=jitter)
            )
