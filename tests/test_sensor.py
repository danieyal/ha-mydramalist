from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.mydramalist.const import (
    CATEGORY_COMPLETED,
    CATEGORY_DROPPED,
    CATEGORY_ON_HOLD,
    CATEGORY_PLAN_TO_WATCH,
    CATEGORY_WATCHING,
    DOMAIN,
)
from custom_components.mydramalist.sensor import (
    MyDramaListCategorySensor,
    MyDramaListTotalSensor,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    pass


async def test_category_sensor_states(
    hass: HomeAssistant, mock_kuryana_client: MagicMock, mock_user_query
) -> None:
    from custom_components.mydramalist.coordinator import MyDramaListCoordinator
    from homeassistant.config_entries import ConfigEntry

    mock_kuryana_client.get_user = AsyncMock(return_value=mock_user_query)

    coordinator = MyDramaListCoordinator(hass, mock_kuryana_client, "testuser")
    await coordinator.async_config_entry_first_refresh()

    entry = ConfigEntry(
        data={"user_id": "testuser"},
        domain=DOMAIN,
        entry_id="test_entry_id",
        source="user",
        title="MyDramaList (testuser)",
        version=1,
    )

    sensor = MyDramaListCategorySensor(coordinator, entry, CATEGORY_COMPLETED)
    sensor.hass = hass
    sensor._handle_coordinator_update()

    assert sensor.native_value == 2
    assert sensor.available is True
    attrs = sensor.extra_state_attributes
    assert len(attrs["items"]) == 2
    assert attrs["items"][0]["name"] == "Goblin"


async def test_total_sensor_states(
    hass: HomeAssistant, mock_kuryana_client: MagicMock, mock_user_query
) -> None:
    from custom_components.mydramalist.coordinator import MyDramaListCoordinator
    from homeassistant.config_entries import ConfigEntry

    mock_kuryana_client.get_user = AsyncMock(return_value=mock_user_query)

    coordinator = MyDramaListCoordinator(hass, mock_kuryana_client, "testuser")
    await coordinator.async_config_entry_first_refresh()

    entry = ConfigEntry(
        data={"user_id": "testuser"},
        domain=DOMAIN,
        entry_id="test_entry_id",
        source="user",
        title="MyDramaList (testuser)",
        version=1,
    )

    sensor = MyDramaListTotalSensor(coordinator, entry)
    sensor.hass = hass
    sensor._handle_coordinator_update()

    assert sensor.native_value == 4
    assert sensor.available is True
    attrs = sensor.extra_state_attributes
    assert attrs[CATEGORY_COMPLETED]["count"] == 2
    assert attrs[CATEGORY_DROPPED]["count"] == 1
    assert attrs[CATEGORY_PLAN_TO_WATCH]["count"] == 1
    assert attrs[CATEGORY_ON_HOLD]["count"] == 0
    assert attrs[CATEGORY_WATCHING]["count"] == 0


async def test_sensor_unavailable_when_no_data(
    hass: HomeAssistant, mock_kuryana_client: MagicMock
) -> None:
    from custom_components.mydramalist.coordinator import MyDramaListCoordinator
    from homeassistant.config_entries import ConfigEntry

    coordinator = MyDramaListCoordinator(hass, mock_kuryana_client, "testuser")
    coordinator.data = None

    entry = ConfigEntry(
        data={"user_id": "testuser"},
        domain=DOMAIN,
        entry_id="test_entry_id",
        source="user",
        title="MyDramaList (testuser)",
        version=1,
    )

    sensor = MyDramaListCategorySensor(coordinator, entry, CATEGORY_COMPLETED)
    sensor.hass = hass
    sensor._handle_coordinator_update()

    assert sensor.available is False
    assert sensor.native_value is None
