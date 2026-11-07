"""Preliminary Clever energy surcharge from Energinet day-ahead prices."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EnergiDataServiceApi
from .const import (
    CONF_ENERGY_ENTITIES,
    CONF_ENERGY_ENTITY,
    DOMAIN,
    OBJECT_IDS,
    OLD_OBJECT_IDS,
    SURCHARGE_OBJECT_ID,
)
from .coordinator import CleverCoordinator

PLATFORMS = [Platform.SENSOR]
type CleverConfigEntry = ConfigEntry[CleverCoordinator]


def surcharge_key(energy_entity: str) -> str:
    return f"surcharge_{energy_entity}"


def surcharge_object_id(energy_entity: str) -> str:
    return f"{SURCHARGE_OBJECT_ID}_{energy_entity.split('.', 1)[-1]}"


def last_month_surcharge_key(energy_entity: str) -> str:
    return f"last_month_surcharge_{energy_entity}"


def last_month_surcharge_object_id(energy_entity: str) -> str:
    return f"energitillaeg_sidste_maaned_{energy_entity.split('.', 1)[-1]}"


async def async_migrate_entry(hass: HomeAssistant, entry: CleverConfigEntry) -> bool:
    """1 -> 2: one energy sensor becomes a list; its surcharge entity keeps its history."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        options = dict(entry.options)
        energy = options.pop(CONF_ENERGY_ENTITY, None) or entry.data.get(CONF_ENERGY_ENTITY)
        options[CONF_ENERGY_ENTITIES] = [energy] if energy else []
        if energy:
            registry = er.async_get(hass)
            if old := registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_surcharge"):
                registry.async_update_entity(
                    old, new_unique_id=f"{entry.entry_id}_{surcharge_key(energy)}"
                )
        hass.config_entries.async_update_entry(entry, options=options, version=2)
    return True


def _migrate_entity_ids(hass: HomeAssistant, entry: CleverConfigEntry) -> None:
    """0.1.0 got English entity ids; rename those (not user-chosen ones) to the Danish ids.

    Renaming in the registry keeps the recorder history.
    """
    registry = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(registry, entry.entry_id):
        key = ent.unique_id.removeprefix(f"{entry.entry_id}_")
        if key in OBJECT_IDS and key in OLD_OBJECT_IDS:
            old = f"sensor.{DOMAIN}_{OLD_OBJECT_IDS[key]}"
            new = f"sensor.{DOMAIN}_{OBJECT_IDS[key]}"
        elif key.startswith("surcharge_"):
            old = f"sensor.{DOMAIN}_{OLD_OBJECT_IDS['surcharge']}"
            new = f"sensor.{DOMAIN}_{surcharge_object_id(key.removeprefix('surcharge_'))}"
        else:
            continue
        if ent.entity_id == old and registry.async_get(new) is None:
            registry.async_update_entity(ent.entity_id, new_entity_id=new)


async def async_setup_entry(hass: HomeAssistant, entry: CleverConfigEntry) -> bool:
    _migrate_entity_ids(hass, entry)
    coordinator = CleverCoordinator(
        hass, entry, EnergiDataServiceApi(async_get_clientsession(hass))
    )
    await coordinator.async_load_stored()
    # A failed first fetch is not fatal: entities show unknown (never 0) until the next attempt.
    await coordinator.async_refresh()
    entry.runtime_data = coordinator
    coordinator.async_schedule()
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _options_updated(hass: HomeAssistant, entry: CleverConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: CleverConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
