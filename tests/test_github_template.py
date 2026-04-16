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
            "release_notes_excerpt": "Added smarter sync • Fixed rendering",
            "stars": 120,
            "stars_delta": 5,
            "forks": 18,
            "forks_delta": 2,
            "has_security_advisories": True,
            "advisories_count": 1,
        },
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
    assert 'Test Digest' in out
    assert 'Firma de AI' in out
    assert 'Built by' in out
    assert 'GitHub Release Watch Digest' in out
    assert 'Highlights' in out
    assert 'Repository Status' in out
    assert 'owner/repo' in out
    assert 'owner/updated' in out
    assert 'First seen' in out or 'first seen' in out
    assert 'Updated' in out
    assert 'Minor' in out
    assert 'Added smarter sync' in out
    assert '★ 120 (+5)' in out
    assert '⑂ 18 (+2)' in out
    assert 'Security advisories: 1' in out
    assert 'firmade.it' in out
    assert 'firmade.ai' in out
    assert 'openclaw-github-release-watch' in out
    assert '#1d4ed8' in out or '#38bdf8' in out


def test_render_empty_digest_has_stable_message():
    out = render(EMPTY_DIGEST)
    assert 'Empty Digest' in out
    assert 'GitHub Release Watch Digest' in out
    assert 'No tracked repositories yet.' in out or 'No new releases were detected' in out
    assert '#134e4a' in out or '#5eead4' in out


if __name__ == '__main__':
    test_render_digest_contains_key_sections()
    test_render_empty_digest_has_stable_message()
    print('ok')
