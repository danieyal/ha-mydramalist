from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from mdl.models.auth import UserProfileResponse
from mdl.models.base import Images, SearchEntry
from mdl.models.reviews import Cast, CreditsResponse
from mdl.models.titles import MovieTitle, TitleResponse
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mydramalist.const import DOMAIN

from .conftest import setup_integration


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
            )
        ]
    )
    await setup_integration(hass, mock_config_entry)

    response = await hass.services.async_call(
        DOMAIN,
        "search",
        {"query": "goblin"},
        blocking=True,
        return_response=True,
    )

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
            "thumb": "https://example.com/goblin.jpg",
        }
    ]
    assert response["people"][0]["name"] == "Gong Yoo"
    assert response["people"][0]["slug"] == "1-gong-yoo"


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
    await setup_integration(hass, mock_config_entry)

    response = await hass.services.async_call(
        DOMAIN,
        "get_drama",
        {"title_id": "18452-goblin"},
        blocking=True,
        return_response=True,
    )

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


async def test_service_get_drama_invalid_id(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_mdl_client.titles.get_title = AsyncMock()
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "get_drama",
            {"title_id": "goblin"},
            blocking=True,
            return_response=True,
        )

    mock_mdl_client.titles.get_title.assert_not_awaited()


async def test_service_refresh(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)
    mock_mdl_client.watchlist.fetch.reset_mock()

    await hass.services.async_call(DOMAIN, "refresh", {}, blocking=True)
    await hass.async_block_till_done()

    assert mock_mdl_client.watchlist.fetch.await_count == 5
