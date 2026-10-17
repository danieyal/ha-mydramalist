from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.recorder import Recorder
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from mdl import MDLServerError
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.mydramalist.const import (
    CATEGORIES,
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


async def test_item_lists_are_not_recorded(
    recorder_mock: Recorder,
    hass: HomeAssistant,
    mock_mdl_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    start = dt_util.utcnow()
    await setup_integration(hass, mock_config_entry)
    await async_wait_recording_done(hass)

    history = await hass.async_add_executor_job(
        get_significant_states,
        hass,
        start,
        None,
        ["sensor.mydramalist_completed", "sensor.mydramalist_total_dramas"],
    )

    completed = history["sensor.mydramalist_completed"][-1]
    assert completed.state == "2"
    assert "items" not in completed.attributes
    assert completed.attributes["stats"] == {"episodes_seen": 32}
    total = history["sensor.mydramalist_total_dramas"][-1]
    assert not set(CATEGORIES) & set(total.attributes)
    # The live state still carries the items for templates and dashboards.
    live = hass.states.get("sensor.mydramalist_completed")
    assert len(live.attributes["items"]) == 2


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
