"""Interstellar Network integration."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .api import InterstellarApiClient
from .const import CARD_URL, CONF_URL, CONF_VERIFY_SSL, PLATFORMS, REQUEST_TIMEOUT_SECONDS
from .coordinator import InterstellarCoordinator
from .repairs import async_delete_repairs, async_update_repairs

@dataclass
class InterstellarRuntimeData:
    coordinator: InterstellarCoordinator
    repair_issue_ids: set[str] = field(default_factory=set)

type InterstellarConfigEntry = ConfigEntry[InterstellarRuntimeData]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Serve the bundled fleet overview card."""
    card = Path(__file__).parent / "frontend" / "interstellar-network-card.js"
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(card), False)])
    return True

async def async_setup_entry(hass: HomeAssistant, entry: InterstellarConfigEntry) -> bool:
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, True)
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    client = InterstellarApiClient(session, entry.data[CONF_URL], REQUEST_TIMEOUT_SECONDS)
    coordinator = InterstellarCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()
    runtime = InterstellarRuntimeData(coordinator)
    entry.runtime_data = runtime

    async_update_repairs(hass, entry)
    entry.async_on_unload(coordinator.async_add_listener(lambda: async_update_repairs(hass, entry)))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: InterstellarConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        async_delete_repairs(hass, entry)
    return unloaded
