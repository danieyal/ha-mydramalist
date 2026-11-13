from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from mdl import AsyncMDLClient, MDLAuthError
from mdl.auth import generate_device_id

from .const import (
    CATEGORIES,
    CONF_CALENDAR_CATEGORIES,
    CONF_DEVICE_ID,
    CONF_UPDATE_INTERVAL,
    DEFAULT_CALENDAR_CATEGORIES,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
    NAME,
)

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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> MyDramaListOptionsFlow:
        return MyDramaListOptionsFlow()

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


class MyDramaListOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            user_input[CONF_UPDATE_INTERVAL] = int(user_input[CONF_UPDATE_INTERVAL])
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_UPDATE_INTERVAL,
                        max=MAX_UPDATE_INTERVAL,
                        step=5,
                        unit_of_measurement="min",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_CALENDAR_CATEGORIES,
                    default=options.get(CONF_CALENDAR_CATEGORIES, DEFAULT_CALENDAR_CATEGORIES),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=CATEGORIES,
                        multiple=True,
                        translation_key=CONF_CALENDAR_CATEGORIES,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
