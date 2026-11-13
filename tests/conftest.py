from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from mdl.auth import InMemoryTokenStore
from mdl.models.auth import ProfileResponse
from mdl.models.base import Images
from mdl.models.misc import EpisodeItem, EpisodeRelationship, Episodes, UserStats
from mdl.models.social import NotificationResponse
from mdl.models.titles import LastActivity, Movie, MovieStatusType, MovieTitle
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mydramalist.const import CONF_DEVICE_ID, DOMAIN

FOOL_IN_LOVE = 810938
VINCENZO = 36269
NOT_ON_LISTS = 999001


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(request: pytest.FixtureRequest) -> None:
    # The recorder has to be set up before hass, and this autouse fixture would
    # otherwise create hass first.
    if "recorder_mock" in request.fixturenames:
        request.getfixturevalue("recorder_mock")
    request.getfixturevalue("enable_custom_integrations")


def _movie(
    title_id: int,
    name: str,
    rating: float,
    seen: int,
    total: int,
    *,
    list_id: int = 0,
    **extra: object,
) -> Movie:
    fields: dict[str, object] = {
        "date_start": "0000-00-00",
        "date_finish": "0000-00-00",
        "updated_at": "2026-11-01T10:00:00Z",
        **extra,
    }
    return Movie(
        list_id=list_id,
        rating=rating,
        episode_seen=seen,
        title=MovieTitle(
            id=title_id,
            title=name,
            episodes=total,
            year=2016,
            type="Drama",
            country="South Korea",
            images=Images(thumb=f"https://i.mydramalist.com/{title_id}t.jpg"),
        ),
        **fields,
    )


@pytest.fixture
def mock_watchlists() -> dict[MovieStatusType, list[Movie]]:
    return {
        MovieStatusType.WATCHING: [
            _movie(FOOL_IN_LOVE, "Fool in Love", 0, 3, 16, list_id=1, date_start="2026-11-01")
        ],
        MovieStatusType.COMPLETED: [
            _movie(18452, "Goblin", 10, 16, 16, list_id=2, date_finish="2026-09-22"),
            _movie(9025, "Descendants of the Sun", 9, 16, 16, list_id=2),
        ],
        MovieStatusType.PLAN_TO_WATCH: [_movie(VINCENZO, "Vincenzo", 0, 0, 20, list_id=3)],
        MovieStatusType.DROPPED: [
            _movie(7963, "The Heirs", 4, 6, 20, list_id=5),
            Movie(deleted=True, title=MovieTitle(id=1, title="Removed")),
        ],
    }


def _airing(
    item_id: int, title_id: int, episode: int, start: datetime, duration: int = 60
) -> EpisodeItem:
    return EpisodeItem(
        id=item_id,
        rid=title_id,
        episode_number=episode,
        released_at=int(start.timestamp()),
        duration=duration,
        permalink=f"/{title_id}-slug/episode/{episode}",
    )


@pytest.fixture
def now() -> datetime:
    return dt_util.utcnow().replace(microsecond=0)


@pytest.fixture
def mock_calendar(now: datetime) -> Episodes:
    return Episodes(
        items=[
            _airing(1, FOOL_IN_LOVE, 3, now - timedelta(days=1)),
            _airing(2, NOT_ON_LISTS, 7, now + timedelta(minutes=30)),
            _airing(3, FOOL_IN_LOVE, 4, now + timedelta(hours=1), duration=70),
            _airing(4, FOOL_IN_LOVE, 5, now + timedelta(days=1), duration=0),
            _airing(5, VINCENZO, 1, now + timedelta(days=2)),
        ],
        relationships=[
            EpisodeRelationship(
                id=FOOL_IN_LOVE,
                title="Fool in Love",
                type="Drama",
                country="South Korea",
                genres="Romance,Comedy",
                url=f"/{FOOL_IN_LOVE}-fool-in-love",
                thumbnail="https://i.mydramalist.com/fool_4t.jpg",
                add_status=True,
            ),
            EpisodeRelationship(id=NOT_ON_LISTS, title="Someone Else's Show", type="TV Show"),
            EpisodeRelationship(id=VINCENZO, title="Vincenzo", type="Drama"),
        ],
    )


@pytest.fixture
def mock_user_stats() -> UserStats:
    return UserStats.model_validate(
        {
            "stats": [
                {"type": "Movie", "collected": 62, "minutes": 6266, "watched": 62},
                {"type": "Shows", "collected": 522, "minutes": 245708, "watched": 4914},
            ],
            "ratings": {"total": 4, "distribution": {"10.0": 1, "9.0": 1, "8.0": 1, "4.0": 1}},
            "comments": 106,
            "reviews": 2,
            "friends": 22,
        }
    )


@pytest.fixture
def mock_mdl_client(
    mock_watchlists: dict[MovieStatusType, list[Movie]],
    mock_calendar: Episodes,
    mock_user_stats: UserStats,
) -> Generator[MagicMock, None, None]:
    client = MagicMock()
    client.tokens = InMemoryTokenStore()

    async def _login(username: str, password: str) -> None:
        client.tokens.set_token("token")

    client.auth.login = AsyncMock(side_effect=_login)
    client.aclose = AsyncMock()
    client.account.get_profile = AsyncMock(
        return_value=ProfileResponse(
            username="testuser",
            display_name="Test User",
            email="someone@example.com",
            images=Images(thumb="https://i.mydramalist.com/avatar_1t.jpg"),
        )
    )
    client.watchlist.get_last_activities = AsyncMock(
        return_value=LastActivity(all="2026-11-01T10:00:00Z")
    )
    client.watchlist.fetch = AsyncMock(
        side_effect=lambda status: mock_watchlists.get(status, [])
    )
    client.users.get_user_stats = AsyncMock(return_value=mock_user_stats)
    client.notifications.fetch = AsyncMock(
        return_value=NotificationResponse(total=3, friends=1, messages=0)
    )
    client.calendar.episodes = AsyncMock(return_value=mock_calendar)

    with (
        patch("custom_components.mydramalist.AsyncMDLClient", return_value=client),
        patch(
            "custom_components.mydramalist.config_flow.AsyncMDLClient",
            return_value=client,
        ),
    ):
        yield client


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id="testuser",
        title="MyDramaList (testuser)",
        data={
            CONF_USERNAME: "testuser",
            CONF_PASSWORD: "secret",
            CONF_DEVICE_ID: "device-123",
        },
    )


async def setup_integration(
    hass: HomeAssistant, entry: MockConfigEntry, options: dict | None = None
) -> None:
    entry.add_to_hass(hass)
    if options is not None:
        hass.config_entries.async_update_entry(entry, options=options)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
