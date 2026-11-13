from __future__ import annotations

from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_CALENDAR_CATEGORIES, DEFAULT_CALENDAR_CATEGORIES
from .coordinator import MyDramaListCalendarCoordinator, MyDramaListCoordinator
from .data import Airing, MyDramaListConfigEntry
from .entity import MyDramaListEntity, tracked_airings

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyDramaListConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    async_add_entities([MyDramaListEpisodeCalendar(runtime.calendar, runtime.coordinator)])


class MyDramaListEpisodeCalendar(
    CoordinatorEntity[MyDramaListCalendarCoordinator], CalendarEntity
):
    """Upcoming episodes of the titles on the chosen lists."""

    _attr_has_entity_name = True
    _attr_translation_key = "episodes"

    def __init__(
        self,
        calendar: MyDramaListCalendarCoordinator,
        lists: MyDramaListCoordinator,
    ) -> None:
        super().__init__(calendar)
        entry = calendar.config_entry
        self._lists = lists
        self._categories: list[str] = entry.options.get(
            CONF_CALENDAR_CATEGORIES, DEFAULT_CALENDAR_CATEGORIES
        )
        self._attr_unique_id = f"{entry.entry_id}_episodes"
        self._attr_device_info = MyDramaListEntity.device_info_for(entry)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # List changes decide which airings are shown.
        self.async_on_remove(self._lists.async_add_listener(self._handle_coordinator_update))

    @property
    def available(self) -> bool:
        # An empty or stale schedule still shows what is known.
        return self._lists.last_update_success

    def _events(self) -> list[tuple[Airing, str]]:
        return tracked_airings(self.coordinator.data, self._lists.data, self._categories)

    @property
    def event(self) -> CalendarEvent | None:
        """The airing in progress, or else the next one."""
        now = dt_util.utcnow()
        for airing, _ in self._events():
            if airing.end > now:
                return self._to_event(airing)
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [
            self._to_event(airing)
            for airing, _ in self._events()
            if airing.end > start_date and airing.start < end_date
        ]

    @callback
    def _to_event(self, airing: Airing) -> CalendarEvent:
        lines = []
        if (found := self._lists.data.find(airing.title_id)) is not None:
            item = found[1]
            if item["episode_total"]:
                lines.append(f"Seen {item['episode_seen'] or 0} of {item['episode_total']}")
        details = ", ".join(part for part in (airing.type, airing.country) if part)
        if details:
            lines.append(details)
        if airing.genres:
            lines.append(", ".join(airing.genres))
        if airing.url:
            lines.append(airing.url)
        return CalendarEvent(
            start=airing.start,
            end=airing.end,
            summary=airing.summary,
            description="\n".join(lines) or None,
            uid=airing.uid,
        )
