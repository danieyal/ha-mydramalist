from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CATEGORIES,
    CONF_CALENDAR_CATEGORIES,
    DEFAULT_CALENDAR_CATEGORIES,
    WEBSITE_URL,
)
from .coordinator import MyDramaListCalendarCoordinator, MyDramaListCoordinator
from .data import Airing, MyDramaListConfigEntry, MyDramaListData, list_stats
from .entity import MyDramaListEntity, upcoming_airings

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MyDramaListSensorDescription(SensorEntityDescription):
    value_fn: Callable[[MyDramaListData], Any]
    attrs_fn: Callable[[MyDramaListData], dict[str, Any] | None] = lambda data: None
    available_fn: Callable[[MyDramaListData], bool] = lambda data: True
    picture_fn: Callable[[MyDramaListData], str | None] = lambda data: None


def _category_description(category: str) -> MyDramaListSensorDescription:
    return MyDramaListSensorDescription(
        key=category,
        translation_key=category,
        native_unit_of_measurement="dramas",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: len(data.lists.get(category, [])),
        attrs_fn=lambda data: {
            "items": data.lists.get(category, []),
            "stats": list_stats(data.lists.get(category, [])),
        },
    )


def _stat(key: str) -> Callable[[MyDramaListData], Any]:
    return lambda data: data.stats.get(key) if data.stats else None


def _unread(key: str) -> Callable[[MyDramaListData], Any]:
    return lambda data: data.unread.get(key) if data.unread else None


SENSORS: tuple[MyDramaListSensorDescription, ...] = (
    *(_category_description(category) for category in CATEGORIES),
    MyDramaListSensorDescription(
        key="total",
        translation_key="total",
        native_unit_of_measurement="dramas",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.total_count,
        # Per-category counts and stats only; the items live on the category sensors.
        attrs_fn=lambda data: {
            **{
                category: {
                    "count": len(items),
                    "stats": list_stats(items),
                }
                for category, items in data.lists.items()
            },
            "username": data.user.username,
            "display_name": data.user.display_name,
            "profile_url": f"{WEBSITE_URL}/profile/{data.user.username}",
        },
        picture_fn=lambda data: data.user.avatar,
    ),
    MyDramaListSensorDescription(
        key="episodes_watched",
        translation_key="episodes_watched",
        native_unit_of_measurement="episodes",
        state_class=SensorStateClass.TOTAL,
        value_fn=_stat("episodes_watched"),
        available_fn=lambda data: data.stats is not None,
    ),
    MyDramaListSensorDescription(
        key="movies_watched",
        translation_key="movies_watched",
        native_unit_of_measurement="movies",
        state_class=SensorStateClass.TOTAL,
        value_fn=_stat("movies_watched"),
        available_fn=lambda data: data.stats is not None,
    ),
    MyDramaListSensorDescription(
        key="time_watched",
        translation_key="time_watched",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_unit_of_measurement=UnitOfTime.DAYS,
        suggested_display_precision=1,
        state_class=SensorStateClass.TOTAL,
        value_fn=_stat("minutes_watched"),
        available_fn=lambda data: data.stats is not None,
    ),
    MyDramaListSensorDescription(
        key="mean_score",
        translation_key="mean_score",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=_stat("mean_score"),
        attrs_fn=lambda data: {
            key: data.stats.get(key)
            for key in ("ratings", "score_distribution", "reviews", "comments", "friends")
        }
        if data.stats
        else None,
        available_fn=lambda data: data.stats is not None,
    ),
    MyDramaListSensorDescription(
        key="unread_notifications",
        translation_key="unread_notifications",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_unread("notifications"),
        attrs_fn=lambda data: {
            "friend_requests": data.unread.get("friend_requests"),
            "messages": data.unread.get("messages"),
        }
        if data.unread
        else None,
        available_fn=lambda data: data.unread is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyDramaListConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    entities: list[SensorEntity] = [
        MyDramaListSensor(runtime.coordinator, description) for description in SENSORS
    ]
    entities.append(MyDramaListNextEpisodeSensor(runtime.calendar, runtime.coordinator))
    async_add_entities(entities)


class MyDramaListSensor(MyDramaListEntity, SensorEntity):
    entity_description: MyDramaListSensorDescription
    # HA reads this per class. Item lists (category sensors) outgrow the recorder's
    # 16 KB attribute limit; the total sensor's per-category attributes are kept out too.
    _unrecorded_attributes = frozenset({"items", *CATEGORIES})

    def __init__(
        self,
        coordinator: MyDramaListCoordinator,
        description: MyDramaListSensorDescription,
    ) -> None:
        super().__init__(coordinator, coordinator.config_entry, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        return super().available and self.entity_description.available_fn(
            self.coordinator.data
        )

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self.entity_description.attrs_fn(self.coordinator.data)

    @property
    def entity_picture(self) -> str | None:
        return self.entity_description.picture_fn(self.coordinator.data)


class MyDramaListNextEpisodeSensor(
    CoordinatorEntity[MyDramaListCalendarCoordinator], SensorEntity
):
    """When the next episode of a tracked title airs."""

    _attr_has_entity_name = True
    _attr_translation_key = "next_episode"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

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
        self._attr_unique_id = f"{entry.entry_id}_next_episode"
        self._attr_device_info = MyDramaListEntity.device_info_for(entry)
        self._next: Airing | None = None
        self._category: str | None = None
        self._unsub_timer: CALLBACK_TYPE | None = None
        self._refresh_next()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._lists.async_add_listener(self._handle_coordinator_update))
        self.async_on_remove(self._cancel_timer)
        self._schedule_rollover()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._refresh_next()
        self._schedule_rollover()
        super()._handle_coordinator_update()

    def _refresh_next(self) -> None:
        upcoming = upcoming_airings(
            self.coordinator.data, self._lists.data, self._categories, dt_util.utcnow()
        )
        self._next, self._category = upcoming[0] if upcoming else (None, None)

    @callback
    def _cancel_timer(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

    @callback
    def _schedule_rollover(self) -> None:
        """Move on to the following episode once this one airs."""
        self._cancel_timer()
        if self._next is not None:
            self._unsub_timer = async_track_point_in_utc_time(
                self.hass, self._handle_rollover, self._next.start
            )

    @callback
    def _handle_rollover(self, now: datetime) -> None:
        self._unsub_timer = None
        self._refresh_next()
        self._schedule_rollover()
        self.async_write_ha_state()

    @property
    def native_value(self) -> datetime | None:
        return self._next.start if self._next else None

    @property
    def entity_picture(self) -> str | None:
        return self._next.thumb if self._next else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._next is None:
            return None
        return {
            "title": self._next.title,
            "title_id": self._next.title_id,
            "episode": self._next.episode,
            "category": self._category,
            "url": self._next.url,
            "thumb": self._next.thumb,
        }
