"""Interstellar Network monitoring and optional server control."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import voluptuous as vol
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .api import InterstellarApiClient, InterstellarApiError
from .const import CARD_PATH, CONF_CONTROL_URL, CONF_URL, CONF_VERIFY_SSL, DOMAIN, PLATFORMS, REQUEST_TIMEOUT_SECONDS
from .coordinator import InterstellarCoordinator
from .repairs import async_delete_repairs, async_update_repairs
from .wol import async_send_magic_packet, effective_wol

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ACTION_ROUTES = {
    "refresh_stats": None,
    "reboot": "/actions/reboot",
    "shutdown": "/actions/shutdown",
    "refresh_packages": "/actions/update/refresh",
    "install_security_updates": "/actions/update/install",
    "install_all_updates": "/actions/update/install",
    "start_service": "/actions/service/start",
    "stop_service": "/actions/service/stop",
    "restart_service": "/actions/service/restart",
    "start_container": "/actions/docker/start",
    "stop_container": "/actions/docker/stop",
    "restart_container": "/actions/docker/restart",
    "restart_docker": "/actions/docker/restart-daemon",
    "restart_health_agent": "/actions/interstellar/restart-health-agent",
    "restart_control_agent": "/actions/interstellar/restart-control-agent",
    "restart_mdns": "/actions/interstellar/restart-mdns",
    "restart_tailscaled": "/actions/tailscale/restart",
}
POWER_ACTIONS = {"reboot", "shutdown"}


@dataclass
class InterstellarRuntimeData:
    coordinator: InterstellarCoordinator
    control_client: InterstellarApiClient | None = None
    repair_issue_ids: set[str] = field(default_factory=set)
    entry: ConfigEntry | None = None


type InterstellarConfigEntry = ConfigEntry[InterstellarRuntimeData]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    card = Path(__file__).parent / "frontend" / "interstellar-network-card.js"
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_PATH, str(card), False)])
    hass.data.setdefault(DOMAIN, {})

    async def require_admin(call: ServiceCall) -> None:
        user_id = getattr(call.context, "user_id", None)
        if not user_id:
            raise HomeAssistantError("An authenticated Home Assistant administrator is required")
        user = await hass.auth.async_get_user(user_id)
        if user is None or not user.is_admin:
            raise HomeAssistantError("A Home Assistant administrator is required")

    async def handle_action(call: ServiceCall) -> dict:
        await require_admin(call)
        machine = call.data["server"]
        runtime = next((r for r in hass.data[DOMAIN].values()
                        if r.coordinator.data.get("host", {}).get("machine_id") == machine), None)
        if runtime is None:
            raise HomeAssistantError("Server is not configured")
        action = call.data["action"]
        if action == "refresh_stats":
            await runtime.coordinator.async_request_refresh()
            return {"status": "refreshed"} if call.return_response else None
        if runtime.control_client is None:
            raise HomeAssistantError("Server control is not configured")
        control = runtime.coordinator.data.get("_control", {})
        if (not runtime.coordinator.last_update_success or control.get("available") is False
                or control.get("control_available") is False):
            raise HomeAssistantError("Server control is unavailable")
        host = runtime.coordinator.data.get("host", {}).get("hostname", "")
        if action in POWER_ACTIONS and call.data.get("confirmation") != host:
            raise HomeAssistantError(f"Confirm the server hostname ({host}) before {action}")
        target = call.data.get("target", "")
        if action in POWER_ACTIONS:
            body = {"confirm_hostname": host}
        elif action.endswith("_service"):
            body = {"service": target}
        elif action.endswith("_container"):
            body = {"container": target}
        elif action == "install_security_updates":
            body = {"type": "security"}
        elif action == "install_all_updates":
            body = {"type": "all"}
        else:
            if target:
                raise HomeAssistantError("This action does not accept a target")
            body = {}
        try:
            result = await runtime.control_client.async_action(ACTION_ROUTES[action], body)
        except InterstellarApiError as err:
            raise HomeAssistantError(str(err)) from err
        hass.async_create_task(runtime.coordinator.async_request_refresh())
        return result if call.return_response else None

    async def handle_wake(call: ServiceCall) -> dict:
        await require_admin(call)
        machine = call.data["server"]
        runtime = next((r for r in hass.data[DOMAIN].values()
                        if (r.entry and r.entry.unique_id == machine)
                        or (r.coordinator.data or {}).get("host", {}).get("machine_id") == machine), None)
        if runtime is None or runtime.entry is None:
            raise HomeAssistantError("Server is not configured")
        settings = effective_wol(runtime.entry.options, runtime.coordinator.data or runtime.coordinator.last_known)
        if not settings["configured"]:
            raise HomeAssistantError("Wake-on-LAN requires an enabled MAC and a verified or configured broadcast address")
        try:
            await async_send_magic_packet(hass, settings["mac_address"], settings["broadcast_address"])
        except (OSError, ValueError) as err:
            raise HomeAssistantError("Could not send the Wake-on-LAN packet") from err
        sent_at = datetime.now(timezone.utc).isoformat()
        runtime.coordinator.last_wake_sent_at = sent_at
        runtime.coordinator.async_update_listeners()
        result = {"status": "packet_sent", "sent_at": sent_at}
        return result if call.return_response else None

    hass.services.async_register(
        DOMAIN, "manage", handle_action,
        schema=vol.Schema({
            vol.Required("server"): cv.string,
            vol.Required("action"): vol.In(ACTION_ROUTES),
            vol.Optional("target", default=""): cv.string,
            vol.Optional("confirmation", default=""): cv.string,
        }),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, "wake", handle_wake,
        schema=vol.Schema({vol.Required("server"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.version > 2:
        return False
    if entry.version < 2:
        # Existing entity unique IDs and health URLs are retained.
        hass.config_entries.async_update_entry(entry, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: InterstellarConfigEntry) -> bool:
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, True)
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    client = InterstellarApiClient(session, entry.data[CONF_URL], REQUEST_TIMEOUT_SECONDS)
    control_url = entry.options.get(CONF_CONTROL_URL, "")
    control_session = async_get_clientsession(hass, verify_ssl=True) if control_url else None
    control_client = InterstellarApiClient(control_session, control_url, REQUEST_TIMEOUT_SECONDS) if control_session else None
    store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.last_known", private=True)
    stored = await store.async_load() or {}
    last_known = stored.get("last_known") if isinstance(stored, dict) else None
    coordinator = InterstellarCoordinator(hass, client, control_client, entry, store, last_known)
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        if not last_known and not entry.options.get("wake_on_lan_mac"):
            raise
        coordinator.data = last_known or {"host": {"machine_id": entry.unique_id, "hostname": entry.title},
                                          "wake_on_lan": {}}
        coordinator.last_update_success = False
    runtime = InterstellarRuntimeData(coordinator, control_client, entry=entry)
    entry.runtime_data = runtime
    hass.data[DOMAIN][entry.entry_id] = runtime

    machine = coordinator.data.get("host", {}).get("machine_id")
    if machine:
        registry = er.async_get(hass)
        stale_update = registry.async_get_entity_id("update", DOMAIN, f"{machine}_system_packages_update")
        if stale_update:
            registry.async_remove(stale_update)
    if machine and entry.unique_id != machine:
        used = any(other.entry_id != entry.entry_id and other.unique_id == machine
                   for other in hass.config_entries.async_entries(DOMAIN))
        if not used:
            hass.config_entries.async_update_entry(entry, unique_id=machine)

    async_update_repairs(hass, entry)
    entry.async_on_unload(coordinator.async_add_listener(lambda: async_update_repairs(hass, entry)))
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: InterstellarConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        async_delete_repairs(hass, entry)
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
