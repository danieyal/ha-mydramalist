import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from mdl import AsyncMDLClient, MDLAuthError
from mdl.models.titles import Movie, MovieStatusType

from .const import (
    CATEGORY_COMPLETED,
    CATEGORY_DROPPED,
    CATEGORY_ON_HOLD,
    CATEGORY_PLAN_TO_WATCH,
    CATEGORY_WATCHING,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

CATEGORY_STATUSES = {
    CATEGORY_WATCHING: MovieStatusType.WATCHING,
    CATEGORY_COMPLETED: MovieStatusType.COMPLETED,
    CATEGORY_PLAN_TO_WATCH: MovieStatusType.PLAN_TO_WATCH,
    CATEGORY_ON_HOLD: MovieStatusType.ON_HOLD,
    CATEGORY_DROPPED: MovieStatusType.DROPPED,
}


def _normalize_item(movie: Movie) -> dict[str, Any]:
    title = movie.title
    return {
        "name": title.title if title else None,
        "id": title.id if title else None,
        "score": movie.rating,
        "episode_seen": movie.episode_seen,
        "episode_total": title.episodes if title else None,
    }


def _normalize_group(movies: list[Movie]) -> dict[str, Any]:
    # The sync endpoint flags removed entries rather than omitting them.
    movies = [movie for movie in movies if not movie.deleted]
    return {
        "items": [_normalize_item(movie) for movie in movies],
        "count": len(movies),
        "stats": {
            "episodes_seen": sum(movie.episode_seen or 0 for movie in movies),
        },
    }


def _normalize_data(lists: dict[str, list[Movie]]) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        category: _normalize_group(movies) for category, movies in lists.items()
    }
    normalized["total_count"] = sum(group["count"] for group in normalized.values())
    return normalized


class MyDramaListCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: AsyncMDLClient
    ) -> None:
        self.username: str = entry.data[CONF_USERNAME]
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{self.username}",
            update_interval=DEFAULT_UPDATE_INTERVAL,
            always_update=True,
        )
        self.client = client
        self._password: str = entry.data[CONF_PASSWORD]

    async def _async_login(self) -> None:
        await self.client.auth.login(self.username, self._password)

    async def _async_fetch_lists(self) -> dict[str, list[Movie]]:
        # Fetched sequentially: a concurrent 401 would make pymdl clear the token
        # that a re-login just stored.
        return {
            category: await self.client.watchlist.fetch(status)
            for category, status in CATEGORY_STATUSES.items()
        }

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            if self.client.tokens.get_token() is None:
                await self._async_login()
            try:
                lists = await self._async_fetch_lists()
            except MDLAuthError:
                # Access tokens expire and pymdl does not refresh them; log in again once.
                await self._async_login()
                lists = await self._async_fetch_lists()
        except MDLAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Authentication failed for '{self.username}': {err}"
            ) from err
        except Exception as err:
            raise UpdateFailed(
                f"Error fetching dramalist for '{self.username}': {err}"
            ) from err

        return _normalize_data(lists)
