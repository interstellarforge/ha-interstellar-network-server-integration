# Changelog

## 0.5.1

- Fix expandable sections (System, Manage, Services, Docker, Network, Disks, …) occasionally collapsing right after being opened: expansion state was only recorded on the asynchronous native `toggle` event, so a Home Assistant state update landing between the click and that event could re-render the section closed. Section open/close is now handled synchronously in the click handler itself, so no race with `hass` updates is possible.

## 0.5.0

- Add responsive `compact`, `detailed`, and hybrid `fleet` card layouts with all-server discovery and predictable machine-ID/case-insensitive hostname filtering.
- Preserve independent per-server section expansion, selected server, interactive layout mode, pending confirmations, and Wake progress across Home Assistant state refreshes.
- Normalize card data by canonical machine ID, retain unavailable servers with last-known values, and warn about unmatched configured servers.
- Add capability-driven Manage controls, read-only explanations, update/power confirmations, and WoL-aware shutdown warnings while keeping all actions behind Home Assistant admin services.
- Surface Toolbox, Control, Tailscale, reboot, and last-known telemetry consistently from the existing health and Control APIs.
- Add Home Assistant Sections sizing through `getGridOptions()`, including default full-width behavior and `full_width: false` support.
- Add regression coverage for state persistence, multiple servers, metadata, management, layouts, unavailable servers, filtering, and grid sizing.

## 0.4.1

- Fix frontend upgrades retaining the pre-0.4 card module by documenting a versioned Lovelace resource URL.
- Register `custom:interstellar-overview-card` and the legacy `custom:interstellar-network-card` alias defensively when an older bundle is already present.
- Expose the loaded card version in the browser console for upgrade diagnosis.

## 0.4.0

- Add admin-only, Home Assistant-originated Wake-on-LAN with learned and configurable MAC/broadcast metadata that remains available while the server is offline.
- Improve the fleet card’s offline, Waking, Managed/Read-only, reboot lifecycle, and shutdown-warning views.
- Remove the misleading OS package `update` entity while preserving package sensors, management actions, and existing sensor unique IDs.
- Guard against duplicate devices when a legacy `interstellar_server` entry exists; document the explicit cross-domain migration path.
- Require Tailscale 1.98.9+ for control while retaining health-only monitoring.

## 0.3.2

- Added optional, Tailscale-backed server control through a separate control service.
- Added OS package update entity, management service, and Docker Repairs.
- Rebuilt the fleet card with responsive summaries, details, policy-aware actions, and confirmations.
- Kept existing monitoring entries and entity unique IDs; added config entry migration to version 2.

## 0.3.0

- Renamed the product and Home Assistant integration to **Interstellar Network**.
- Canonicalized the integration domain as `interstellar_network`.
- Renamed the HACS/GitHub repository target to `home-assistant-interstellar-network`.
- Renamed the dashboard card to `custom:interstellar-network-card`.
- Updated manufacturer, diagnostics metadata, documentation, workflows, release artifacts,
  entity metadata, and user-facing strings to the canonical name.

## 0.2.0

- Added server roles, expected-service policy, telemetry, Repairs, and a dashboard card.

## 0.1.0

- Initial Home Assistant integration.
