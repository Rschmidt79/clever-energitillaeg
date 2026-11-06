"""Saved Energinet responses; HTTP is mocked, no network."""

import gzip
import json
from datetime import datetime
from pathlib import Path

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.clever_energitillaeg.const import API_URL, DK_TZ, DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"
_ROWS: list | None = None


def all_rows() -> list:
    global _ROWS
    if _ROWS is None:
        with gzip.open(FIXTURES / "dayaheadprices_2025-10_2026-11.json.gz", "rt") as fh:
            _ROWS = json.load(fh)
    return _ROWS


def month_records(month: str, mutate=None) -> list[dict]:
    recs = [
        {"TimeDK": t, "PriceArea": a, "DayAheadPriceDKK": p}
        for t, a, p in all_rows()
        if t[:7] == month
    ]
    return mutate(recs) if mutate else recs


def body(records: list[dict]) -> dict:
    return {"total": len(records), "limit": 0, "dataset": "DayAheadPrices", "records": records}


def local(*args) -> datetime:
    return datetime(*args, tzinfo=DK_TZ)


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
async def dk_time(hass, freezer):
    await hass.config.async_set_time_zone("Europe/Copenhagen")
    freezer.move_to(local(2026, 11, 6, 9, 0))
    return freezer


class Http:
    def __init__(self, mock):
        self.mock = mock

    def respond(self, payload=None, status=200, exc=None, text=None):
        self.mock.clear_requests()
        if exc is not None:
            self.mock.get(API_URL, exc=exc)
        elif text is not None:
            self.mock.get(API_URL, status=status, text=text)
        else:
            self.mock.get(
                API_URL, status=status, json=payload, headers={"content-type": "application/json"}
            )

    @property
    def calls(self):
        return self.mock.mock_calls


@pytest.fixture
def http(aioclient_mock):
    return Http(aioclient_mock)


def make_entry(version: int = 2, **options) -> MockConfigEntry:
    opts = {"threshold": 0.89, "vat_percent": 25.0} | options
    if version == 2 and "energy_entity" in opts:
        opts["energy_entities"] = [opts.pop("energy_entity")]
    return MockConfigEntry(
        domain=DOMAIN,
        title="Clever energitillæg",
        version=version,
        data={},
        options=opts,
        unique_id=DOMAIN,
        entry_id="01TESTENTRY0000000000000000",
    )


def now_dk():
    return dt_util.now().astimezone(DK_TZ)
