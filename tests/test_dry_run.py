#!/usr/bin/env python3
"""Tests for --dry-run mode: state must not be written."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'modules'))

from release_watch.checker import GitHubReleaseChecker


class FakeDryRunChecker(GitHubReleaseChecker):
    """Test helper that injects API responses and skips real HTTP."""

    def __init__(self, responses, repo_info=None, release_history=None, advisories=None, *args, **kwargs):
        self._responses = responses
        self._repo_info = repo_info or {}
        self._release_history = release_history or {}
        self._advisories = advisories or {}
        super().__init__(*args, **kwargs)

    def get_latest_release(self, repo: str):
        response = self._responses.get(repo)
        if response is None:
            return {"ok": False, "repo": repo, "error": "not mocked", "status": 404, "rate_limit": {}}
        return {"repo": repo, **response}

    def get_repo_info(self, repo: str):
        return self._repo_info.get(repo, {})

    def get_release_history(self, repo: str, per_page: int = 50):
        return self._release_history.get(repo, [])

    def get_repo_advisories(self, repo: str, per_page: int = 10):
        return self._advisories.get(repo, [])

    def get_authenticated_user(self):
        return {"ok": True, "login": "alex", "name": "Alex", "html_url": "https://github.com/alex", "avatar_url": "https://avatars.example/alex.png"}

    def get_viewer_starred_repos(self, *, limit=None, sort=None, direction=None):
        return {"ok": True, "items": []}


class TestDryRunStatePreservation(unittest.TestCase):
    """State file must not be modified when running in --dry-run mode."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "github-config.json"
        self.state_path = Path(self.temp_dir.name) / "github-state.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_config(self, repos):
        payload = {"enabled": True, "repos": repos, "state_path": str(self.state_path)}
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    def test_dry_run_does_not_create_state_file(self):
        """--dry-run must not create a state file when none existed."""
        self.write_config(["owner/repo"])
        checker = FakeDryRunChecker(
            responses={
                "owner/repo": {
                    "ok": True, "tag_name": "v1.0.0", "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "First", "prerelease": False, "draft": False, "rate_limit": {},
                }
            },
            config_path=self.config_path, state_path=self.state_path, token="test", dry_run=True,
        )
        result = checker.check_repos()
        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertFalse(self.state_path.exists(), "State file must not be created in dry-run mode")

    def test_dry_run_preserves_existing_state(self):
        """--dry-run must not modify an existing state file."""
        self.write_config(["owner/repo"])
        # First, run normally to create state
        normal = FakeDryRunChecker(
            responses={
                "owner/repo": {
                    "ok": True, "tag_name": "v1.0.0", "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "First", "prerelease": False, "draft": False, "rate_limit": {},
                }
            },
            config_path=self.config_path, state_path=self.state_path, token="test", dry_run=False,
        )
        normal.check_repos()
        self.assertTrue(self.state_path.exists())
        original_mtime = self.state_path.stat().st_mtime_ns
        original_content = self.state_path.read_text()

        # Now, dry-run with a different version
        dry = FakeDryRunChecker(
            responses={
                "owner/repo": {
                    "ok": True, "tag_name": "v99.0.0", "name": "v99.0.0",
                    "published_at": "2026-04-10T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v99.0.0",
                    "body": "Big update", "prerelease": False, "draft": False, "rate_limit": {},
                }
            },
            config_path=self.config_path, state_path=self.state_path, token="test", dry_run=True,
        )
        result = dry.check_repos()
        self.assertTrue(result["dry_run"])
        # State file must be unchanged
        self.assertEqual(self.state_path.read_text(), original_content)
        self.assertEqual(self.state_path.stat().st_mtime_ns, original_mtime)

    def test_dry_run_flag_in_output_header(self):
        """Output JSON must carry dry_run: true when dry-run mode is active."""
        self.write_config(["owner/repo"])
        checker = FakeDryRunChecker(
            responses={
                "owner/repo": {
                    "ok": True, "tag_name": "v1.0.0", "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "First", "prerelease": False, "draft": False, "rate_limit": {},
                }
            },
            config_path=self.config_path, state_path=self.state_path, token="test", dry_run=True,
        )
        result = checker.check_repos()
        self.assertTrue(result["dry_run"])

    def test_normal_mode_still_writes_state(self):
        """Normal mode (dry_run=False) must still write state."""
        self.write_config(["owner/repo"])
        checker = FakeDryRunChecker(
            responses={
                "owner/repo": {
                    "ok": True, "tag_name": "v1.0.0", "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "First", "prerelease": False, "draft": False, "rate_limit": {},
                }
            },
            config_path=self.config_path, state_path=self.state_path, token="test", dry_run=False,
        )
        result = checker.check_repos()
        self.assertFalse(result.get("dry_run", False))
        self.assertTrue(self.state_path.exists())

    def test_dry_run_returns_full_results(self):
        """--dry-run must return the same data shape as normal mode."""
        self.write_config(["owner/repo"])
        checker = FakeDryRunChecker(
            responses={
                "owner/repo": {
                    "ok": True, "tag_name": "v1.5.0", "name": "v1.5.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.5.0",
                    "body": "Release", "prerelease": False, "draft": False, "rate_limit": {},
                }
            },
            config_path=self.config_path, state_path=self.state_path, token="test", dry_run=True,
        )
        result = checker.check_repos()
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["repo"], "owner/repo")
        self.assertEqual(result["results"][0]["latest_tag"], "v1.5.0")

    def test_dry_run_generate_digest_does_not_write_state(self):
        """generate_digest with check_first=True in dry-run must not write state."""
        self.write_config(["owner/repo"])
        checker = FakeDryRunChecker(
            responses={
                "owner/repo": {
                    "ok": True, "tag_name": "v1.0.0", "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "First", "prerelease": False, "draft": False, "rate_limit": {},
                }
            },
            config_path=self.config_path, state_path=self.state_path, token="test", dry_run=True,
        )
        digest = checker.generate_digest(check_first=True)
        self.assertFalse(self.state_path.exists(), "State file must not be created by dry-run digest")

    def test_dry_run_does_not_write_atomic_temp_file(self):
        """No .tmp file should be left behind after dry-run."""
        self.write_config(["owner/repo"])
        checker = FakeDryRunChecker(
            responses={
                "owner/repo": {
                    "ok": True, "tag_name": "v1.0.0", "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "First", "prerelease": False, "draft": False, "rate_limit": {},
                }
            },
            config_path=self.config_path, state_path=self.state_path, token="test", dry_run=True,
        )
        checker.check_repos()
        temp_files = list(Path(self.temp_dir.name).glob("*.tmp"))
        self.assertEqual(len(temp_files), 0, f"No .tmp files should exist: {temp_files}")

    def test_dry_run_get_status_snapshot_still_reads_state(self):
        """get_status_snapshot (read-only) should work normally regardless of dry_run."""
        self.write_config(["owner/repo"])
        normal = FakeDryRunChecker(
            responses={
                "owner/repo": {
                    "ok": True, "tag_name": "v1.0.0", "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "First", "prerelease": False, "draft": False, "rate_limit": {},
                }
            },
            config_path=self.config_path, state_path=self.state_path, token="test", dry_run=False,
        )
        normal.check_repos()
        dry = FakeDryRunChecker(
            responses={},
            config_path=self.config_path, state_path=self.state_path, token="test", dry_run=True,
        )
        snapshot = dry.get_status_snapshot()
        self.assertTrue(snapshot["ok"])

    def test_dry_run_with_viewer_starred_does_not_write_state(self):
        """Checker with viewer_starred enabled must not write state in dry-run."""
        payload = {
            "enabled": True,
            "repos": [],
            "viewer_starred": {"enabled": True, "limit": 5},
            "state_path": str(self.state_path),
        }
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        checker = FakeDryRunChecker(
            responses={},
            config_path=self.config_path, state_path=self.state_path, token="test", dry_run=True,
        )
        result = checker.check_repos()
        self.assertTrue(result["dry_run"])
        self.assertFalse(self.state_path.exists(), "State file must not be created in dry-run with viewer_starred")

    def test_dry_run_caches_are_saved_only_in_normal_mode(self):
        """Cache dirtiness should not cause state writes in dry-run mode."""
        self.write_config(["owner/repo"])
        normal = FakeDryRunChecker(
            responses={
                "owner/repo": {
                    "ok": True, "tag_name": "v1.0.0", "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "First", "prerelease": False, "draft": False, "rate_limit": {},
                }
            },
            config_path=self.config_path, state_path=self.state_path, token="test", dry_run=False,
        )
        normal.check_repos()
        original_mtime = self.state_path.stat().st_mtime_ns

        # Dry-run with different data to make cache dirty
        dry = FakeDryRunChecker(
            responses={
                "owner/repo": {
                    "ok": True, "tag_name": "v2.0.0", "name": "v2.0.0",
                    "published_at": "2026-04-10T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v2.0.0",
                    "body": "Second", "prerelease": False, "draft": False, "rate_limit": {},
                }
            },
            config_path=self.config_path, state_path=self.state_path, token="test", dry_run=True,
        )
        dry.check_repos()
        self.assertEqual(self.state_path.stat().st_mtime_ns, original_mtime)


if __name__ == "__main__":
    unittest.main()
