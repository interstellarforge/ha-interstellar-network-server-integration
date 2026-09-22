"""Coordinator for Interstellar Network."""
from __future__ import annotations
import time
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import InterstellarApiClient, InterstellarApiError
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

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.client.async_get_stats()
            if self.control_client:
                try:
                    data["_control"] = await self.control_client.async_get_control()
                except InterstellarApiError:
                    reason = data.get("control_plane", {}).get("control_unavailable_reason")
                    data["_control"] = {"available": False, "control_unavailable_reason": reason or "Control API unavailable"}
            summary = {key: data.get(key) for key in (
                "status", "agent_version", "timestamp_utc", "host", "cpu", "memory",
                "disk_root", "network", "updates", "system", "service_policy",
                "wake_on_lan", "control_plane")}
            control = data.get("_control") or {}
            summary["_control"] = {key: control.get(key) for key in (
                "available", "control_available", "control_unavailable_reason", "version",
                "toolbox_version", "last_reboot_action", "last_reboot_duration_seconds")}
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
