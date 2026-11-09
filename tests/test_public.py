"""Public charging (e.g. DC fast charging) entered with services."""

import pytest
import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError

from custom_components.clever_energitillaeg.const import DOMAIN

from .conftest import body, local, month_records
from .test_integration import ENERGY, at, energy, setup

PUB = "sensor.clever_energitillaeg_offentlig_ladning"
PUB_LAST = "sensor.clever_energitillaeg_offentlig_ladning_sidste_maaned"
PUB_SUR = "sensor.clever_energitillaeg_foreloebigt_energitillaeg_offentlig_ladning"
PUB_SUR_LAST = "sensor.clever_energitillaeg_energitillaeg_sidste_maaned_offentlig_ladning"
TOTAL = "sensor.clever_energitillaeg_foreloebigt_energitillaeg_i_alt"
TOTAL_LAST = "sensor.clever_energitillaeg_energitillaeg_sidste_maaned_i_alt"
PAID = "sensor.clever_energitillaeg_offentlig_ladning_betalt"
PAID_LAST = "sensor.clever_energitillaeg_offentlig_ladning_betalt_sidste_maaned"
SAVING = "sensor.clever_energitillaeg_offentlig_ladning_besparelse_med_clever"
SAVING_LAST = "sensor.clever_energitillaeg_offentlig_ladning_besparelse_med_clever_sidste_maaned"


def two_months():
    return month_records("2026-10") + month_records("2026-11")


async def add(hass, **data):
    return await hass.services.async_call(
        DOMAIN, "tilfoej_offentlig_ladning", data, blocking=True, return_response=True
    )


async def remove(hass, **data):
    return await hass.services.async_call(
        DOMAIN, "fjern_offentlig_ladning", data, blocking=True, return_response=True
    )


def state(hass, entity_id):
    return hass.states.get(entity_id).state


async def test_nothing_entered_is_zero(hass, dk_time, http):
    await setup(hass, http, month_records("2026-11"))
    assert state(hass, PUB) == "0" and state(hass, PUB_SUR) == "0.0"
    assert state(hass, TOTAL) == "0.0"
    assert state(hass, PAID) == "0" and state(hass, SAVING) == "0.0"
    pub = hass.states.get(PUB)
    assert pub.attributes["device_class"] == "energy"
    assert pub.attributes["state_class"] == "total"
    assert pub.attributes["ladninger"] == [] and pub.attributes["maaned"] == "2026-11"


async def test_add_dc_charge_this_month(hass, dk_time, http):
    energy(hass, "189.574")
    await setup(hass, http, month_records("2026-11"), energy_entity=ENERGY)
    resp = await add(hass, kwh=120, pris=540, note="Tur til København")
    assert resp["kwh"] == 120.0 and resp["pris"] == 540.0 and len(resp["id"]) == 8
    assert resp["maaned"] == "2026-11" and resp["dato"] == "2026-11-06"  # default: today
    await hass.async_block_till_done()
    assert state(hass, PUB) == "120.0"
    charges = hass.states.get(PUB).attributes["ladninger"]
    assert charges == [
        {
            "id": resp["id"],
            "dato": "2026-11-06",
            "kwh": 120.0,
            "pris": 540.0,
            "note": "Tur til København",
        }
    ]
    assert state(hass, PUB_SUR) == str(round(1.59 * 120, 2))  # 190.8: only the surcharge
    assert state(hass, PAID) == "540.0"
    assert hass.states.get(PAID).attributes["pris_pr_kwh"] == 4.5
    saving = hass.states.get(SAVING)
    assert saving.state == str(round(540 - 190.8, 2))
    assert saving.attributes["betalt"] == 540.0 and saving.attributes["med_clever"] == 190.8
    assert hass.states.get(PUB_SUR).attributes["besparelse_med_clever"] == 349.2
    # The home surcharge is unchanged; the total is rate × all kWh, as Clever bills it.
    assert state(hass, "sensor.clever_energitillaeg_foreloebigt_energitillaeg_monthly_energy") == (
        str(round(1.59 * 189.574, 2))
    )
    total = hass.states.get(TOTAL)
    assert total.state == str(round(1.59 * (189.574 + 120), 2))
    assert total.attributes["energi_kwh"] == 309.574
    assert total.attributes["energi_kwh_dele"] == {ENERGY: 189.574, "offentlig_ladning": 120.0}
    # The total follows the energy sensor.
    energy(hass, "200")
    await hass.async_block_till_done()
    assert state(hass, TOTAL) == str(round(1.59 * 320, 2))
    await add(hass, kwh=30.5, pris=150.25)
    await hass.async_block_till_done()
    assert state(hass, PUB) == "150.5" and state(hass, PAID) == "690.25"


async def test_total_unavailable_when_an_energy_sensor_is(hass, dk_time, http):
    energy(hass, "unavailable")
    await setup(hass, http, month_records("2026-11"), energy_entity=ENERGY)
    await add(hass, kwh=120, pris=540)
    await hass.async_block_till_done()
    assert state(hass, PUB_SUR) == "190.8"
    assert state(hass, TOTAL) == "unavailable"


async def test_charge_in_last_month(hass, dk_time, http):
    hass.states.async_set(
        ENERGY,
        "189.574",
        {
            "unit_of_measurement": "kWh",
            "device_class": "energy",
            "last_reset": "2026-10-31T23:00:00+00:00",
            "last_period": "264.206",
        },
    )
    await setup(hass, http, two_months(), energy_entity=ENERGY)
    resp = await add(hass, kwh=80, pris=320, dato="2026-10-20")
    await hass.async_block_till_done()
    assert resp["maaned"] == "2026-10" and resp["dato"] == "2026-10-20"
    assert state(hass, PUB) == "0" and state(hass, PUB_LAST) == "80.0"
    assert state(hass, PUB_SUR_LAST) == str(round(0.62 * 80, 2))
    assert state(hass, PAID_LAST) == "320.0" and state(hass, PAID) == "0"
    assert state(hass, SAVING_LAST) == str(round(320 - 0.62 * 80, 2))
    assert state(hass, TOTAL_LAST) == str(round(0.62 * (264.206 + 80), 2))
    assert state(hass, TOTAL) == str(round(1.59 * 189.574, 2))


async def test_remove(hass, dk_time, http):
    await setup(hass, http, month_records("2026-11"))
    first = await add(hass, kwh=120, pris=540)
    await add(hass, kwh=10, pris=45, dato="2026-11-02")  # added last, stopped earlier
    removed = await remove(hass)
    assert removed["kwh"] == 10.0  # the most recently added, not the latest time
    await hass.async_block_till_done()
    assert state(hass, PUB) == "120.0"
    with pytest.raises(ServiceValidationError):
        await remove(hass, id="findesikke")
    assert (await remove(hass, id=first["id"]))["kwh"] == 120.0
    await hass.async_block_till_done()
    assert state(hass, PUB) == "0"
    with pytest.raises(ServiceValidationError):
        await remove(hass)


@pytest.mark.parametrize("kwh", [0, -5, 1001, "x"])
async def test_invalid_kwh(hass, dk_time, http, kwh):
    await setup(hass, http, month_records("2026-11"))
    with pytest.raises(vol.Invalid):
        await add(hass, kwh=kwh, pris=10)


@pytest.mark.parametrize("data", [{"kwh": 10}, {"kwh": 10, "pris": -1}, {"kwh": 10, "pris": "x"}])
async def test_price_required_and_valid(hass, dk_time, http, data):
    await setup(hass, http, month_records("2026-11"))
    with pytest.raises(vol.Invalid):
        await add(hass, **data)


async def test_free_charge_is_allowed(hass, dk_time, http):
    await setup(hass, http, month_records("2026-11"))
    await add(hass, kwh=20, pris=0)
    await hass.async_block_till_done()
    assert state(hass, PAID) == "0.0" and state(hass, SAVING) == str(round(-1.59 * 20, 2))


async def test_future_time_rejected(hass, dk_time, http):
    await setup(hass, http, month_records("2026-11"))
    with pytest.raises(ServiceValidationError):
        await add(hass, kwh=10, pris=10, dato="2026-11-07")


async def test_not_loaded(hass, dk_time, http):
    entry = await setup(hass, http, month_records("2026-11"))
    await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(ServiceValidationError):
        await add(hass, kwh=10, pris=10)


async def test_survives_restart(hass, dk_time, http, hass_storage):
    entry = await setup(hass, http, month_records("2026-11"))
    await add(hass, kwh=120, pris=540, note="Tur")
    key = f"{DOMAIN}.{entry.entry_id}.offentlig_ladning"
    assert hass_storage[key]["data"]["ladninger"][0]["kwh"] == 120.0
    http.respond(body(month_records("2026-11")))
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert state(hass, PUB) == "120.0"
    assert hass.states.get(PUB).attributes["ladninger"][0]["note"] == "Tur"
    assert state(hass, PAID) == "540.0"


async def test_month_change_moves_charges_to_last_month(hass, freezer, http):
    await hass.config.async_set_time_zone("Europe/Copenhagen")
    freezer.move_to(local(2026, 11, 30, 20, 0))
    await setup(hass, http, month_records("2026-11"))
    await add(hass, kwh=120, pris=540)
    await hass.async_block_till_done()
    assert state(hass, PUB) == "120.0"
    rate_nov = float(state(hass, "sensor.clever_energitillaeg_foreloebig_sats"))
    http.respond(body(month_records("2026-11")))
    await at(hass, freezer, local(2026, 12, 1, 0, 0))
    assert state(hass, PUB) == "0" and state(hass, PUB_LAST) == "120.0"
    assert hass.states.get(PUB).attributes["last_reset"].startswith("2026-12-01T00:00:00+01:00")
    # Before the 00:05 fetch November is not "last month" in the data yet: unavailable, never 0.
    assert state(hass, PUB_SUR_LAST) == "unavailable" and state(hass, PUB_SUR) == "unavailable"
    await at(hass, freezer, local(2026, 12, 1, 0, 5))
    assert state(hass, PUB_SUR_LAST) == str(round(rate_nov * 120, 2))
    assert state(hass, TOTAL_LAST) == str(round(rate_nov * 120, 2))
    assert state(hass, PAID_LAST) == "540.0" and state(hass, PAID) == "0"
    assert state(hass, SAVING_LAST) == str(round(540 - rate_nov * 120, 2))


WITH = "sensor.clever_energitillaeg_med_clever"
WITHOUT = "sensor.clever_energitillaeg_uden_clever"
DIFF = "sensor.clever_energitillaeg_forskel_med_clever"
COST = "sensor.hjemmeladning_pris_maaned"


async def test_comparison_this_month_fixed_home_price(hass, dk_time, http):
    energy(hass, "189.574")
    await setup(hass, http, month_records("2026-11"), energy_entity=ENERGY, home_price=1.2)
    await add(hass, kwh=120, pris=540)
    await hass.async_block_till_done()
    surcharge = round(1.59 * (189.574 + 120), 2)
    med = round(849 + surcharge, 2)
    uden = round(round(1.2 * 189.574, 2) + 540, 2)
    assert state(hass, WITH) == str(med)
    assert state(hass, WITHOUT) == str(uden)
    diff = hass.states.get(DIFF)
    assert diff.state == str(round(uden - med, 2))
    a = diff.attributes
    assert a["billigst"] == "Uden Clever" and a["abonnement"] == 849.0
    assert a["energitillaeg"] == surcharge and a["offentlig_ladning_betalt"] == 540.0
    assert a["hjemme_kwh"] == 189.574 and a["hjemmeladning_pris"] == round(1.2 * 189.574, 2)
    assert a["hjemmeladning_kilde"] == "fast kr./kWh" and a["mangler"] is None
    assert "Clever Power" in a["note"]


async def test_comparison_needs_home_price_when_home_is_tracked(hass, dk_time, http):
    energy(hass, "189.574")
    await setup(hass, http, month_records("2026-11"), energy_entity=ENERGY)
    assert state(hass, WITH) == str(round(849 + round(1.59 * 189.574, 2), 2))
    assert state(hass, WITHOUT) == "unavailable" and state(hass, DIFF) == "unavailable"


async def test_comparison_with_cost_sensor(hass, dk_time, http):
    energy(hass, "189.574")
    attrs = {"unit_of_measurement": "kr", "last_reset": "2026-10-31T23:00:00+00:00"}
    hass.states.async_set(COST, "210.5", attrs)
    await setup(
        hass,
        http,
        month_records("2026-11"),
        energy_entity=ENERGY,
        home_cost_entity=COST,
        home_price=9.99,  # ignored when a sensor is chosen
    )
    await add(hass, kwh=120, pris=540)
    await hass.async_block_till_done()
    assert state(hass, WITHOUT) == str(round(210.5 + 540, 2))
    hass.states.async_set(COST, "300", attrs)
    await hass.async_block_till_done()
    assert state(hass, WITHOUT) == "840.0"
    hass.states.async_set(COST, "300", attrs | {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()
    assert state(hass, WITHOUT) == "unavailable"
    hass.states.async_set(COST, "300", attrs | {"last_reset": "2026-09-30T22:00:00+00:00"})
    await hass.async_block_till_done()
    assert state(hass, WITHOUT) == "unavailable"


async def test_comparison_without_home_tracking_custom_subscription(hass, dk_time, http):
    await setup(hass, http, month_records("2026-11"), subscription=100)
    await add(hass, kwh=120, pris=900)
    await hass.async_block_till_done()
    assert state(hass, WITH) == str(round(100 + 190.8, 2))
    assert state(hass, WITHOUT) == "900.0"
    diff = hass.states.get(DIFF)
    assert diff.state == str(round(900 - 290.8, 2)) and diff.attributes["billigst"] == "Clever"


async def test_comparison_unavailable_without_energy(hass, dk_time, http):
    energy(hass, "unavailable")
    await setup(hass, http, month_records("2026-11"), energy_entity=ENERGY, home_price=1.2)
    assert state(hass, WITH) == "unavailable" and state(hass, DIFF) == "unavailable"
    assert state(hass, WITHOUT) == "unavailable"


async def test_comparison_last_month(hass, dk_time, http):
    hass.states.async_set(
        ENERGY,
        "189.574",
        {
            "unit_of_measurement": "kWh",
            "last_reset": "2026-10-31T23:00:00+00:00",
            "last_period": "264.206",
        },
    )
    hass.states.async_set(
        COST,
        "100",
        {
            "unit_of_measurement": "DKK",
            "last_reset": "2026-10-31T23:00:00+00:00",
            "last_period": "310.25",
        },
    )
    await setup(hass, http, two_months(), energy_entity=ENERGY, home_cost_entity=COST)
    await add(hass, kwh=80, pris=320, dato="2026-10-20")
    await hass.async_block_till_done()
    med = round(849 + round(0.62 * (264.206 + 80), 2), 2)
    uden = round(310.25 + 320, 2)
    assert state(hass, WITH + "_sidste_maaned") == str(med)
    assert state(hass, WITHOUT + "_sidste_maaned") == str(uden)
    assert state(hass, DIFF + "_sidste_maaned") == str(round(uden - med, 2))
