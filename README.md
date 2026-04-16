# GitHub Release Watch

Focused GitHub release monitoring and digest generation for OpenClaw.

## What it does

- tracks selected GitHub repositories
- checks latest published releases
- stores release state locally
- generates digest JSON
- renders HTML email digests
- sends email through IMM-Romania

## Current positioning

GitHub Release Watch is the extracted product core from the GitHub release-monitoring component previously living inside `openclaw-msp`.

## Naming convention

- **GitHub repo:** `asistent-alex/openclaw-github-release-watch`
- **Public name:** `GitHub Release Watch`
- **Skill slug / local skill folder:** `github-release-watch`

## Quick start

```bash
python3 scripts/release-watch.py --help
python3 scripts/release-watch.py repos --config data/github-release-watch-repos.example.json
python3 scripts/release-watch.py check --config data/github-release-watch-repos.example.json
python3 scripts/release-watch.py digest --check --config data/github-release-watch-repos.example.json
```
