from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from mdl import AsyncMDLClient, MDLAuthError
from mdl.auth import generate_device_id

from .const import CONF_DEVICE_ID, DOMAIN, NAME

_PASSWORD_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)


def _build_schema(default_username: Any = vol.UNDEFINED) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_USERNAME, default=default_username): TextSelector(
                TextSelectorConfig(autocomplete="username")
            ),
            vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
        }
    )


async def _async_validate_login(
    username: str, password: str, device_id: str
) -> dict[str, str]:
    client = AsyncMDLClient(device_id=device_id)
    try:
        await client.auth.login(username, password)
    except MDLAuthError:
        return {"base": "invalid_auth"}
    except Exception:
        return {"base": "cannot_connect"}
    finally:
        await client.aclose()
    return {}


class MyDramaListConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_configured()

            device_id = generate_device_id()
            errors = await _async_validate_login(username, password, device_id)
            if not errors:
                return self.async_create_entry(
                    title=f"{NAME} ({username})",
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_DEVICE_ID: device_id,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        username = entry.data[CONF_USERNAME]

        errors: dict[str, str] = {}

        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            errors = await _async_validate_login(
                username, password, entry.data[CONF_DEVICE_ID]
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: password}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR}),
            description_placeholders={"username": username},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()

        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_mismatch()

            errors = await _async_validate_login(
                username, password, entry.data[CONF_DEVICE_ID]
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                    title=f"{NAME} ({username})",
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_build_schema(entry.data[CONF_USERNAME]),
            errors=errors,
        )
