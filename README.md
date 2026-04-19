# GitHub Release Watch

GitHub Release Watch monitors selected GitHub repositories, detects stable releases, and turns them into a clean digest you can review in JSON, render as HTML, or send by email through IMM-Romania.

If you want a daily release briefing without drowning in raw changelogs, this repo is the thing.

## Why it exists

Most release feeds are noisy:
- raw release notes are messy
- important changes are buried
- repo context is missing
- non-release ecosystem projects get mixed with actual shipped versions

GitHub Release Watch fixes that by producing a digest that is:
- **release-focused** — tracks stable published releases only
- **digest-friendly** — clean summaries, better grouping, less repetition
- **email-safe** — Outlook-friendly HTML cards
- **practical** — includes semver, stars/forks, advisories, cadence, and ecosystem watch

## What you get

- stable-only GitHub release monitoring (`draft=false`, `prerelease=false`)
- local state for delta-aware checks
- semantic version classification (`major`, `minor`, `patch`, `non-semver`)
- cleaned release-note excerpts
- stars/forks context with human-readable formatting (`1.2k`, `169k`)
- security advisory signal
- categorized digest rendering
- separate **OpenClaw Ecosystem Watch** section for interesting repos without releases
- HTML email digest delivery through IMM-Romania
- cached GitHub metadata for faster reruns and previews

## Quick start for humans

### 1. Requirements

Core checker / renderer:
- Python 3
- optional but recommended: `GITHUB_TOKEN`

Email delivery only:
- local `imm-romania` skill install
- expected default path: `~/.openclaw/skills/imm-romania`
- required entrypoint: `scripts/imm-romania.py`

### 2. Create a config

```bash
cp data/github-release-watch-repos.example.json data/github-release-watch-repos.json
```

Then edit:
- `recipient`
- `repos`
- optional `viewer_starred`
- optional `categories`
- optional `interesting_repos`

### 3. Run it

Inspect configured repos:

```bash
python3 scripts/release-watch.py repos \
  --config data/github-release-watch-repos.json
```

Run a release check:

```bash
python3 scripts/release-watch.py check \
  --config data/github-release-watch-repos.json
```

Generate a digest:

```bash
python3 scripts/release-watch.py digest \
  --check \
  --config data/github-release-watch-repos.json
```

Send the email digest:

```bash
bash scripts/release-watch-email.sh
```

## Example config

```json
{
  "enabled": true,
  "recipient": "ops@example.com",
  "viewer_starred": {
    "enabled": true,
    "limit": 30,
    "sort": "created",
    "direction": "desc"
  },
  "categories": [
    {
      "name": "OpenClaw Ecosystem",
      "emoji": "🦀",
      "description": "Platforma, extensii și produse din ecosistemul OpenClaw.",
      "repos": [
        "openclaw/openclaw",
        "Martian-Engineering/lossless-claw",
        "DenchHQ/DenchClaw"
      ]
    }
  ],
  "repos": [
    "openclaw/openclaw",
    "Martian-Engineering/lossless-claw",
    "DenchHQ/DenchClaw"
  ],
  "interesting_repos": [
    {
      "repo": "ChatPRD/tradclaw",
      "label": "Tradclaw",
      "kind": "ecosystem",
      "reason": "Interesting OpenClaw starter repo without GitHub releases yet."
    }
  ]
}
```

## For agents and contributors

If you are working on the repo itself:
- read **`AGENTS.md`** for agent/contributor-specific guidance
- read **`SKILL.md`** for the OpenClaw skill contract

Short version:
- `repos` = release-tracked repos
- `viewer_starred` = authenticated user's starred repositories surfaced inside GRW
- `interesting_repos` = ecosystem visibility, not release status
- keep README human-first
- keep cron summaries deterministic
- do not reintroduce duplicate signals like `Same` + `Unchanged`

## Repo layout

```text
modules/release_watch/         Core checker, config, and digest renderer
scripts/release-watch.py       Main CLI entrypoint
scripts/release-watch-email.sh Email wrapper via IMM-Romania
data/                          Example config + local state files
tests/                         Checker and HTML renderer tests
references/                    Setup and workflow notes
AGENTS.md                      Agent/contributor notes
SKILL.md                       OpenClaw skill metadata and contract
```

## Token and config details

### GitHub token sources

Supported token sources:
1. `GITHUB_TOKEN` environment variable
2. `~/.openclaw/openclaw.json` with `env.GITHUB_TOKEN`

Example:

```bash
export GITHUB_TOKEN=ghp_your_token_here
```

### Default files

- config: `data/github-release-watch-repos.json`
- example config: `data/github-release-watch-repos.example.json`
- state: `data/github-release-watch-state.json`

The state file is created automatically.
Do not commit live state or private local config.

## Environment variables

### Core GitHub Release Watch

- `GITHUB_TOKEN`
- `GITHUB_RELEASE_WATCH_REPOS`
- `GITHUB_RELEASE_WATCH_RECIPIENT`
- `GITHUB_RELEASE_WATCH_CONFIG_PATH`
- `GITHUB_RELEASE_WATCH_STATE_PATH`

### IMM-Romania integration

- `IMM_ROMANIA_PATH`

Notes:
- repo overrides force the checker enabled even without a config file
- if no repos are configured, the checker exits cleanly in no-op mode
- the email wrapper also exits cleanly when there is no config or no recipient

## Email wrapper behavior

`bash scripts/release-watch-email.sh` does this:

1. resolve config/state paths
2. resolve recipient from env or config
3. run `release-watch.py digest --check`
4. render HTML via `modules/release_watch/render_digest.py`
5. send HTML mail through IMM-Romania when valid
6. fall back to plain-text body if needed
7. emit one short deterministic cron summary

If `IMM_ROMANIA_PATH` is wrong or IMM-Romania is missing, the wrapper fails loudly.
If no config or recipient exists, it exits cleanly.

## Testing

Current verification commands:

```bash
python3 -m unittest tests/test_github_checker.py
python3 tests/test_github_template.py
bash -n scripts/release-watch-email.sh
```

What they cover:
- checker state transitions
- update detection and repo overrides
- authenticated viewer-starred fetch/state/render behavior
- digest generation from saved state
- categorized digest rendering
- ecosystem watch rendering
- HTML template stability

## Email card anatomy

Repository cards in the HTML digest are intentionally split into clear sections:
- repo title + stars/forks + release/version context
- timing/meta line (`since`, `avg`, `pace`)
- **Project overview** for the repository description
- **Latest release summary** for the cleaned human-readable release excerpt
- security / attention badges aligned with the release-summary header when present

This keeps the card compact while making the repo description distinct from the latest release notes.

## Operational notes

- this project is intentionally lightweight and stdlib-first
- release checks use local state for change detection
- authenticated viewer-starred repos can be surfaced as a separate first-class section
- repeated GitHub metadata fetches are cached for faster reruns
- GitHub rate limits are much better with `GITHUB_TOKEN`
- email delivery is optional; checking and rendering work without IMM-Romania

## References

- setup notes: `references/setup.md`
- workflow notes: `references/workflows.md`
- skill entrypoint metadata: `SKILL.md`
