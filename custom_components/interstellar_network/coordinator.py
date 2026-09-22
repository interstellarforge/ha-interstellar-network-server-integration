"""Coordinator for Interstellar Network."""
from __future__ import annotations
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import InterstellarApiClient, InterstellarApiError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

class InterstellarCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, client: InterstellarApiClient) -> None:
        super().__init__(hass, logger=__import__("logging").getLogger(__name__), name=DOMAIN, update_interval=DEFAULT_SCAN_INTERVAL)
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.async_get_stats()
        except InterstellarApiError as err:
            raise UpdateFailed(str(err)) from err
