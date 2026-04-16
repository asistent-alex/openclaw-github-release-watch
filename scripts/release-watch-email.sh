#!/bin/bash

# GitHub Release Watch Email Wrapper
# Uses GitHub Release Watch for release-check logic and IMM-Romania for mail delivery.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WATCH_CLI="$PROJECT_DIR/scripts/release-watch.py"
IMM_ROMANIA_PATH="${IMM_ROMANIA_PATH:-$HOME/.openclaw/skills/imm-romania}"
IMM_CLI="$IMM_ROMANIA_PATH/scripts/imm-romania.py"
CONFIG_PATH="${GITHUB_RELEASE_WATCH_CONFIG_PATH:-$PROJECT_DIR/data/github-release-watch-repos.json}"
STATE_PATH="${GITHUB_RELEASE_WATCH_STATE_PATH:-$PROJECT_DIR/data/github-release-watch-state.json}"

if [[ ! -f "$IMM_CLI" ]]; then
  echo "IMM-Romania CLI not found at $IMM_CLI"
  exit 1
fi

REPO_ARGS=()
CONFIG_ARGS=(--state "$STATE_PATH")

if [[ -n "${GITHUB_RELEASE_WATCH_REPOS:-}" ]]; then
  IFS=',' read -r -a REPOS <<< "$GITHUB_RELEASE_WATCH_REPOS"
  for repo in "${REPOS[@]}"; do
    repo="$(printf '%s' "$repo" | xargs)"
    [[ -n "$repo" ]] && REPO_ARGS+=(--repo "$repo")
  done
elif [[ -f "$CONFIG_PATH" ]]; then
  CONFIG_ARGS+=(--config "$CONFIG_PATH")
else
  echo "No GitHub Release Watch config found; exiting cleanly."
  exit 0
fi

RECIPIENT="${GITHUB_RELEASE_WATCH_RECIPIENT:-}"
if [[ -z "$RECIPIENT" && -f "$CONFIG_PATH" ]]; then
  RECIPIENT=$(python3 - <<'PY' "$CONFIG_PATH"
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
try:
    raw = json.loads(path.read_text(encoding='utf-8'))
    print(raw.get('recipient', ''))
except Exception:
    print('')
PY
)
fi

if [[ -z "$RECIPIENT" ]]; then
  echo "No GitHub Release Watch recipient configured; exiting cleanly."
  exit 0
fi

DIGEST_JSON=$(python3 "$WATCH_CLI" digest --check "${CONFIG_ARGS[@]}" "${REPO_ARGS[@]}")
SUBJECT=$(printf '%s' "$DIGEST_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["subject"])')
BODY=$(printf '%s' "$DIGEST_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["body"])')
HTML=$(printf '%s' "$DIGEST_JSON" | python3 "$PROJECT_DIR/modules/release_watch/render_digest.py")
ENABLED=$(printf '%s' "$DIGEST_JSON" | python3 -c 'import json,sys; data=json.load(sys.stdin); print("yes" if data.get("results") or data.get("has_updates") or "No GitHub repositories are configured" not in data.get("body", "") else "no")')

if [[ "$ENABLED" != "yes" ]]; then
  echo "GitHub Release Watch not enabled; exiting cleanly."
  exit 0
fi

if [[ -n "$HTML" && "$HTML" != "<p>Invalid digest</p>" ]]; then
  python3 "$IMM_CLI" mail send --to "$RECIPIENT" --subject "$SUBJECT" --body "$HTML" --html
else
  python3 "$IMM_CLI" mail send --to "$RECIPIENT" --subject "$SUBJECT" --body "$BODY"
fi
