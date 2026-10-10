from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from mdl.auth import InMemoryTokenStore
from mdl.models.titles import Movie, MovieStatusType, MovieTitle
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mydramalist.const import CONF_DEVICE_ID, DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    pass


def _movie(title_id: int, name: str, rating: float, seen: int, total: int) -> Movie:
    return Movie(
        rating=rating,
        episode_seen=seen,
        title=MovieTitle(id=title_id, title=name, episodes=total),
    )


@pytest.fixture
def mock_watchlists() -> dict[MovieStatusType, list[Movie]]:
    return {
        MovieStatusType.COMPLETED: [
            _movie(18452, "Goblin", 10, 16, 16),
            _movie(9025, "Descendants of the Sun", 9, 16, 16),
        ],
        MovieStatusType.PLAN_TO_WATCH: [_movie(36269, "Vincenzo", 0, 0, 20)],
        MovieStatusType.DROPPED: [
            _movie(7963, "The Heirs", 4, 6, 20),
            Movie(deleted=True, title=MovieTitle(id=1, title="Removed")),
        ],
    }


@pytest.fixture
def mock_mdl_client(
    mock_watchlists: dict[MovieStatusType, list[Movie]],
) -> Generator[MagicMock, None, None]:
    client = MagicMock()
    client.tokens = InMemoryTokenStore()

    async def _login(username: str, password: str) -> None:
        client.tokens.set_token("token")

    client.auth.login = AsyncMock(side_effect=_login)
    client.aclose = AsyncMock()
    client.watchlist.fetch = AsyncMock(
        side_effect=lambda status: mock_watchlists.get(status, [])
    )

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


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
