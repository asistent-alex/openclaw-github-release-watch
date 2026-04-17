# GitHub Release Watch

Focused GitHub release monitoring and digest generation for OpenClaw.

GitHub Release Watch is a small Python-first skill for tracking stable GitHub releases, storing state locally, generating structured digests, rendering Outlook-friendly HTML, and optionally sending the digest by email through IMM-Romania.

## What it does

- tracks selected GitHub repositories
- checks stable published releases only (`draft=false`, `prerelease=false`)
- stores release state locally for delta-aware monitoring
- classifies semantic version changes (`major`, `minor`, `patch`, `non-semver`)
- extracts cleaned release-notes excerpts and short AI-style summaries
- tracks stars/forks momentum and security advisory signals
- generates digest JSON
- renders HTML email digests
- sends email through IMM-Romania

## Naming convention

- **GitHub repo:** `asistent-alex/openclaw-github-release-watch`
- **Public name:** `GitHub Release Watch`
- **Skill slug / local skill folder:** `github-release-watch`

## Repository layout

```text
modules/release_watch/        Core checker, config, and digest renderer
scripts/release-watch.py      Main CLI entrypoint
scripts/release-watch-email.sh Email wrapper via IMM-Romania
data/                         Example config + local state files
tests/                        Checker and HTML renderer tests
references/                   Setup and workflow notes
```

## Real setup

### Prerequisites

Required to use the checker and digest renderer:

- **Python 3**
- GitHub API access to the repositories you want to monitor
- recommended: **`GITHUB_TOKEN`** for reliable rate limits

Required only for email delivery:

- local **IMM-Romania** skill install
- default expected path: `~/.openclaw/skills/imm-romania`
- required entrypoint inside that skill: `scripts/imm-romania.py`

Important:
- the main checker and digest renderer work **without** IMM-Romania
- the email wrapper does **not** send mail without IMM-Romania
- this repo does **not** currently expose formal packaging via `pyproject.toml` or `requirements.txt`; run it directly from the repo root with `python3`

### GitHub token

Public repositories can be checked anonymously, but authenticated access is strongly recommended.

Supported token sources:

1. `GITHUB_TOKEN` environment variable
2. `~/.openclaw/openclaw.json` with `env.GITHUB_TOKEN`

Example:

```bash
export GITHUB_TOKEN=ghp_your_token_here
```

### Config and state files

Default paths used by the code:

- config: `data/github-release-watch-repos.json`
- example config: `data/github-release-watch-repos.example.json`
- state: `data/github-release-watch-state.json`

A practical local bootstrap is:

```bash
cp data/github-release-watch-repos.example.json data/github-release-watch-repos.json
```

Then edit the live config and set at minimum:

- `recipient` — email recipient for the digest wrapper
- `repos` — flat list of `owner/repo` values
- optional `categories` — grouped sections for the rendered HTML digest

Example config shape:

```json
{
  "enabled": true,
  "recipient": "ops@example.com",
  "categories": [
    {
      "name": "AI Agents",
      "emoji": "🤖",
      "description": "Agent runtimes and orchestration tools",
      "repos": [
        "openclaw/openclaw",
        "Martian-Engineering/lossless-claw"
      ]
    }
  ],
  "repos": [
    "openclaw/openclaw",
    "Martian-Engineering/lossless-claw"
  ]
}
```

The state file is created and updated automatically by the checker.
Do not commit live state or private local config.

## Environment variables actually used

### Core GitHub Release Watch variables

- `GITHUB_TOKEN` — GitHub API token
- `GITHUB_RELEASE_WATCH_REPOS` — comma-separated repo override
- `GITHUB_RELEASE_WATCH_RECIPIENT` — digest recipient override
- `GITHUB_RELEASE_WATCH_CONFIG_PATH` — override config path for the email wrapper
- `GITHUB_RELEASE_WATCH_STATE_PATH` — override saved state path for the email wrapper

### IMM-Romania integration variable

- `IMM_ROMANIA_PATH` — override local path to the IMM-Romania skill

Notes:
- repo overrides force the checker enabled even without a config file
- if no repos are configured, the checker exits cleanly in disabled/no-op mode
- the email wrapper also exits cleanly when there is no config or no recipient

## Quick start

### 1. Inspect the CLI

```bash
python3 scripts/release-watch.py --help
```

### 2. List configured repositories

```bash
python3 scripts/release-watch.py repos \
  --config data/github-release-watch-repos.example.json
```

### 3. Run a release check

```bash
python3 scripts/release-watch.py check \
  --config data/github-release-watch-repos.example.json
```

### 4. Generate a digest from a fresh check

```bash
python3 scripts/release-watch.py digest \
  --check \
  --config data/github-release-watch-repos.example.json
```

### 5. Review saved status

```bash
python3 scripts/release-watch.py status \
  --config data/github-release-watch-repos.example.json
```

## Email delivery workflow

Use the wrapper when you want the digest rendered and mailed through IMM-Romania:

```bash
bash scripts/release-watch-email.sh
```

The wrapper behavior is:

1. resolve config/state paths
2. resolve recipient from `GITHUB_RELEASE_WATCH_RECIPIENT` or config JSON
3. run `release-watch.py digest --check`
4. render HTML via `modules/release_watch/render_digest.py`
5. send HTML mail through IMM-Romania when HTML is valid
6. fall back to plain-text body if HTML rendering is invalid

If `IMM_ROMANIA_PATH` is wrong or IMM-Romania is missing, the wrapper fails loudly.
If no config or recipient exists, it exits cleanly without sending.

## Testing

Verified commands currently used in this repo:

```bash
python3 -m unittest tests/test_github_checker.py
python3 tests/test_github_template.py
```

What these cover:

- checker state transitions
- update detection and repo overrides
- digest generation from saved state
- categorized digest rendering
- HTML template stability for update and empty-digest cases

## Operational notes

- This project is stdlib-first and intentionally lightweight.
- The checker stores local state so repeated runs can detect changes and deltas.
- GitHub rate limits are much better with `GITHUB_TOKEN` than with anonymous requests.
- Email delivery is a wrapper concern, not a requirement for local checking or digest generation.
- The daily/cron use case is best served by the shell wrapper once config and recipient are in place.

## Current feature set

- stable-only release monitoring
- semantic change classification
- release-notes cleanup and short update summaries
- stars / forks context with saved-state deltas
- security advisory presence signal
- categorized HTML digest rendering

## References

- setup notes: `references/setup.md`
- workflow notes: `references/workflows.md`
- skill entrypoint metadata: `SKILL.md`
