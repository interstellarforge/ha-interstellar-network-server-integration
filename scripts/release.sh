#!/usr/bin/env bash
set -Eeuo pipefail

# Interstellar Network - one-command Home Assistant / HACS release helper
#
# Usage:
#   ./scripts/release.sh 0.3.1
#
# Or simply:
#   ./scripts/release.sh
# and enter the version when prompted.
#
# What it does:
#   1. Checks Git/GitHub CLI and repository state
#   2. Updates manifest.json version
#   3. Commits ALL pending release changes (after confirmation)
#   4. Pushes the current branch
#   5. Creates and pushes tag vX.Y.Z
#   6. Creates the GitHub Release
#   7. Can cleanly recreate an accidentally-created release/tag

REMOTE="${REMOTE:-origin}"
MANIFEST="custom_components/interstellar_network/manifest.json"

die() {
  printf '\nERROR: %s\n' "$*" >&2
  exit 1
}

info() {
  printf '\n==> %s\n' "$*"
}

yes_no() {
  local prompt="$1"
  local default="${2:-y}"
  local answer

  if [[ "$default" == "y" ]]; then
    read -r -p "$prompt [Y/n] " answer
    answer="${answer:-y}"
  else
    read -r -p "$prompt [y/N] " answer
    answer="${answer:-n}"
  fi

  [[ "$answer" =~ ^[Yy]$ ]]
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command '$1' was not found."
}

need_cmd git
need_cmd gh
need_cmd python3

# Always operate from the repository root, regardless of where the script is called from.
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" \
  || die "This does not appear to be a Git repository."
cd "$REPO_ROOT"

[[ -f "$MANIFEST" ]] \
  || die "Cannot find $MANIFEST. Are you in the Interstellar Network repository?"

# Version can be passed as 0.3.1 or v0.3.1.
VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  read -r -p "Version to release (example: 0.3.1): " VERSION
fi
VERSION="${VERSION#v}"

[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]] \
  || die "Invalid version '$VERSION'. Use semantic versioning, for example 0.3.1."

TAG="v${VERSION}"
BRANCH="$(git branch --show-current)"
[[ -n "$BRANCH" ]] || die "Detached HEAD is not supported."

REMOTE_URL="$(git remote get-url "$REMOTE" 2>/dev/null)" \
  || die "Git remote '$REMOTE' does not exist."

info "Interstellar Network release ${TAG}"
echo "Repository: $REPO_ROOT"
echo "Branch:     $BRANCH"
echo "Remote:     $REMOTE_URL"

# Make sure gh is usable before changing anything.
gh auth status >/dev/null 2>&1 \
  || die "GitHub CLI is not authenticated. Run: gh auth login"

info "Fetching latest remote state and tags"
git fetch "$REMOTE" --tags --prune

# Warn if the local branch is behind the remote branch.
if git show-ref --verify --quiet "refs/remotes/${REMOTE}/${BRANCH}"; then
  LOCAL_HEAD="$(git rev-parse HEAD)"
  REMOTE_HEAD="$(git rev-parse "${REMOTE}/${BRANCH}")"

  if [[ "$LOCAL_HEAD" != "$REMOTE_HEAD" ]]; then
    if git merge-base --is-ancestor "$LOCAL_HEAD" "$REMOTE_HEAD"; then
      die "Your local '$BRANCH' is behind '$REMOTE/$BRANCH'. Pull/rebase first, then rerun."
    fi
  fi
fi

# Detect an existing release/tag. This fixes the exact situation where
# `gh release create` was run before the local tag existed.
RELEASE_EXISTS=0
LOCAL_TAG_EXISTS=0
REMOTE_TAG_EXISTS=0

gh release view "$TAG" >/dev/null 2>&1 && RELEASE_EXISTS=1
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null 2>&1 && LOCAL_TAG_EXISTS=1
git ls-remote --exit-code --tags "$REMOTE" "refs/tags/$TAG" >/dev/null 2>&1 \
  && REMOTE_TAG_EXISTS=1 || true

if (( RELEASE_EXISTS || LOCAL_TAG_EXISTS || REMOTE_TAG_EXISTS )); then
  echo
  echo "A release/tag named '$TAG' already exists:"
  (( RELEASE_EXISTS ))    && echo "  - GitHub Release exists"
  (( LOCAL_TAG_EXISTS ))  && echo "  - Local Git tag exists"
  (( REMOTE_TAG_EXISTS )) && echo "  - Remote Git tag exists"

  if ! yes_no "Delete/recreate $TAG so it points at the release commit?" "n"; then
    die "Release cancelled. Nothing was changed."
  fi

  info "Removing existing ${TAG}"

  if (( RELEASE_EXISTS )); then
    # --cleanup-tag also removes the GitHub-side tag when possible.
    gh release delete "$TAG" --cleanup-tag --yes || true
  fi

  # Make absolutely sure the remote tag is gone.
  if git ls-remote --exit-code --tags "$REMOTE" "refs/tags/$TAG" >/dev/null 2>&1; then
    git push "$REMOTE" ":refs/tags/$TAG"
  fi

  # And remove any local copy.
  if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null 2>&1; then
    git tag -d "$TAG"
  fi
fi

info "Setting manifest version to ${VERSION}"
python3 - "$MANIFEST" "$VERSION" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
version = sys.argv[2]

data = json.loads(path.read_text())
old = data.get("version")
data["version"] = version
path.write_text(json.dumps(data, indent=2) + "\n")

print(f"manifest.json: {old!s} -> {version}")
PY

# Lightweight local checks before we create a release.
info "Running release preflight checks"

python3 -m json.tool "$MANIFEST" >/dev/null

if [[ -d custom_components/interstellar_network ]]; then
  python3 -m compileall -q custom_components/interstellar_network
fi

git diff --check

# The script deliberately supports both situations:
# - you have pending source changes
# - all changes were already committed and only a release/tag is needed
if [[ -n "$(git status --porcelain)" ]]; then
  echo
  echo "Changes that will be included in ${TAG}:"
  git status --short
  echo

  if ! yes_no "Commit ALL changes above as '${TAG}'?" "y"; then
    die "Release cancelled. Your files were left unchanged."
  fi

  git add -A
  git commit -m "Release ${TAG}"
else
  info "Working tree is already clean"
  echo "No release commit is necessary; ${TAG} will point at the current HEAD."
fi

# Double-check the committed manifest contains the requested version.
COMMITTED_VERSION="$(
  git show "HEAD:${MANIFEST}" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])'
)"

[[ "$COMMITTED_VERSION" == "$VERSION" ]] \
  || die "Committed manifest version is '$COMMITTED_VERSION', expected '$VERSION'."

info "Pushing branch ${BRANCH}"
git push "$REMOTE" "$BRANCH"

# Fetch again so the local remote-tracking ref reflects what we just pushed.
git fetch "$REMOTE" "$BRANCH" --quiet

[[ "$(git rev-parse HEAD)" == "$(git rev-parse "${REMOTE}/${BRANCH}")" ]] \
  || die "Remote branch did not end up on the same commit as local HEAD."

info "Creating tag ${TAG}"
git tag -a "$TAG" -m "Interstellar Network ${TAG}"

info "Pushing tag ${TAG}"
git push "$REMOTE" "$TAG"

info "Creating GitHub Release ${TAG}"
gh release create "$TAG" \
  --verify-tag \
  --title "Interstellar Network ${TAG}" \
  --generate-notes

RELEASE_URL="$(
  gh release view "$TAG" --json url --jq '.url' 2>/dev/null || true
)"

echo
echo "============================================================"
echo " Interstellar Network ${TAG} released successfully"
echo "============================================================"
echo "Commit:  $(git rev-parse --short HEAD)"
echo "Branch:  ${BRANCH}"
echo "Tag:     ${TAG}"
[[ -n "$RELEASE_URL" ]] && echo "Release: ${RELEASE_URL}"
echo
echo "HACS can now discover ${VERSION} from the GitHub release."
