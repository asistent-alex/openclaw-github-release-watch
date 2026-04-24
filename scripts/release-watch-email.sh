#!/bin/bash

# GitHub Release Watch Email Wrapper
# Uses GitHub Release Watch for release-check logic and IMM-Romania for mail delivery.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WATCH_CLI="$PROJECT_DIR/scripts/release-watch.py"
IMM_ROMANIA_PATH="${IMM_ROMANIA_PATH:-$HOME/.openclaw/skills/nexlink}"
IMM_CLI="$IMM_ROMANIA_PATH/scripts/nexlink.py"
CONFIG_PATH="${GITHUB_RELEASE_WATCH_CONFIG_PATH:-$PROJECT_DIR/data/github-release-watch-repos.json}"
STATE_PATH="${GITHUB_RELEASE_WATCH_STATE_PATH:-$PROJECT_DIR/data/github-release-watch-state.json}"

if [[ ! -f "$IMM_CLI" ]]; then
  echo "IMM-Romania CLI not found at $IMM_CLI"
  exit 1
fi

CONFIG_ARGS=(--state "$STATE_PATH")

if [[ -f "$CONFIG_PATH" ]]; then
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

DIGEST_JSON=$(python3 "$WATCH_CLI" digest --check --dry-run "${CONFIG_ARGS[@]}")
SUBJECT=$(printf '%s' "$DIGEST_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["subject"])')
BODY=$(printf '%s' "$DIGEST_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["body"])')
HTML=$(printf '%s' "$DIGEST_JSON" | python3 "$PROJECT_DIR/modules/release_watch/render_digest.py")
ENABLED=$(printf '%s' "$DIGEST_JSON" | python3 -c 'import json,sys; data=json.load(sys.stdin); print("yes" if data.get("results") or data.get("has_updates") or "No GitHub repositories are configured" not in data.get("body", "") else "no")')
SUMMARY=$(printf '%s' "$DIGEST_JSON" | python3 -c 'import json,sys; data=json.load(sys.stdin); updates=int(data.get("updates") or 0); failures=int(data.get("failures") or 0); interesting=len(data.get("interesting_repos") or []); print((f"GitHub release digest email sent successfully with {updates} update" + ("s" if updates != 1 else "") + (f" and {interesting} ecosystem repo" + ("s" if interesting != 1 else "") if interesting else "") + (f"; {failures} repo checks need review." if failures else ".")) if data.get("results") or data.get("interesting_repos") else "GitHub Release Watch not enabled; exiting cleanly.")')

if [[ "$ENABLED" != "yes" ]]; then
  echo "$SUMMARY"
  exit 0
fi

if [[ -n "$HTML" && "$HTML" != "<p>Invalid digest</p>" ]]; then
  python3 "$IMM_CLI" mail send --to "$RECIPIENT" --subject "$SUBJECT" --body "$HTML" --html >/dev/null
else
  python3 "$IMM_CLI" mail send --to "$RECIPIENT" --subject "$SUBJECT" --body "$BODY" >/dev/null
fi

echo "$SUMMARY"
