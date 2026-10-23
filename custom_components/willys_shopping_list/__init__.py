"""Willys shopping list integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WillysApi, WillysApiError, WillysAuthError
from .const import (
    ATTR_DELTA,
    ATTR_LIST_ID,
    ATTR_NAME,
    ATTR_PICK_UNIT,
    ATTR_PRODUCT_CODE,
    ATTR_QUANTITY,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
    SERVICE_ADD_PRODUCT,
    SERVICE_CHANGE_QUANTITY,
    SERVICE_CREATE_LIST,
    SERVICE_DELETE_LIST,
    SERVICE_GET_LIST,
    SERVICE_GET_LISTS,
    SERVICE_REMOVE_PRODUCT,
)

_LIST_ID_SCHEMA = vol.Required(ATTR_LIST_ID)
_PRODUCT_SCHEMA = {
    vol.Required(ATTR_LIST_ID): cv.string,
    vol.Required(ATTR_PRODUCT_CODE): cv.string,
}


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register integration actions, including before account setup completes."""

    def get_api(call: ServiceCall) -> WillysApi:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries or entries[0].runtime_data is None:
            raise ServiceValidationError("Lägg först till Willys-integrationen i Home Assistant.")
        return entries[0].runtime_data

    async def get_lists(call: ServiceCall) -> dict[str, Any]:
        return {"lists": await get_api(call).async_get_lists()}

    async def get_list(call: ServiceCall) -> dict[str, Any]:
        return await get_api(call).async_get_list(call.data[ATTR_LIST_ID])

    async def create_list(call: ServiceCall) -> None:
        await get_api(call).async_create_list(call.data[ATTR_NAME])

    async def delete_list(call: ServiceCall) -> None:
        await get_api(call).async_delete_list(call.data[ATTR_LIST_ID])

    async def add_product(call: ServiceCall) -> None:
        await get_api(call).async_add_product(
            call.data[ATTR_LIST_ID],
            call.data[ATTR_PRODUCT_CODE],
            call.data[ATTR_QUANTITY],
            call.data.get(ATTR_PICK_UNIT, "pieces"),
        )

    async def remove_product(call: ServiceCall) -> None:
        await get_api(call).async_remove_product(
            call.data[ATTR_LIST_ID], call.data[ATTR_PRODUCT_CODE]
        )

    async def change_quantity(call: ServiceCall) -> None:
        await get_api(call).async_change_quantity(
            call.data[ATTR_LIST_ID],
            call.data[ATTR_PRODUCT_CODE],
            call.data[ATTR_DELTA],
        )

    schemas: dict[str, vol.Schema] = {
        SERVICE_GET_LISTS: vol.Schema({}),
        SERVICE_GET_LIST: vol.Schema({_LIST_ID_SCHEMA: cv.string}),
        SERVICE_CREATE_LIST: vol.Schema({vol.Required(ATTR_NAME): cv.string}),
        SERVICE_DELETE_LIST: vol.Schema({_LIST_ID_SCHEMA: cv.string}),
        SERVICE_ADD_PRODUCT: vol.Schema(
            {
                **_PRODUCT_SCHEMA,
                vol.Required(ATTR_QUANTITY): vol.All(int, vol.Range(min=1)),
                vol.Optional(ATTR_PICK_UNIT, default="pieces"): cv.string,
            }
        ),
        SERVICE_REMOVE_PRODUCT: vol.Schema(_PRODUCT_SCHEMA),
        SERVICE_CHANGE_QUANTITY: vol.Schema(
            {
                **_PRODUCT_SCHEMA,
                vol.Required(ATTR_DELTA): vol.All(
                    int,
                    vol.Any(vol.Range(min=-100, max=-1), vol.Range(min=1, max=100)),
                ),
            }
        ),
    }

    handlers = {
        SERVICE_GET_LISTS: (get_lists, SupportsResponse.ONLY),
        SERVICE_GET_LIST: (get_list, SupportsResponse.ONLY),
        SERVICE_CREATE_LIST: (create_list, SupportsResponse.NONE),
        SERVICE_DELETE_LIST: (delete_list, SupportsResponse.NONE),
        SERVICE_ADD_PRODUCT: (add_product, SupportsResponse.NONE),
        SERVICE_REMOVE_PRODUCT: (remove_product, SupportsResponse.NONE),
        SERVICE_CHANGE_QUANTITY: (change_quantity, SupportsResponse.NONE),
    }

    for service, (handler, response_mode) in handlers.items():
        hass.services.async_register(
            DOMAIN,
            service,
            handler,
            schema=schemas[service],
            supports_response=response_mode,
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: Any) -> bool:
    """Log in to Willys and store the live API client for actions."""
    api = WillysApi(async_get_clientsession(hass))
    try:
        await api.async_login(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    except WillysAuthError as err:
        raise ConfigEntryAuthFailed("Willys avvisade inloggningsuppgifterna.") from err
    except WillysApiError as err:
        raise ConfigEntryNotReady(f"Kunde inte ansluta till Willys: {err}") from err
    entry.runtime_data = api
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Any) -> bool:
    """Clear the live client when the config entry is unloaded."""
    entry.runtime_data = None
    return True
