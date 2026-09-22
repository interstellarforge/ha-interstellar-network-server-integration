#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$EUID" -ne 0 ]]; then
  echo "Run with sudo/root."
  exit 1
fi

if ! command -v tailscale >/dev/null 2>&1; then
  echo "Tailscale must be installed and connected first."
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-zeroconf

HOSTNAME_SHORT="$(hostname -s)"
MACHINE_ID="$(cat /etc/machine-id)"
LAN_IP="$(ip -4 route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
TS_DNS="$(
  tailscale status --json |
    python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["Self"]["DNSName"].rstrip("."))'
)"
URL="https://${TS_DNS}"

if [[ -z "$LAN_IP" || -z "$TS_DNS" ]]; then
  echo "Could not determine LAN IP or Tailscale DNS name."
  exit 1
fi

install -o root -g root -m 0755 interstellar-mdns.py /usr/local/lib/interstellar-mdns.py

cat >/etc/default/interstellar-mdns <<EOF
INTERSTELLAR_HOSTNAME=${HOSTNAME_SHORT}
INTERSTELLAR_MACHINE_ID=${MACHINE_ID}
INTERSTELLAR_URL=${URL}
INTERSTELLAR_LAN_IP=${LAN_IP}
INTERSTELLAR_AGENT_VERSION=3.0.0
EOF
chmod 0644 /etc/default/interstellar-mdns

cat >/etc/systemd/system/interstellar-mdns.service <<'EOF'
[Unit]
Description=Interstellar Network mDNS discovery announcer
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=simple
DynamicUser=yes
EnvironmentFile=/etc/default/interstellar-mdns
ExecStart=/usr/bin/python3 /usr/local/lib/interstellar-mdns.py
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
UMask=0077

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now interstellar-mdns

echo
echo "mDNS discovery enabled:"
echo "  Service: _interstellar._tcp.local."
echo "  Host:    ${HOSTNAME_SHORT}"
echo "  LAN IP:  ${LAN_IP}"
echo "  URL:     ${URL}"
echo
echo "Check with:"
echo "  systemctl status interstellar-mdns"
