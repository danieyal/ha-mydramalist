from __future__ import annotations

from datetime import datetime, timedelta
from http import HTTPStatus
from unittest.mock import MagicMock
from urllib.parse import urlencode

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from mdl.models.misc import EpisodeItem, EpisodeRelationship, Episodes
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mydramalist.const import (
    CATEGORY_COMPLETED,
    CATEGORY_WATCHING,
    CONF_CALENDAR_CATEGORIES,
)

from .conftest import FOOL_IN_LOVE, setup_integration

ENTITY_ID = "calendar.mydramalist_episodes"


async def _events(
    hass: HomeAssistant, start: datetime, end: datetime
) -> list[dict]:
    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {"entity_id": ENTITY_ID, "start_date_time": start, "end_date_time": end},
        blocking=True,
        return_response=True,
    )
    return response[ENTITY_ID]["events"]


async def test_calendar_shows_episodes_of_tracked_lists(
    hass: HomeAssistant,
    mock_mdl_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    now: datetime,
) -> None:
    await setup_integration(hass, mock_config_entry)

    events = await _events(hass, now - timedelta(days=3), now + timedelta(days=7))

    # Watching and Plan to Watch by default; the title on no list is left out.
    assert [event["summary"] for event in events] == [
        "Fool in Love · Episode 3",
        "Fool in Love · Episode 4",
        "Fool in Love · Episode 5",
        "Vincenzo · Episode 1",
    ]
    episode_4 = events[1]
    assert dt_util.parse_datetime(episode_4["start"]) == now + timedelta(hours=1)
    assert dt_util.parse_datetime(episode_4["end"]) == now + timedelta(hours=1, minutes=70)
    assert episode_4["description"].splitlines() == [
        "Seen 3 of 16",
        "Drama, South Korea",
        "Romance, Comedy",
        f"https://mydramalist.com/{FOOL_IN_LOVE}-slug/episode/4",
    ]
    # No duration means an hour-long event.
    episode_5 = events[2]
    assert dt_util.parse_datetime(episode_5["end"]) - dt_util.parse_datetime(
        episode_5["start"]
    ) == timedelta(hours=1)


async def test_calendar_state_is_next_event(
    hass: HomeAssistant,
    mock_mdl_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(ENTITY_ID)
    assert state.state == "off"
    assert state.attributes["message"] == "Fool in Love · Episode 4"


async def test_calendar_categories_option(
    hass: HomeAssistant,
    mock_mdl_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    now: datetime,
) -> None:
    await setup_integration(
        hass,
        mock_config_entry,
        {CONF_CALENDAR_CATEGORIES: [CATEGORY_WATCHING, CATEGORY_COMPLETED]},
    )

    events = await _events(hass, now - timedelta(days=3), now + timedelta(days=7))
    assert {event["summary"].split(" · ")[0] for event in events} == {"Fool in Love"}


async def test_calendar_http_api(
    hass: HomeAssistant,
    hass_client,
    mock_mdl_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    now: datetime,
) -> None:
    await setup_integration(hass, mock_config_entry)
    client = await hass_client()

    query = urlencode(
        {
            "start": (now + timedelta(minutes=10)).isoformat(),
            "end": (now + timedelta(hours=3)).isoformat(),
        }
    )
    response = await client.get(f"/api/calendars/{ENTITY_ID}?{query}")

    assert response.status == HTTPStatus.OK
    events = await response.json()
    assert [event["summary"] for event in events] == ["Fool in Love · Episode 4"]


async def test_calendar_keeps_airings_that_left_the_window(
    hass: HomeAssistant,
    mock_mdl_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    now: datetime,
) -> None:
    await setup_integration(hass, mock_config_entry)
    calendar = mock_config_entry.runtime_data.calendar

    # A day later the API window has moved on: yesterday's episode 3 is gone, episode 4
    # was rescheduled, and episode 5 was dropped from the schedule.
    moved = now + timedelta(hours=5)
    mock_mdl_client.calendar.episodes.return_value = Episodes(
        items=[
            EpisodeItem(
                id=3, rid=FOOL_IN_LOVE, episode_number=4, released_at=int(moved.timestamp())
            )
        ],
        relationships=[EpisodeRelationship(id=FOOL_IN_LOVE, title="Fool in Love")],
    )
    await calendar.async_refresh()

    by_uid = {airing.uid: airing for airing in calendar.data}
    # Kept: airings from before the new window (1, and 2 for a title on no list).
    # Replaced: 3, moved into the window. Dropped: 4 and 5, gone from the window.
    assert set(by_uid) == {"1", "2", "3"}
    assert by_uid["3"].start == moved
