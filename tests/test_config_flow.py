from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.clever_energitillaeg.const import DOMAIN

from .conftest import body, make_entry, month_records


async def test_user_flow_defaults_and_single_instance(hass, dk_time, http):
    http.respond(body(month_records("2026-11")))
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"threshold": 0.89, "vat_percent": 25.0}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {"threshold": 0.89, "vat_percent": 25.0}
    await hass.async_block_till_done()
    again = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert again["type"] is FlowResultType.ABORT


async def test_user_flow_with_energy_entity(hass, dk_time, http):
    http.respond(body(month_records("2026-11")))
    hass.states.async_set("sensor.e", "1", {"device_class": "energy", "unit_of_measurement": "kWh"})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"energy_entities": ["sensor.e", "sensor.f"], "threshold": 0.89, "vat_percent": 25.0},
    )
    assert result["options"]["energy_entities"] == ["sensor.e", "sensor.f"]


async def test_options_flow_set_and_clear_energy_entity(hass, dk_time, http):
    http.respond(body(month_records("2026-11")))
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"energy_entities": ["sensor.e"], "threshold": 0.95, "vat_percent": 25.0}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {
        "energy_entities": ["sensor.e"],
        "threshold": 0.95,
        "vat_percent": 25.0,
    }
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"threshold": 0.95, "vat_percent": 25.0}
    )
    await hass.async_block_till_done()
    assert "energy_entities" not in entry.options
