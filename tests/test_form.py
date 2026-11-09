"""Dashboard form entities shipped with the integration."""

import pytest
from homeassistant.exceptions import ServiceValidationError

from .conftest import month_records
from .test_integration import setup
from .test_public import PAID, PUB, WITHOUT, state

DATE = "date.clever_energitillaeg_dc_dato"
KWH = "number.clever_energitillaeg_dc_kwh"
PRICE = "number.clever_energitillaeg_dc_pris"
NOTE = "text.clever_energitillaeg_dc_note"
ADD = "button.clever_energitillaeg_tilfoej_dc_ladning"
UNDO = "button.clever_energitillaeg_fortryd_seneste_dc_ladning"


async def fill(hass, kwh=None, pris=None, note=None, dato=None):
    if dato is not None:
        await hass.services.async_call(
            "date", "set_value", {"entity_id": DATE, "date": dato}, blocking=True
        )
    if kwh is not None:
        await hass.services.async_call(
            "number", "set_value", {"entity_id": KWH, "value": kwh}, blocking=True
        )
    if pris is not None:
        await hass.services.async_call(
            "number", "set_value", {"entity_id": PRICE, "value": pris}, blocking=True
        )
    if note is not None:
        await hass.services.async_call(
            "text", "set_value", {"entity_id": NOTE, "value": note}, blocking=True
        )


async def press(hass, entity_id):
    await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)
    await hass.async_block_till_done()


async def test_form_adds_charge_and_clears(hass, dk_time, http):
    await setup(hass, http, month_records("2026-11"))
    assert state(hass, DATE) == "2026-11-06"  # today
    assert state(hass, KWH) == "0.0" and state(hass, PRICE) == "0.0" and state(hass, NOTE) == ""
    await fill(hass, kwh=47, pris=122.12, note="Ikast", dato="2026-11-03")
    assert state(hass, DATE) == "2026-11-03" and state(hass, NOTE) == "Ikast"
    await press(hass, ADD)
    assert state(hass, PUB) == "47.0" and state(hass, PAID) == "122.12"
    charge = hass.states.get(PUB).attributes["ladninger"][0]
    assert charge["dato"] == "2026-11-03" and charge["note"] == "Ikast"
    # kWh, price and note are cleared; the date is kept for the next receipt.
    assert state(hass, KWH) == "0.0" and state(hass, PRICE) == "0.0" and state(hass, NOTE) == ""
    assert state(hass, DATE) == "2026-11-03"
    await press(hass, UNDO)
    assert state(hass, PUB) == "0"


async def test_form_needs_kwh_and_rejects_future(hass, dk_time, http):
    await setup(hass, http, month_records("2026-11"))
    with pytest.raises(ServiceValidationError):
        await press(hass, ADD)
    await fill(hass, kwh=10, pris=40, dato="2026-11-07")
    with pytest.raises(ServiceValidationError):
        await press(hass, ADD)
    assert state(hass, PUB) == "0" and state(hass, KWH) == "10.0"  # nothing lost
    with pytest.raises(ServiceValidationError):
        await press(hass, UNDO)


async def test_form_zero_price_with_alternative_is_no_receipt(hass, dk_time, http):
    await setup(hass, http, month_records("2026-11"), public_price=4.5)
    await fill(hass, kwh=100)
    await press(hass, ADD)
    assert hass.states.get(PUB).attributes["ladninger"][0]["pris"] is None
    assert state(hass, WITHOUT) == "450.0"


async def test_form_zero_price_without_alternative_is_free(hass, dk_time, http):
    await setup(hass, http, month_records("2026-11"))
    await fill(hass, kwh=20)
    await press(hass, ADD)
    assert hass.states.get(PUB).attributes["ladninger"][0]["pris"] == 0.0
    assert state(hass, WITHOUT) == "0.0"
