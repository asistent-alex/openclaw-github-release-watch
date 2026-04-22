# prompt-to-pr — ♻️ Refactor
**Task:** Unify repo card layout, move Updated/First seen badges to the top, and align Highlights with the standard card template.
**Branch:** main

---

## Preflight
- Git: ✅
- Tests: ✅ (`tests/test_github_template.py`)
- Coverage: ⚠️ not checked
- Conventions: ✅ workspace context loaded
- hardshell: ✅ applied

## Context Summary
- Language: Python
- Core file: `modules/release_watch/render_digest.py`
- Test file: `tests/test_github_template.py`
- Scope: HTML renderer only; digest/checker logic unchanged

## Plan Metadata
- Overall Risk: LOW
- Confidence: HIGH
- Blast Radius: narrow
- Rollback: easy
- Unknowns: none
- Fast Path: no

## Tasks
- [x] Extract reusable badge-row and card-shell helpers
- [x] Move status badges into a top badge strip
- [x] Make Highlights use the same repo-card summary structure
- [x] Align ecosystem cards with the same card family
- [x] Add regression tests for badge ordering and summary structure
- [x] Run targeted tests

## Test Results
- Baseline: `pytest -q tests/test_github_template.py` → `2 passed in 0.12s`
- Final: `pytest -q tests/test_github_template.py` → `4 passed in 0.39s`

## Verify Summary
- `Updated` / `First seen` badges now render before repo title/meta
- Highlights now keep the shared `Latest release summary` structure
- Ecosystem cards now use the same card-family structure (`Project overview` + summary block)
- No digest data logic changed; renderer-only refactor

## Session State
- Status: WAITING_APPROVAL
- Files modified: `modules/release_watch/render_digest.py`, `tests/test_github_template.py`
- Next action: user review / decide whether to keep iterating or commit
