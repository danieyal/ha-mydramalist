from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from homeassistant.core import HomeAssistant

from custom_components.mydramalist.const import DOMAIN
from custom_components.mydramalist.services import async_setup_services, async_unload_services


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    pass


async def test_service_search(
    hass: HomeAssistant, mock_kuryana_client: MagicMock
) -> None:
    from kuryana.types.search import (
        SearchDrama,
        SearchPerson,
        SearchResultQuery,
        SearchResults,
    )
    from datetime import datetime

    mock_search_result = SearchResultQuery(
        query="goblin",
        results=SearchResults(
            dramas=[
                SearchDrama(
                    slug="goblin",
                    thumb="https://example.com/goblin.jpg",
                    mdl_id="123",
                    title="Goblin",
                    ranking="1",
                    type="Drama",
                    year=2016,
                    series=True,
                )
            ],
            people=[],
        ),
        scrape_date=datetime(2025, 6, 13, 12, 0, 0),
    )
    mock_kuryana_client.search = AsyncMock(return_value=mock_search_result)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["test_entry"] = {"client": mock_kuryana_client}
    async_setup_services(hass)

    response = await hass.services.async_call(
        DOMAIN,
        "search",
        {"query": "goblin"},
        blocking=True,
        return_response=True,
    )

    assert response is not None
    assert len(response["dramas"]) == 1
    assert response["dramas"][0]["title"] == "Goblin"
    assert response["dramas"][0]["year"] == 2016


async def test_service_get_drama(
    hass: HomeAssistant, mock_kuryana_client: MagicMock
) -> None:
    from kuryana.types.drama import (
        DramaCast,
        DramaData,
        DramaDetails,
        DramaOthers,
        DramaQuery,
    )
    from datetime import datetime

    mock_drama_result = DramaQuery(
        slug_query="goblin",
        data=DramaData(
            link="https://mydramalist.com/123-goblin",
            title="Goblin",
            complete_title="Guardian: The Lonely and Great God",
            sub_title="Goblin",
            year="2016",
            rating=9.1,
            poster="https://example.com/poster.jpg",
            synopsis="A synopsis...",
            casts=[
                DramaCast(
                    name="Gong Yoo",
                    profile_image="https://example.com/gongyoo.jpg",
                    slug="gong-yoo",
                    link="https://mydramalist.com/people/gong-yoo",
                )
            ],
            details=DramaDetails(
                country="South Korea",
                type="Drama",
                episodes="16",
                aired="Dec 2, 2016 - Jan 21, 2017",
                original_network="tvN",
                duration="1 hr. 10 min.",
                score="9.1",
                ranked="#1",
                popularity="#1",
                content_rating="15+",
                watchers="50000",
                favorites="10000",
            ),
            others=DramaOthers(
                related_content=[],
                native_title=["쓸쓸하고 찬란하神-도깨비"],
                also_known_as=["Guardian"],
                genres=["Comedy", "Fantasy", "Romance"],
                tags=["Goblin", "Grim Reaper"],
            ),
        ),
        scrape_date=datetime(2025, 6, 13, 12, 0, 0),
    )
    mock_kuryana_client.get_drama = AsyncMock(return_value=mock_drama_result)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["test_entry"] = {"client": mock_kuryana_client}
    async_setup_services(hass)

    response = await hass.services.async_call(
        DOMAIN,
        "get_drama",
        {"slug": "goblin"},
        blocking=True,
        return_response=True,
    )

    assert response is not None
    assert response["title"] == "Goblin"
    assert response["complete_title"] == "Guardian: The Lonely and Great God"
    assert response["rating"] == 9.1
    assert len(response["casts"]) == 1
    assert response["casts"][0]["name"] == "Gong Yoo"
    assert response["details"]["country"] == "South Korea"


async def test_service_refresh(
    hass: HomeAssistant, mock_kuryana_client: MagicMock, mock_user_query
) -> None:
    from custom_components.mydramalist.coordinator import MyDramaListCoordinator

    mock_kuryana_client.get_user = AsyncMock(return_value=mock_user_query)

    coordinator = MyDramaListCoordinator(hass, mock_kuryana_client, "testuser")
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["test_entry"] = {
        "client": mock_kuryana_client,
        "coordinator": coordinator,
    }
    async_setup_services(hass)

    mock_kuryana_client.get_user.reset_mock()

    await hass.services.async_call(
        DOMAIN,
        "refresh",
        {},
        blocking=True,
    )

    mock_kuryana_client.get_user.assert_called_once()
