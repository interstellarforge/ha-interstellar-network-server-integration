"""Constants for Interstellar Network."""
from datetime import timedelta

DOMAIN = "interstellar_network"
PLATFORMS = ["sensor", "binary_sensor"]
CONF_URL = "url"
CONF_VERIFY_SSL = "verify_ssl"
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)
REQUEST_TIMEOUT_SECONDS = 10
MANUFACTURER = "Interstellar Network"
ZEROCONF_TYPE = "_interstellar._tcp.local."
DISK_WARNING_PERCENT = 90.0
INODE_WARNING_PERCENT = 90.0
CARD_URL = "/interstellar_network/interstellar-network-card.js"
