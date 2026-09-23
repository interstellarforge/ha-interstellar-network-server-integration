"""Sensors for Interstellar Network."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfTime
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util
from . import InterstellarConfigEntry
from .entity import InterstellarEntity, machine_id
from .wol import effective_wol

ValueFn=Callable[[dict[str,Any]],Any]
def get(data,*path):
    value=data
    for key in path:
        if not isinstance(value,dict): return None
        value=value.get(key)
    return value

def timestamp(value):
    if not value: return None
    if isinstance(value,datetime): return value
    return dt_util.parse_datetime(str(value))

@dataclass(frozen=True,kw_only=True)
class Desc(SensorEntityDescription):
    value_fn: ValueFn

D=(
 Desc(key="server_roles", translation_key="server_roles", value_fn=lambda d:", ".join(get(d,"host","roles") or ["general"])),
 Desc(key="cpu_usage",translation_key="cpu_usage",native_unit_of_measurement=PERCENTAGE,state_class=SensorStateClass.MEASUREMENT,suggested_display_precision=1,value_fn=lambda d:get(d,"cpu","used_percent")),
 Desc(key="cpu_iowait",translation_key="cpu_iowait",native_unit_of_measurement=PERCENTAGE,state_class=SensorStateClass.MEASUREMENT,suggested_display_precision=2,value_fn=lambda d:get(d,"cpu","iowait_percent")),
 Desc(key="cpu_steal",translation_key="cpu_steal",native_unit_of_measurement=PERCENTAGE,state_class=SensorStateClass.MEASUREMENT,suggested_display_precision=2,value_fn=lambda d:get(d,"cpu","steal_percent")),
 Desc(key="load_1m",translation_key="load_1m",state_class=SensorStateClass.MEASUREMENT,suggested_display_precision=2,value_fn=lambda d:get(d,"cpu","load","1m")),
 Desc(key="memory_usage",translation_key="memory_usage",native_unit_of_measurement=PERCENTAGE,state_class=SensorStateClass.MEASUREMENT,suggested_display_precision=1,value_fn=lambda d:get(d,"memory","used_percent")),
 Desc(key="swap_usage",translation_key="swap_usage",native_unit_of_measurement=PERCENTAGE,state_class=SensorStateClass.MEASUREMENT,suggested_display_precision=1,value_fn=lambda d:get(d,"memory","swap","used_percent")),
 Desc(key="root_disk_usage",translation_key="root_disk_usage",native_unit_of_measurement=PERCENTAGE,state_class=SensorStateClass.MEASUREMENT,suggested_display_precision=1,value_fn=lambda d:get(d,"disk_root","used_percent")),
 Desc(key="root_inode_usage",translation_key="root_inode_usage",native_unit_of_measurement=PERCENTAGE,state_class=SensorStateClass.MEASUREMENT,suggested_display_precision=1,value_fn=lambda d:get(d,"disk_root","inode_used_percent")),
 Desc(key="uptime",translation_key="uptime",native_unit_of_measurement=UnitOfTime.SECONDS,device_class=SensorDeviceClass.DURATION,state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:get(d,"host","uptime_seconds")),
 Desc(key="boot_time",translation_key="boot_time",device_class=SensorDeviceClass.TIMESTAMP,value_fn=lambda d:timestamp(get(d,"host","boot_time_utc"))),
 Desc(key="pending_updates",translation_key="pending_updates",state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:get(d,"updates","pending")),
 Desc(key="pending_security_updates",translation_key="pending_security_updates",state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:get(d,"updates","pending_security")),
 Desc(key="last_successful_update",translation_key="last_successful_update",device_class=SensorDeviceClass.TIMESTAMP,value_fn=lambda d:timestamp(get(d,"updates","last_successful_update_utc"))),
 Desc(key="failed_systemd_units",translation_key="failed_systemd_units",state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:get(d,"system","failed_systemd_units")),
 Desc(key="oom_kills",translation_key="oom_kills",state_class=SensorStateClass.TOTAL_INCREASING,value_fn=lambda d:get(d,"system","oom_kills_since_boot")),
 Desc(key="listening_tcp_ports",translation_key="listening_tcp_ports",state_class=SensorStateClass.MEASUREMENT,value_fn=lambda d:len(get(d,"network","listening_tcp") or [])),
 Desc(key="lan_ipv4",translation_key="lan_ipv4",value_fn=lambda d:next((a.get("address") for a in (get(d,"network","addresses") or []) if a.get("kind")=="lan"),None)),
 Desc(key="tailscale_ipv4",translation_key="tailscale_ipv4",value_fn=lambda d:get(d,"network","tailscale_ipv4")),
)

class StandardSensor(InterstellarEntity,SensorEntity):
    entity_description: Desc
    def __init__(self,c,desc):
        super().__init__(c); self.entity_description=desc; self.interstellar_key=desc.key; self._attr_unique_id=f"{machine_id(c.data)}_{desc.key}"
    @property
    def native_value(self): return self.entity_description.value_fn(self.coordinator.data)
    @property
    def extra_state_attributes(self):
        attrs=self.interstellar_attributes()
        if self.interstellar_key=="listening_tcp_ports": attrs["sockets"]=get(self.coordinator.data,"network","listening_tcp") or []
        if self.interstellar_key in ("pending_updates","pending_security_updates"): attrs["packages"]=get(self.coordinator.data,"updates","packages") or []
        return attrs

class DynamicSensor(InterstellarEntity,SensorEntity):
    def __init__(self,c,key,name,value_fn,unit=None,state_class=None,device_class=None,category=EntityCategory.DIAGNOSTIC,attributes_fn=None):
        super().__init__(c); self.interstellar_key=key; self._attr_unique_id=f"{machine_id(c.data)}_{key}"; self._attr_name=name
        self._value_fn=value_fn; self._attrs_fn=attributes_fn; self._attr_native_unit_of_measurement=unit; self._attr_state_class=state_class; self._attr_device_class=device_class; self._attr_entity_category=category
    @property
    def native_value(self): return self._value_fn(self.coordinator.data)
    @property
    def extra_state_attributes(self):
        attrs=self.interstellar_attributes()
        if self._attrs_fn: attrs.update(self._attrs_fn(self.coordinator.data) or {})
        return attrs

def dynamic_entities(c):
    entities=[]
    for t in c.data.get("temperatures",[]):
        name=t.get("name"); safe=(name or "sensor").lower().replace("/","_").replace(" ","_")
        entities.append(DynamicSensor(c,f"temperature_{safe}",f"Temperature {name}",lambda d,n=name:next((x.get("celsius") for x in d.get("temperatures",[]) if x.get("name")==n),None),UnitOfTemperature.CELSIUS,SensorStateClass.MEASUREMENT,SensorDeviceClass.TEMPERATURE))
    for fs in c.data.get("filesystems",[]):
        mount=fs.get("mountpoint"); safe=(mount or "root").strip("/").replace("/","_") or "root"
        if mount!="/":
            entities.append(DynamicSensor(c,f"fs_{safe}_usage",f"Filesystem {mount} usage",lambda d,m=mount:next((x.get("used_percent") for x in d.get("filesystems",[]) if x.get("mountpoint")==m),None),PERCENTAGE,SensorStateClass.MEASUREMENT))
            entities.append(DynamicSensor(c,f"fs_{safe}_inode_usage",f"Filesystem {mount} inode usage",lambda d,m=mount:next((x.get("inode_used_percent") for x in d.get("filesystems",[]) if x.get("mountpoint")==m),None),PERCENTAGE,SensorStateClass.MEASUREMENT))
    for iface in c.data.get("network",{}).get("interfaces",[]):
        name=iface.get("interface"); safe=(name or "iface").replace(".","_")
        for suffix,label,field,unit,state in (("rx_total","RX total","rx_bytes","B",SensorStateClass.TOTAL_INCREASING),("tx_total","TX total","tx_bytes","B",SensorStateClass.TOTAL_INCREASING),("rx_rate","RX rate","rx_bytes_per_second","B/s",SensorStateClass.MEASUREMENT),("tx_rate","TX rate","tx_bytes_per_second","B/s",SensorStateClass.MEASUREMENT)):
            entities.append(DynamicSensor(c,f"net_{safe}_{suffix}",f"{name} {label}",lambda d,n=name,f=field:next((x.get(f) for x in d.get("network",{}).get("interfaces",[]) if x.get("interface")==n),None),unit,state,SensorDeviceClass.DATA_SIZE if field.endswith("bytes") else None))
    for dev in c.data.get("disk_io",[]):
        name=dev.get("device"); safe=(name or "disk").replace("/","_")
        for suffix,label,field,unit,state in (("read_total","Read total","read_bytes","B",SensorStateClass.TOTAL_INCREASING),("write_total","Write total","write_bytes","B",SensorStateClass.TOTAL_INCREASING),("read_rate","Read rate","read_bytes_per_second","B/s",SensorStateClass.MEASUREMENT),("write_rate","Write rate","write_bytes_per_second","B/s",SensorStateClass.MEASUREMENT)):
            entities.append(DynamicSensor(c,f"disk_{safe}_{suffix}",f"{name} {label}",lambda d,n=name,f=field:next((x.get(f) for x in d.get("disk_io",[]) if x.get("device")==n),None),unit,state,SensorDeviceClass.DATA_SIZE if field.endswith("bytes") else None))
    return entities


class ServerSnapshotSensor(InterstellarEntity, SensorEntity):
    """Card data, grouped per machine without hundreds of UI entities."""
    interstellar_key = "server_snapshot"
    _attr_name = "Server snapshot"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{machine_id(coordinator.data)}_server_snapshot"

    @property
    def available(self):
        return True

    @property
    def native_value(self):
        return "online" if self.coordinator.last_update_success else "offline"

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data
        control = d.get("_control", {})
        entry = self.coordinator.config_entry
        wake = effective_wol(entry.options if entry else {}, d)
        return {**self.interstellar_attributes(),
                "snapshot": {
                    "host": d.get("host", {}), "timestamp_utc": d.get("timestamp_utc"), "agent_version": d.get("agent_version"),
                    "cpu": d.get("cpu", {}), "memory": d.get("memory", {}),
                    "disk_root": d.get("disk_root", {}), "filesystems": d.get("filesystems", [])[:20],
                    "disk_io": d.get("disk_io", [])[:20], "network": d.get("network", {}),
                    "temperatures": d.get("temperatures", []), "services": d.get("services", {}),
                    "service_policy": d.get("service_policy", {}), "updates": d.get("updates", {}),
                    "system": d.get("system", {}), "time": d.get("time", {}),
                    "wake_on_lan": wake, "wake_sent_at": self.coordinator.last_wake_sent_at,
                    "control": {"available": bool(self.coordinator.last_update_success and
                                                  control.get("control_available", control.get("available", bool(control)))),
                                "unavailable_reason": control.get("control_unavailable_reason") or d.get("control_plane", {}).get("control_unavailable_reason"),
                                # Stable code so the card can explain the cause rather
                                # than guess from prose. See api.py for the values.
                                "error_code": control.get("control_error_code"),
                                "service": {key: d.get("control_plane", {}).get(key) for key in (
                                    "installed", "api_service_active", "helper_service_active",
                                    "serve_expected")},
                                "version": control.get("version"), "toolbox_version": control.get("toolbox_version"),
                                "tailscale_version": control.get("tailscale_version") or get(d, "network", "tailscale", "version"),
                                "tailscale_daemon_version": control.get("tailscale_daemon_version") or get(d, "network", "tailscale", "daemon_version"),
                                "boot_time_utc": control.get("boot_time_utc"),
                                "last_reboot_action": control.get("last_reboot_action"),
                                "last_reboot_duration_seconds": control.get("last_reboot_duration_seconds"),
                                "policy": control.get("policy", {}), "docker": control.get("docker", {}),
                                "actions": control.get("actions", [])[:10]},
                }}

async def async_setup_entry(hass,entry:InterstellarConfigEntry,async_add_entities):
    c=entry.runtime_data.coordinator
    entities=[StandardSensor(c,d) for d in D] + [ServerSnapshotSensor(c)]
    async_add_entities(entities)
    added=set(e.unique_id for e in entities)
    def add_dynamic():
        new=[]
        for e in dynamic_entities(c):
            if e.unique_id not in added: added.add(e.unique_id); new.append(e)
        if new: async_add_entities(new)
    add_dynamic()
    entry.async_on_unload(c.async_add_listener(add_dynamic))
