# Interstellar Network


> **Rename notice for v0.3.0:** this is the canonical **Interstellar Network** naming release.
> If you installed an earlier experimental build, remove that custom component/config entry
> before installing v0.3.0, then add **Interstellar Network** again.


Home Assistant integration for **Interstellar Network**.

It brings every managed node in your Interstellar Network into Home Assistant with health,
metrics, service state, update state, Repairs issues, and a unified Interstellar Network dashboard card.

## Features

- Automatic Zeroconf/mDNS discovery (`_interstellar._tcp.local.`)
- Manual setup using a Tailscale Serve URL
- Multiple servers / one Home Assistant device per server
- Server roles and expected-service monitoring
- CPU usage, load, iowait and steal
- RAM and swap
- Filesystem usage, free space and inode utilization
- Disk I/O totals and rates
- Network RX/TX totals and rates per interface
- Boot time and uptime
- Pending package and security updates
- Last successful package update
- OOM kills and failed systemd units
- NTP and reboot-required state
- Individual service status entities
- Home Assistant Repairs issues
- Interstellar Network dashboard card
- Read-only design: no reboot, shell, firewall, package, or Docker control

## Requirements

- Home Assistant 2026.8.0 or newer
- Interstellar Toolbox v4.1+ / health agent v3.0.0+
- Recommended: Tailscale Serve for remote health API access

## HACS installation

Until this repository is submitted to the default HACS store, add it as a custom repository:

1. Open **HACS**
2. Open **Integrations**
3. Open the menu → **Custom repositories**
4. Add this GitHub repository URL
5. Category: **Integration**
6. Search for **Interstellar Network**
7. Download the latest release
8. Restart Home Assistant
9. Go to **Settings → Devices & services → Add integration**
10. Search for **Interstellar Network**

Future GitHub releases will then show up as normal HACS updates.

## Manual installation

Copy:

```text
custom_components/interstellar_network
```

to:

```text
/config/custom_components/interstellar_network
```

Then restart Home Assistant.

## Node setup

On every Interstellar Network node:

1. Run `interstellar`
2. Open **Health API agent**
3. Install/upgrade the health agent
4. Configure roles and expected services
5. Enable Tailscale Serve
6. Enable Home Assistant auto-discovery if Home Assistant can see the server over mDNS

The health agent remains localhost-only and read-only.

## Dashboard card

The integration serves:

```text
/interstellar_network/interstellar-network-card.js
```

Add it once as a Home Assistant dashboard resource:

- URL: `/interstellar_network/interstellar-network-card.js`
- Type: `JavaScript Module`

Then add a Manual card:

```yaml
type: custom:interstellar-network-card
title: Interstellar Network
```

## Security model

The integration is intentionally read-only. The health plane does **not** expose
reboot, update, firewall, Docker, shell, or other privileged operations.

Recommended path:

```text
Home Assistant
      │
      │ Tailscale
      ▼
Tailscale Serve
      │
      ▼
127.0.0.1:9127
interstellar-agent
```

Administrative operations remain separate through SSH/Tailscale + sudo + `interstellar`.

## Releases

The integration uses semantic versions. The version in
`custom_components/interstellar_network/manifest.json` must match the GitHub release tag
without the leading `v`.

Example:

```text
manifest: 0.3.0
tag:      v0.3.0
```

Use `scripts/release.sh 0.3.0` to prepare a release commit and tag.

## License

MIT
