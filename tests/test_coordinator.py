from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from mdl import MDLAuthError, MDLServerError
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

from .conftest import setup_integration


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

    data = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"].data
    assert data["total_count"] == 4

    assert data[CATEGORY_WATCHING] == {
        "items": [],
        "count": 0,
        "stats": {"episodes_seen": 0},
    }
    assert data[CATEGORY_COMPLETED]["count"] == 2
    assert data[CATEGORY_COMPLETED]["items"][0] == {
        "name": "Goblin",
        "id": 18452,
        "score": 10,
        "episode_seen": 16,
        "episode_total": 16,
    }
    assert data[CATEGORY_COMPLETED]["stats"] == {"episodes_seen": 32}
    assert data[CATEGORY_PLAN_TO_WATCH]["items"][0]["name"] == "Vincenzo"
    assert data[CATEGORY_ON_HOLD]["count"] == 0
    # The deleted sync entry is dropped.
    assert data[CATEGORY_DROPPED]["count"] == 1
    assert data[CATEGORY_DROPPED]["items"][0]["name"] == "The Heirs"


async def test_coordinator_relogs_in_when_token_expires(
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


async def test_diagnostics_redacts_password(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert diagnostics["config_entry"]["data"][CONF_USERNAME] == "testuser"
    assert diagnostics["config_entry"]["data"][CONF_PASSWORD] == "**REDACTED**"
    assert diagnostics["coordinator_data"]["total_count"] == 4
