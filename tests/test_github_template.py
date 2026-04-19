#!/usr/bin/env python3
"""Tests for render_digest.py."""

import json
import subprocess
import sys
from pathlib import Path

RENDERER = Path(__file__).resolve().parents[1] / 'modules' / 'release_watch' / 'render_digest.py'

TEST_DIGEST = {
    "subject": "Test Digest",
    "results": [
        {
            "repo": "owner/repo",
            "status": "first_seen",
            "latest_tag": "v1.0.0",
            "html_url": "https://example.com/releases/tag/v1.0.0",
            "published_at": "2026-04-09T00:00:00Z",
        },
        {
            "repo": "owner/updated",
            "status": "updated",
            "previous_tag": "v0.9.0",
            "latest_tag": "v1.0.0",
            "html_url": "https://example.com/releases/tag/v1.0.0",
            "published_at": "2026-04-09T01:00:00Z",
            "semver_change": "minor",
            "description": "Open-source AI agent that builds zero-human businesses, grows audiences, ships code, all autonomously.",
            "release_notes_excerpt": "Added smarter sync • Fixed rendering",
            "stars": 120,
            "stars_delta": 5,
            "forks": 18,
            "forks_delta": 2,
            "has_security_advisories": True,
            "advisories_count": 1,
            "release_attention": "high",
            "release_attention_reasons": ["major version change", "security advisories present"],
            "release_attention_action": "review before upgrade",
            "repo_trend": "accelerating",
            "repo_trend_reason": "release cadence is speeding up",
            "days_since_last_release": 12,
            "avg_release_interval_days": 21,
        },
    ],
    "interesting_repos": [
        {
            "repo": "ecosystem/tradclaw",
            "label": "Tradclaw",
            "description": "Household and parenting OpenClaw starter repo",
            "reason": "Interesting ecosystem project, but not release-tracked yet.",
            "stars": 257,
            "forks": 25,
            "html_url": "https://github.com/ChatPRD/tradclaw",
            "updated_at": "2026-04-19T11:59:02Z"
        }
    ],
    "updates": 1,
    "failures": 0,
}

EMPTY_DIGEST = {
    "subject": "Empty Digest",
    "results": [],
    "updates": 0,
    "failures": 0,
}


def render(payload: dict) -> str:
    proc = subprocess.run(
        [sys.executable, str(RENDERER)],
        input=json.dumps(payload).encode('utf-8'),
        stdout=subprocess.PIPE,
        check=True,
    )
    return proc.stdout.decode('utf-8')


def test_render_digest_contains_key_sections():
    out = render(TEST_DIGEST)
    # Dynamic subject includes repo short names + update count
    assert 'repo' in out or 'updated' in out  # dynamic subject has repo names
    assert '1 update across 2 tracked repos' in out
    assert 'Firma de AI' in out
    assert 'Built by' in out
    assert 'GitHub Release Watch' in out
    assert 'height:3px' in out
    assert 'Executive Dashboard' not in out
    assert 'Recommended action:' not in out
    assert 'Highlights' in out
    assert 'Repository Status' in out
    assert 'owner/repo' in out
    assert 'owner/updated' in out
    assert 'First seen' in out or 'first seen' in out
    assert 'Updated' in out
    assert 'Minor' in out
    assert 'Added smarter sync' in out
    assert 'Project overview' in out
    assert 'Latest release summary' in out
    assert 'AI Summary of updates' not in out
    assert '120 (+5)' in out
    assert '18 (+2)' in out
    assert '#eab308' in out
    assert 'Security (1)' in out
    assert 'Attention: High' in out
    assert 'since ' in out
    assert 'avg ' in out
    assert 'pace faster lately' in out
    assert 'Release cadence is speeding up.' not in out
    assert 'firmade.it' in out
    assert 'firmade.ai' in out
    assert 'openclaw-github-release-watch' in out
    assert '#1d4ed8' in out or '#38bdf8' in out
    assert 'OpenClaw Ecosystem Watch' in out
    assert 'Tradclaw' in out
    assert 'No releases yet' in out


def test_render_empty_digest_has_stable_message():
    out = render(EMPTY_DIGEST)
    # Dynamic subject: no updates → "No new releases — 0 tracked repos stable"
    assert 'No new releases' in out
    assert 'GitHub Release Watch' in out
    assert 'Executive Dashboard' not in out
    assert 'No immediate action required' not in out
    assert 'No tracked repositories yet.' in out or 'No new releases were detected' in out
    assert '#134e4a' in out or '#5eead4' in out
    assert 'Needs review' in out


if __name__ == '__main__':
    test_render_digest_contains_key_sections()
    test_render_empty_digest_has_stable_message()
    print('ok')
