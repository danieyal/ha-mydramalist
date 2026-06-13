from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CATEGORIES, DOMAIN, NAME
from .coordinator import MyDramaListCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MyDramaListCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[SensorEntity] = []

    for category in CATEGORIES:
        entities.append(MyDramaListCategorySensor(coordinator, entry, category))

    entities.append(MyDramaListTotalSensor(coordinator, entry))

    async_add_entities(entities)


class MyDramaListCategorySensor(CoordinatorEntity[MyDramaListCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "dramas"

    def __init__(
        self,
        coordinator: MyDramaListCoordinator,
        entry: ConfigEntry,
        category: str,
    ) -> None:
        super().__init__(coordinator)
        self._category = category
        self._attr_translation_key = category
        self._attr_unique_id = f"{entry.entry_id}_{category}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data.get("user_id", entry.entry_id))},
            name=NAME,
            entry_type=DeviceEntryType.SERVICE,
        )
        self._sync_state()

    def _sync_state(self) -> None:
        data = self.coordinator.data
        if data is None:
            return

        category_data = data.get(self._category, {})
        self._attr_available = True
        self._attr_native_value = category_data.get("count", 0)
        self._attr_extra_state_attributes = {
            "items": category_data.get("items", []),
            "stats": category_data.get("stats", {}),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.coordinator.data is None:
            self._attr_available = False
            self.async_write_ha_state()
            return

        self._sync_state()
        self.async_write_ha_state()


class MyDramaListTotalSensor(CoordinatorEntity[MyDramaListCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "total"

    def __init__(
        self,
        coordinator: MyDramaListCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_total"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data.get("user_id", entry.entry_id))},
            name=NAME,
            entry_type=DeviceEntryType.SERVICE,
        )
        self._sync_state()

    def _sync_state(self) -> None:
        data = self.coordinator.data
        if data is None:
            return

        self._attr_available = True
        self._attr_native_value = data.get("total_count", 0)

        attributes: dict[str, Any] = {}
        for category in CATEGORIES:
            category_data = data.get(category, {})
            attributes[category] = {
                "count": category_data.get("count", 0),
                "items": category_data.get("items", []),
                "stats": category_data.get("stats", {}),
            }

        self._attr_extra_state_attributes = attributes

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.coordinator.data is None:
            self._attr_available = False
            self.async_write_ha_state()
            return

        self._sync_state()
        self.async_write_ha_state()
