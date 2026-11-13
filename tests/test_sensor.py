from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun.api import FrozenDateTimeFactory

from homeassistant.components.recorder import Recorder
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from mdl import MDLNetworkError, MDLServerError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
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
    CONF_CALENDAR_CATEGORIES,
)

from .conftest import FOOL_IN_LOVE, VINCENZO, setup_integration


async def test_category_sensor_states(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get("sensor.mydramalist_completed")
    assert state is not None
    assert state.state == "2"
    assert state.attributes["unit_of_measurement"] == "dramas"
    assert state.attributes["state_class"] == "measurement"
    assert [item["name"] for item in state.attributes["items"]] == [
        "Goblin",
        "Descendants of the Sun",
    ]
    assert state.attributes["items"][0]["url"] == "https://mydramalist.com/18452"
    assert state.attributes["stats"] == {"episodes_seen": 32, "mean_score": 9.5}

    watching = hass.states.get("sensor.mydramalist_watching")
    assert watching.state == "1"
    assert watching.attributes["items"][0]["progress"] == 19
    # Unscored titles do not count towards the mean.
    assert watching.attributes["stats"] == {"episodes_seen": 3, "mean_score": None}
    assert hass.states.get("sensor.mydramalist_on_hold").state == "0"


async def test_total_sensor_states(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get("sensor.mydramalist_total_dramas")
    assert state is not None
    assert state.state == "5"
    assert state.attributes[CATEGORY_COMPLETED] == {
        "count": 2,
        "stats": {"episodes_seen": 32, "mean_score": 9.5},
    }
    assert state.attributes[CATEGORY_DROPPED]["count"] == 1
    assert state.attributes[CATEGORY_PLAN_TO_WATCH]["count"] == 1
    assert state.attributes[CATEGORY_ON_HOLD]["count"] == 0
    assert state.attributes[CATEGORY_WATCHING]["count"] == 1
    # Item lists are only on the category sensors.
    assert "items" not in state.attributes[CATEGORY_COMPLETED]


async def test_stats_sensors(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)

    episodes = hass.states.get("sensor.mydramalist_episodes_watched")
    assert episodes.state == "4914"
    assert episodes.attributes["state_class"] == "total"
    assert hass.states.get("sensor.mydramalist_movies_watched").state == "62"

    time_watched = hass.states.get("sensor.mydramalist_time_watched")
    # 251974 minutes, shown in days.
    assert float(time_watched.state) == pytest.approx(251974 / 1440)
    assert time_watched.attributes["unit_of_measurement"] == "d"

    mean = hass.states.get("sensor.mydramalist_mean_score")
    assert mean.state == "7.75"
    assert mean.attributes["ratings"] == 4
    assert mean.attributes["score_distribution"] == {"4.0": 1, "8.0": 1, "9.0": 1, "10.0": 1}
    assert mean.attributes["friends"] == 22

    unread = hass.states.get("sensor.mydramalist_unread_notifications")
    assert unread.state == "3"
    assert unread.attributes["friend_requests"] == 1
    assert unread.attributes["messages"] == 0


async def test_stats_sensors_unavailable_without_stats(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_mdl_client.users.get_user_stats.side_effect = MDLNetworkError(
        "Forbidden", status_code=403
    )
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get("sensor.mydramalist_episodes_watched").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.mydramalist_completed").state == "2"


async def test_next_episode_sensor(
    hass: HomeAssistant,
    mock_mdl_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    now: datetime,
) -> None:
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get("sensor.mydramalist_next_episode")
    # The airing in 30 minutes is of a title on no list, so episode 4 is next.
    assert dt_util.parse_datetime(state.state) == now + timedelta(hours=1)
    assert state.attributes["title"] == "Fool in Love"
    assert state.attributes["title_id"] == FOOL_IN_LOVE
    assert state.attributes["episode"] == 4
    assert state.attributes["category"] == CATEGORY_WATCHING
    assert state.attributes["url"] == (
        f"https://mydramalist.com/{FOOL_IN_LOVE}-slug/episode/4"
    )
    assert state.attributes["entity_picture"] == "https://i.mydramalist.com/fool_4t.jpg"


async def test_next_episode_moves_on_when_episode_airs(
    hass: HomeAssistant,
    mock_mdl_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    now: datetime,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to(now)
    await setup_integration(hass, mock_config_entry)

    freezer.move_to(now + timedelta(hours=1, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mydramalist_next_episode")
    assert state.attributes["episode"] == 5
    assert dt_util.parse_datetime(state.state) == now + timedelta(days=1)


async def test_next_episode_respects_calendar_categories(
    hass: HomeAssistant,
    mock_mdl_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    now: datetime,
) -> None:
    await setup_integration(
        hass, mock_config_entry, {CONF_CALENDAR_CATEGORIES: [CATEGORY_PLAN_TO_WATCH]}
    )

    state = hass.states.get("sensor.mydramalist_next_episode")
    assert state.attributes["title_id"] == VINCENZO
    assert dt_util.parse_datetime(state.state) == now + timedelta(days=2)


async def test_next_episode_unknown_without_airings(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(
        hass, mock_config_entry, {CONF_CALENDAR_CATEGORIES: [CATEGORY_ON_HOLD]}
    )

    state = hass.states.get("sensor.mydramalist_next_episode")
    assert state.state == STATE_UNKNOWN


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
    assert completed.attributes["stats"] == {"episodes_seen": 32, "mean_score": 9.5}
    total = history["sensor.mydramalist_total_dramas"][-1]
    assert not set(CATEGORIES) & set(total.attributes)
    # The live state still carries the items for templates and dashboards.
    live = hass.states.get("sensor.mydramalist_completed")
    assert len(live.attributes["items"]) == 2


async def test_sensor_unavailable_when_update_fails(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)

    mock_mdl_client.watchlist.get_last_activities = AsyncMock(
        side_effect=MDLServerError("Server error", status_code=500)
    )
    coordinator = mock_config_entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.mydramalist_completed").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.mydramalist_total_dramas").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.mydramalist_episodes_watched").state == STATE_UNAVAILABLE
