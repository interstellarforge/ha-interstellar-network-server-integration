"""Base entity helpers."""
from __future__ import annotations
from typing import Any
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, MANUFACTURER
from .coordinator import InterstellarCoordinator

def machine_id(data: dict[str, Any]) -> str:
    host=data.get("host",{})
    return host.get("machine_id") or data.get("machine_id") or host.get("hostname") or "unknown"

def hostname(data: dict[str, Any]) -> str:
    return data.get("host",{}).get("hostname") or data.get("hostname") or "Interstellar Network node"

class InterstellarEntity(CoordinatorEntity[InterstellarCoordinator]):
    _attr_has_entity_name=True
    interstellar_key="unknown"

    @property
    def device_info(self) -> DeviceInfo:
        data=self.coordinator.data; host=data.get("host",{})
        roles=host.get("roles") or ["general"]
        return DeviceInfo(identifiers={(DOMAIN,machine_id(data))}, name=hostname(data), manufacturer=MANUFACTURER,
            model=f"{', '.join(roles)} · {host.get('virtualization','Linux')}", sw_version=host.get("os"), hw_version=host.get("architecture"), configuration_url=self.coordinator.client.base_url)

    def interstellar_attributes(self) -> dict[str, Any]:
        data=self.coordinator.data
        return {"interstellar_network_id":machine_id(data), "interstellar_hostname":hostname(data),
                "interstellar_roles":data.get("host",{}).get("roles",[]),
                "interstellar_expected_services":data.get("service_policy",{}).get("expected_services",[]),
                "interstellar_key":self.interstellar_key}

    @property
    def extra_state_attributes(self):
        return self.interstellar_attributes()
