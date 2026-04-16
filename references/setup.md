# GitHub Release Watch Setup

## Required dependency

Install and keep `imm-romania` available at:

- default path: `~/.openclaw/skills/imm-romania`
- override path: set `IMM_ROMANIA_PATH`

This skill uses IMM-Romania for Exchange-backed email delivery.

## Typical local paths

- Release Watch skill: `~/.openclaw/skills/github-release-watch`
- IMM-Romania skill: `~/.openclaw/skills/imm-romania`

## Entry point

```bash
python3 scripts/release-watch.py --help
```

## Config

Use either:
- `data/github-release-watch-repos.example.json` as a starting point
- `GITHUB_RELEASE_WATCH_REPOS` env override
- `GITHUB_RELEASE_WATCH_RECIPIENT` env var for digest recipient

The config may also define `categories` to group repositories inside the rendered digest.

Tracked state stores release metadata plus derived context such as:
- semantic version change type
- release-notes excerpt
- stars / forks counts and deltas
- security advisory presence signal

## Notes

Do not commit live state or private local config.
