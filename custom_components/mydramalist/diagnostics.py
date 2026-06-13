from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    return {
        "config_entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "data": {
                "user_id": entry.data.get("user_id"),
                "api_url": entry.data.get("api_url"),
            },
        },
        "coordinator_data": coordinator.data,
        "last_update_success": coordinator.last_update_success,
        "last_update_error": str(coordinator.last_exception)
        if coordinator.last_exception
        else None,
    }
