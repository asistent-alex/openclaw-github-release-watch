# AGENTS.md

Agent-specific notes for `github-release-watch`.

## Purpose
This repo is a release-focused monitoring skill for GitHub repositories.
Keep the human-facing README optimized for people first: what the project does, why it matters, how to run it, and how to configure it.

## Documentation split
- `README.md` → humans first
- `AGENTS.md` → agent/build/test/contribution context
- `SKILL.md` → OpenClaw skill contract and metadata

## Key repo rules
- Treat release-tracked repos and non-release ecosystem repos as separate concepts.
- `repos` are for release monitoring.
- `interesting_repos` are for ecosystem visibility and should not pollute release status logic.
- Avoid reintroducing duplicate signals like `Same` + `Unchanged` in repo cards.
- Prefer deterministic cron summaries over model-generated chatter.

## Validation
Before shipping changes, run:

```bash
python3 -m unittest tests/test_github_checker.py
python3 tests/test_github_template.py
bash -n scripts/release-watch-email.sh
```

## Documentation guidance
When editing docs:
- Put the elevator pitch and quick start near the top.
- Keep config examples realistic and short.
- Put deeper operational details below the quick start.
- Prefer examples that match the current digest behavior (`interesting_repos`, ecosystem watch, human-readable repo metrics).
