#!/usr/bin/env python3
"""Unit tests for GitHub Release Watch checker."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'modules'))

from release_watch.checker import GitHubReleaseChecker


class FakeChecker(GitHubReleaseChecker):
    """Test helper with injected API responses."""

    def __init__(self, responses, *args, **kwargs):
        self._responses = responses
        super().__init__(*args, **kwargs)

    def get_latest_release(self, repo: str):
        response = self._responses[repo]
        return {"repo": repo, **response}


class TestGitHubReleaseChecker(unittest.TestCase):
    """Tests for release checker state transitions."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "github-config.json"
        self.state_path = Path(self.temp_dir.name) / "github-state.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_config(self, repos):
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump({"enabled": True, "repos": repos, "state_path": str(self.state_path)}, handle)

    def test_no_config_is_clean_noop(self):
        checker = GitHubReleaseChecker(config_path=self.config_path, state_path=self.state_path, token="test")
        result = checker.check_repos()
        self.assertTrue(result["ok"])
        self.assertFalse(result["enabled"])
        self.assertEqual(result["count"], 0)

    def test_first_run_marks_first_seen(self):
        self.write_config(["owner/repo"])
        checker = FakeChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "prerelease": False,
                    "draft": False,
                    "rate_limit": {},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
        )
        result = checker.check_repos()
        self.assertEqual(result["results"][0]["status"], "first_seen")
        self.assertEqual(result["updates"], 0)

    def test_second_run_detects_update(self):
        self.write_config(["owner/repo"])
        first = FakeChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "prerelease": False,
                    "draft": False,
                    "rate_limit": {},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
        )
        first.check_repos()

        second = FakeChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.1.0",
                    "name": "v1.1.0",
                    "published_at": "2026-04-10T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.1.0",
                    "prerelease": False,
                    "draft": False,
                    "rate_limit": {},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
        )
        result = second.check_repos()
        item = result["results"][0]
        self.assertEqual(item["status"], "updated")
        self.assertEqual(item["previous_tag"], "v1.0.0")
        self.assertEqual(item["latest_tag"], "v1.1.0")
        self.assertEqual(result["updates"], 1)

    def test_fetch_error_is_recorded(self):
        self.write_config(["owner/repo"])
        checker = FakeChecker(
            responses={
                "owner/repo": {
                    "ok": False,
                    "error": "rate limit exceeded",
                    "status": 403,
                    "rate_limit": {"remaining": "0"},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
        )
        result = checker.check_repos()
        self.assertEqual(result["failures"], 1)
        self.assertEqual(result["results"][0]["status"], "error")

    def test_digest_uses_saved_state(self):
        self.write_config(["owner/repo"])
        checker = FakeChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v2.0.0",
                    "name": "v2.0.0",
                    "published_at": "2026-04-11T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v2.0.0",
                    "prerelease": False,
                    "draft": False,
                    "rate_limit": {},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
        )
        checker.check_repos()
        digest = checker.generate_digest(check_first=False)
        self.assertTrue(digest["ok"])
        self.assertIn("GitHub Releases Monitor", digest["body"])
        self.assertIn("owner/repo", digest["body"])

    def test_repo_override_enables_checker(self):
        checker = FakeChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "prerelease": False,
                    "draft": False,
                    "rate_limit": {},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
            repo_overrides=["owner/repo"],
        )
        result = checker.check_repos()
        self.assertTrue(result["enabled"])
        self.assertEqual(result["count"], 1)


if __name__ == "__main__":
    unittest.main()
