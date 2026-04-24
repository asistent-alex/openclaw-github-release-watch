#!/usr/bin/env python3
"""Tests for --dry-run mode."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'modules'))

from release_watch.checker import GitHubReleaseChecker


class FakeCheckerDryRun(GitHubReleaseChecker):
    """Test helper with injected API responses."""

    def __init__(self, responses, repo_info=None, release_history=None, advisories=None, viewer_starred=None, authenticated_user=None, *args, **kwargs):
        self._responses = responses
        self._repo_info = repo_info or {}
        self._release_history = release_history or {}
        self._advisories = advisories or {}
        self._viewer_starred = viewer_starred or {"ok": True, "items": []}
        self._authenticated_user = authenticated_user or {
            "ok": True,
            "login": "alex",
            "name": "Alex",
            "html_url": "https://github.com/alex",
            "avatar_url": "https://avatars.example/alex.png",
        }
        super().__init__(*args, **kwargs)

    def get_latest_release(self, repo: str):
        response = self._responses.get(repo)
        if response is None:
            return {
                "ok": False,
                "repo": repo,
                "error": "not mocked",
                "status": 404,
                "rate_limit": {},
            }
        return {"repo": repo, **response}

    def get_repo_info(self, repo: str):
        return self._repo_info.get(repo, {})

    def get_release_history(self, repo: str, per_page: int = 50):
        return self._release_history.get(repo, [])

    def get_repo_advisories(self, repo: str, per_page: int = 10):
        return self._advisories.get(repo, [])

    def get_authenticated_user(self):
        return self._authenticated_user

    def get_viewer_starred_repos(self, *, limit=None, sort=None, direction=None):
        payload = dict(self._viewer_starred)
        payload.setdefault("ok", True)
        payload.setdefault("login", self._authenticated_user.get("login"))
        payload.setdefault("name", self._authenticated_user.get("name"))
        payload.setdefault("html_url", self._authenticated_user.get("html_url"))
        payload.setdefault("avatar_url", self._authenticated_user.get("avatar_url"))
        payload.setdefault("limit", limit)
        payload.setdefault("sort", sort)
        payload.setdefault("direction", direction)
        payload.setdefault("items", [])
        return payload


class TestDryRun(unittest.TestCase):
    """Tests for dry-run behavior."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "github-config.json"
        self.state_path = Path(self.temp_dir.name) / "github-state.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_config(self, repos, categories=None, viewer_starred=None):
        payload = {
            "enabled": True,
            "repos": repos,
            "state_path": str(self.state_path),
        }
        if categories is not None:
            payload["categories"] = categories
        if viewer_starred is not None:
            payload["viewer_starred"] = viewer_starred
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    def test_dry_run_does_not_write_state_file(self):
        """State file must not be created or modified when dry_run=True."""
        self.write_config(["owner/repo"])
        checker = FakeCheckerDryRun(
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
            dry_run=True,
        )
        result = checker.check_repos()
        self.assertTrue(result["ok"])
        self.assertFalse(self.state_path.exists())

    def test_dry_run_returns_results(self):
        """dry_run must still return full results."""
        self.write_config(["owner/repo"])
        checker = FakeCheckerDryRun(
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
            dry_run=True,
        )
        result = checker.check_repos()
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["status"], "first_seen")

    def test_normal_run_writes_state_file(self):
        """Normal run must create state file."""
        self.write_config(["owner/repo"])
        checker = FakeCheckerDryRun(
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
            dry_run=False,
        )
        result = checker.check_repos()
        self.assertTrue(result["ok"])
        self.assertTrue(self.state_path.exists())

    def test_dry_run_preserves_existing_state(self):
        """dry_run must not overwrite existing state."""
        self.write_config(["owner/repo"])
        # Pre-seed state with a marker
        pre_state = {
            "schema_version": "1.1.0",
            "repos": {
                "owner/repo": {
                    "latest_tag": "v0.9.0",
                    "last_checked": "2026-04-08T00:00:00Z",
                }
            },
            "viewer_starred": {},
            "api_cache": {},
        }
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(pre_state, handle)

        checker = FakeCheckerDryRun(
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
            dry_run=True,
        )
        checker.check_repos()
        with open(self.state_path) as f:
            post_state = json.load(f)
        self.assertEqual(post_state["repos"]["owner/repo"]["latest_tag"], "v0.9.0")

    def test_dry_run_flag_on_checker(self):
        """dry_run attribute must be settable and readable."""
        checker = GitHubReleaseChecker(dry_run=True)
        self.assertTrue(checker.dry_run)
        checker2 = GitHubReleaseChecker(dry_run=False)
        self.assertFalse(checker2.dry_run)


if __name__ == "__main__":
    unittest.main()
