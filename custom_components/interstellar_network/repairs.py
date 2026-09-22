"""Home Assistant Repairs issues for Interstellar Network."""
from __future__ import annotations
from homeassistant.helpers import issue_registry as ir
from .const import DOMAIN, DISK_WARNING_PERCENT, INODE_WARNING_PERCENT


def _id(entry, suffix: str) -> str:
    return f"{entry.entry_id}_{suffix}"


def _set_issue(hass, entry, suffix: str, active: bool, *, severity, translation_key: str, placeholders: dict[str, str]) -> None:
    issue_id = _id(entry, suffix)
    if active:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            is_persistent=False,
            severity=severity,
            translation_key=translation_key,
            translation_placeholders=placeholders,
        )
        entry.runtime_data.repair_issue_ids.add(issue_id)
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        entry.runtime_data.repair_issue_ids.discard(issue_id)


def async_update_repairs(hass, entry) -> None:
    """Create/delete actionable issues from the latest stats."""
    if not entry.runtime_data.coordinator.last_update_success:
        return
    data = entry.runtime_data.coordinator.data
    hostname = data.get("host", {}).get("hostname", entry.title)
    disk = data.get("disk_root", {})
    system = data.get("system", {})
    updates = data.get("updates", {})
    time_data = data.get("time", {})
    policy = data.get("service_policy", {})

    disk_pct = disk.get("used_percent")
    _set_issue(hass, entry, "disk_full", disk_pct is not None and disk_pct >= DISK_WARNING_PERCENT,
               severity=ir.IssueSeverity.WARNING, translation_key="disk_full",
               placeholders={"server": hostname, "percent": str(disk_pct), "threshold": str(DISK_WARNING_PERCENT)})

    inode_pct = disk.get("inode_used_percent")
    _set_issue(hass, entry, "inodes_full", inode_pct is not None and inode_pct >= INODE_WARNING_PERCENT,
               severity=ir.IssueSeverity.WARNING, translation_key="inodes_full",
               placeholders={"server": hostname, "percent": str(inode_pct), "threshold": str(INODE_WARNING_PERCENT)})

    failed = int(system.get("failed_systemd_units") or 0)
    _set_issue(hass, entry, "failed_units", failed > 0,
               severity=ir.IssueSeverity.ERROR, translation_key="failed_units",
               placeholders={"server": hostname, "count": str(failed)})

    _set_issue(hass, entry, "ntp", time_data.get("synchronized") is False,
               severity=ir.IssueSeverity.WARNING, translation_key="ntp_unsynchronized",
               placeholders={"server": hostname})

    _set_issue(hass, entry, "reboot", bool(system.get("reboot_required")),
               severity=ir.IssueSeverity.WARNING, translation_key="reboot_required",
               placeholders={"server": hostname})

    security = int(updates.get("pending_security") or 0)
    _set_issue(hass, entry, "security_updates", security > 0,
               severity=ir.IssueSeverity.WARNING, translation_key="security_updates",
               placeholders={"server": hostname, "count": str(security)})

    oom = int(system.get("oom_kills_since_boot") or 0)
    _set_issue(hass, entry, "oom", oom > 0,
               severity=ir.IssueSeverity.WARNING, translation_key="oom_kills",
               placeholders={"server": hostname, "count": str(oom)})

    expected_now: set[str] = set()
    for problem in policy.get("problems", []):
        service = problem.get("service")
        if not service:
            continue
        suffix = f"expected_{service.replace('.', '_').replace('@', '_')}"
        expected_now.add(_id(entry, suffix))
        _set_issue(hass, entry, suffix, True,
                   severity=ir.IssueSeverity.ERROR, translation_key="expected_service_down",
                   placeholders={"server": hostname, "service": service, "state": str(problem.get("state", "unknown"))})

    control = data.get("_control", {})
    control_policy = control.get("policy", {})
    docker = control.get("docker", {})
    docker_expected = "docker" in policy.get("expected_services", [])
    _set_issue(hass, entry, "docker_down", docker_expected and docker.get("installed") is True and
               docker.get("daemon_running") is False,
               severity=ir.IssueSeverity.ERROR, translation_key="docker_down",
               placeholders={"server": hostname})
    expected_containers = set(control_policy.get("expected_containers", []))
    current_containers = {item.get("name"): item for item in docker.get("containers", [])}
    dynamic_now = set()
    for name in expected_containers:
        item = current_containers.get(name)
        if not item or item.get("state") != "running":
            suffix = f"container_stopped_{name}"
            dynamic_now.add(_id(entry, suffix))
            _set_issue(hass, entry, suffix, docker.get("daemon_running") is True,
                       severity=ir.IssueSeverity.ERROR, translation_key="expected_container_stopped",
                       placeholders={"server": hostname, "container": name})
    for name, item in current_containers.items():
        if item.get("health") == "unhealthy":
            suffix = f"container_unhealthy_{name}"
            dynamic_now.add(_id(entry, suffix))
            _set_issue(hass, entry, suffix, True,
                       severity=ir.IssueSeverity.WARNING, translation_key="container_unhealthy",
                       placeholders={"server": hostname, "container": name})

    for issue_id in set(entry.runtime_data.repair_issue_ids):
        if ((issue_id.startswith(f"{entry.entry_id}_expected_") and issue_id not in expected_now) or
            (issue_id.startswith(f"{entry.entry_id}_container_") and issue_id not in dynamic_now)):
            ir.async_delete_issue(hass, DOMAIN, issue_id)
            entry.runtime_data.repair_issue_ids.discard(issue_id)


def async_delete_repairs(hass, entry) -> None:
    for issue_id in set(entry.runtime_data.repair_issue_ids):
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    entry.runtime_data.repair_issue_ids.clear()
