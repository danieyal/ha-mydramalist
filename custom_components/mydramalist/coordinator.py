from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from mdl import AsyncMDLClient, MDLAuthError, MDLError

from .const import (
    CALENDAR_RETENTION,
    CALENDAR_UPDATE_INTERVAL,
    CATEGORY_STATUSES,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .data import (
    Airing,
    MyDramaListConfigEntry,
    MyDramaListData,
    UserData,
    airings_from_calendar,
    normalize_list,
    normalize_stats,
)

_LOGGER = logging.getLogger(__name__)


class MyDramaListCoordinator(DataUpdateCoordinator[MyDramaListData]):
    """Polls the signed-in user's lists, watch stats and unread counts."""

    config_entry: MyDramaListConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: MyDramaListConfigEntry, client: AsyncMDLClient
    ) -> None:
        self.username: str = entry.data[CONF_USERNAME]
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{self.username}",
            update_interval=timedelta(
                minutes=entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
            ),
            always_update=False,
        )
        self.client = client
        self._password: str = entry.data[CONF_PASSWORD]
        self._user: UserData | None = None

    async def _async_login(self) -> None:
        await self.client.auth.login(self.username, self._password)

    async def _async_update_data(self) -> MyDramaListData:
        try:
            if self.client.tokens.get_token() is None:
                await self._async_login()
            try:
                return await self._async_fetch()
            except MDLAuthError:
                # pymdl refreshes an expired token itself; this only runs once the
                # refresh token is rejected too.
                await self._async_login()
                return await self._async_fetch()
        except MDLAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="auth_failed",
                translation_placeholders={"username": self.username, "error": str(err)},
            ) from err
        except MDLError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"username": self.username, "error": str(err)},
            ) from err

    async def _async_fetch(self) -> MyDramaListData:
        if self._user is None:
            profile = await self.client.account.get_profile()
            self._user = UserData(
                # The login name may differ from the profile's username (an email, say),
                # and /users/{id}/stats needs the latter.
                username=profile.username or self.username,
                display_name=profile.display_name,
                avatar=profile.images.thumb if profile.images else None,
            )

        previous = self.data
        activity = await self.client.watchlist.get_last_activities()
        if previous and activity.all and activity.all == previous.last_activity:
            lists = previous.lists
        else:
            # Sequential on purpose: one client and one token are shared by all calls.
            lists = {
                category: normalize_list(await self.client.watchlist.fetch(status))
                for category, status in CATEGORY_STATUSES.items()
            }

        return MyDramaListData(
            lists=lists,
            user=self._user,
            last_activity=activity.all,
            stats=await self._async_optional(
                "watch stats", self._async_fetch_stats, previous and previous.stats
            ),
            unread=await self._async_optional(
                "notifications", self._async_fetch_unread, previous and previous.unread
            ),
        )

    async def _async_fetch_stats(self) -> dict[str, Any]:
        assert self._user is not None
        return normalize_stats(await self.client.users.get_user_stats(self._user.username))

    async def _async_fetch_unread(self) -> dict[str, int]:
        response = await self.client.notifications.fetch(page=1, limit=1)
        return {
            "notifications": response.total or 0,
            "friend_requests": response.friends or 0,
            "messages": response.messages or 0,
        }

    async def _async_optional(self, what: str, fetch: Any, fallback: Any) -> Any:
        """Fetch data the lists do not depend on, keeping the last value on failure."""
        try:
            return await fetch()
        except MDLAuthError:
            raise
        except MDLError as err:
            _LOGGER.debug("Could not fetch MyDramaList %s: %s", what, err)
            return fallback or None


class MyDramaListCalendarCoordinator(DataUpdateCoordinator[list[Airing]]):
    """Polls the site-wide airing schedule (a rolling week, starting yesterday UTC).

    Each poll is merged with earlier ones so airings that have left the API's window
    stay on the calendar for a while.
    """

    config_entry: MyDramaListConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: MyDramaListConfigEntry, client: AsyncMDLClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.data[CONF_USERNAME]}_calendar",
            update_interval=CALENDAR_UPDATE_INTERVAL,
            always_update=False,
        )
        self.client = client

    async def _async_update_data(self) -> list[Airing]:
        try:
            calendar = await self.client.calendar.episodes()
        except MDLError as err:
            # The schedule needs no login; leave re-authentication to the list
            # coordinator.
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="calendar_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        fresh = airings_from_calendar(calendar)
        if not fresh:
            return self.data or []
        window_start = fresh[0].start
        cutoff = dt_util.utcnow() - CALENDAR_RETENTION
        fresh_uids = {airing.uid for airing in fresh}
        # Keep earlier airings from before the new window; inside it, the API is
        # authoritative (an episode that moved or was dropped must not linger).
        kept = [
            airing
            for airing in self.data or []
            if cutoff <= airing.start < window_start and airing.uid not in fresh_uids
        ]
        return kept + fresh
