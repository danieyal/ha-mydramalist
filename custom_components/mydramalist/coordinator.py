import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from kuryana import AsyncKuryana
from kuryana.types.user import UserDataList, UserDataListGroup, UserDataListItem, UserQuery

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

_MODEL_KEY_MAP = {
    "Completed": CATEGORY_COMPLETED,
    "Plan_to_Watch": CATEGORY_PLAN_TO_WATCH,
    "Plan to Watch": CATEGORY_PLAN_TO_WATCH,
    "On_hold": CATEGORY_ON_HOLD,
    "On-hold": CATEGORY_ON_HOLD,
    "On Hold": CATEGORY_ON_HOLD,
    "Dropped": CATEGORY_DROPPED,
    "Watching": CATEGORY_WATCHING,
    "Currently Watching": CATEGORY_WATCHING,
    "Currently-Watching": CATEGORY_WATCHING,
}


def _normalize_item(item: UserDataListItem) -> dict[str, Any]:
    return {
        "name": item.name,
        "id": item.id,
        "score": item.score,
        "episode_seen": item.episode_seen,
        "episode_total": item.episode_total,
    }


def _normalize_group(group: UserDataListGroup) -> dict[str, Any]:
    items = [_normalize_item(item) for item in group.items]
    stats = dict(group.stats)
    return {
        "items": items,
        "count": len(items),
        "stats": stats,
    }


def _normalize_data(user_query: UserQuery) -> dict[str, Any]:
    raw_list = user_query.data.list
    normalized: dict[str, Any] = {
        CATEGORY_WATCHING: {"items": [], "count": 0, "stats": {}},
        CATEGORY_COMPLETED: {"items": [], "count": 0, "stats": {}},
        CATEGORY_PLAN_TO_WATCH: {"items": [], "count": 0, "stats": {}},
        CATEGORY_ON_HOLD: {"items": [], "count": 0, "stats": {}},
        CATEGORY_DROPPED: {"items": [], "count": 0, "stats": {}},
    }
    total_count = 0

    if isinstance(raw_list, UserDataList):
        entries = {
            CATEGORY_COMPLETED: raw_list.Completed,
            CATEGORY_PLAN_TO_WATCH: raw_list.Plan_to_Watch,
            CATEGORY_ON_HOLD: raw_list.On_hold,
            CATEGORY_DROPPED: raw_list.Dropped,
        }
        for category, group in entries.items():
            normalized[category] = _normalize_group(group)
            total_count += len(group.items)
    else:
        for key, group in raw_list.items():
            category = _MODEL_KEY_MAP.get(key, key.lower().replace(" ", "_"))
            if category not in normalized:
                normalized[category] = _normalize_group(group)
            else:
                normalized[category] = _normalize_group(group)
            total_count += len(group.items)

    normalized["total_count"] = total_count
    normalized["scrape_date"] = user_query.scrape_date.isoformat()

    return normalized


class MyDramaListCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, client: AsyncKuryana, user_id: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{user_id}",
            update_interval=DEFAULT_UPDATE_INTERVAL,
            always_update=True,
        )
        self.client = client
        self.user_id = user_id

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            user_query: UserQuery = await self.client.get_user(self.user_id)
        except Exception as err:
            raise UpdateFailed(
                f"Error fetching dramalist for '{self.user_id}': {err}"
            ) from err

        return _normalize_data(user_query)
