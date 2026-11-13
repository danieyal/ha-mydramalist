from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL, add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from mdl import AsyncMDLClient
from mdl.auth import generate_device_id

from .const import (
    CARD_FILENAME,
    CONF_DEVICE_ID,
    CONF_USER_ID,
    DOMAIN,
    FRONTEND_URL,
    PLATFORMS,
    VERSION,
)
from .coordinator import MyDramaListCalendarCoordinator, MyDramaListCoordinator
from .data import MyDramaListConfigEntry, MyDramaListRuntimeData
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_setup_services(hass)
    await _async_register_cards(hass)
    return True


async def _async_register_cards(hass: HomeAssistant) -> None:
    """Serve the bundled Lovelace cards and load them on every dashboard."""
    if hass.http is None:
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL, str(Path(__file__).parent / "frontend"), True)]
    )
    # The frontend is an after-dependency: present with default_config, absent in
    # minimal setups, where the card can still be added as a dashboard resource.
    if DATA_EXTRA_MODULE_URL in hass.data:
        add_extra_js_url(hass, f"{FRONTEND_URL}/{CARD_FILENAME}?v={VERSION}")


async def async_migrate_entry(hass: HomeAssistant, entry: MyDramaListConfigEntry) -> bool:
    if entry.version == 1:
        # Version 1 read a public dramalist through Kuryana. The MyDramaList app API
        # only serves the logged-in user's lists, so keep the profile slug as the
        # username and let the reauth flow collect the password.
        hass.config_entries.async_update_entry(
            entry,
            data={
                CONF_USERNAME: entry.data[CONF_USER_ID],
                CONF_DEVICE_ID: generate_device_id(),
            },
            version=2,
        )
        _LOGGER.info("Migrated MyDramaList entry %s to version 2", entry.entry_id)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: MyDramaListConfigEntry) -> bool:
    if CONF_PASSWORD not in entry.data:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="password_required"
        )

    client = AsyncMDLClient(device_id=entry.data[CONF_DEVICE_ID])
    coordinator = MyDramaListCoordinator(hass, entry, client)
    calendar = MyDramaListCalendarCoordinator(hass, entry, client)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.aclose()
        raise
    # The schedule is optional: a failure leaves the calendar empty until the next poll.
    await calendar.async_refresh()

    entry.runtime_data = MyDramaListRuntimeData(
        client=client, coordinator=coordinator, calendar=calendar
    )
    entry.async_on_unload(client.aclose)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: MyDramaListConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
