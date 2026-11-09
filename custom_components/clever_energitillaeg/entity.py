"""Shared entity base."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, NAME, OBJECT_IDS
from .coordinator import CleverCoordinator


class CleverEntity(CoordinatorEntity[CleverCoordinator]):
    _platform = "sensor"
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: CleverCoordinator, key: str, object_id: str | None = None):
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        if object_id is None:
            self._attr_translation_key = key
            object_id = OBJECT_IDS[key]
        # Danish entity ids regardless of the HA language (æ/ø spelled ae/oe).
        self.entity_id = f"{self._platform}.{DOMAIN}_{object_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            manufacturer="Energinet (data)",
            model="Foreløbigt energitillæg",
            entry_type=DeviceEntryType.SERVICE,
        )
