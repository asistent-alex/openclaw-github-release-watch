# About GitHub Release Watch

**Stable release monitoring, clean digests, zero noise.**

GitHub Release Watch is an OpenClaw skill that monitors GitHub repositories you care about, detects new stable releases, and turns them into concise, actionable digests — JSON for automation, HTML for email, plain text for cron.

## Why it exists

Most release feeds are firehoses. Raw changelogs bury the important stuff. Repo context is missing. Non-release projects get mixed with shipped versions. GitHub Release Watch filters the noise and gives you signal: what changed, why it matters, and whether you should act.

## What makes it different

- **Stable-only by default** — prereleases and drafts are tracked but clearly marked, not mixed into your update feed.
- **Delta-aware** — remembers what you've already seen. Only new releases surface as updates.
- **Attention-aware** — scores releases for breaking changes, security advisories, and deprecations so you know what needs review before upgrading.
- **Context-rich** — stars, forks, release cadence, and trend analysis accompany every repo entry.
- **Ecosystem-aware** — separate section for interesting repos that don't ship releases yet (Ecosystem Watch).
- **Starred Radar** — surfaces your own GitHub stars as digest context, highlighting overlap with tracked repos.
- **Email-safe HTML** — renders Outlook-friendly cards that degrade gracefully in texty clients.

## How it works

1. **Check** — fetches latest releases from GitHub API, compares against local state, classifies changes.
2. **Digest** — produces structured JSON with status, semver, excerpts, attention scores, and metadata.
3. **Render** — generates HTML email cards or plain-text summaries.
4. **Deliver** — sends via NexLink / Exchange, or outputs locally for cron and automation.

## Built for

Teams and individuals who:
- track multiple GitHub dependencies
- want a daily release briefing without drowning in changelogs
- need email delivery that works in corporate Outlook
- care about breaking changes and security advisories, not just version numbers

## Built by

**[Firma de AI](https://firmade.ai)** — supported by **[Firma de IT](https://firmade.it)**

Part of the OpenClaw ecosystem. Follows [Hardshell coding standards](https://github.com/asistent-alex/openclaw-hardshell).

## License

MIT