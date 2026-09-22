"""Config flow for Interstellar Network."""
from __future__ import annotations
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from .api import InterstellarApiClient, InterstellarCannotConnect, InterstellarInvalidResponse
from .const import CONF_URL, CONF_VERIFY_SSL, DOMAIN, REQUEST_TIMEOUT_SECONDS


def normalize_url(url: str) -> str:
    return url.strip().rstrip("/")

def machine_id(data: dict[str, Any]) -> str:
    host = data.get("host", {})
    return host.get("machine_id") or data.get("machine_id") or host.get("hostname") or data.get("hostname") or ""

def hostname(data: dict[str, Any]) -> str:
    host = data.get("host", {})
    return host.get("hostname") or data.get("hostname") or "Interstellar Network node"

async def validate(hass, url: str, verify_ssl: bool) -> dict[str, Any]:
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    return await InterstellarApiClient(session, url, REQUEST_TIMEOUT_SECONDS).async_get_stats()

class InterstellarServerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered_url: str | None = None
        self._discovered_data: dict[str, Any] | None = None

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            url = normalize_url(user_input[CONF_URL])
            verify_ssl = user_input[CONF_VERIFY_SSL]
            try:
                data = await validate(self.hass, url, verify_ssl)
            except InterstellarCannotConnect:
                errors["base"] = "cannot_connect"
            except InterstellarInvalidResponse:
                errors["base"] = "invalid_response"
            else:
                uid = machine_id(data)
                if uid:
                    await self.async_set_unique_id(uid)
                    self._abort_if_unique_id_configured(updates={CONF_URL:url, CONF_VERIFY_SSL:verify_ssl})
                return self.async_create_entry(title=hostname(data), data={CONF_URL:url, CONF_VERIFY_SSL:verify_ssl})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({vol.Required(CONF_URL):str, vol.Required(CONF_VERIFY_SSL, default=True):bool}), errors=errors)

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo):
        props = discovery_info.properties or {}
        url = props.get("url") or props.get("URL") or ""
        if not url:
            return self.async_abort(reason="missing_url")
        url = normalize_url(str(url))
        try:
            data = await validate(self.hass, url, True)
        except (InterstellarCannotConnect, InterstellarInvalidResponse):
            return self.async_abort(reason="cannot_connect")
        uid = props.get("machine_id") or props.get("id") or machine_id(data)
        if not uid:
            return self.async_abort(reason="missing_unique_id")
        await self.async_set_unique_id(str(uid))
        self._abort_if_unique_id_configured(updates={CONF_URL:url, CONF_VERIFY_SSL:True})
        self._discovered_url, self._discovered_data = url, data
        self.context["title_placeholders"] = {"name": hostname(data)}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(self, user_input=None):
        if self._discovered_url is None or self._discovered_data is None:
            return self.async_abort(reason="cannot_connect")
        if user_input is not None:
            return self.async_create_entry(title=hostname(self._discovered_data), data={CONF_URL:self._discovered_url, CONF_VERIFY_SSL:True})
        return self.async_show_form(step_id="zeroconf_confirm", description_placeholders={"name":hostname(self._discovered_data), "url":self._discovered_url})
