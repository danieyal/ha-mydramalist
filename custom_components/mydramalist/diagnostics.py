from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .data import MyDramaListConfigEntry

TO_REDACT = {CONF_PASSWORD, CONF_EMAIL}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MyDramaListConfigEntry
) -> dict[str, Any]:
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    calendar = runtime.calendar
    data = coordinator.data

    return {
        "config_entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "coordinator_data": async_redact_data(asdict(data), TO_REDACT) if data else None,
        "last_update_success": coordinator.last_update_success,
        "last_update_error": str(coordinator.last_exception)
        if coordinator.last_exception
        else None,
        "calendar": {
            "airings": len(calendar.data or []),
            "first": calendar.data[0].start.isoformat() if calendar.data else None,
            "last": calendar.data[-1].start.isoformat() if calendar.data else None,
            "last_update_success": calendar.last_update_success,
        },
    }
