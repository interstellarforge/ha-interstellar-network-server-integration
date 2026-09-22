const {JSDOM} = require('jsdom');
const fs = require('fs');
const assert = require('assert');
const path = require('path');

const script = fs.readFileSync(path.join(__dirname, '../custom_components/interstellar_network/frontend/interstellar-network-card.js'), 'utf8');
const dom = new JSDOM('<html><body></body></html>', {runScripts: 'dangerously', url: 'http://localhost'});
dom.window.eval(script);

assert.equal(dom.window.interstellarNetworkCardVersion, '0.5.0');
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
        updates: {pending: 2, pending_security: 1, packages: []},
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
          unavailable_reason: managed ? null : 'Control API unavailable',
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
  const systemDetails = result.card.shadowRoot.querySelector('[data-section="system"]');
  const servicesDetails = result.card.shadowRoot.querySelector('[data-section="services"]');
  servicesDetails.open = true;
  servicesDetails.dispatchEvent(new dom.window.Event('toggle'));
  systemDetails.open = false;
  systemDetails.dispatchEvent(new dom.window.Event('toggle'));
  const updatedAtlas = snapshot('machine-a', 'Atlas');
  updatedAtlas.attributes.snapshot.cpu.used_percent = 43;
  result.card.hass = {states: {'sensor.atlas_snapshot': updatedAtlas}, callService: async (...args) => result.calls.push(args)};
  assert.equal(result.card.shadowRoot.querySelector('[data-section="system"]').open, false);
  assert.equal(result.card.shadowRoot.querySelector('[data-section="services"]').open, true);
  const reopenedSystem = result.card.shadowRoot.querySelector('[data-section="system"]');
  reopenedSystem.open = true;
  reopenedSystem.dispatchEvent(new dom.window.Event('toggle'));
  result.card.hass = {states: {'sensor.atlas_snapshot': updatedAtlas}, callService: async (...args) => result.calls.push(args)};
  assert.equal(result.card.shadowRoot.querySelector('[data-section="system"]').open, true);
  assert.equal(result.card.shadowRoot.querySelector('[data-section="services"]').open, true);

  // Manage expansion and button clicks survive a render and don't toggle the parent.
  let manage = result.card.shadowRoot.querySelector('[data-section="manage"]');
  manage.open = true;
  manage.dispatchEvent(new dom.window.Event('toggle'));
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
  assert(result.card.shadowRoot.textContent.includes('This server is currently read-only'));
  assert.equal(result.card.shadowRoot.querySelectorAll('[data-action="reboot"]').length, 0);
  assert.equal(result.card.shadowRoot.querySelectorAll('[data-action="install_all_updates"]').length, 0);
  assert(result.card.shadowRoot.querySelector('[data-action="refresh_stats"]'));

  // Wake state is explicit and survives render updates.
  dom.window.setTimeout = () => 0;
  result = makeCard({mode: 'detailed', default_expanded: {manage: true}}, {'sensor.jupiter_snapshot': snapshot('machine-j', 'Jupiter', {online: false, wake: true})});
  result.card.shadowRoot.querySelector('[data-action="wake"]').click();
  await tick();
  assert.equal(result.calls.at(-1)[1], 'wake');
  assert(result.card.shadowRoot.textContent.includes('Waking'));
  result.card.hass = {states: {'sensor.jupiter_snapshot': snapshot('machine-j', 'Jupiter', {online: false, wake: true})}, callService: async (...args) => result.calls.push(args)};
  assert(result.card.shadowRoot.textContent.includes('Waking'));

  // Content escaping and responsive/full-width CSS remain enforced.
  result = makeCard({mode: 'compact'}, {'sensor.bad': snapshot('machine-x', '<script>alert(1)</script>')});
  assert.equal(result.card.shadowRoot.querySelectorAll('script').length, 0);
  assert(result.card.shadowRoot.textContent.includes('<script>alert(1)</script>'));
  assert(script.includes('repeat(auto-fit,minmax'));
  assert(script.includes('@media(max-width:700px)'));
  assert(script.includes('width:100%;max-width:none'));

  console.log('card state, multi-server, data, management, compact/detailed, WoL, filtering, sizing and escaping: OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
