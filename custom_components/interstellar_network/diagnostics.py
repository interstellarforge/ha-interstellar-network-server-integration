"""Diagnostics for Interstellar Network."""
from homeassistant.components.diagnostics import async_redact_data
from . import InterstellarConfigEntry
TO_REDACT={"addresses","tailscale_ipv4","preferred_source","gateway","listen_urls","urls","machine_id"}
async def async_get_config_entry_diagnostics(hass,entry:InterstellarConfigEntry):
    return {"entry":{"title":entry.title,"data":{"url":"<redacted>","verify_ssl":entry.data.get("verify_ssl",True)}},"stats":async_redact_data(entry.runtime_data.coordinator.data,TO_REDACT)}
