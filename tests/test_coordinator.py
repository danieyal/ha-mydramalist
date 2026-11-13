from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from mdl import MDLAuthError, MDLNetworkError, MDLServerError
from mdl.models.titles import LastActivity
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mydramalist.const import (
    CATEGORY_COMPLETED,
    CATEGORY_DROPPED,
    CATEGORY_ON_HOLD,
    CATEGORY_PLAN_TO_WATCH,
    CATEGORY_WATCHING,
    CONF_DEVICE_ID,
    DOMAIN,
)
from custom_components.mydramalist.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import FOOL_IN_LOVE, setup_integration


def _auth_error() -> MDLAuthError:
    return MDLAuthError("Unauthorized", status_code=401)


def _reauth_flows(hass: HomeAssistant) -> list:
    return [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["context"]["source"] == SOURCE_REAUTH
    ]


async def test_coordinator_normalizes_data(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    mock_mdl_client.auth.login.assert_awaited_once_with("testuser", "secret")

    data = mock_config_entry.runtime_data.coordinator.data
    assert data.total_count == 5
    assert data.user.display_name == "Test User"

    assert data.lists[CATEGORY_WATCHING][0] == {
        "id": FOOL_IN_LOVE,
        "name": "Fool in Love",
        "url": f"https://mydramalist.com/{FOOL_IN_LOVE}",
        "thumb": f"https://i.mydramalist.com/{FOOL_IN_LOVE}t.jpg",
        "year": 2016,
        "type": "Drama",
        "country": "South Korea",
        "score": 0,
        "episode_seen": 3,
        "episode_total": 16,
        "progress": 19,
        "date_start": "2026-11-01",
        "date_finish": None,
        "updated_at": "2026-11-01T10:00:00Z",
    }
    completed = data.lists[CATEGORY_COMPLETED]
    assert [item["name"] for item in completed] == ["Goblin", "Descendants of the Sun"]
    assert completed[0]["date_finish"] == "2026-09-22"
    # "0000-00-00" is the API's placeholder for no date.
    assert completed[1]["date_finish"] is None
    assert data.lists[CATEGORY_PLAN_TO_WATCH][0]["name"] == "Vincenzo"
    assert data.lists[CATEGORY_ON_HOLD] == []
    # The deleted sync entry is dropped.
    assert [item["name"] for item in data.lists[CATEGORY_DROPPED]] == ["The Heirs"]

    assert data.stats["episodes_watched"] == 4914
    assert data.stats["minutes_watched"] == 251974
    assert data.stats["mean_score"] == 7.75
    assert data.unread == {"notifications": 3, "friend_requests": 1, "messages": 0}


async def test_unchanged_last_activity_skips_list_fetch(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data.coordinator
    assert mock_mdl_client.watchlist.fetch.await_count == 5
    mock_mdl_client.watchlist.fetch.reset_mock()

    await coordinator.async_refresh()
    assert mock_mdl_client.watchlist.fetch.await_count == 0
    assert coordinator.data.total_count == 5

    mock_mdl_client.watchlist.get_last_activities.return_value = LastActivity(
        all="2026-11-13T12:00:00Z"
    )
    await coordinator.async_refresh()
    assert mock_mdl_client.watchlist.fetch.await_count == 5
    # The profile is only read once.
    mock_mdl_client.account.get_profile.assert_awaited_once()


async def test_missing_last_activity_always_fetches(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_mdl_client.watchlist.get_last_activities.return_value = LastActivity()
    await setup_integration(hass, mock_config_entry)
    mock_mdl_client.watchlist.fetch.reset_mock()

    await mock_config_entry.runtime_data.coordinator.async_refresh()
    assert mock_mdl_client.watchlist.fetch.await_count == 5


async def test_stats_failure_keeps_lists_working(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_mdl_client.users.get_user_stats.side_effect = MDLNetworkError(
        "Forbidden", status_code=403
    )
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    data = mock_config_entry.runtime_data.coordinator.data
    assert data.stats is None
    assert data.total_count == 5


async def test_coordinator_relogs_in_when_refresh_fails(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    fetch = mock_mdl_client.watchlist.fetch
    original = fetch.side_effect
    calls = 0

    def _expire_once(status):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _auth_error()
        return original(status)

    fetch.side_effect = _expire_once

    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_mdl_client.auth.login.await_count == 2


async def test_coordinator_auth_failure_starts_reauth(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_mdl_client.auth.login = AsyncMock(side_effect=_auth_error())

    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    assert len(_reauth_flows(hass)) == 1
    mock_mdl_client.aclose.assert_awaited_once()


async def test_coordinator_update_failure(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_mdl_client.watchlist.fetch = AsyncMock(
        side_effect=MDLServerError("Server error", status_code=500)
    )

    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert _reauth_flows(hass) == []
    mock_mdl_client.aclose.assert_awaited_once()


async def test_calendar_failure_does_not_block_setup(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_mdl_client.calendar.episodes.side_effect = MDLServerError("down", status_code=503)

    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data.calendar.data is None


async def test_migrate_kuryana_entry_requests_password(
    hass: HomeAssistant, mock_mdl_client: MagicMock
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        unique_id="testuser",
        data={"user_id": "testuser", "api_url": "https://kuryana.tbdh.app/"},
    )

    await setup_integration(hass, entry)

    assert entry.version == 2
    assert entry.data[CONF_USERNAME] == "testuser"
    assert entry.data[CONF_DEVICE_ID]
    assert set(entry.data) == {CONF_USERNAME, CONF_DEVICE_ID}
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert len(_reauth_flows(hass)) == 1
    mock_mdl_client.auth.login.assert_not_awaited()


async def test_unload_closes_client(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    mock_mdl_client.aclose.assert_awaited_once()


async def test_diagnostics_redacts_credentials(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert diagnostics["config_entry"]["data"][CONF_USERNAME] == "testuser"
    assert diagnostics["config_entry"]["data"][CONF_PASSWORD] == "**REDACTED**"
    assert "someone@example.com" not in str(diagnostics)
    assert len(diagnostics["coordinator_data"]["lists"][CATEGORY_COMPLETED]) == 2
    assert diagnostics["calendar"]["airings"] == 5
