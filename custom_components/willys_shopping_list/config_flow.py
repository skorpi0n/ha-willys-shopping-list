"""Config flow for Willys shopping list."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WillysApi, WillysApiError, WillysAuthError
from .const import CONF_PASSWORD, CONF_USERNAME, DOMAIN


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the user setup flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, str] | None = None):
        """Ask for credentials and validate them with Willys."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id("willys_account")
            self._abort_if_unique_id_configured()
            api = WillysApi(async_get_clientsession(self.hass))
            try:
                await api.async_login(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            except WillysApiError as err:
                errors["base"] = "invalid_auth" if isinstance(err, WillysAuthError) else "cannot_connect"
            else:
                return self.async_create_entry(
                    title="Willys",
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, str]):
        """Start credential repair when Willys rejects a saved password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, str] | None = None):
        """Validate and save a replacement password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            api = WillysApi(async_get_clientsession(self.hass))
            try:
                await api.async_login(entry.data[CONF_USERNAME], user_input[CONF_PASSWORD])
            except WillysApiError as err:
                errors["base"] = "invalid_auth" if isinstance(err, WillysAuthError) else "cannot_connect"
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )
