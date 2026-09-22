#!/usr/bin/env python3
"""Advertise an Interstellar health agent through mDNS/Zeroconf.

The advertised URL points to Tailscale Serve; the health agent itself can
remain localhost-only.
"""

from __future__ import annotations

import os
import signal
import socket
import sys
import time

from zeroconf import IPVersion, ServiceInfo, Zeroconf

SERVICE_TYPE = "_interstellar._tcp.local."

hostname = os.environ["INTERSTELLAR_HOSTNAME"]
machine_id = os.environ["INTERSTELLAR_MACHINE_ID"]
url = os.environ["INTERSTELLAR_URL"].rstrip("/")
lan_ip = os.environ["INTERSTELLAR_LAN_IP"]
agent_version = os.environ.get("INTERSTELLAR_AGENT_VERSION", "unknown")

properties = {
    "url": url,
    "machine_id": machine_id,
    "hostname": hostname,
    "agent_version": agent_version,
    "transport": "tailscale-serve",
}

info = ServiceInfo(
    SERVICE_TYPE,
    f"{hostname}.{SERVICE_TYPE}",
    addresses=[socket.inet_aton(lan_ip)],
    port=443,
    properties=properties,
    server=f"{hostname}.local.",
)

zc = Zeroconf(ip_version=IPVersion.V4Only)
running = True


def stop(*_args):
    global running
    running = False


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

try:
    zc.register_service(info)
    print(
        f"Advertising {hostname} as {SERVICE_TYPE} "
        f"on {lan_ip}; health URL={url}",
        flush=True,
    )
    while running:
        time.sleep(1)
finally:
    try:
        zc.unregister_service(info)
    finally:
        zc.close()
