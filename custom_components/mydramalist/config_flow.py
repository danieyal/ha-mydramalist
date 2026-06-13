from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig

from kuryana import AsyncKuryana
from kuryana.types.user import UserQuery

from .const import CONF_API_URL, CONF_USER_ID, DEFAULT_API_URL, DOMAIN, NAME


def _normalize_api_url(url: str) -> str:
    url = url.strip()
    if not url.endswith("/"):
        url += "/"
    return url


def _build_schema(default_api_url: str = DEFAULT_API_URL) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_USER_ID): TextSelector(),
            vol.Optional(CONF_API_URL, default=default_api_url): TextSelector(
                TextSelectorConfig(type="url")
            ),
        }
    )


class MyDramaListConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            user_id = user_input[CONF_USER_ID].strip()
            api_url = _normalize_api_url(
                user_input.get(CONF_API_URL, "") or DEFAULT_API_URL
            )

            try:
                client = AsyncKuryana(base_url=api_url)
                result: UserQuery = await client.get_user(user_id)
                await client.client.aclose()
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_id.lower())
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"{NAME} ({result.data.link.rstrip('/').split('/')[-1]})",
                    data={
                        CONF_USER_ID: user_id,
                        CONF_API_URL: api_url,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        current_user_id = entry.data.get(CONF_USER_ID, "")
        current_api_url = entry.data.get(CONF_API_URL, DEFAULT_API_URL)

        errors: dict[str, str] = {}

        if user_input is not None:
            user_id = user_input[CONF_USER_ID].strip()
            api_url = _normalize_api_url(
                user_input.get(CONF_API_URL, "") or DEFAULT_API_URL
            )

            try:
                client = AsyncKuryana(base_url=api_url)
                result: UserQuery = await client.get_user(user_id)
                await client.client.aclose()
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_id.lower())
                self._abort_if_unique_id_mismatch()

                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_USER_ID: user_id,
                        CONF_API_URL: api_url,
                    },
                    title=f"{NAME} ({result.data.link.rstrip('/').split('/')[-1]})",
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USER_ID, default=current_user_id): TextSelector(),
                    vol.Optional(
                        CONF_API_URL, default=current_api_url
                    ): TextSelector(TextSelectorConfig(type="url")),
                }
            ),
            errors=errors,
        )
