const {JSDOM} = require('jsdom');
const fs = require('fs');
const assert = require('assert');
const path = require('path');

const script = fs.readFileSync(path.join(__dirname, '../custom_components/interstellar_network/frontend/interstellar-network-card.js'), 'utf8');
const dom = new JSDOM('<html><body></body></html>', {runScripts: 'dangerously', url: 'http://localhost'});
dom.window.eval(script);

assert.equal(dom.window.interstellarNetworkCardVersion, '0.5.3');
assert(dom.window.customElements.get('interstellar-network-card'));
assert(dom.window.customElements.get('interstellar-overview-card'));

// Loading after a stale legacy alias must not prevent the canonical overview alias from registering.
const legacyDom = new JSDOM('<html><body></body></html>', {runScripts: 'dangerously', url: 'http://localhost'});
legacyDom.window.customElements.define('interstellar-network-card', class extends legacyDom.window.HTMLElement {});
assert.doesNotThrow(() => legacyDom.window.eval(script));
assert(legacyDom.window.customElements.get('interstellar-overview-card'));

const snapshot = (id, name, options = {}) => {
  const online = options.online !== false;
  const managed = options.managed !== false;
  return {
    state: online ? 'online' : 'offline',
    attributes: {
      interstellar_network_id: options.attributeId || id,
      interstellar_key: 'server_snapshot',
      interstellar_hostname: name,
      snapshot: {
        host: {
          machine_id: id,
          hostname: name,
          roles: options.roles || ['development'],
          uptime_seconds: 104400,
          boot_time_utc: '2026-09-21T14:27:23Z',
          os: 'Debian GNU/Linux 13 (trixie)',
          kernel: '6.12.107+deb13-amd64',
          architecture: 'x86_64',
          virtualization: 'kvm',
        },
        timestamp_utc: '2026-09-22T18:00:00Z',
        agent_version: '3.2.0',
        cpu: {used_percent: 42, count: 4, model: 'Intel Core i5'},
        memory: {used_percent: 50, total_bytes: 1000, used_bytes: 500},
        disk_root: {used_percent: 30, inode_used_percent: 4, total_bytes: 1000, used_bytes: 300},
        filesystems: [{mountpoint: '/', used_percent: 30, inode_used_percent: 4, total_bytes: 1000, used_bytes: 300}],
        updates: options.updates || {pending: 2, pending_security: options.securityUpdates ?? 1, packages: []},
        system: {reboot_required: false, failed_systemd_units: 0, failed_units: [], oom_kills_since_boot: 0},
        service_policy: {expected_services: ['ssh', 'docker'], problems: []},
        services: {ssh: 'active', docker: options.dockerState || 'active', plex: options.plexState || 'inactive'},
        network: {
          addresses: [{kind: 'lan', address: '192.168.1.2'}],
          tailscale: {version: '1.98.9', connected: true},
        },
        wake_on_lan: {configured: options.wake === true, mac_address: 'aa:bb:cc:dd:ee:fe', broadcast_address: '192.168.1.255'},
        control: {
          available: managed,
          version: '0.2.0',
          toolbox_version: '4.5.0',
          tailscale_version: '1.98.9',
          last_reboot_action: {timestamp: '2026-09-20T10:00:00Z', status: 'successful'},
          last_reboot_duration_seconds: 75,
          policy: {
            expected_containers: options.expectedContainers || [],
            manageable_services: options.manageableServices || ['docker'],
            manageable_containers: options.manageableContainers || [],
            sensitive_services_opt_in: [],
          },
          docker: options.docker || {installed: true, daemon_running: true, version: '28.0', running: 0, stopped: 0, containers: []},
          actions: [],
          error_code: managed ? null : (options.errorCode || 'connection_refused'),
          unavailable_reason: managed ? null : (options.unavailableReason || 'The connection was refused'),
        },
      },
    },
  };
};

const makeCard = (config = {}, states = {}) => {
  const card = dom.window.document.createElement('interstellar-network-card');
  dom.window.document.body.append(card);
  card.setConfig(config);
  const calls = [];
  card.hass = {states, callService: async (...args) => calls.push(args)};
  return {card, calls};
};
const tick = () => new Promise(resolve => setImmediate(resolve));

(async () => {
  const atlas = snapshot('machine-a', 'Atlas');
  const jupiter = snapshot('machine-j', 'Jupiter', {
    roles: ['media', 'docker-host'],
    manageableContainers: ['plex'],
    expectedContainers: ['plex'],
    docker: {installed: true, daemon_running: true, version: '28.0', running: 1, stopped: 0,
      containers: [{name: 'plex', state: 'running', health: 'healthy', project: 'media'}]},
  });
  const two = {'sensor.atlas_snapshot': atlas, 'sensor.jupiter_snapshot': jupiter};

  // Multi-server discovery and deterministic filtering.
  let result = makeCard({mode: 'detailed'}, two);
  assert.equal(result.card.shadowRoot.querySelectorAll('.detailed-server').length, 2);
  assert(result.card.shadowRoot.textContent.includes('Atlas'));
  assert(result.card.shadowRoot.textContent.includes('Jupiter'));
  assert.equal(result.card.getGridOptions().columns, 'full');
  assert.equal(result.card.getGridOptions().min_columns, 6);

  result = makeCard({mode: 'detailed', full_width: false, servers: ['atlas', 'JUPITER']}, two);
  assert.equal(result.card.shadowRoot.querySelectorAll('.detailed-server').length, 2);
  assert.equal(result.card.getGridOptions().columns, 12);
  result = makeCard({mode: 'detailed', servers: ['jupiter']}, two);
  assert.equal(result.card.shadowRoot.querySelectorAll('.detailed-server').length, 1);
  assert(result.card.shadowRoot.textContent.includes('Jupiter'));
  assert(!result.card.shadowRoot.textContent.includes('Atlas'));
  result = makeCard({mode: 'detailed', servers: ['machine-a']}, two);
  assert.equal(result.card.shadowRoot.querySelectorAll('.detailed-server').length, 1);
  assert(result.card.shadowRoot.textContent.includes('Atlas'));
  result = makeCard({mode: 'detailed', servers: ['atlas', 'missing-node']}, two);
  assert(result.card.shadowRoot.textContent.includes('Configured server not found: missing-node'));

  // Canonical snapshot machine_id wins even when entity metadata collides.
  const collision = {
    'sensor.atlas_snapshot': snapshot('machine-a', 'Atlas', {attributeId: 'duplicated'}),
    'sensor.jupiter_snapshot': snapshot('machine-j', 'Jupiter', {attributeId: 'duplicated'}),
  };
  result = makeCard({mode: 'detailed'}, collision);
  assert.equal(result.card.shadowRoot.querySelectorAll('.detailed-server').length, 2);

  // Offline snapshots remain present and clearly stale.
  result = makeCard({mode: 'compact'}, {'sensor.jupiter_snapshot': snapshot('machine-j', 'Jupiter', {online: false, wake: true})});
  assert.equal(result.card.shadowRoot.querySelectorAll('.compact-server').length, 1);
  assert(result.card.shadowRoot.textContent.includes('Offline'));
  assert(result.card.shadowRoot.textContent.includes('Last seen'));
  assert(result.card.shadowRoot.textContent.includes('last known'));

  // Compact mode renders all servers, summaries, and relevant service/container chips.
  result = makeCard({mode: 'compact', compact: {max_services: 8}}, two);
  assert.equal(result.card.shadowRoot.querySelectorAll('.compact-server').length, 2);
  assert(result.card.shadowRoot.textContent.includes('CPU'));
  assert(result.card.shadowRoot.textContent.includes('Updates 2 · Security 1'));
  assert(result.card.shadowRoot.textContent.includes('SSH'));
  assert(result.card.shadowRoot.textContent.toLowerCase().includes('plex'));
  result.card.shadowRoot.querySelector('[data-select-server="machine-j"]').click();
  assert.equal(result.card._mode, 'detailed');
  assert.equal(result.card._selectedServer, 'machine-j');
  assert.equal(result.card.shadowRoot.querySelectorAll('.detailed-server').length, 2);

  // System metadata from health and Control API is surfaced.
  result = makeCard({mode: 'detailed', default_expanded: {system: true}}, {'sensor.atlas_snapshot': atlas});
  const system = result.card.shadowRoot.querySelector('[data-section="system"]');
  assert(system.open);
  for (const value of ['Intel Core i5', '3.2.0', '4.5.0', '0.2.0', '1.98.9', 'successful', '0h 1m']) {
    assert(system.textContent.includes(value), `missing System value: ${value}`);
  }

  // Expansion state survives HA/coordinator updates independently per section.
  // Toggling must happen synchronously on the summary click (not the async native
  // `toggle` event) so a hass update landing between click and toggle can't collapse
  // a section the user just opened.
  // Each click fully re-renders the shadow DOM, so elements must be re-queried afterwards
  // rather than reused across clicks (a stale, now-detached reference never sees clicks).
  result.card.shadowRoot.querySelector('[data-section="services"]').querySelector('summary').click();
  result.card.shadowRoot.querySelector('[data-section="system"]').querySelector('summary').click();
  assert.equal(result.card.shadowRoot.querySelector('[data-section="system"]').open, false);
  const updatedAtlas = snapshot('machine-a', 'Atlas');
  updatedAtlas.attributes.snapshot.cpu.used_percent = 43;
  result.card.hass = {states: {'sensor.atlas_snapshot': updatedAtlas}, callService: async (...args) => result.calls.push(args)};
  assert.equal(result.card.shadowRoot.querySelector('[data-section="system"]').open, false);
  assert.equal(result.card.shadowRoot.querySelector('[data-section="services"]').open, true);
  result.card.shadowRoot.querySelector('[data-section="system"]').querySelector('summary').click();
  result.card.hass = {states: {'sensor.atlas_snapshot': updatedAtlas}, callService: async (...args) => result.calls.push(args)};
  assert.equal(result.card.shadowRoot.querySelector('[data-section="system"]').open, true);
  assert.equal(result.card.shadowRoot.querySelector('[data-section="services"]').open, true);

  // A hass update firing in the same tick as a section-open click must not win the race
  // and collapse the section (the original bug: state was only recorded on the async
  // native `toggle` event, so a render() in between could rebuild a closed <details>).
  const manageBeforeOpen = result.card.shadowRoot.querySelector('[data-section="manage"]');
  manageBeforeOpen.querySelector('summary').click();
  result.card.hass = {states: {'sensor.atlas_snapshot': updatedAtlas}, callService: async (...args) => result.calls.push(args)};
  assert.equal(result.card.shadowRoot.querySelector('[data-section="manage"]').open, true, 'section must stay open across an immediate hass update');

  // Manage expansion and button clicks survive a render and don't toggle the parent.
  let manage = result.card.shadowRoot.querySelector('[data-section="manage"]');
  manage.querySelector('[data-action="refresh_stats"]').click();
  await tick();
  manage = result.card.shadowRoot.querySelector('[data-section="manage"]');
  assert.equal(manage.open, true);
  assert.equal(result.calls.at(-1)[1], 'manage');
  assert.equal(result.calls.at(-1)[2].action, 'refresh_stats');

  // Managed capability controls are visible; dangerous actions require confirmation.
  for (const action of ['refresh_packages', 'install_security_updates', 'install_all_updates', 'restart_health_agent',
    'restart_control_agent', 'restart_mdns', 'reboot', 'shutdown']) {
    assert(result.card.shadowRoot.querySelector(`[data-action="${action}"]`), `missing action ${action}`);
  }
  const beforeDangerous = result.calls.length;
  result.card.shadowRoot.querySelector('[data-action="install_all_updates"]').click();
  assert(result.card.shadowRoot.querySelector('.confirm-dialog'));
  assert.equal(result.calls.length, beforeDangerous);
  // A normal HA update must not dismiss the pending confirmation.
  result.card.hass = {states: {'sensor.atlas_snapshot': updatedAtlas}, callService: async (...args) => result.calls.push(args)};
  assert(result.card.shadowRoot.querySelector('.confirm-dialog'));
  result.card.shadowRoot.querySelector('[data-modal="confirm"]').click();
  await tick();
  assert.equal(result.calls.at(-1)[2].action, 'install_all_updates');

  // Power confirmation requires the exact hostname and shutdown warning reflects WoL.
  result.card.shadowRoot.querySelector('[data-action="shutdown"]').click();
  assert(result.card.shadowRoot.querySelector('#confirm-text').textContent.includes('physical access'));
  let input = result.card.shadowRoot.querySelector('#confirm-input');
  input.value = 'wrong';
  input.dispatchEvent(new dom.window.Event('input', {bubbles: true}));
  result.card.shadowRoot.querySelector('[data-modal="confirm"]').click();
  await tick();
  assert(result.card.shadowRoot.querySelector('.confirm-dialog'));
  input = result.card.shadowRoot.querySelector('#confirm-input');
  input.value = 'Atlas';
  input.dispatchEvent(new dom.window.Event('input', {bubbles: true}));
  result.card.shadowRoot.querySelector('[data-modal="confirm"]').click();
  await tick();
  assert.equal(result.calls.at(-1)[2].confirmation, 'Atlas');

  result = makeCard({mode: 'detailed'}, {'sensor.atlas_snapshot': snapshot('machine-a', 'Atlas', {wake: true})});
  result.card.shadowRoot.querySelector('[data-action="shutdown"]').click();
  assert(result.card.shadowRoot.querySelector('#confirm-text').textContent.includes('woken again from Home Assistant'));

  // Read-only servers have no destructive controls and explain their state.
  result = makeCard({mode: 'detailed', default_expanded: {manage: true}}, {'sensor.atlas_snapshot': snapshot('machine-a', 'Atlas', {managed: false})});
  assert(result.card.shadowRoot.textContent.includes('Read-only'));
  assert(result.card.shadowRoot.textContent.includes('Connection refused'));
  assert.equal(result.card.shadowRoot.querySelectorAll('[data-action="reboot"]').length, 0);
  assert.equal(result.card.shadowRoot.querySelectorAll('[data-action="install_all_updates"]').length, 0);
  assert(result.card.shadowRoot.querySelector('[data-action="refresh_stats"]'));

  // A missing tailnet grant is a reachable-but-unauthorized control API. It must
  // never be shown as a stopped service, and must name the required capability.
  const blocked = snapshot('machine-a', 'Atlas', {
    managed: false,
    errorCode: 'tailscale_capability_missing',
    unavailableReason: 'Tailscale control capability is not granted to Home Assistant',
  });
  blocked.attributes.snapshot.control.toolbox_version = null;
  blocked.attributes.snapshot.control.version = null;
  result = makeCard({mode: 'detailed', default_expanded: {manage: true, system: true}},
    {'sensor.atlas_snapshot': blocked});
  const blockedText = result.card.shadowRoot.textContent;
  assert(blockedText.includes('Read-only'));
  assert(blockedText.includes('Control API reachable'));
  assert(blockedText.includes('Tailscale control capability missing'));
  assert(blockedText.includes('interstellarnetwork.nl/cap/server-control'));
  assert(!blockedText.includes('Control API is not active'), 'must not blame the service');
  // Control-sourced System values say why they are absent instead of showing a dash.
  const blockedSystem = result.card.shadowRoot.querySelector('[data-section="system"]');
  assert(blockedSystem.textContent.includes('Authorization required'));
  assert(blockedSystem.textContent.includes('1.98.9'), 'health-sourced Tailscale version still shows');
  // No management is faked.
  for (const action of ['reboot', 'shutdown', 'install_all_updates', 'restart_control_agent']) {
    assert.equal(result.card.shadowRoot.querySelectorAll(`[data-action="${action}"]`).length, 0,
      `${action} must not be offered without authorization`);
  }

  // An unconfigured control URL reads differently from an authorization failure.
  result = makeCard({mode: 'detailed', default_expanded: {manage: true}}, {
    'sensor.atlas_snapshot': snapshot('machine-a', 'Atlas', {
      managed: false, errorCode: 'not_configured',
      unavailableReason: 'No control URL is configured for this server'}),
  });
  assert(result.card.shadowRoot.textContent.includes('No control URL configured'));
  assert(!result.card.shadowRoot.textContent.includes('interstellarnetwork.nl/cap/server-control'));

  // Wake state is explicit and survives render updates.
  dom.window.setTimeout = () => 0;
  result = makeCard({mode: 'detailed', default_expanded: {manage: true}}, {'sensor.jupiter_snapshot': snapshot('machine-j', 'Jupiter', {online: false, wake: true})});
  result.card.shadowRoot.querySelector('[data-action="wake"]').click();
  await tick();
  assert.equal(result.calls.at(-1)[1], 'wake');
  assert(result.card.shadowRoot.textContent.includes('Waking'));
  result.card.hass = {states: {'sensor.jupiter_snapshot': snapshot('machine-j', 'Jupiter', {online: false, wake: true})}, callService: async (...args) => result.calls.push(args)};
  assert(result.card.shadowRoot.textContent.includes('Waking'));

  // Every reported problem explains itself on hover, and the status pill carries
  // the whole list, so "Problem" is never a dead end.
  const sick = snapshot('machine-s', 'Sick');
  Object.assign(sick.attributes.snapshot.system, {
    oom_kills_since_boot: 3, reboot_required: true,
    failed_systemd_units: 1, failed_units: [{unit: 'backup.service'}],
  });
  sick.attributes.snapshot.updates = {pending: 12, pending_security: 4, packages: []};
  sick.attributes.snapshot.disk_root.used_percent = 94;
  sick.attributes.snapshot.services.ssh = 'failed';
  sick.attributes.snapshot.service_policy.problems = [{service: 'ssh', state: 'failed'}];
  sick.attributes.snapshot.control.docker = {installed: true, daemon_running: true, version: '28.0', running: 1, stopped: 0,
    containers: [{name: 'plex', state: 'running', health: 'unhealthy', project: 'media'}]};
  result = makeCard({mode: 'detailed'}, {'sensor.sick_snapshot': sick});
  const statusTitle = result.card.shadowRoot.querySelector('.detailed-server .status').getAttribute('title');
  for (const fragment of ['7 problems', 'Service down', 'failed unit', '4 security', 'Disk warning', 'OOM', 'unhealthy', 'Reboot required']) {
    assert(statusTitle.includes(fragment), `status hover missing: ${fragment}`);
  }
  assert(statusTitle.includes('kernel killed 3 processes'), 'OOM must be spelled out, not abbreviated');
  const badges = [...result.card.shadowRoot.querySelectorAll('.badges span')];
  assert.equal(badges.length, 7);
  for (const badge of badges) {
    assert(badge.getAttribute('title').length > badge.textContent.length, `badge ${badge.textContent} explains nothing`);
  }
  assert(badges.find(b => b.textContent === 'OOM').getAttribute('title').includes('ran out of RAM'));
  assert(badges.find(b => b.textContent === 'Reboot required').getAttribute('title').includes('only takes effect after a reboot'));
  // Resource meters explain the metric itself.
  assert(result.card.shadowRoot.querySelector('.resources .bar-row:last-child .bar-head span').getAttribute('title').includes('inodes'));

  // A healthy server says why it is healthy rather than showing an empty tooltip.
  result = makeCard({mode: 'detailed'}, {'sensor.atlas_snapshot': snapshot('machine-a', 'Atlas', {securityUpdates: 0})});
  assert(result.card.shadowRoot.querySelector('.detailed-server .status').getAttribute('title').includes('No problems reported'));

  // A failing service chip names the exact state and what that state means.
  result = makeCard({mode: 'compact'}, {'sensor.sick_snapshot': sick});
  const sshChip = [...result.card.shadowRoot.querySelectorAll('.service-chip')].find(c => c.textContent.includes('SSH'));
  assert(sshChip.classList.contains('problem'));
  assert(sshChip.getAttribute('title').includes('failed'));
  assert(sshChip.getAttribute('title').includes('expected to be running'));
  assert(sshChip.getAttribute('title').includes('systemd stopped trying to restart it'));
  const compactStatus = result.card.shadowRoot.querySelector('.compact-server .status');
  assert(compactStatus.getAttribute('title').includes('Service down'));
  // Offline servers explain the staleness instead of listing stale problems.
  result = makeCard({mode: 'compact'}, {'sensor.jupiter_snapshot': snapshot('machine-j', 'Jupiter', {online: false})});
  assert(result.card.shadowRoot.querySelector('.compact-server .status').getAttribute('title').includes('last reported data'));

  // The updates footer is colour-coded: security beats plain pending beats clean.
  const level = states => makeCard({mode: 'compact'}, states).card.shadowRoot.querySelector('.updates-line').className;
  assert(level({'sensor.sick_snapshot': sick}).includes('critical'));
  assert(level({'sensor.a': snapshot('machine-a', 'Atlas', {updates: {pending: 5, pending_security: 0, packages: []}})}).includes('warning'));
  assert(level({'sensor.a': snapshot('machine-a', 'Atlas', {updates: {pending: 0, pending_security: 0, packages: []}})}).includes('ok'));
  assert(level({'sensor.a': snapshot('machine-a', 'Atlas', {updates: {packages: []}})}).includes('unknown'));

  // Compact cards lay out as columns so headers align at the top of a row and the
  // updates footer aligns at the bottom, whatever each card holds in between.
  assert(script.includes('.compact-server{display:flex;flex-direction:column'));
  assert(script.includes('height:100%'));
  assert(script.includes('.compact-footer{display:flex;justify-content:space-between;flex-wrap:wrap;gap:5px;margin-top:auto'));

  // Content escaping and responsive/full-width CSS remain enforced.
  result = makeCard({mode: 'compact'}, {'sensor.bad': snapshot('machine-x', '<script>alert(1)</script>')});
  assert.equal(result.card.shadowRoot.querySelectorAll('script').length, 0);
  assert(result.card.shadowRoot.textContent.includes('<script>alert(1)</script>'));
  assert(script.includes('repeat(auto-fit,minmax'));
  assert(script.includes('@media(max-width:700px)'));
  assert(script.includes('width:100%;max-width:none'));

  console.log('card state, multi-server, data, management, compact/detailed, explanations, WoL, filtering, sizing and escaping: OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
