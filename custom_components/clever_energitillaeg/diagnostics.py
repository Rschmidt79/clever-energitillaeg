"""Diagnostics: configuration and the current calculation (no personal data)."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import CleverConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CleverConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "options": dict(entry.options),
        "status": data.status if data else None,
        "month": data.month if data else None,
        "error": data.error if data else None,
        "http_status": data.http_status if data else None,
        "fetched": data.fetched.isoformat() if data and data.fetched else None,
        "last_attempt": data.last_attempt.isoformat() if data else None,
        "result": data.result.as_dict() if data and data.result else None,
        "last_update_success": coordinator.last_update_success,
    }
