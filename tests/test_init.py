from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path
from unittest.mock import MagicMock

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.service import async_get_all_descriptions
from homeassistant.setup import async_setup_component

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mydramalist.const import DOMAIN, VERSION

from .conftest import setup_integration

COMPONENT = Path(__file__).parent.parent / "custom_components" / DOMAIN


async def test_cards_are_served_and_loaded(
    hass: HomeAssistant,
    hass_client_no_auth,
    mock_mdl_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    await async_setup_component(hass, "http", {})
    extra_modules = MagicMock()
    hass.data[DATA_EXTRA_MODULE_URL] = extra_modules

    await setup_integration(hass, mock_config_entry)

    url = f"/mydramalist_static/mydramalist-card.js?v={VERSION}"
    extra_modules.add.assert_called_once_with(url)
    client = await hass_client_no_auth()
    response = await client.get(url)
    assert response.status == HTTPStatus.OK
    body = await response.text()
    assert 'customElements.define(type, cls)' in body
    assert f'const VERSION = "{VERSION}"' in body


async def test_setup_without_http(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    assert hass.http is None
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get("sensor.mydramalist_completed") is not None


def test_versions_match() -> None:
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert manifest["version"] == VERSION


def test_translations_match_strings() -> None:
    assert (COMPONENT / "strings.json").read_text() == (
        COMPONENT / "translations" / "en.json"
    ).read_text()


async def test_service_descriptions(
    hass: HomeAssistant, mock_mdl_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, mock_config_entry)

    descriptions = (await async_get_all_descriptions(hass))[DOMAIN]
    strings = json.loads((COMPONENT / "strings.json").read_text())["services"]
    icons = json.loads((COMPONENT / "icons.json").read_text())["services"]

    assert set(descriptions) == set(strings) == set(icons)
    for service, description in descriptions.items():
        assert set(description["fields"]) == set(strings[service].get("fields", {})), service
        assert "config_entry_id" in description["fields"], service
