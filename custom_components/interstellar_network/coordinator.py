"""Coordinator for Interstellar Network."""
from __future__ import annotations
import time
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import (InterstellarApiClient, InterstellarApiError, InterstellarConnectionRefused,
                  InterstellarDnsError)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

class InterstellarCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, client: InterstellarApiClient, control_client: InterstellarApiClient | None = None, entry=None, store=None, last_known=None) -> None:
        super().__init__(hass, logger=__import__("logging").getLogger(__name__), config_entry=entry, name=DOMAIN, update_interval=DEFAULT_SCAN_INTERVAL)
        self.client = client
        self.control_client = control_client
        self.store = store
        self.last_known = last_known or {}
        self.last_wake_sent_at = None
        self._last_save = 0.0
        self._last_saved_wol = self.last_known.get("wake_on_lan")

    def _control_failure(self, err: InterstellarApiError, data: dict[str, Any]) -> dict[str, Any]:
        """Describe why control is unavailable without conflating causes.

        A 403 means Home Assistant reached the control API and was refused for
        lack of the Tailscale app capability. That is a completely different
        problem from the service being stopped, so the node's own local status
        is only consulted when the connection never reached the API at all.
        """
        reason = err.reason
        if isinstance(err, (InterstellarConnectionRefused, InterstellarDnsError)):
            local = data.get("control_plane") or {}
            local_reason = (local.get("control_service_unavailable_reason")
                            or local.get("control_unavailable_reason"))
            if local_reason:
                reason = local_reason
        return {"available": False, "control_error_code": err.error_code,
                "control_unavailable_reason": reason}

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.client.async_get_stats()
            if self.control_client:
                try:
                    data["_control"] = await self.control_client.async_get_control()
                except InterstellarApiError as err:
                    self.logger.debug("Control API unavailable (%s): %s", err.error_code, err)
                    data["_control"] = self._control_failure(err, data)
            else:
                data["_control"] = {"available": False, "control_error_code": "not_configured",
                                    "control_unavailable_reason": "No control URL is configured for this server"}
            summary = {key: data.get(key) for key in (
                "status", "agent_version", "timestamp_utc", "host", "cpu", "memory",
                "disk_root", "filesystems", "disk_io", "network", "temperatures",
                "services", "updates", "system", "time", "service_policy",
                "wake_on_lan", "control_plane")}
            control = data.get("_control") or {}
            summary["_control"] = {key: control.get(key) for key in (
                "available", "control_available", "control_unavailable_reason",
                "control_error_code", "version",
                "toolbox_version", "tailscale_version", "tailscale_daemon_version",
                "boot_time_utc", "last_reboot_action", "last_reboot_duration_seconds",
                "policy", "docker")}
            summary["_control"]["actions"] = control.get("actions", [])[:5]
            self.last_known = summary
            if self.store and (self._last_save == 0 or self._last_saved_wol != summary["wake_on_lan"]
                               or time.monotonic() - self._last_save >= 300):
                try:
                    await self.store.async_save({"last_known": summary})
                except OSError:
                    self.logger.warning("Could not persist the last known Interstellar server state")
                else:
                    self._last_save = time.monotonic()
                    self._last_saved_wol = summary["wake_on_lan"]
            return data
        except InterstellarApiError as err:
            raise UpdateFailed(str(err)) from err
