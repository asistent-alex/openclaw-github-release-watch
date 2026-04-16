# GitHub Release Watch

Focused GitHub release monitoring and digest generation for OpenClaw.

## What it does

- tracks selected GitHub repositories
- checks stable published releases
- stores release state locally for delta-aware monitoring
- classifies semantic version changes
- extracts cleaned release-notes excerpts
- tracks stars/forks momentum and security advisory signals
- generates digest JSON
- renders HTML email digests
- sends email through IMM-Romania

## Current positioning

GitHub Release Watch is a focused product for high-signal GitHub release monitoring, digest generation, and upgrade awareness.

## Naming convention

- **GitHub repo:** `asistent-alex/openclaw-github-release-watch`
- **Public name:** `GitHub Release Watch`
- **Skill slug / local skill folder:** `github-release-watch`

## Current feature set

- stable-only release monitoring (`draft=false`, `prerelease=false`)
- semantic change classification (`major`, `minor`, `patch`, `non-semver`)
- release-notes excerpts for digest highlights
- stars / forks context with deltas from previous state
- security advisory presence signal
- categorized HTML digest rendering

## Dependencies

### Required

- **Python 3** — used by the CLI and renderer
- **GitHub access** — public repos work anonymously, but authenticated use is strongly recommended for better rate limits
- **`GITHUB_TOKEN`** or `~/.openclaw/openclaw.json` with `env.GITHUB_TOKEN` — recommended for reliable GitHub API access

### Required for email delivery

- **IMM-Romania skill** installed locally
- default expected path: `~/.openclaw/skills/imm-romania`
- override path: `IMM_ROMANIA_PATH`
- required entrypoint: `scripts/imm-romania.py`

Without IMM-Romania, the checker and digest renderer still work, but the email wrapper will not send mail.

### Config / runtime files

- config default: `data/github-release-watch-repos.json`
- example config: `data/github-release-watch-repos.example.json`
- state default: `data/github-release-watch-state.json`

## Quick start

```bash
python3 scripts/release-watch.py --help
python3 scripts/release-watch.py repos --config data/github-release-watch-repos.example.json
python3 scripts/release-watch.py check --config data/github-release-watch-repos.example.json
python3 scripts/release-watch.py digest --check --config data/github-release-watch-repos.example.json
```
