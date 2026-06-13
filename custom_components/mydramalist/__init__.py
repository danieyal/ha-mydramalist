import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from kuryana import AsyncKuryana

from .const import DEFAULT_API_URL, DOMAIN, PLATFORMS
from .coordinator import MyDramaListCoordinator
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api_url = entry.data.get("api_url", DEFAULT_API_URL)
    user_id = entry.data["user_id"]

    client = AsyncKuryana(base_url=api_url)

    coordinator = MyDramaListCoordinator(hass, client, user_id)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        await client.client.aclose()
        raise ConfigEntryNotReady(
            f"Failed to fetch dramalist data for user '{user_id}': {err}"
        ) from err

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
        await data["client"].client.aclose()

    if not hass.data[DOMAIN]:
        async_unload_services(hass)

    return unload_ok
