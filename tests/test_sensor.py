from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from mdl import MDLServerError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mydramalist.const import (
    CATEGORY_COMPLETED,
    CATEGORY_DROPPED,
    CATEGORY_ON_HOLD,
    CATEGORY_PLAN_TO_WATCH,
    CATEGORY_WATCHING,
    DOMAIN,
)

from .conftest import setup_integration


async def test_category_sensor_states(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get("sensor.mydramalist_completed")
    assert state is not None
    assert state.state == "2"
    assert len(state.attributes["items"]) == 2
    assert state.attributes["items"][0]["name"] == "Goblin"
    assert state.attributes["stats"] == {"episodes_seen": 32}

    assert hass.states.get("sensor.mydramalist_watching").state == "0"


async def test_total_sensor_states(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get("sensor.mydramalist_total_dramas")
    assert state is not None
    assert state.state == "4"
    assert state.attributes[CATEGORY_COMPLETED]["count"] == 2
    assert state.attributes[CATEGORY_DROPPED]["count"] == 1
    assert state.attributes[CATEGORY_PLAN_TO_WATCH]["count"] == 1
    assert state.attributes[CATEGORY_ON_HOLD]["count"] == 0
    assert state.attributes[CATEGORY_WATCHING]["count"] == 0


async def test_sensor_unavailable_when_update_fails(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)

    mock_mdl_client.watchlist.fetch = AsyncMock(
        side_effect=MDLServerError("Server error", status_code=500)
    )
    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.mydramalist_completed").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.mydramalist_total_dramas").state == STATE_UNAVAILABLE
