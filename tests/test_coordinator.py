from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from homeassistant.core import HomeAssistant

from custom_components.mydramalist.const import (
    CATEGORY_COMPLETED,
    CATEGORY_DROPPED,
    CATEGORY_ON_HOLD,
    CATEGORY_PLAN_TO_WATCH,
    CATEGORY_WATCHING,
)
from custom_components.mydramalist.coordinator import MyDramaListCoordinator


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    pass


async def test_coordinator_normalizes_data(
    hass: HomeAssistant, mock_kuryana_client: MagicMock, mock_user_query
) -> None:
    mock_kuryana_client.get_user = AsyncMock(return_value=mock_user_query)

    coordinator = MyDramaListCoordinator(hass, mock_kuryana_client, "testuser")
    await coordinator.async_config_entry_first_refresh()

    data = coordinator.data
    assert data is not None
    assert data["total_count"] == 4

    assert data[CATEGORY_WATCHING]["count"] == 0
    assert len(data[CATEGORY_WATCHING]["items"]) == 0

    assert data[CATEGORY_COMPLETED]["count"] == 2
    assert data[CATEGORY_COMPLETED]["items"][0]["name"] == "Goblin"
    assert data[CATEGORY_COMPLETED]["items"][0]["score"] == "10"
    assert data[CATEGORY_COMPLETED]["items"][0]["episode_seen"] == "16"
    assert data[CATEGORY_COMPLETED]["items"][0]["episode_total"] == "16"

    assert data[CATEGORY_PLAN_TO_WATCH]["count"] == 1
    assert data[CATEGORY_PLAN_TO_WATCH]["items"][0]["name"] == "Vincenzo"

    assert data[CATEGORY_ON_HOLD]["count"] == 0

    assert data[CATEGORY_DROPPED]["count"] == 1
    assert data[CATEGORY_DROPPED]["items"][0]["name"] == "The Heirs"

    assert data["scrape_date"] == "2025-06-13T12:00:00"


async def test_coordinator_update_failure(
    hass: HomeAssistant, mock_kuryana_client: MagicMock
) -> None:
    from homeassistant.helpers.update_coordinator import UpdateFailed

    mock_kuryana_client.get_user = AsyncMock(
        side_effect=Exception("Network error")
    )

    coordinator = MyDramaListCoordinator(hass, mock_kuryana_client, "testuser")

    with pytest.raises(UpdateFailed, match="Error fetching dramalist"):
        await coordinator.async_config_entry_first_refresh()
