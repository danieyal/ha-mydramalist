import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed

from mdl import AsyncMDLClient
from mdl.auth import generate_device_id

from .const import CONF_DEVICE_ID, CONF_USER_ID, DOMAIN, PLATFORMS
from .coordinator import MyDramaListCoordinator
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    async_setup_services(hass)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if CONF_PASSWORD not in entry.data:
        raise ConfigEntryAuthFailed("A MyDramaList password is required")

    client = AsyncMDLClient(device_id=entry.data[CONF_DEVICE_ID])

    coordinator = MyDramaListCoordinator(hass, entry, client)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.aclose()
        raise

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["client"].aclose()

    return unload_ok
