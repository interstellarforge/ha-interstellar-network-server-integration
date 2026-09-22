"""Home Assistant-side Wake-on-LAN policy. No target control API is involved."""
from __future__ import annotations

import ipaddress
import re
from functools import partial
from typing import Any

import wakeonlan

from .const import CONF_WOL_BROADCAST, CONF_WOL_ENABLED, CONF_WOL_MAC

_MAC = re.compile(r"(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}\Z")


def normalize_mac(value: str) -> str:
    if not isinstance(value, str) or not _MAC.fullmatch(value):
        raise ValueError("Enter a six-byte MAC address")
    groups = re.split("[:-]", value.lower())
    first = int(groups[0], 16)
    if first & 1 or all(group == "00" for group in groups):
        raise ValueError("WoL requires a unicast, nonzero MAC address")
    return ":".join(groups)


def validate_broadcast(value: str) -> str:
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as err:
        raise ValueError("Enter an IPv4 broadcast address") from err
    if (address.is_multicast or address.is_loopback or address.is_unspecified
            or address.is_link_local or (int(address) & 1) == 0):
        raise ValueError("Invalid IPv4 broadcast address")
    return str(address)


def effective_wol(options: dict, data: dict[str, Any]) -> dict[str, Any]:
    reported = data.get("wake_on_lan") or {}
    enabled = options.get(CONF_WOL_ENABLED, reported.get("enabled", False))
    raw_mac = options.get(CONF_WOL_MAC) or reported.get("mac_address") or ""
    raw_broadcast = options.get(CONF_WOL_BROADCAST) or reported.get("broadcast_address") or ""
    try:
        mac = normalize_mac(raw_mac)
    except ValueError:
        mac = None
    try:
        broadcast = validate_broadcast(raw_broadcast)
    except ValueError:
        broadcast = None
    supported = reported.get("supported")
    configured = bool(enabled and mac and broadcast and supported is not False)
    return {"configured": configured, "enabled": bool(enabled), "supported": supported,
            "mac_address": mac, "broadcast_address": broadcast,
            "interface": reported.get("interface")}


async def async_send_magic_packet(hass, mac: str, broadcast: str) -> None:
    """Send a standard UDP magic packet from Home Assistant's own network stack."""
    await hass.async_add_executor_job(partial(wakeonlan.send_magic_packet, mac, ip_address=broadcast))
