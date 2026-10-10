from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from mdl import MDLAuthError, MDLServerError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mydramalist.const import CONF_DEVICE_ID, DOMAIN

from .conftest import setup_integration


async def test_user_step_form(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_user_flow_success(
    hass: HomeAssistant, mock_mdl_client: MagicMock
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: " testuser ", CONF_PASSWORD: "secret"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "MyDramaList (testuser)"
    assert result["data"][CONF_USERNAME] == "testuser"
    assert result["data"][CONF_PASSWORD] == "secret"
    assert result["data"][CONF_DEVICE_ID]
    assert result["result"].unique_id == "testuser"
    mock_mdl_client.auth.login.assert_any_await("testuser", "secret")


async def test_user_flow_invalid_auth(
    hass: HomeAssistant, mock_mdl_client: MagicMock
) -> None:
    mock_mdl_client.auth.login = AsyncMock(
        side_effect=MDLAuthError("Unauthorized", status_code=401)
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "testuser", CONF_PASSWORD: "wrong"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    mock_mdl_client.aclose.assert_awaited_once()


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, mock_mdl_client: MagicMock
) -> None:
    mock_mdl_client.auth.login = AsyncMock(
        side_effect=MDLServerError("Server error", status_code=500)
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "testuser", CONF_PASSWORD: "secret"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "TESTUSER", CONF_PASSWORD: "secret"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_mdl_client.auth.login.assert_not_awaited()


async def test_reauth_flow(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)

    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["username"] == "testuser"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-secret"}
    )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "new-secret"
    assert mock_config_entry.data[CONF_DEVICE_ID] == "device-123"


async def test_reauth_flow_invalid_auth(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)
    mock_mdl_client.auth.login = AsyncMock(
        side_effect=MDLAuthError("Unauthorized", status_code=401)
    )

    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "wrong"}
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert mock_config_entry.data[CONF_PASSWORD] == "secret"


async def test_reconfigure_flow(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)

    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "TestUser", CONF_PASSWORD: "new-secret"}
    )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_USERNAME] == "TestUser"
    assert mock_config_entry.data[CONF_PASSWORD] == "new-secret"
    assert mock_config_entry.title == "MyDramaList (TestUser)"


async def test_reconfigure_flow_other_user(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)

    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "someoneelse", CONF_PASSWORD: "secret"}
    )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"
