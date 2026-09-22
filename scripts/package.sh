#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="$(python3 - <<'PY'
import json
print(json.load(open("custom_components/interstellar_network/manifest.json"))["version"])
PY
)"

mkdir -p dist
rm -f "dist/interstellar-network-v${VERSION}.zip"

zip -qr "dist/interstellar-network-v${VERSION}.zip" \
  custom_components/interstellar_network \
  server_helper \
  README.md \
  CHANGELOG.md \
  LICENSE \
  -x '*/__pycache__/*' '*.pyc'

echo "Created dist/interstellar-network-v${VERSION}.zip"
