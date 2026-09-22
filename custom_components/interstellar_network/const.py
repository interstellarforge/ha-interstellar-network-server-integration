"""Constants for Interstellar Network."""
from datetime import timedelta

DOMAIN = "interstellar_network"
PLATFORMS = ["sensor", "binary_sensor"]
CONF_URL = "url"
CONF_CONTROL_URL = "control_url"
CONF_VERIFY_SSL = "verify_ssl"
CONF_WOL_ENABLED = "wake_on_lan_enabled"
CONF_WOL_MAC = "wake_on_lan_mac"
CONF_WOL_BROADCAST = "wake_on_lan_broadcast"
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)
REQUEST_TIMEOUT_SECONDS = 10
MANUFACTURER = "Interstellar Network"
ZEROCONF_TYPE = "_interstellar._tcp.local."
DISK_WARNING_PERCENT = 90.0
INODE_WARNING_PERCENT = 90.0
CARD_PATH = "/interstellar_network/interstellar-network-card.js"
CARD_VERSION = "0.4.1"
CARD_URL = f"{CARD_PATH}?v={CARD_VERSION}"
