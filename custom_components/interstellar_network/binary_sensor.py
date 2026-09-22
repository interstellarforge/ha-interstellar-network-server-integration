"""Binary sensors for Interstellar Network."""
from __future__ import annotations
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory
from . import InterstellarConfigEntry
from .entity import InterstellarEntity, machine_id

class BoolSensor(InterstellarEntity,BinarySensorEntity):
    def __init__(self,c,key,name,value_fn,device_class=None,category=EntityCategory.DIAGNOSTIC,attributes_fn=None):
        super().__init__(c); self.interstellar_key=key; self._attr_unique_id=f"{machine_id(c.data)}_{key}"; self._attr_name=name; self._value_fn=value_fn; self._attrs_fn=attributes_fn; self._attr_device_class=device_class; self._attr_entity_category=category
    @property
    def is_on(self): return self._value_fn(self.coordinator.data)
    @property
    def extra_state_attributes(self):
        attrs=self.interstellar_attributes()
        if self._attrs_fn: attrs.update(self._attrs_fn(self.coordinator.data) or {})
        return attrs

def static_entities(c):
    return [
      BoolSensor(c,"system_healthy","System healthy",lambda d:(d.get("system",{}).get("failed_systemd_units",0)==0 and d.get("service_policy",{}).get("healthy",True) and d.get("time",{}).get("synchronized") is not False and (d.get("disk_root",{}).get("used_percent") or 0)<90),BinarySensorDeviceClass.CONNECTIVITY,None),
      BoolSensor(c,"reboot_required","Reboot required",lambda d:bool(d.get("system",{}).get("reboot_required")),BinarySensorDeviceClass.PROBLEM),
      BoolSensor(c,"time_synchronized","Time synchronized",lambda d:d.get("time",{}).get("synchronized"),BinarySensorDeviceClass.CONNECTIVITY),
      BoolSensor(c,"expected_services_healthy","Expected services healthy",lambda d:d.get("service_policy",{}).get("healthy",True),BinarySensorDeviceClass.CONNECTIVITY,None,lambda d:{"problems":d.get("service_policy",{}).get("problems",[])}),
    ]

def dynamic_entities(c):
    out=[]
    expected=set(c.data.get("service_policy",{}).get("expected_services",[]))
    for service in c.data.get("services",{}):
        safe=service.replace(".","_").replace("@","_")
        out.append(BoolSensor(c,f"service_{safe}",f"Service {service}",lambda d,s=service:d.get("services",{}).get(s)=="active",BinarySensorDeviceClass.RUNNING,EntityCategory.DIAGNOSTIC,lambda d,s=service:{"raw_state":d.get("services",{}).get(s),"expected":s in d.get("service_policy",{}).get("expected_services",[])}))
        if service in expected:
            out.append(BoolSensor(c,f"expected_service_{safe}_problem",f"Expected service {service} problem",lambda d,s=service:d.get("services",{}).get(s)!="active",BinarySensorDeviceClass.PROBLEM,None,lambda d,s=service:{"raw_state":d.get("services",{}).get(s)}))
    return out

async def async_setup_entry(hass,entry:InterstellarConfigEntry,async_add_entities):
    c=entry.runtime_data.coordinator
    entities=static_entities(c); async_add_entities(entities)
    added=set(e.unique_id for e in entities)
    def add_dynamic():
        new=[]
        for e in dynamic_entities(c):
            if e.unique_id not in added: added.add(e.unique_id); new.append(e)
        if new: async_add_entities(new)
    add_dynamic(); entry.async_on_unload(c.async_add_listener(add_dynamic))
