from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from mdl import MDLNotFoundError, MDLServerError, MDLSyncError
from mdl.models.auth import UserProfileResponse
from mdl.models.base import Images, SearchEntry
from mdl.models.reviews import Cast, CreditsResponse
from mdl.models.titles import (
    LastActivity,
    Movie,
    MovieStatusType,
    MovieTitle,
    SyncFailure,
    SyncWatchListResponse,
    TitleResponse,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mydramalist.const import DOMAIN
from custom_components.mydramalist.services import parse_title_id

from .conftest import FOOL_IN_LOVE, VINCENZO, setup_integration


async def _call(hass: HomeAssistant, service: str, data: dict, **kwargs) -> dict:
    return await hass.services.async_call(
        DOMAIN, service, data, blocking=True, return_response=True, **kwargs
    )


def _progress(title_id: int, list_id: int, seen: int, total: int = 16) -> Movie:
    return Movie(
        list_id=list_id,
        episode_seen=seen,
        rating=0,
        title=MovieTitle(id=title_id, title="Fool in Love", episodes=total),
    )


def _echo_update(mock_mdl_client: MagicMock) -> AsyncMock:
    """Make watchlist.update return the entry it would save."""

    async def _update(title_id, *, current=None, status=None, episode_seen=None, **kwargs):
        current = current or _progress(title_id, 0, 0)
        changes = {"episode_seen": episode_seen, "rating": kwargs.get("rating")}
        if status is not None:
            changes["list_id"] = MovieStatusType(status).list_id
        return current.model_copy(
            update={key: value for key, value in changes.items() if value is not None}
        )

    mock_mdl_client.watchlist.update = AsyncMock(side_effect=_update)
    return mock_mdl_client.watchlist.update


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("18452", 18452),
        (18452, 18452),
        (" 18452-goblin ", 18452),
        ("https://mydramalist.com/18452-goblin", 18452),
        ("https://mydramalist.com/18452-goblin/episode/3", 18452),
        ("/18452-goblin", 18452),
    ],
)
def test_parse_title_id(value, expected) -> None:
    assert parse_title_id(value) == expected


@pytest.mark.parametrize("value", ["goblin", "https://mydramalist.com/search?q=goblin", ""])
def test_parse_title_id_rejects(value) -> None:
    with pytest.raises(ServiceValidationError):
        parse_title_id(value)


async def test_service_search(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_mdl_client.search.titles = AsyncMock(
        return_value=[
            MovieTitle(
                id=18452,
                title="Goblin",
                year=2016,
                type="Drama",
                country="South Korea",
                episodes=16,
                rating=8.8,
                images=Images(thumb="https://example.com/goblin.jpg"),
            )
        ]
    )
    mock_mdl_client.search.people = AsyncMock(
        return_value=[
            UserProfileResponse(
                id=1, slug="1-gong-yoo", name="Gong Yoo", nationality="South Korean"
            ),
            # Live people search sends only a site path, no slug.
            UserProfileResponse(id=440, name="Gong Yoo", url="/people/440-gong-yoo"),
        ]
    )
    await setup_integration(hass, mock_config_entry)

    response = await _call(hass, "search", {"query": "goblin"})

    mock_mdl_client.search.titles.assert_awaited_once_with("goblin")
    assert response["dramas"] == [
        {
            "id": 18452,
            "title": "Goblin",
            "original_title": None,
            "year": 2016,
            "type": "Drama",
            "country": "South Korea",
            "episodes": 16,
            "rating": 8.8,
            "rank": None,
            "url": "https://mydramalist.com/18452",
            "thumb": "https://example.com/goblin.jpg",
        }
    ]
    assert response["people"][0]["name"] == "Gong Yoo"
    assert response["people"][0]["slug"] == "1-gong-yoo"
    assert response["people"][1]["slug"] == "440-gong-yoo"


async def test_service_get_drama(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_mdl_client.titles.get_title = AsyncMock(
        return_value=TitleResponse(
            id=18452,
            title="Goblin",
            original_title="쓸쓸하고 찬란하神-도깨비",
            year=2016,
            rating=8.8,
            synopsis="A synopsis...",
            permalink="https://mydramalist.com/18452-goblin",
            country="South Korea",
            episodes=16,
            images=Images(poster="https://example.com/poster.jpg"),
            genres=[SearchEntry(id=1, name="Fantasy"), SearchEntry(id=2, name="Romance")],
        )
    )
    mock_mdl_client.titles.get_credits = AsyncMock(
        return_value=CreditsResponse(
            cast=[Cast(id=1, name="Gong Yoo", character_name="Kim Shin", role="Main Role")]
        )
    )
    mock_mdl_client.watchlist.get_progress = AsyncMock(
        return_value=_progress(18452, 2, 16)
    )
    await setup_integration(hass, mock_config_entry)

    response = await _call(hass, "get_drama", {"title_id": "18452-goblin"})

    mock_mdl_client.titles.get_title.assert_awaited_once_with(18452)
    mock_mdl_client.titles.get_credits.assert_awaited_once_with(18452)
    assert response["title"] == "Goblin"
    assert response["original_title"] == "쓸쓸하고 찬란하神-도깨비"
    assert response["rating"] == 8.8
    assert response["poster"] == "https://example.com/poster.jpg"
    assert response["link"] == "https://mydramalist.com/18452-goblin"
    assert response["genres"] == ["Fantasy", "Romance"]
    assert response["tags"] == []
    assert response["casts"] == [
        {
            "id": 1,
            "name": "Gong Yoo",
            "character_name": "Kim Shin",
            "role": "Main Role",
            "thumb": None,
        }
    ]
    assert response["my_entry"]["status"] == "completed"
    assert response["my_entry"]["episode_seen"] == 16


async def test_service_get_drama_not_on_lists(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_mdl_client.titles.get_title = AsyncMock(return_value=TitleResponse(id=5))
    mock_mdl_client.titles.get_credits = AsyncMock(return_value=CreditsResponse())
    mock_mdl_client.watchlist.get_progress = AsyncMock(return_value=_progress(5, 0, 0))
    await setup_integration(hass, mock_config_entry)

    response = await _call(hass, "get_drama", {"title_id": 5})
    assert response["my_entry"] is None


async def test_service_get_drama_invalid_id(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_mdl_client.titles.get_title = AsyncMock()
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError):
        await _call(hass, "get_drama", {"title_id": "goblin"})

    mock_mdl_client.titles.get_title.assert_not_awaited()


async def test_service_get_drama_unknown_title(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_mdl_client.titles.get_title = AsyncMock(
        side_effect=MDLNotFoundError("Not Found", status_code=404)
    )
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError, match="no title"):
        await _call(hass, "get_drama", {"title_id": 1})


async def test_service_api_error(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_mdl_client.titles.get_recommendations = AsyncMock(
        side_effect=MDLServerError("Bad Gateway", status_code=502)
    )
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(HomeAssistantError, match="Bad Gateway"):
        await _call(hass, "get_recommendations", {"title_id": 1})


async def test_service_get_recommendations_and_titles(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    titles = [MovieTitle(id=713793, title="Fake It Till You Make It", permalink="/713793-x")]
    mock_mdl_client.titles.get_recommendations = AsyncMock(return_value=titles)
    mock_mdl_client.explore.top_airing = AsyncMock(return_value=titles)
    await setup_integration(hass, mock_config_entry)

    recs = await _call(hass, "get_recommendations", {"title_id": "18452-goblin"})
    mock_mdl_client.titles.get_recommendations.assert_awaited_once_with(18452)
    assert recs["titles"][0]["url"] == "https://mydramalist.com/713793-x"

    feed = await _call(hass, "get_titles", {"feed": "top_airing"})
    assert feed["titles"][0]["title"] == "Fake It Till You Make It"


async def test_service_get_airing_schedule(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)

    tracked = await _call(hass, "get_airing_schedule", {})
    assert [(a["title_id"], a["episode"], a["aired"]) for a in tracked["airings"]] == [
        (FOOL_IN_LOVE, 3, True),
        (FOOL_IN_LOVE, 4, False),
        (FOOL_IN_LOVE, 5, False),
        (VINCENZO, 1, False),
    ]
    assert tracked["airings"][0]["category"] == "watching"

    everything = await _call(hass, "get_airing_schedule", {"only_tracked": False})
    assert len(everything["airings"]) == 5
    assert everything["airings"][1]["category"] is None


async def test_service_update_entry(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    update = _echo_update(mock_mdl_client)
    await setup_integration(hass, mock_config_entry)

    response = await _call(
        hass,
        "update_entry",
        {
            "title_id": "https://mydramalist.com/810938-fool-in-love",
            "status": "on_hold",
            "episode_seen": 5,
            "score": 8.5,
            "date_start": "2026-11-01",
            "note": "paused for now",
        },
    )

    update.assert_awaited_once_with(
        FOOL_IN_LOVE,
        status=MovieStatusType.ON_HOLD,
        episode_seen=5,
        rating=8.5,
        date_start=date(2026, 11, 1),
        date_finish=None,
        times_rewatched=None,
        note="paused for now",
    )
    assert response["entry"]["status"] == "on_hold"
    assert response["entry"]["episode_seen"] == 5


async def test_service_update_entry_refreshes_lists(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    _echo_update(mock_mdl_client)
    await setup_integration(hass, mock_config_entry)
    mock_mdl_client.watchlist.get_last_activities.return_value = LastActivity(
        all="2026-11-13T12:00:00Z"
    )
    mock_mdl_client.watchlist.fetch.reset_mock()

    await _call(hass, "update_entry", {"title_id": FOOL_IN_LOVE, "episode_seen": 4})
    await hass.async_block_till_done()

    assert mock_mdl_client.watchlist.fetch.await_count == 5


@pytest.mark.parametrize("score", [-1, 10.5])
async def test_service_update_entry_validates_score(
    hass: HomeAssistant,
    mock_mdl_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    score: float,
) -> None:
    await setup_integration(hass, mock_config_entry)
    with pytest.raises(Exception, match="value must be"):
        await _call(hass, "update_entry", {"title_id": 1, "score": score})


async def test_service_update_entry_rejected(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_mdl_client.watchlist.update = AsyncMock(
        side_effect=MDLSyncError([SyncFailure(id=1, message="This show has not aired yet.")])
    )
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(HomeAssistantError, match="not aired yet"):
        await _call(hass, "update_entry", {"title_id": 1, "score": 9})


async def test_service_update_entry_needs_status_to_add(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_mdl_client.watchlist.update = AsyncMock(
        side_effect=ValueError("status is required for a title that is on none of your lists")
    )
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError, match="status is required"):
        await _call(hass, "update_entry", {"title_id": 1, "episode_seen": 1})


async def test_service_mark_episode_watched(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    update = _echo_update(mock_mdl_client)
    current = _progress(FOOL_IN_LOVE, 1, 3)
    mock_mdl_client.watchlist.get_progress = AsyncMock(return_value=current)
    await setup_integration(hass, mock_config_entry)

    response = await _call(hass, "mark_episode_watched", {"title_id": FOOL_IN_LOVE})

    update.assert_awaited_once_with(
        FOOL_IN_LOVE, status=MovieStatusType.WATCHING, episode_seen=4, current=current
    )
    assert response["entry"]["episode_seen"] == 4
    assert response["entry"]["status"] == "watching"


async def test_service_mark_last_episode_completes(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    update = _echo_update(mock_mdl_client)
    mock_mdl_client.watchlist.get_progress = AsyncMock(
        return_value=_progress(FOOL_IN_LOVE, 1, 15)
    )
    await setup_integration(hass, mock_config_entry)

    response = await _call(
        hass, "mark_episode_watched", {"title_id": FOOL_IN_LOVE, "episodes": 3}
    )

    assert update.await_args.kwargs["episode_seen"] == 16
    assert update.await_args.kwargs["status"] is MovieStatusType.COMPLETED
    assert response["entry"]["status"] == "completed"


async def test_service_mark_last_episode_without_completing(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    update = _echo_update(mock_mdl_client)
    mock_mdl_client.watchlist.get_progress = AsyncMock(
        return_value=_progress(FOOL_IN_LOVE, 1, 15)
    )
    await setup_integration(hass, mock_config_entry)

    await _call(
        hass,
        "mark_episode_watched",
        {"title_id": FOOL_IN_LOVE, "complete_when_finished": False},
    )

    assert update.await_args.kwargs["status"] is MovieStatusType.WATCHING


async def test_service_mark_episode_adds_planned_title_to_watching(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    update = _echo_update(mock_mdl_client)
    mock_mdl_client.watchlist.get_progress = AsyncMock(
        return_value=_progress(VINCENZO, 3, 0, total=20)
    )
    await setup_integration(hass, mock_config_entry)

    await _call(hass, "mark_episode_watched", {"title_id": VINCENZO})

    assert update.await_args.kwargs["status"] is MovieStatusType.WATCHING
    assert update.await_args.kwargs["episode_seen"] == 1


async def test_service_mark_episode_on_completed_title(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    update = _echo_update(mock_mdl_client)
    mock_mdl_client.watchlist.get_progress = AsyncMock(
        return_value=_progress(18452, 2, 16)
    )
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError, match="already completed"):
        await _call(hass, "mark_episode_watched", {"title_id": 18452})
    update.assert_not_awaited()


async def test_service_remove_entry(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_mdl_client.watchlist.remove = AsyncMock(
        return_value=SyncWatchListResponse(deleted={"titles": 1})
    )
    await setup_integration(hass, mock_config_entry)

    response = await _call(hass, "remove_entry", {"title_id": "36269-vincenzo"})

    mock_mdl_client.watchlist.remove.assert_awaited_once_with([VINCENZO])
    assert response == {"removed": 1}


async def test_service_remove_entry_not_on_list(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_mdl_client.watchlist.remove = AsyncMock(
        return_value=SyncWatchListResponse(deleted={"titles": 0})
    )
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError, match="not on any"):
        await _call(hass, "remove_entry", {"title_id": 1})


async def test_service_write_without_response(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    _echo_update(mock_mdl_client)
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        DOMAIN, "update_entry", {"title_id": 1, "status": "watching"}, blocking=True
    )


async def test_service_targets_config_entry(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_mdl_client.explore.trending = AsyncMock(return_value=[])
    await setup_integration(hass, mock_config_entry)

    response = await _call(
        hass,
        "get_titles",
        {"feed": "trending", "config_entry_id": mock_config_entry.entry_id},
    )
    assert response == {"titles": []}

    with pytest.raises(ServiceValidationError, match="No MyDramaList account"):
        await _call(hass, "get_titles", {"feed": "trending", "config_entry_id": "nope"})


async def test_service_without_loaded_entry(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)
    await hass.config_entries.async_unload(mock_config_entry.entry_id)

    with pytest.raises(ServiceValidationError, match="set up and loaded"):
        await _call(hass, "search", {"query": "goblin"})


async def test_service_refresh(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)
    mock_mdl_client.watchlist.get_last_activities.reset_mock()
    mock_mdl_client.calendar.episodes.reset_mock()

    await hass.services.async_call(DOMAIN, "refresh", {}, blocking=True)
    await hass.async_block_till_done()

    mock_mdl_client.watchlist.get_last_activities.assert_awaited_once()
    mock_mdl_client.calendar.episodes.assert_awaited_once()
