<div align="center">

# GitHub Release Watch

**Stable release monitoring, clean digests, zero noise**

**Built for [Firma de AI](https://firmade.ai), supported by [Firma de IT](https://firmade.it)**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![OpenClaw Skill](https://img.shields.io/badge/OpenClaw-Skill-green.svg)](https://clawhub.ai)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-brightgreen.svg)](https://www.python.org/)
[![Firma de AI](https://img.shields.io/badge/built%20by-Firma%20de%20AI-6366f1.svg)](https://firmade.ai)
[![Firma de IT](https://img.shields.io/badge/supported%20by-Firma%20de%20IT-0ea5e9.svg)](https://firmade.it)

</div>

---

GitHub Release Watch monitors selected GitHub repositories, detects stable releases, and turns them into a clean digest you can review in JSON, render as HTML, or send by email through NexLink.

> Public positioning: **Firma de AI — GitHub Release Monitor**
> Internal skill / CLI name: **`github-release-watch`**

## Why this is useful

Most release feeds are noisy — raw changelogs bury important changes, repo context is missing, and non-release ecosystem projects get mixed with shipped versions.

GitHub Release Watch fixes that by producing digests that are:

- **release-focused** — tracks stable published releases only (`draft=false`, `prerelease=false`)
- **digest-friendly** — clean summaries, better grouping, less repetition
- **email-safe** — Outlook-friendly HTML cards
- **practical** — includes semver, stars/forks, advisories, cadence, and ecosystem watch

Built by [Firma de AI](https://firmade.ai), supported by [Firma de IT](https://firmade.it).

## What it does

- stable-only GitHub release monitoring with delta-aware state
- semantic version classification (`major`, `minor`, `patch`, `non-semver`)
- cleaned release-note excerpts (strips changelog noise)
- stars/forks context with human-readable formatting (`1.2k`, `169k`)
- security advisory signal per repo
- release attention scoring (breaking changes, security, deprecations)
- repo trend analysis (accelerating, steady, noisy)
- categorized digest rendering with per-category grouping
- **Starred Projects Radar** — surfaces your GitHub stars inside the digest
- **OpenClaw Ecosystem Watch** — tracks interesting repos without releases
- HTML email digest delivery through NexLink
- cached GitHub metadata for faster reruns and previews

## Quick start

### Requirements

Core checker / renderer:
- Python 3.10+
- optional but recommended: `GITHUB_TOKEN`

Email delivery only:
- local NexLink skill install
- expected default path: `~/.openclaw/skills/nexlink`

### 1. Create a config

```bash
cp data/github-release-watch-repos.example.json data/github-release-watch-repos.json
```

Then edit `recipient`, `repos`, and optional sections (`viewer_starred`, `categories`, `interesting_repos`).

### 2. Run it

```bash
python3 scripts/release-watch.py check --config data/github-release-watch-repos.json
python3 scripts/release-watch.py digest --check --config data/github-release-watch-repos.json
```

### 3. Send the email digest

```bash
bash scripts/release-watch-email.sh
```

## Main capabilities

| What you can do | Command |
|---|---|
| Inspect configured repos | `python3 scripts/release-watch.py repos --config data/github-release-watch-repos.json` |
| Run a release check with asset info | `python3 scripts/release-watch.py check --assets --config data/github-release-watch-repos.json` |
| Run a release check | `python3 scripts/release-watch.py check --config data/github-release-watch-repos.json` |
| Run a release check (preview only, no state write) | `python3 scripts/release-watch.py check --dry-run --config data/github-release-watch-repos.json` |
| Generate a digest | `python3 scripts/release-watch.py digest --check --config data/github-release-watch-repos.json` |
| Generate a digest (preview only, no state write) | `python3 scripts/release-watch.py digest --check --dry-run --config data/github-release-watch-repos.json` |
| Generate from saved state | `python3 scripts/release-watch.py digest --config data/github-release-watch-repos.json` |
| Send email digest | `bash scripts/release-watch-email.sh` (*always uses `--dry-run` under the hood*) |
| Override repos on the fly | `python3 scripts/release-watch.py check --repo openclaw/openclaw --repo Martian-Engineering/lossless-claw` |

### Dry-run previews (state-safe)

`--dry-run` runs the full check and digest generation but **never touches the state file**.
The output JSON includes `"dry_run": true` so downstream tools know it was a preview.

```bash
# Preview a release check
python3 scripts/release-watch.py check --dry-run --config data/github-release-watch-repos.json

# Preview a digest
python3 scripts/release-watch.py digest --check --dry-run --config data/github-release-watch-repos.json
```

The email wrapper (`release-watch-email.sh`) always passes `--dry-run` to `digest --check`,
so cron email previews never persist state. On each real cron cycle, the saved state is
updated once by the main check run, and all email sends are safe previews of that state.

### Combined workflows

#### Daily cron check + email

```bash
python3 scripts/release-watch.py digest --check --config data/github-release-watch-repos.json | \
  python3 modules/release_watch/render_digest.py > /tmp/grw-digest.html
```

Or use the one-shot wrapper:

```bash
bash scripts/release-watch-email.sh
```

#### Preview without sending

```bash
python3 scripts/release-watch.py digest --check --config data/github-release-watch-repos.json
```

This outputs JSON — pipe to `render_digest.py` for HTML, or read the JSON directly.

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
      "description": "Platform, extensions, and products from the OpenClaw ecosystem.",
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

## Configuration

### GitHub token sources

Supported token sources (in order of priority):

1. `GITHUB_TOKEN` environment variable
2. `~/.openclaw/openclaw.json` → `env.GITHUB_TOKEN`

```bash
export GITHUB_TOKEN=ghp_your_token_here
```

### Default files

| File | Purpose |
|---|---|
| `data/github-release-watch-repos.json` | Live config (do not commit) |
| `data/github-release-watch-repos.example.json` | Example config template |
| `data/github-release-watch-state.json` | Local state (auto-created, do not commit) |

### Environment variables

| Variable | Purpose |
|---|---|
| `GITHUB_TOKEN` | GitHub API authentication |
| `GITHUB_RELEASE_WATCH_REPOS` | Comma-separated repo overrides |
| `GITHUB_RELEASE_WATCH_RECIPIENT` | Override email recipient |
| `GITHUB_RELEASE_WATCH_CONFIG_PATH` | Override config path |
| `GITHUB_RELEASE_WATCH_STATE_PATH` | Override state path |
| `NEXLINK_PATH` | Path to NexLink skill (email delivery) |

## Installation options

### From Git

```bash
cd ~/.openclaw/skills/
git clone https://github.com/asistent-alex/openclaw-github-release-watch.git
cd openclaw-github-release-watch
```

No pip install needed — the project is stdlib-first with no required dependencies.

### From ClawHub

Use the published listing/slug once the public package is live on ClawHub. The public title is intended to be:

**Firma de AI — GitHub Release Monitor**

## Repo layout

```text
modules/release_watch/         Core checker, config, and digest renderer
scripts/release-watch.py       Main CLI entrypoint
scripts/release-watch-email.sh Email wrapper via NexLink
data/                          Example config + local state files
tests/                         Checker and HTML renderer tests
references/                    Setup and workflow notes
AGENTS.md                      Agent/contributor notes
SKILL.md                       OpenClaw skill metadata and contract
ABOUT.md                       Project about and positioning
```

## Testing

```bash
python3 -m unittest tests/test_github_checker.py -v
python3 tests/test_github_template.py
bash -n scripts/release-watch-email.sh
```

Covers: checker state transitions, update detection, repo overrides, viewer-starred fetch/state/render, digest generation, categorized rendering, ecosystem watch, HTML template stability, **dry-run state preservation (10 tests)**.

## For agents and contributors

- read **`AGENTS.md`** for agent/contributor-specific guidance
- read **`SKILL.md`** for the OpenClaw skill contract
- `repos` = release-tracked repos
- `viewer_starred` = authenticated user's starred repositories surfaced inside GRW
- `interesting_repos` = ecosystem visibility, not release status
- keep README human-first
- keep cron summaries deterministic
- do not reintroduce duplicate signals like `Same` + `Unchanged`

## Brand positioning

For public listings, release notes, and marketing copy, prefer:

- **Title:** Firma de AI — GitHub Release Monitor
- **Subtitle:** Stable release monitoring, clean digests, zero noise
- **Brand line:** Built by Firma de AI, supported by Firma de IT.
- **Links:** https://firmade.ai · https://firmade.it

## Roadmap

- [x] Stable-only release monitoring
- [x] Semantic version classification
- [x] Release-note cleanup and excerpting
- [x] Stars/forks context with delta tracking
- [x] Security advisory signal
- [x] Release attention scoring
- [x] Repo trend analysis
- [x] Categorized digest rendering
- [x] Starred Projects Radar
- [x] OpenClaw Ecosystem Watch
- [x] HTML email delivery through NexLink
- [x] Atomic state writes
- [x] Prerelease/draft visibility (skipped status)
- [ ] ClawHub package listing
- [ ] Webhook / Slack delivery
- [ ] Digest scheduling UI
- [ ] Multi-recipient digests
- [ ] Release comparison links

## License

MIT — see [LICENSE](LICENSE).

This project follows the [Hardshell Coding Standards](https://github.com/asistent-alex/openclaw-hardshell).

---

<div align="center">

**[Firma de AI](https://firmade.ai) · [Firma de IT](https://firmade.it) · Stable release monitoring with ☕**

[Hardshell](https://github.com/asistent-alex/openclaw-hardshell) · [prompt-to-pr](https://github.com/asistent-alex/openclaw-prompt-to-pr) · [Report Bug](https://github.com/asistent-alex/openclaw-github-release-watch/issues) · [Request Feature](https://github.com/asistent-alex/openclaw-github-release-watch/issues)

</div>