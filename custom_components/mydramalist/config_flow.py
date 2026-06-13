from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig

from kuryana import AsyncKuryana
from kuryana.types.user import UserQuery

from .const import CONF_API_URL, CONF_USER_ID, DEFAULT_API_URL, DOMAIN, NAME


class MyDramaListConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            user_id = user_input[CONF_USER_ID].strip()
            api_url = user_input.get(CONF_API_URL, "").strip() or DEFAULT_API_URL

            if not api_url.endswith("/"):
                api_url += "/"

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
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USER_ID): TextSelector(),
                    vol.Optional(CONF_API_URL, default=DEFAULT_API_URL): TextSelector(
                        TextSelectorConfig(type="url")
                    ),
                }
            ),
            errors=errors,
        )
