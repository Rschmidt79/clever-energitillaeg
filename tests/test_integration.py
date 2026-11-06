"""Config entry, coordinator, scheduling and sensors in a real HA instance."""

import asyncio
from datetime import timedelta

import pytest
from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

from custom_components.clever_energitillaeg.const import API_URL

from .conftest import body, local, make_entry, month_records

ENERGY = "sensor.monthly_energy"


def ids(hass):
    reg = er.async_get(hass)
    out = {}
    for e in reg.entities.values():
        if e.platform == "clever_energitillaeg":
            key = e.unique_id.split("_", 1)[1]
            out["surcharge" if key == f"surcharge_{ENERGY}" else key] = e.entity_id
    return out


async def setup(hass, http, payload=None, **options):
    if payload is not None:
        http.respond(body(payload))
    entry = make_entry(**options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def at(hass, freezer, moment):
    moment = moment + timedelta(seconds=61)  # past the per-install second offset
    freezer.move_to(moment)
    async_fire_time_changed(hass, moment)
    await hass.async_block_till_done()


def energy(hass, kwh, last_reset="2026-10-31T23:00:00+00:00", unit="kWh"):
    attrs = {
        "unit_of_measurement": unit,
        "device_class": "energy",
        "state_class": "total_increasing",
    }
    if last_reset:
        attrs["last_reset"] = last_reset
    hass.states.async_set(ENERGY, kwh, attrs)


async def test_setup_current_month(hass, dk_time, http):
    energy(hass, "189.574")
    entry = await setup(hass, http, month_records("2026-11"), energy_entity=ENERGY)
    assert entry.state is ConfigEntryState.LOADED
    e = ids(hass)
    rate = hass.states.get(e["rate"])
    a = rate.attributes
    assert rate.state == "1.59" and a["status"] == "ok" and a["maaned"] == "2026-11"
    assert a["dage_indgaar"] == [f"2026-11-{d:02d}" for d in range(1, 8)]
    assert (
        a["medtager_dage_efter_i_dag"] is True
        and a["afventer_dage"] == 23
        and a["manglende_dage"] == []
    )
    assert a["sats_raa"] == 1.5943 and "månedens afslutning" in a["note"]
    assert hass.states.get(e["national_average"]).state == "2.4843"
    assert hass.states.get(e["average_dk1"]).state == "2.4147"
    assert hass.states.get(e["average_dk2"]).state == "2.554"
    assert hass.states.get(e["last_fetch"]).state.startswith("2026-11-06T08:00")
    assert hass.states.get(e["surcharge"]).state == str(round(1.59 * 189.574, 2))
    q = str(http.calls[0][1])
    assert "start=2026-11-01T00:00" in q and "end=2026-12-01T00:00" in q and "limit=0" in q
    energy(hass, "200")
    await hass.async_block_till_done()
    assert hass.states.get(e["surcharge"]).state == "318.0" and len(http.calls) == 1


async def test_no_energy_entity_no_surcharge_sensor(hass, dk_time, http):
    await setup(hass, http, month_records("2026-11"))
    assert "surcharge" not in ids(hass)


@pytest.mark.parametrize(
    "state,reset,unit,expected",
    [
        ("unavailable", "2026-10-31T23:00:00+00:00", "kWh", "unavailable"),
        ("unknown", "2026-10-31T23:00:00+00:00", "kWh", "unavailable"),
        ("12", None, "kWh", "unavailable"),
        ("12", "2026-09-30T22:00:00+00:00", "kWh", "unavailable"),
        ("12", "2026-10-31T23:00:00+00:00", "W", "unavailable"),
        ("12000", "2026-10-31T23:00:00+00:00", "Wh", "19.08"),
        ("0", "2026-10-31T23:00:00+00:00", "kWh", "0.0"),
    ],
)
async def test_energy_sensor_states(hass, dk_time, http, state, reset, unit, expected):
    energy(hass, state, reset, unit)
    await setup(hass, http, month_records("2026-11"), energy_entity=ENERGY)
    assert hass.states.get(ids(hass)["surcharge"]).state == expected


@pytest.mark.parametrize("kind", ["http500", "http400", "timeout", "client", "html", "empty"])
async def test_failed_fetch_keeps_last_good_value(hass, dk_time, http, kind):
    energy(hass, "100")
    await setup(hass, http, month_records("2026-11"), energy_entity=ENERGY)
    e = ids(hass)
    good = hass.states.get(e["rate"])
    {
        "http500": lambda: http.respond({"statusCode": 500}, status=500),
        "http400": lambda: http.respond({"statusCode": 400}, status=400),
        "timeout": lambda: http.respond(exc=TimeoutError()),
        "client": lambda: http.respond(exc=ClientError()),
        "html": lambda: http.respond(text="<html>maintenance</html>"),
        "empty": lambda: http.respond(body([])),
    }[kind]()
    await at(hass, dk_time, local(2026, 11, 7, 14, 30))
    s = hass.states.get(e["rate"])
    assert s.state == good.state and s.attributes["status"] == "fejl"
    assert s.attributes["hentet"] == good.attributes["hentet"]
    assert s.attributes["sidste_forsoeg"].startswith("2026-11-07T14:31")
    assert hass.states.get(e["surcharge"]).state == "159.0"
    # Evening retry because today's fetch failed.
    http.respond(body(month_records("2026-11")))
    await at(hass, dk_time, local(2026, 11, 7, 18, 30))
    assert hass.states.get(e["rate"]).attributes["status"] == "ok" and len(http.calls) == 1


async def test_failure_without_previous_value_is_unknown(hass, dk_time, http):
    energy(hass, "100")
    http.respond(exc=ClientError())
    entry = await setup(hass, http, energy_entity=ENERGY)
    assert entry.state is ConfigEntryState.LOADED
    e = ids(hass)
    s = hass.states.get(e["rate"])
    assert s.state == "unknown" and s.attributes["status"] == "fejl"
    assert hass.states.get(e["national_average"]).state == "unknown"
    assert hass.states.get(e["surcharge"]).state == "unavailable"


async def test_no_complete_day_is_unknown(hass, dk_time, http):
    await setup(
        hass, http, month_records("2026-11", lambda r: [x for x in r if x["PriceArea"] == "DK1"])
    )
    s = hass.states.get(ids(hass)["rate"])
    assert s.state == "unknown" and s.attributes["status"] == "ingen_data"


async def test_rate_limit_retried_once(hass, dk_time, http):
    calls = []

    async def side(method, url, data):
        calls.append(url)
        status = 429 if len(calls) == 1 else 200
        return AiohttpClientMockResponse(
            method,
            url,
            status=status,
            json=body(month_records("2026-11")),
            headers={"content-type": "application/json"},
        )

    http.mock.clear_requests()
    http.mock.get(API_URL, side_effect=side)
    entry = make_entry()
    entry.add_to_hass(hass)
    task = hass.async_create_task(hass.config_entries.async_setup(entry.entry_id))
    for _ in range(20):
        await asyncio.sleep(0)
    assert len(calls) == 1 and not task.done()
    moment = local(2026, 11, 6, 9, 1, 20)
    dk_time.move_to(moment)
    async_fire_time_changed(hass, moment)
    assert await task
    await hass.async_block_till_done()
    assert len(calls) == 2
    assert hass.states.get(ids(hass)["rate"]).attributes["status"] == "ok"


async def test_schedule_retry_skipped_and_month_start(hass, dk_time, http):
    await setup(hass, http, month_records("2026-11"))
    await at(hass, dk_time, local(2026, 11, 6, 14, 30))
    assert len(http.calls) == 2  # setup + daily
    await at(hass, dk_time, local(2026, 11, 6, 18, 30))
    await at(hass, dk_time, local(2026, 11, 7, 0, 5))
    assert len(http.calls) == 2  # retry skipped after success, 00:05 only on the 1st


async def test_month_change(hass, freezer, http):
    await hass.config.async_set_time_zone("Europe/Copenhagen")
    freezer.move_to(local(2026, 10, 31, 9, 0))
    energy(hass, "1141.267", "2026-09-30T22:00:00+00:00")
    await setup(hass, http, month_records("2026-10"), energy_entity=ENERGY)
    e = ids(hass)
    assert hass.states.get(e["rate"]).state == "0.62"
    assert hass.states.get(e["surcharge"]).state == str(round(0.62 * 1141.267, 2))
    # Midnight: the month changes before the new fetch -> never October's rate.
    await at(hass, freezer, local(2026, 11, 1, 0, 0))
    energy(hass, "0.0", "2026-10-31T23:00:00+00:00")
    await hass.async_block_till_done()
    assert hass.states.get(e["surcharge"]).state == "unavailable"
    http.respond(
        body(month_records("2026-11", lambda r: [x for x in r if x["TimeDK"] < "2026-11-03"]))
    )
    await at(hass, freezer, local(2026, 11, 1, 0, 5))
    s = hass.states.get(e["rate"])
    assert s.attributes["maaned"] == "2026-11" and s.attributes["dage_indgaar"] == [
        "2026-11-01",
        "2026-11-02",
    ]
    assert "start=2026-11-01T00:00" in str(http.calls[-1][1])
    assert hass.states.get(e["surcharge"]).state == "0.0"


async def test_failed_fetch_in_new_month_drops_old_value(hass, freezer, http):
    await hass.config.async_set_time_zone("Europe/Copenhagen")
    freezer.move_to(local(2026, 10, 31, 9, 0))
    await setup(hass, http, month_records("2026-10"))
    http.respond({"statusCode": 503}, status=503)
    await at(hass, freezer, local(2026, 11, 1, 0, 5))
    s = hass.states.get(ids(hass)["rate"])
    assert s.state == "unknown" and s.attributes["maaned"] == "2026-11"


async def test_restart_with_failed_fetch_uses_stored_month(hass, dk_time, http, hass_storage):
    entry = await setup(hass, http, month_records("2026-11"))
    good = hass.states.get(ids(hass)["rate"]).state
    assert await hass.config_entries.async_unload(entry.entry_id)
    http.respond(exc=ClientError())
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    s = hass.states.get(ids(hass)["rate"])
    assert s.state == good and s.attributes["status"] == "fejl"


async def test_options_change_reloads_and_recalculates(hass, dk_time, http):
    entry = await setup(hass, http, month_records("2026-11"))
    http.respond(body(month_records("2026-11")))
    hass.config_entries.async_update_entry(entry, options={"threshold": 1.0, "vat_percent": 25.0})
    await hass.async_block_till_done()
    s = hass.states.get(ids(hass)["rate"])
    assert s.state == str(round(1.5943 + 0.89 - 1.0, 2)) and s.attributes["grundsats"] == 1.0


async def test_saved_production_response(hass, dk_time, http):
    import json

    from .conftest import FIXTURES

    raw = json.loads((FIXTURES / "prod_query_2026-11.json").read_text())
    http.respond(raw)
    await setup(hass, http)
    assert hass.states.get(ids(hass)["rate"]).state == "1.59"


async def test_diagnostics(hass, dk_time, http):
    from custom_components.clever_energitillaeg.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    entry = await setup(hass, http, month_records("2026-11"))
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["status"] == "ok" and diag["result"]["rate"] == 1.59
    assert diag["options"] == {"threshold": 0.89, "vat_percent": 25.0}


async def test_danish_entity_ids_and_names(hass, dk_time, http):
    energy(hass, "10")
    await setup(hass, http, month_records("2026-11"), energy_entity=ENERGY)
    e = ids(hass)
    assert e == {
        "rate": "sensor.clever_energitillaeg_foreloebig_sats",
        "national_average": "sensor.clever_energitillaeg_landsgennemsnit",
        "average_dk1": "sensor.clever_energitillaeg_gennemsnit_dk1",
        "average_dk2": "sensor.clever_energitillaeg_gennemsnit_dk2",
        "last_fetch": "sensor.clever_energitillaeg_seneste_hentning",
        "surcharge": "sensor.clever_energitillaeg_foreloebigt_energitillaeg_monthly_energy",
    }
    rate = hass.states.get(e["rate"])
    assert rate.attributes["friendly_name"] == "Clever energitillæg Foreløbig sats"
    assert hass.states.get(e["surcharge"]).attributes["friendly_name"] == (
        "Clever energitillæg Foreløbigt energitillæg – monthly_energy"
    )
    assert rate.attributes["unit_of_measurement"] == "kr./kWh"
    t = hass.states.get(e["surcharge"])
    assert t.attributes["unit_of_measurement"] == "kr." and t.attributes["energisensor"] == ENERGY


async def test_migrates_0_1_0_entry_ids_and_single_sensor(hass, dk_time, http):
    """0.1.0: config version 1, one energy_entity, English entity ids -> Danish, history kept."""
    from custom_components.clever_energitillaeg.const import OLD_OBJECT_IDS

    entry = make_entry(version=1, energy_entity=ENERGY)
    entry.add_to_hass(hass)
    reg = er.async_get(hass)
    for key, old in OLD_OBJECT_IDS.items():
        reg.async_get_or_create(
            "sensor",
            "clever_energitillaeg",
            f"{entry.entry_id}_{key}",
            suggested_object_id=f"clever_energitillaeg_{old}",
            config_entry=entry,
        )
    old_surcharge = reg.async_get("sensor.clever_energitillaeg_preliminary_surcharge")
    # A user-chosen id is left alone.
    reg.async_update_entity(
        "sensor.clever_energitillaeg_average_dk2", new_entity_id="sensor.mit_eget_navn"
    )
    energy(hass, "10")
    http.respond(body(month_records("2026-11")))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.version == 2 and entry.options == {
        "threshold": 0.89,
        "vat_percent": 25.0,
        "energy_entities": [ENERGY],
    }
    e = ids(hass)
    assert e["rate"] == "sensor.clever_energitillaeg_foreloebig_sats"
    assert e["surcharge"] == "sensor.clever_energitillaeg_foreloebigt_energitillaeg_monthly_energy"
    assert e["average_dk2"] == "sensor.mit_eget_navn"
    # Same registry entry (renamed, not recreated): the recorder keeps its history.
    assert reg.async_get(e["surcharge"]).id == old_surcharge.id
    assert len([x for x in reg.entities.values() if x.platform == "clever_energitillaeg"]) == 6
    assert hass.states.get("sensor.clever_energitillaeg_foreloebig_sats").state == "1.59"
    assert hass.states.get(e["surcharge"]).state == "15.9"
    assert hass.states.get("sensor.clever_energitillaeg_preliminary_rate") is None


async def test_migrates_0_1_0_entry_without_energy_sensor(hass, dk_time, http):
    entry = make_entry(version=1)
    entry.add_to_hass(hass)
    http.respond(body(month_records("2026-11")))
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.version == 2 and entry.options["energy_entities"] == []


async def test_several_energy_sensors_each_get_a_surcharge(hass, dk_time, http):
    energy(hass, "100")
    hass.states.async_set(
        "sensor.bil_to",
        "50",
        {
            "unit_of_measurement": "kWh",
            "device_class": "energy",
            "friendly_name": "Bil to i måneden",
            "last_reset": "2026-10-31T23:00:00+00:00",
        },
    )
    entry = await setup(
        hass, http, month_records("2026-11"), energy_entities=[ENERGY, "sensor.bil_to"]
    )
    one = hass.states.get("sensor.clever_energitillaeg_foreloebigt_energitillaeg_monthly_energy")
    two = hass.states.get("sensor.clever_energitillaeg_foreloebigt_energitillaeg_bil_to")
    assert one.state == "159.0" and two.state == "79.5"
    assert two.attributes["friendly_name"] == (
        "Clever energitillæg Foreløbigt energitillæg – Bil to i måneden"
    )
    # Deselecting a sensor removes its surcharge entity (no orphan).
    http.respond(body(month_records("2026-11")))
    hass.config_entries.async_update_entry(
        entry, options=entry.options | {"energy_entities": ["sensor.bil_to"]}
    )
    await hass.async_block_till_done()
    reg = er.async_get(hass)
    assert (
        reg.async_get("sensor.clever_energitillaeg_foreloebigt_energitillaeg_monthly_energy")
        is None
    )
    assert (
        hass.states.get("sensor.clever_energitillaeg_foreloebigt_energitillaeg_bil_to").state
        == "79.5"
    )
