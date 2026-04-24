---
name: github-release-watch
description: Monitor selected GitHub repositories and produce structured release digests with HTML/email delivery. Use when tracking releases, building GitHub update digests, checking release status, or sending release-watch briefings by email. Depends on imm-romania for Exchange-backed mail delivery.
---

# GitHub Release Watch

Use this skill for GitHub release monitoring and digest workflows:
- track configured repositories
- check latest published releases
- generate digest JSON
- render Outlook-friendly HTML digests
- send release digest emails via IMM-Romania

## Dependency

This skill depends on **`imm-romania`** for Exchange-backed email delivery.

## Main entrypoints

- `python3 scripts/release-watch.py repos ...`
- `python3 scripts/release-watch.py check [--dry-run] ...`
- `python3 scripts/release-watch.py status ...`
- `python3 scripts/release-watch.py digest [--check] [--dry-run] ...`
- `bash scripts/release-watch-email.sh` (*always runs `--dry-run` — state is never written by email previews*)

## Dry-run mode

`--dry-run` runs a full release check or digest generation but **never saves state**.
Use it for previews, testing, or email scripts. The output JSON includes `"dry_run": true`.
Normal mode (no flag) still writes state as expected.

## References

- Setup and dependency notes: `references/setup.md`
- Workflow overview: `references/workflows.md`
