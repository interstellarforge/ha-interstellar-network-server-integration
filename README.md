# Interstellar Network for Home Assistant

The integration monitors Debian and Ubuntu servers and, when explicitly configured, manages a small set of server actions. It supports multiple servers, Zeroconf discovery, one HA device per machine ID, Repairs, and the `custom:interstellar-overview-card` fleet dashboard.

## Requirements

- Home Assistant 2026.8.0 or newer
- Interstellar Toolbox 4.5.0 / health agent 3.2.0 for WoL telemetry
- Optional Interstellar control service 0.2.0 and Tailscale **1.98.9+** Serve with an app capability Grant for management

Existing health-only entries continue to work, including when control is unavailable or Tailscale is too old for the control plane. This integration release is 0.4.0.

## Install

Add `https://github.com/interstellarforge/ha-interstellar-network-server-integration` as a HACS custom integration repository, download it, and restart Home Assistant. Add **Interstellar Network** through Devices & services. Discovery uses `_interstellar._tcp.local.`; manual setup accepts the health Serve URL, normally `https://atlas.example.ts.net`.

The health API stays read-only and remains available at `/`, `/health`, `/stats`, and `/metrics`. Monitoring needs no control URL.

## Enable management

1. Confirm `tailscale version --daemon` reports 1.98.9 or newer for both Client and Daemon. Then on the server, run `interstellar` → **Interstellar API / Agent** → **Install / repair / upgrade Control API**. Choose manageable services and containers. Expected and manageable are separate lists. The toolbox writes root-owned `/etc/interstellar/control-policy.json`.
2. Give the Home Assistant Tailscale identity the `interstellarnetwork.nl/cap/server-control` app capability for the server, and allow it to connect to the control Serve port in your tailnet policy. Grant only the HA node or a narrow user group.
   For example, with HA tagged `tag:home-assistant` and servers tagged `tag:interstellar-server`, a narrow tailnet Grant is:

   ```json
   {
     "grants": [{
       "src": ["tag:home-assistant"],
       "dst": ["tag:interstellar-server"],
       "ip": ["tcp:8443"],
       "app": {"interstellarnetwork.nl/cap/server-control": [{}]}
     }]
   }
   ```

3. On the server, configure a separate Tailscale Serve listener:

   ```bash
   sudo tailscale serve --bg --https=8443 \
     --accept-app-caps=interstellarnetwork.nl/cap/server-control \
     unix:/run/interstellar-control-api/api.sock
   tailscale serve status
   ```

4. In the HA config entry **Options**, set the control URL to `https://atlas.example.ts.net:8443`. The integration always verifies TLS for control requests.

Do not use Tailscale Funnel for the control listener. The control API is a private Unix HTTP socket; the root helper has a second Unix socket and checks the API process UID. Both server-side policy and the HA UI check targets. The helper is the authority.

For deliberate opt-in to managing `ssh`, `sshd`, or `tailscaled`, edit the root-owned policy's `sensitive_services_opt_in` array as well as `manageable_services`. Restart the health agent after policy edits to refresh its view. Tailscale restart has a dedicated control action, which may briefly disconnect HA.

Security-only updates use `unattended-upgrades` only when its configured origins are exclusively security repositories and automatic reboot is disabled. Otherwise that action fails with an audit entry. Normal **Install updates** runs `apt-get upgrade`, never full-upgrade. Reboot is a separate action.

## Wake-on-LAN

Enable WoL on the target through Toolbox → **Tailscale & networking** → **Wake-on-LAN**. Select a physical NIC, verify magic-packet support (`g` in `Supports Wake-on`), and test persistence after reboot. Health telemetry supplies the MAC and, when safely known, the IPv4 broadcast address. In the HA integration **Options**, enable WoL, confirm or override the MAC, and enter a broadcast address if the server did not report one. A usable MAC **and** broadcast address are required. HA does not assume `255.255.255.255` will work.

`interstellar_network.wake` targets a server by stable machine ID and sends a standard UDP magic packet **from Home Assistant**, even if both health and control APIs on the target are offline. It requires an authenticated HA administrator. A returned `packet_sent` means only that HA sent the packet; the card waits for health to reconnect before showing the server online. HA and the target normally need the same L2 network. A future allowlisted relay on another awake Interstellar node is possible but is not included here. There is no target Control API Wake endpoint.

Do not treat shutdown as routine until a real powered-off WoL test succeeds. See the [Atlas canary checklist](https://github.com/interstellarforge/interstellar-network-node/blob/main/docs/atlas-canary.md).

## Dashboard card

Add `/interstellar_network/interstellar-network-card.js` as a JavaScript module resource, then use:

```yaml
type: custom:interstellar-overview-card
title: Interstellar Server Fleet
default_expanded: false
show:
  system: true
  updates: true
  services: true
  docker: true
  network: true
  disks: true
  temperatures: true
  actions: true
roles:
  - development
  - docker-host
# Optional: servers: [atlas, jupiter]
```

All servers are shown by default. The former `custom:interstellar-network-card` type remains an alias. The card groups by machine ID, shows fleet totals and filters, and uses expandable sections on desktop and mobile. Service and container controls appear only for targets in server policy. It asks for confirmation before actions; reboot and shutdown require typing the hostname. The HA `interstellar_network.manage` service enforces that hostname rule for all callers and requires an authenticated administrator. Automations without user context are blocked for management and Wake. Control requests use the Home Assistant node's Tailscale identity; they do not carry the individual HA user's identity.

OS package counts use the existing `pending_updates` and `pending_security_updates` sensors; last update time and reboot required use the existing timestamp sensor and binary sensor. The former system-packages `update` entity was removed because a package count has no installed/latest version pair. Its stale registry entry is removed during setup. Use the card or admin-only `interstellar_network.manage` for update actions. No component `update` entities are created until a secure source of real installed/latest versions exists. Power actions have no one-click button entities. The WoL binary sensor keeps its configuration attributes available while the target is offline.

## Action API

The control listener exposes read-only `GET /`, `/state`, `/actions`, `/actions/{id}` and the following exact POST routes:

| Route | Arguments |
| --- | --- |
| `/actions/reboot`, `/actions/shutdown` | `{"confirm_hostname":"atlas"}` |
| `/actions/update/refresh` | none |
| `/actions/update/install` | `{"type":"security"}` or `{"type":"all"}` |
| `/actions/service/start`, `/stop`, `/restart` | `{"service":"configured-name"}` |
| `/actions/docker/start`, `/stop`, `/restart` | `{"container":"configured-name"}` |
| `/actions/docker/restart-daemon` | none |
| `/actions/interstellar/restart-health-agent`, `/restart-control-agent`, `/restart-mdns` | none |
| `/actions/tailscale/restart` | none |

POST returns HTTP 202 with an action ID and `queued` status. Action reads show `queued`, `running`, `dispatched`, `successful`, or `failed`, with timestamps and short summaries. Recent actions are bounded to 100 server-side, and `GET /actions` returns the latest 50. There is no shell, Docker exec, arbitrary unit, arbitrary Compose path, image pull, full-upgrade, or self-update endpoint.

## Migration

Config entries from version 1 migrate to version 2 without changing health URLs or existing entity unique IDs. The existing `interstellar_network` device and sensor IDs stay based on machine ID. A hostname change updates the device name without adding another device. Control and WoL are opt-in through entry options. WoL metadata and the last known summary are saved through Home Assistant’s supported storage API, so an offline server remains visible after HA restarts.

The older `interstellar_server` domain needs an explicit migration. Home Assistant treats a config entry’s domain as immutable and `async_update_entry` cannot change it. Automatic cross-domain conversion would risk duplicate devices. The new config flow aborts if a legacy entry has the same machine ID or health URL. Record old entity IDs and automation references, back up HA, remove the old entry through Devices & services, then add the server under `interstellar_network`. Map or rename new entity IDs and update automations and dashboards as needed; verify there is one device for the machine. Do not edit `.storage` files directly. Same-domain version-1 entries migrate to version 2 and retain their machine-ID-based unique IDs.

For the socket permissions, helper protocol, and threat model, see [control architecture](https://github.com/interstellarforge/interstellar-network-node/blob/main/docs/control-architecture.md).

## Security limits

Tailscale Serve supplies capability and identity headers. The private API socket prevents ordinary local processes from forging these headers; local root can still access it and is part of the trusted host boundary. Tailnet Grants and HTTPS are required for remote access. The health process has no write actions or access to the helper socket. Audit records include the machine ID, action, target, Tailscale identity when supplied, status, and timestamps, without command output or credentials.
