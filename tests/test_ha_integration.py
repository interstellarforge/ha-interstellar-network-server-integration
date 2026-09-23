"""Integration behavior against Home Assistant Core 2026.8."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.config_entries import ConfigEntryNotReady
    from homeassistant.helpers.update_coordinator import UpdateFailed
    from custom_components.interstellar_network import async_migrate_entry, async_setup, async_setup_entry, InterstellarRuntimeData
    from custom_components.interstellar_network.api import (
        InterstellarCannotConnect, InterstellarCapabilityMissing, InterstellarConnectionRefused,
        InterstellarInvalidResponse, InterstellarNotFound, InterstellarServerError,
        InterstellarServiceUnavailable, InterstellarTimeout)
    from custom_components.interstellar_network.config_flow import machine_id, legacy_entry_exists, InterstellarServerConfigFlow, InterstellarOptionsFlow
    from custom_components.interstellar_network import config_flow
    from custom_components.interstellar_network.coordinator import InterstellarCoordinator
    from custom_components.interstellar_network.sensor import ServerSnapshotSensor, StandardSensor, D
    from custom_components.interstellar_network.wol import async_send_magic_packet, effective_wol, normalize_mac, validate_broadcast
    from custom_components.interstellar_network.const import CARD_PATH, CARD_URL, PLATFORMS
    from custom_components.interstellar_network import repairs
except ImportError:
    raise unittest.SkipTest("Home Assistant Core is unavailable")


def stats(identifier="machine-a", name="atlas"):
    return {"status":"ok", "host":{"machine_id":identifier,"hostname":name,"roles":["docker-host"],"os_version":"13"},
            "updates":{"pending":2,"pending_security":1,"packages":[]},
            "services":{"ssh":"active","docker":"active"},
            "service_policy":{"expected_services":["ssh","docker"],"manageable_services":["docker"],"problems":[]},
            "system":{"failed_systemd_units":0,"reboot_required":False,"oom_kills_since_boot":0},
            "disk_root":{"used_percent":20,"inode_used_percent":2},"time":{"synchronized":True}}


class FakeCoordinator:
    def __init__(self,data):
        self.data=data
        self.client=SimpleNamespace(base_url="https://atlas.ts.net")
        self.control_client=AsyncMock()
        self.async_request_refresh=AsyncMock()
        self.last_update_success=True
        self.last_wake_sent_at=None
        self.config_entry=None
        self.async_update_listeners=MagicMock()


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_card_resource_uses_release_cache_key(self):
        self.assertEqual("/interstellar_network/interstellar-network-card.js", CARD_PATH)
        self.assertEqual(f"{CARD_PATH}?v=0.5.2", CARD_URL)

    async def test_migration_keeps_unique_id(self):
        self.assertEqual("machine-a",machine_id(stats()))
        entry=SimpleNamespace(version=1,unique_id="old-host",data={"url":"https://atlas.ts.net"})
        hass=SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=MagicMock()))
        self.assertTrue(await async_migrate_entry(hass,entry))
        hass.config_entries.async_update_entry.assert_called_once_with(entry,version=2)
        self.assertEqual("old-host",entry.unique_id)

    async def test_legacy_domain_guard(self):
        legacy=SimpleNamespace(unique_id="machine-a",data={"url":"https://atlas.ts.net","verify_ssl":True})
        hass=SimpleNamespace(config_entries=SimpleNamespace(async_entries=lambda domain:[legacy] if domain=="interstellar_server" else []))
        self.assertTrue(legacy_entry_exists(hass,"machine-a","https://new-name.ts.net"))
        self.assertTrue(legacy_entry_exists(hass,"different","https://atlas.ts.net"))
        self.assertFalse(legacy_entry_exists(hass,"machine-b","https://jupiter.ts.net"))

    async def test_config_flow_and_control_url_validation(self):
        flow=InterstellarServerConfigFlow()
        form=await flow.async_step_user()
        self.assertEqual("user",form["step_id"])
        options=InterstellarOptionsFlow()
        rejected=await options.async_step_init({"control_url":"http://localhost:9128"})
        self.assertEqual("https_required",rejected["errors"]["control_url"])
        accepted=await options.async_step_init({"control_url":"https://atlas.ts.net:8443"})
        self.assertEqual("https://atlas.ts.net:8443",accepted["data"]["control_url"])
        invalid_mac=await options.async_step_init({"control_url":"", "wake_on_lan_enabled":True,
            "wake_on_lan_mac":"not-a-mac", "wake_on_lan_broadcast":"192.168.1.255"})
        self.assertEqual("invalid_mac",invalid_mac["errors"]["wake_on_lan_mac"])
        invalid_broadcast=await options.async_step_init({"control_url":"", "wake_on_lan_enabled":True,
            "wake_on_lan_mac":"aa:bb:cc:dd:ee:fe", "wake_on_lan_broadcast":"192.168.1.42"})
        self.assertEqual("invalid_broadcast",invalid_broadcast["errors"]["wake_on_lan_broadcast"])
        configured=await options.async_step_init({"control_url":"", "wake_on_lan_enabled":True,
            "wake_on_lan_mac":"AA:BB:CC:DD:EE:FE", "wake_on_lan_broadcast":"192.168.1.255"})
        self.assertEqual("aa:bb:cc:dd:ee:fe",configured["data"]["wake_on_lan_mac"])

    async def test_zeroconf_uses_stats_machine_id(self):
        flow=InterstellarServerConfigFlow()
        flow.hass=SimpleNamespace(config_entries=SimpleNamespace(async_entries=lambda domain:[]))
        flow.context={}
        discovered=SimpleNamespace(properties={"url":"https://atlas.ts.net", "machine_id":"stale-mdns-id"})
        with patch.object(config_flow,"validate",new=AsyncMock(return_value=stats())), \
             patch.object(flow,"async_set_unique_id",new=AsyncMock()) as set_id, \
             patch.object(flow,"_abort_if_unique_id_configured"):
            result=await flow.async_step_zeroconf(discovered)
        set_id.assert_awaited_once_with("machine-a")
        self.assertEqual("zeroconf_confirm",result["step_id"])

    async def test_coordinator_handles_control_and_health_outages(self):
        health=SimpleNamespace(async_get_stats=AsyncMock(return_value=stats()))
        control=SimpleNamespace(async_get_control=AsyncMock(side_effect=InterstellarCannotConnect("offline")))
        coordinator=InterstellarCoordinator(MagicMock(),health,control)
        data=await coordinator._async_update_data()
        self.assertEqual("machine-a",data["host"]["machine_id"])
        self.assertFalse(data["_control"]["available"])
        health.async_get_stats.side_effect=InterstellarCannotConnect("offline")
        with self.assertRaises(UpdateFailed):
            await coordinator._async_update_data()

    async def test_control_403_is_reported_as_a_missing_capability(self):
        """Atlas and Jupiter returned 403 while their control services ran fine.

        Reporting that as "Control API is not active" sent debugging down the
        wrong path, so an authorization failure must never borrow the health
        agent's local service status.
        """
        payload=stats()
        payload["control_plane"]={"installed":True,"api_service_active":True,
                                  "helper_service_active":True,"serve_expected":True,
                                  "control_service_unavailable_reason":None}
        health=SimpleNamespace(async_get_stats=AsyncMock(return_value=payload))
        control=SimpleNamespace(async_get_control=AsyncMock(
            side_effect=InterstellarCapabilityMissing(403,"HTTP 403: Tailscale control capability required")))
        coordinator=InterstellarCoordinator(MagicMock(),health,control)
        data=await coordinator._async_update_data()
        self.assertFalse(data["_control"]["available"])
        self.assertEqual("tailscale_capability_missing",data["_control"]["control_error_code"])
        self.assertEqual("Tailscale control capability is not granted to Home Assistant",
                         data["_control"]["control_unavailable_reason"])
        self.assertNotIn("not active",data["_control"]["control_unavailable_reason"])

    async def test_control_failures_keep_distinct_reasons(self):
        for error,code in ((InterstellarNotFound(404),"not_found"),
                           (InterstellarServerError(500),"server_error"),
                           (InterstellarServiceUnavailable(503),"service_unavailable"),
                           (InterstellarTimeout("slow"),"timeout"),
                           (InterstellarInvalidResponse("bad"),"invalid_response")):
            health=SimpleNamespace(async_get_stats=AsyncMock(return_value=stats()))
            control=SimpleNamespace(async_get_control=AsyncMock(side_effect=error))
            coordinator=InterstellarCoordinator(MagicMock(),health,control)
            data=await coordinator._async_update_data()
            self.assertEqual(code,data["_control"]["control_error_code"])
            self.assertEqual(error.reason,data["_control"]["control_unavailable_reason"])

    async def test_refused_connection_prefers_the_node_local_reason(self):
        """A refused connection never reached the API, so the node explains it best."""
        payload=stats()
        payload["control_plane"]={"installed":False,
                                  "control_service_unavailable_reason":"Control plane is not installed"}
        health=SimpleNamespace(async_get_stats=AsyncMock(return_value=payload))
        control=SimpleNamespace(async_get_control=AsyncMock(side_effect=InterstellarConnectionRefused("refused")))
        coordinator=InterstellarCoordinator(MagicMock(),health,control)
        data=await coordinator._async_update_data()
        self.assertEqual("connection_refused",data["_control"]["control_error_code"])
        self.assertEqual("Control plane is not installed",data["_control"]["control_unavailable_reason"])

    async def test_missing_control_url_is_its_own_state(self):
        health=SimpleNamespace(async_get_stats=AsyncMock(return_value=stats()))
        coordinator=InterstellarCoordinator(MagicMock(),health,None)
        data=await coordinator._async_update_data()
        self.assertEqual("not_configured",data["_control"]["control_error_code"])
        self.assertFalse(data["_control"]["available"])

    async def test_snapshot_surfaces_control_error_code(self):
        payload=stats()
        payload["_control"]={"available":False,"control_error_code":"tailscale_capability_missing",
                             "control_unavailable_reason":"Tailscale control capability is not granted to Home Assistant"}
        payload["control_plane"]={"installed":True,"api_service_active":True,
                                  "helper_service_active":True,"serve_expected":True}
        sensor=ServerSnapshotSensor(FakeCoordinator(payload))
        control=sensor.extra_state_attributes["snapshot"]["control"]
        self.assertFalse(control["available"])
        self.assertEqual("tailscale_capability_missing",control["error_code"])
        self.assertIn("capability is not granted",control["unavailable_reason"])
        # Local service facts stay separate from remote authorization.
        self.assertTrue(control["service"]["api_service_active"])
        self.assertTrue(control["service"]["serve_expected"])

    async def test_control_url_is_derived_from_a_magicdns_health_url(self):
        self.assertEqual("https://atlas.tail24b95.ts.net:8443",
                         config_flow.suggested_control_url("https://atlas.tail24b95.ts.net"))
        self.assertEqual("https://jupiter-1.tail24b95.ts.net:8443",
                         config_flow.suggested_control_url("https://jupiter-1.tail24b95.ts.net/"))
        # Anything that is not a plain MagicDNS HTTPS host is left to the operator.
        for url in ("http://atlas.tail24b95.ts.net", "https://192.168.1.10",
                    "https://atlas.example.com", "https://atlas.tail24b95.ts.net:9127",
                    "https://atlas.tail24b95.ts.net/control", ""):
            self.assertEqual("",config_flow.suggested_control_url(url),url)

    async def test_existing_control_url_with_a_path_is_retained(self):
        """A hand-configured /control URL must not break by reopening the form."""
        options=InterstellarOptionsFlow()
        entry=SimpleNamespace(options={"control_url":"https://atlas.tail24b95.ts.net/control"},
                              data={"url":"https://atlas.tail24b95.ts.net"},runtime_data=None)
        with patch.object(type(options),"config_entry",property(lambda self:entry)):
            kept=await options.async_step_init({"control_url":"https://atlas.tail24b95.ts.net/control"})
            self.assertEqual("https://atlas.tail24b95.ts.net/control",kept["data"]["control_url"])
            # Changing it to another path-based URL is still rejected.
            rejected=await options.async_step_init({"control_url":"https://atlas.tail24b95.ts.net/other"})
            self.assertEqual("https_required",rejected["errors"]["control_url"])

    async def test_control_metadata_is_preserved_for_card_and_offline_state(self):
        data=stats();data.update({"services":{"ssh":"active"},"filesystems":[{"mountpoint":"/srv"}],
            "disk_io":[{"device":"sda"}],"temperatures":[{"name":"CPU","celsius":42}],"time":{"synchronized":True}})
        control_state={"control_available":True,"version":"0.2.1","toolbox_version":"4.5.1",
            "tailscale_version":"1.102.4","tailscale_daemon_version":"1.102.4-t3caf7d9e7-g084ee3b64",
            "boot_time_utc":"2026-09-21T14:27:23+00:00",
            "last_reboot_action":{"status":"successful","timestamp":"2026-09-21T14:27:00+00:00"},
            "last_reboot_duration_seconds":75,"policy":{"manageable_services":["docker"]},
            "docker":{"installed":True},"actions":[]}
        health=SimpleNamespace(async_get_stats=AsyncMock(return_value=data))
        control=SimpleNamespace(async_get_control=AsyncMock(return_value=control_state))
        coordinator=InterstellarCoordinator(MagicMock(),health,control)
        # _async_update_data returns the payload; DataUpdateCoordinator normally
        # assigns it, so mirror that before reading entity attributes.
        coordinator.data=await coordinator._async_update_data()
        self.assertEqual("1.102.4",coordinator.last_known["_control"]["tailscale_version"])
        self.assertEqual([{"mountpoint":"/srv"}],coordinator.last_known["filesystems"])
        self.assertEqual({"ssh":"active"},coordinator.last_known["services"])
        snapshot=ServerSnapshotSensor(coordinator).extra_state_attributes["snapshot"]
        self.assertTrue(snapshot["control"]["available"])
        self.assertIsNone(snapshot["control"]["error_code"])
        self.assertEqual("4.5.1",snapshot["control"]["toolbox_version"])
        self.assertEqual("0.2.1",snapshot["control"]["version"])
        self.assertEqual("1.102.4",snapshot["control"]["tailscale_version"])
        self.assertEqual(75,snapshot["control"]["last_reboot_duration_seconds"])
        self.assertEqual("successful",snapshot["control"]["last_reboot_action"]["status"])
        self.assertEqual("2026-09-21T14:27:23+00:00",snapshot["control"]["boot_time_utc"])

    async def test_wol_last_known_saved_before_health_outage(self):
        data=stats();data["wake_on_lan"]={"supported":True,"enabled":True,
            "mac_address":"aa:bb:cc:dd:ee:fe","broadcast_address":"192.168.1.255"}
        health=SimpleNamespace(async_get_stats=AsyncMock(return_value=data))
        store=SimpleNamespace(async_save=AsyncMock())
        coordinator=InterstellarCoordinator(MagicMock(),health,None,store=store)
        await coordinator._async_update_data()
        self.assertEqual(data["wake_on_lan"],store.async_save.call_args.args[0]["last_known"]["wake_on_lan"])
        health.async_get_stats.side_effect=InterstellarCannotConnect("powered off")
        with self.assertRaises(UpdateFailed):
            await coordinator._async_update_data()
        self.assertEqual("aa:bb:cc:dd:ee:fe",coordinator.last_known["wake_on_lan"]["mac_address"])

    async def test_offline_startup_restores_wake_metadata(self):
        known=stats();known["wake_on_lan"]={"supported":True,"enabled":True,
            "mac_address":"aa:bb:cc:dd:ee:fe","broadcast_address":"192.168.1.255"}
        coordinator=MagicMock(data=None,last_update_success=True)
        coordinator.async_config_entry_first_refresh=AsyncMock(side_effect=ConfigEntryNotReady())
        coordinator.async_add_listener.return_value=lambda:None
        entry=SimpleNamespace(data={"url":"https://atlas.ts.net","verify_ssl":True},options={},
            entry_id="entry-a",unique_id="machine-a",title="Atlas",async_on_unload=MagicMock(),
            add_update_listener=MagicMock(return_value=lambda:None))
        hass=MagicMock();hass.data={"interstellar_network":{}}
        hass.config_entries.async_forward_entry_setups=AsyncMock()
        hass.config_entries.async_entries.return_value=[]
        store=MagicMock();store.async_load=AsyncMock(return_value={"last_known":known})
        with patch("custom_components.interstellar_network.Store",return_value=store), \
             patch("custom_components.interstellar_network.InterstellarCoordinator",return_value=coordinator), \
             patch("custom_components.interstellar_network.InterstellarApiClient"), \
             patch("custom_components.interstellar_network.async_get_clientsession"), \
             patch("custom_components.interstellar_network.er.async_get") as registry, \
             patch("custom_components.interstellar_network.async_update_repairs"):
            registry.return_value.async_get_entity_id.return_value=None
            self.assertTrue(await async_setup_entry(hass,entry))
        self.assertEqual(known,coordinator.data)
        self.assertFalse(coordinator.last_update_success)
        self.assertEqual("machine-a",entry.runtime_data.coordinator.data["host"]["machine_id"])
        hass.config_entries.async_forward_entry_setups.assert_awaited_once()

    async def test_sensors_and_os_update_semantics(self):
        data=stats();data["_control"]={"policy":{"manageable_services":["docker"]},"actions":[]}
        coordinator=FakeCoordinator(data)
        existing=StandardSensor(coordinator,next(d for d in D if d.key=="pending_updates"))
        self.assertEqual("machine-a_pending_updates",existing.unique_id)
        self.assertEqual(2,existing.native_value)
        snapshot=ServerSnapshotSensor(coordinator)
        self.assertEqual("machine-a_server_snapshot",snapshot.unique_id)
        self.assertIn("docker",snapshot.extra_state_attributes["snapshot"]["service_policy"]["manageable_services"])
        self.assertTrue(snapshot.available)
        coordinator.last_update_success=False
        self.assertTrue(snapshot.available)
        self.assertEqual("offline",snapshot.native_value)
        coordinator.last_update_success=True
        self.assertNotIn("update",PLATFORMS)
        self.assertEqual("machine-a_pending_updates",existing.unique_id)

    async def test_repairs_create_and_remove_docker_issue(self):
        data=stats();data["_control"]={"policy":{"expected_containers":["plex"]},
             "docker":{"installed":True,"daemon_running":True,"containers":[{"name":"plex","state":"running","health":"unhealthy"}]}}
        entry=SimpleNamespace(entry_id="entry-a",title="Atlas",runtime_data=InterstellarRuntimeData(FakeCoordinator(data)))
        created=[];deleted=[]
        with patch.object(repairs.ir,"async_create_issue",side_effect=lambda *a,**k:created.append(a[2])),patch.object(repairs.ir,"async_delete_issue",side_effect=lambda *a:deleted.append(a[2])):
            repairs.async_update_repairs(MagicMock(),entry)
            self.assertIn("entry-a_container_unhealthy_plex",created)
            data["_control"]["docker"]["containers"][0]["health"]="healthy"
            repairs.async_update_repairs(MagicMock(),entry)
            self.assertIn("entry-a_container_unhealthy_plex",deleted)
            entry.runtime_data.coordinator.last_update_success=False
            created.clear()
            repairs.async_update_repairs(MagicMock(),entry)
            self.assertEqual([],created)

    async def test_multiple_server_routing_and_power_confirmation(self):
        hass=MagicMock();hass.http.async_register_static_paths=AsyncMock();hass.data={}
        hass.auth.async_get_user=AsyncMock(return_value=SimpleNamespace(is_admin=True))
        registered={};hass.services.async_register.side_effect=lambda domain,name,handler,**kw:registered.setdefault(name,handler)
        hass.async_create_task.side_effect=lambda coro:asyncio.create_task(coro)
        await async_setup(hass,{})
        a=FakeCoordinator(stats("machine-a","atlas"));b=FakeCoordinator(stats("machine-b","jupiter"))
        hass.data["interstellar_network"]={"a":InterstellarRuntimeData(a,a.control_client),"b":InterstellarRuntimeData(b,b.control_client)}
        handler=registered["manage"]
        with self.assertRaises(HomeAssistantError):
            await handler(SimpleNamespace(data={"server":"machine-a","action":"reboot","confirmation":"wrong","target":""},return_response=True,context=SimpleNamespace(user_id="admin")))
        self.assertEqual(0,a.control_client.async_action.await_count)
        b.control_client.async_action.return_value={"action_id":"id","status":"queued"}
        result=await handler(SimpleNamespace(data={"server":"machine-b","action":"reboot","confirmation":"jupiter","target":""},return_response=True,context=SimpleNamespace(user_id="admin")))
        self.assertEqual("id",result["action_id"])
        self.assertEqual(0,a.control_client.async_action.await_count)
        b.control_client.async_action.assert_awaited_once_with("/actions/reboot",{"confirm_hostname":"jupiter"})
        await asyncio.sleep(0)

    async def test_wake_offline_uses_last_known_metadata_and_admin(self):
        hass=MagicMock();hass.http.async_register_static_paths=AsyncMock();hass.data={}
        hass.auth.async_get_user=AsyncMock(return_value=SimpleNamespace(is_admin=True))
        registered={};hass.services.async_register.side_effect=lambda domain,name,handler,**kw:registered.setdefault(name,handler)
        await async_setup(hass,{})
        data=stats();data["wake_on_lan"]={"supported":True,"enabled":True,"interface":"enp3s0",
            "mac_address":"aa:bb:cc:dd:ee:fe","broadcast_address":"192.168.1.255"}
        coordinator=FakeCoordinator(data);coordinator.last_update_success=False
        entry=SimpleNamespace(unique_id="machine-a",options={})
        hass.data["interstellar_network"]={"a":InterstellarRuntimeData(coordinator,None,entry=entry)}
        call=SimpleNamespace(data={"server":"machine-a"},return_response=True,context=SimpleNamespace(user_id="admin"))
        with patch("custom_components.interstellar_network.async_send_magic_packet",new=AsyncMock()) as send:
            result=await registered["wake"](call)
        self.assertEqual("packet_sent",result["status"])
        self.assertIsNotNone(coordinator.last_wake_sent_at)
        send.assert_awaited_once_with(hass,"aa:bb:cc:dd:ee:fe","192.168.1.255")
        hass.auth.async_get_user.return_value=SimpleNamespace(is_admin=False)
        with self.assertRaises(HomeAssistantError):
            await registered["wake"](call)
        with self.assertRaises(HomeAssistantError):
            await registered["manage"](SimpleNamespace(data={"server":"machine-a","action":"reboot","confirmation":"atlas"},return_response=True,context=SimpleNamespace(user_id=None)))

    async def test_wol_validation_and_override(self):
        data={"wake_on_lan":{"supported":True,"enabled":True,"mac_address":"aa:bb:cc:dd:ee:fe","broadcast_address":"192.168.1.255"}}
        self.assertTrue(effective_wol({},data)["configured"])
        self.assertEqual("192.168.2.255",effective_wol({"wake_on_lan_broadcast":"192.168.2.255"},data)["broadcast_address"])
        with self.assertRaises(ValueError): normalize_mac("aa:bb:cc:dd:ee:gg")
        with self.assertRaises(ValueError): validate_broadcast("224.0.0.1")

    async def test_magic_packet_uses_ha_executor_and_selected_broadcast(self):
        hass=SimpleNamespace(async_add_executor_job=AsyncMock(side_effect=lambda job:job()))
        with patch("custom_components.interstellar_network.wol.wakeonlan.send_magic_packet") as send:
            await async_send_magic_packet(hass,"aa:bb:cc:dd:ee:fe","192.168.4.255")
        send.assert_called_once_with("aa:bb:cc:dd:ee:fe",ip_address="192.168.4.255")


if __name__ == "__main__": unittest.main()
