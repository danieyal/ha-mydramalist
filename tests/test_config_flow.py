from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant

from custom_components.mydramalist.config_flow import MyDramaListConfigFlow
from custom_components.mydramalist.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    pass


async def test_user_step_form(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_user_flow_success(
    hass: HomeAssistant, mock_kuryana_client: MagicMock, mock_user_query
) -> None:
    mock_kuryana_client.get_user = AsyncMock(return_value=mock_user_query)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"user_id": "testuser", "api_url": "https://kuryana.tbdh.app"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "MyDramaList (testuser)"
    assert result["data"]["user_id"] == "testuser"
    assert result["data"]["api_url"] == "https://kuryana.tbdh.app/"


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, mock_kuryana_client: MagicMock
) -> None:
    mock_kuryana_client.get_user = AsyncMock(
        side_effect=Exception("Connection error")
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"user_id": "baduser", "api_url": "https://kuryana.tbdh.app"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_already_configured(
    hass: HomeAssistant,
    mock_kuryana_client: MagicMock,
    mock_user_query,
) -> None:
    mock_kuryana_client.get_user = AsyncMock(return_value=mock_user_query)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"user_id": "testuser", "api_url": "https://kuryana.tbdh.app"},
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"user_id": "TESTUSER", "api_url": "https://kuryana.tbdh.app"},
    )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
