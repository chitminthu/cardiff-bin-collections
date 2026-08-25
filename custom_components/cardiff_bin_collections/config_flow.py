"""Config flow for Cardiff Bin Collections."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
)

from .api import (
    AddressMatch,
    CardiffBinCollectionsApi,
    CardiffBinCollectionsConnectionError,
    CardiffBinCollectionsNoAddresses,
    CardiffBinCollectionsResponseError,
    CollectionData,
    format_postcode,
)
from .const import (
    CONF_ADDRESS,
    CONF_POSTCODE,
    CONF_UPRN,
    DOMAIN,
    PENDING_COLLECTIONS,
    UK_POSTCODE_PATTERN,
)


class CardiffBinCollectionsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle configuration for Cardiff Bin Collections."""

    VERSION = 2

    def __init__(self) -> None:
        self._postcode = ""
        self._addresses: dict[str, AddressMatch] = {}
        self._reconfigure_entry = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a Cardiff postcode and retrieve matching addresses."""
        return await self._async_postcode_step("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow the property to be changed from the integration UI."""
        self._reconfigure_entry = self._get_reconfigure_entry()
        return await self._async_postcode_step("reconfigure", user_input)

    async def _async_postcode_step(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Validate a postcode and retrieve matching addresses."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._postcode = format_postcode(str(user_input[CONF_POSTCODE]))
            if not re.fullmatch(UK_POSTCODE_PATTERN, self._postcode):
                errors[CONF_POSTCODE] = "invalid_postcode"
            else:
                api = CardiffBinCollectionsApi(async_get_clientsession(self.hass))
                try:
                    matches = await api.search_addresses(self._postcode)
                except CardiffBinCollectionsNoAddresses:
                    errors["base"] = "no_addresses"
                except CardiffBinCollectionsConnectionError:
                    errors["base"] = "cannot_connect"
                except CardiffBinCollectionsResponseError:
                    errors["base"] = "invalid_response"
                else:
                    self._addresses = {str(match.uprn): match for match in matches}
                    if step_id == "reconfigure":
                        return await self.async_step_reconfigure_address()
                    return await self.async_step_address()

        suggested_postcode = (
            self._reconfigure_entry.data.get(CONF_POSTCODE, "")
            if self._reconfigure_entry is not None
            else ""
        )
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POSTCODE, default=suggested_postcode
                    ): TextSelector()
                }
            ),
            errors=errors,
        )

    async def async_step_address(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user select a matching residential address."""
        return await self._async_address_step("address", user_input)

    async def async_step_reconfigure_address(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select and validate a replacement property."""
        return await self._async_address_step("reconfigure_address", user_input)

    async def _async_address_step(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Select an address and confirm collection data is available."""
        errors: dict[str, str] = {}
        if user_input is not None:
            uprn_text = str(user_input[CONF_UPRN])
            match = self._addresses[uprn_text]
            try:
                collections = await CardiffBinCollectionsApi(
                    async_get_clientsession(self.hass)
                ).collections(match.uprn)
            except CardiffBinCollectionsConnectionError:
                errors["base"] = "cannot_connect"
            except CardiffBinCollectionsResponseError:
                errors["base"] = "invalid_response"
            else:
                if not collections.weeks:
                    errors["base"] = "no_collections"
                else:
                    data = {
                        CONF_UPRN: match.uprn,
                        CONF_ADDRESS: match.address,
                        CONF_POSTCODE: self._postcode,
                    }
                    if self._reconfigure_entry is not None:
                        await self.async_set_unique_id(uprn_text)
                        self._abort_if_unique_id_configured()
                        self._stage_collections(match.uprn, collections)
                        return self.async_update_reload_and_abort(
                            self._reconfigure_entry,
                            title=match.address,
                            data=data,
                            unique_id=uprn_text,
                        )
                    await self.async_set_unique_id(uprn_text)
                    self._abort_if_unique_id_configured()
                    self._stage_collections(match.uprn, collections)
                    return self.async_create_entry(title=match.address, data=data)

        selector = SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"value": uprn, "label": match.address}
                    for uprn, match in self._addresses.items()
                ]
            )
        )
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({vol.Required(CONF_UPRN): selector}),
            errors=errors,
        )

    def _stage_collections(self, uprn: int, data: CollectionData) -> None:
        """Pass already-validated data to setup without another council request."""
        self.hass.data.setdefault(PENDING_COLLECTIONS, {})[str(uprn)] = data
