"""Config flow for Interstellar Network."""
from __future__ import annotations
from typing import Any
from urllib.parse import urlsplit
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from .api import InterstellarApiClient, InterstellarCannotConnect, InterstellarInvalidResponse
from .const import (CONF_URL, CONF_CONTROL_URL, CONF_VERIFY_SSL, CONF_WOL_ENABLED,
                    CONF_WOL_MAC, CONF_WOL_BROADCAST, CONTROL_SERVE_PORT, DOMAIN,
                    REQUEST_TIMEOUT_SECONDS)
from .wol import normalize_mac, validate_broadcast


def normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


def suggested_control_url(health_url: str) -> str:
    """Canonical control topology is the health host on port 8443.

    Only suggested for a Tailscale MagicDNS host served over HTTPS on the
    default port. Anything else (a plain LAN address, a custom port, a reverse
    proxy) is left to the operator, since the control listener is a separate
    Serve handler that may not exist there.
    """
    parsed = urlsplit(normalize_url(health_url))
    if parsed.scheme != "https" or not parsed.hostname or parsed.port or parsed.path:
        return ""
    if not parsed.hostname.endswith(".ts.net"):
        return ""
    return f"https://{parsed.hostname}:{CONTROL_SERVE_PORT}"

def machine_id(data: dict[str, Any]) -> str:
    host = data.get("host", {})
    return host.get("machine_id") or data.get("machine_id") or host.get("hostname") or data.get("hostname") or ""

def hostname(data: dict[str, Any]) -> str:
    host = data.get("host", {})
    return host.get("hostname") or data.get("hostname") or "Interstellar Network node"


def legacy_entry_exists(hass, uid: str, url: str) -> bool:
    """Avoid a second device while the old integration still owns this server."""
    return any(entry.unique_id == uid or normalize_url(entry.data.get(CONF_URL, "")) == url
               for entry in hass.config_entries.async_entries("interstellar_server"))

async def validate(hass, url: str, verify_ssl: bool) -> dict[str, Any]:
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    return await InterstellarApiClient(session, url, REQUEST_TIMEOUT_SECONDS).async_get_stats()

class InterstellarServerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return InterstellarOptionsFlow()

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
                if uid and legacy_entry_exists(self.hass, uid, url):
                    return self.async_abort(reason="legacy_entry_exists")
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
        uid = machine_id(data) or props.get("machine_id") or props.get("id")
        if not uid:
            return self.async_abort(reason="missing_unique_id")
        if legacy_entry_exists(self.hass, str(uid), url):
            return self.async_abort(reason="legacy_entry_exists")
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


class InterstellarOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        try:
            entry = self.config_entry
        except ValueError:
            entry = None
        options = entry.options if entry else {}
        reported = (entry.runtime_data.coordinator.data or {}).get("wake_on_lan", {}) if entry and getattr(entry, "runtime_data", None) else {}
        if user_input is not None:
            value = normalize_url(user_input.get(CONF_CONTROL_URL, ""))
            # A URL that is already stored keeps working. Only a changed value has
            # to meet the canonical rules, so an existing path-based control URL is
            # never silently broken by reopening this form.
            if value and value != normalize_url(options.get(CONF_CONTROL_URL, "")):
                parsed = urlsplit(value)
                if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                        or parsed.path or parsed.query or parsed.fragment):
                    return self.async_show_form(step_id="init", data_schema=self._schema(user_input), errors={CONF_CONTROL_URL: "https_required"})
            enabled = bool(user_input.get(CONF_WOL_ENABLED, False))
            raw_mac = user_input.get(CONF_WOL_MAC, "").strip()
            raw_broadcast = user_input.get(CONF_WOL_BROADCAST, "").strip()
            errors = {}
            try:
                mac = normalize_mac(raw_mac) if raw_mac else ""
            except ValueError:
                errors[CONF_WOL_MAC] = "invalid_mac"
                mac = ""
            try:
                broadcast = validate_broadcast(raw_broadcast) if raw_broadcast else ""
            except ValueError:
                errors[CONF_WOL_BROADCAST] = "invalid_broadcast"
                broadcast = ""
            if enabled and not errors:
                if not mac:
                    errors[CONF_WOL_MAC] = "invalid_mac"
                if not broadcast:
                    errors[CONF_WOL_BROADCAST] = "missing_broadcast"
            if errors:
                return self.async_show_form(step_id="init", data_schema=self._schema(user_input), errors=errors)
            return self.async_create_entry(title="", data={CONF_CONTROL_URL: value,
                CONF_WOL_ENABLED: enabled, CONF_WOL_MAC: mac, CONF_WOL_BROADCAST: broadcast})
        # Prefill the canonical :8443 control URL for a MagicDNS health host, but
        # never replace a control URL the operator already configured.
        control_url = options.get(CONF_CONTROL_URL, "")
        if not control_url and entry:
            control_url = suggested_control_url(entry.data.get(CONF_URL, ""))
        return self.async_show_form(step_id="init", data_schema=self._schema({
            CONF_CONTROL_URL: control_url,
            CONF_WOL_ENABLED: options.get(CONF_WOL_ENABLED, reported.get("enabled", False)),
            CONF_WOL_MAC: options.get(CONF_WOL_MAC) or reported.get("mac_address") or "",
            CONF_WOL_BROADCAST: options.get(CONF_WOL_BROADCAST) or reported.get("broadcast_address") or "",
        }))

    @staticmethod
    def _schema(defaults):
        return vol.Schema({
            vol.Optional(CONF_CONTROL_URL, default=defaults.get(CONF_CONTROL_URL, "")): str,
            vol.Optional(CONF_WOL_ENABLED, default=defaults.get(CONF_WOL_ENABLED, False)): bool,
            vol.Optional(CONF_WOL_MAC, default=defaults.get(CONF_WOL_MAC, "")): str,
            vol.Optional(CONF_WOL_BROADCAST, default=defaults.get(CONF_WOL_BROADCAST, "")): str,
        })
