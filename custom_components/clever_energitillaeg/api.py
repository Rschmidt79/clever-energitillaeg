"""Energi Data Service client (open API, no credentials)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

from .const import API_URL, PRICE_AREAS, RATE_LIMIT_DELAY, REQUEST_TIMEOUT


class PriceApiError(Exception):
    """Fetching or decoding the prices failed."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def month_query(month: str, next_month: str) -> dict[str, str]:
    """Query for one Danish calendar month; end is exclusive."""
    return {
        "start": f"{month}-01T00:00",
        "end": f"{next_month}-01T00:00",
        "filter": json.dumps({"PriceArea": list(PRICE_AREAS)}, separators=(",", ":")),
        "columns": "TimeDK,PriceArea,DayAheadPriceDKK",
        "sort": "TimeUTC asc",
        "limit": "0",
    }


class EnergiDataServiceApi:
    """Fetch DayAheadPrices for a whole month."""

    def __init__(self, session: aiohttp.ClientSession, rate_limit_delay: float = RATE_LIMIT_DELAY):
        self._session = session
        self._delay = rate_limit_delay

    async def _get(self, params: dict[str, str]) -> tuple[int, Any]:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with self._session.get(API_URL, params=params, timeout=timeout) as resp:
            text = await resp.text()
            return resp.status, text

    async def async_month_records(self, month: str, next_month: str) -> list[dict[str, Any]]:
        """Return the month's records; one retry after HTTP 429."""
        params = month_query(month, next_month)
        try:
            status, text = await self._get(params)
            if status == 429:
                await asyncio.sleep(self._delay)
                status, text = await self._get(params)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise PriceApiError(f"Ingen svar: {type(err).__name__}") from err
        if status != 200:
            raise PriceApiError(f"HTTP {status}", status)
        try:
            body = json.loads(text)
        except ValueError as err:
            raise PriceApiError("Svaret er ikke JSON", status) from err
        records = body.get("records") if isinstance(body, dict) else None
        if not isinstance(records, list) or not records:
            raise PriceApiError("Svaret indeholder ingen records", status)
        return records
