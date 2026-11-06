"""Preliminary Clever energy surcharge from Energinet day-ahead prices."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EnergiDataServiceApi
from .coordinator import CleverCoordinator

PLATFORMS = [Platform.SENSOR]
type CleverConfigEntry = ConfigEntry[CleverCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: CleverConfigEntry) -> bool:
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
