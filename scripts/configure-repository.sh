#!/usr/bin/env bash
set -Eeuo pipefail

OWNER="${1:-}"
REPO="${2:-ha-interstellar-network-server-integration}"

if [[ -z "$OWNER" ]]; then
  echo "Usage: $0 <github-user-or-org> [repository-name]"
  exit 1
fi

python3 - "$OWNER" "$REPO" <<'PY'
import json
from pathlib import Path
import sys

owner, repo = sys.argv[1], sys.argv[2]
manifest_path = Path("custom_components/interstellar_network/manifest.json")
data = json.loads(manifest_path.read_text())
data["codeowners"] = [f"@{owner}"]
data["documentation"] = f"https://github.com/{owner}/{repo}#readme"
data["issue_tracker"] = f"https://github.com/{owner}/{repo}/issues"
manifest_path.write_text(json.dumps(data, indent=2) + "\n")

readme = Path("README.md")
txt = readme.read_text()
txt = txt.replace(
    "add this GitHub repository URL",
    f"add `https://github.com/{owner}/{repo}`"
)
readme.write_text(txt)

print(f"Configured repository metadata for https://github.com/{owner}/{repo}")
PY
