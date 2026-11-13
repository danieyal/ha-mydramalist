from __future__ import annotations

from datetime import datetime

from homeassistant.const import CONF_USERNAME
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME, WEBSITE_URL
from .coordinator import MyDramaListCoordinator
from .data import Airing, MyDramaListConfigEntry, MyDramaListData


class MyDramaListEntity(CoordinatorEntity[MyDramaListCoordinator]):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MyDramaListCoordinator,
        entry: MyDramaListConfigEntry,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = self.device_info_for(entry)

    @staticmethod
    def device_info_for(entry: MyDramaListConfigEntry) -> DeviceInfo:
        username = entry.data.get(CONF_USERNAME, entry.entry_id)
        return DeviceInfo(
            identifiers={(DOMAIN, username)},
            name=NAME,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=f"{WEBSITE_URL}/dramalist/{username}",
        )


def tracked_airings(
    airings: list[Airing] | None,
    lists: MyDramaListData | None,
    categories: list[str],
) -> list[tuple[Airing, str]]:
    """Airings of titles on the given list categories, with each title's category."""
    if not airings or lists is None:
        return []
    title_categories = lists.title_categories()
    tracked: list[tuple[Airing, str]] = []
    for airing in airings:
        category = title_categories.get(airing.title_id)
        if category in categories:
            tracked.append((airing, category))
    return tracked


def upcoming_airings(
    airings: list[Airing] | None,
    lists: MyDramaListData | None,
    categories: list[str],
    now: datetime,
) -> list[tuple[Airing, str]]:
    return [
        (airing, category)
        for airing, category in tracked_airings(airings, lists, categories)
        if airing.start > now
    ]
