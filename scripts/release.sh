#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="${1:-}"
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]]; then
  echo "Usage: $0 <semver>, e.g. 0.3.0"
  exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Working tree is not clean."
  exit 1
fi

python3 - "$VERSION" <<'PY'
import json, sys
from pathlib import Path

version = sys.argv[1]
path = Path("custom_components/interstellar_network/manifest.json")
data = json.loads(path.read_text())
data["version"] = version
path.write_text(json.dumps(data, indent=2) + "\n")
print(f"manifest.json -> {version}")
PY

git add custom_components/interstellar_network/manifest.json
git commit -m "Release v${VERSION}"
git tag -a "v${VERSION}" -m "Interstellar Network v${VERSION}"

echo
echo "Prepared v${VERSION}."
echo "Push with:"
echo "  git push origin main"
echo "  git push origin v${VERSION}"
echo
echo "Then create a GitHub Release from tag v${VERSION}."
