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

    def __init__(self, responses, repo_info=None, release_history=None, advisories=None, *args, **kwargs):
        self._responses = responses
        self._repo_info = repo_info or {}
        self._release_history = release_history or {}
        self._advisories = advisories or {}
        super().__init__(*args, **kwargs)

    def get_latest_release(self, repo: str):
        response = self._responses[repo]
        return {"repo": repo, **response}

    def get_repo_info(self, repo: str):
        return self._repo_info.get(repo, {})

    def get_release_history(self, repo: str, per_page: int = 50):
        return self._release_history.get(repo, [])

    def get_repo_advisories(self, repo: str, per_page: int = 10):
        return self._advisories.get(repo, [])


class TestGitHubReleaseChecker(unittest.TestCase):
    """Tests for release checker state transitions."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "github-config.json"
        self.state_path = Path(self.temp_dir.name) / "github-state.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_config(self, repos, categories=None):
        payload = {
            "enabled": True,
            "repos": repos,
            "state_path": str(self.state_path),
        }
        if categories is not None:
            payload["categories"] = categories
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

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

    def test_categories_are_preserved_in_snapshot_and_digest(self):
        self.write_config(
            ["owner/repo"],
            categories=[
                {
                    "name": "Core",
                    "emoji": "⚙️",
                    "description": "Core infra",
                    "repos": ["owner/repo"],
                }
            ],
        )
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
        checker.check_repos()
        snapshot = checker.get_status_snapshot()
        digest = checker.generate_digest(check_first=False)
        self.assertEqual(len(snapshot["categories"]), 1)
        self.assertEqual(snapshot["categories"][0]["name"], "Core")
        self.assertEqual(len(digest["categories"]), 1)

    def test_repo_enrichment_populates_description_and_metrics(self):
        self.write_config(["owner/repo"])
        checker = FakeChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v2.0.0",
                    "name": "Release 2.0.0",
                    "published_at": "2026-04-11T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v2.0.0",
                    "prerelease": False,
                    "draft": False,
                    "rate_limit": {},
                }
            },
            repo_info={
                "owner/repo": {
                    "description": "Useful repo"
                }
            },
            release_history={
                "owner/repo": [
                    {"published_at": "2026-04-11T00:00:00Z"},
                    {"published_at": "2026-04-01T00:00:00Z"},
                    {"published_at": "2026-03-22T00:00:00Z"},
                ]
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
        )
        result = checker.check_repos()
        item = result["results"][0]
        self.assertEqual(item["description"], "Useful repo")
        self.assertIsNotNone(item["avg_release_interval_days"])
        self.assertIsNotNone(item["days_since_last_release"])

    def test_invalid_history_dates_do_not_break_metrics(self):
        self.write_config(["owner/repo"])
        checker = FakeChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "not-a-date",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "",
                    "prerelease": False,
                    "draft": False,
                    "rate_limit": {},
                }
            },
            release_history={
                "owner/repo": [
                    {"published_at": "bad-date"},
                    {"published_at": None},
                ]
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
        )
        result = checker.check_repos()
        item = result["results"][0]
        self.assertIsNone(item["avg_release_interval_days"])
        self.assertIsNone(item["days_since_last_release"])

    def test_prerelease_is_filtered_out_in_stable_only_mode(self):
        self.write_config(["owner/repo"])
        checker = FakeChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v2.0.0-rc1",
                    "name": "v2.0.0-rc1",
                    "published_at": "2026-04-11T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v2.0.0-rc1",
                    "body": "Release candidate",
                    "prerelease": True,
                    "draft": False,
                    "rate_limit": {},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
        )
        result = checker.check_repos()
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"], [])
        self.assertEqual(result["updates"], 0)

    def test_semver_change_is_classified(self):
        self.write_config(["owner/repo"])
        first = FakeChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.2.3",
                    "name": "v1.2.3",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.2.3",
                    "body": "Initial stable release",
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
                    "tag_name": "v1.3.0",
                    "name": "v1.3.0",
                    "published_at": "2026-04-10T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.3.0",
                    "body": "Minor improvements",
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
        self.assertEqual(result["results"][0]["semver_change"], "minor")

    def test_release_notes_excerpt_is_cleaned_and_stored(self):
        self.write_config(["owner/repo"])
        checker = FakeChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-10T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "# Highlights\n- Added smarter sync\n- Fixed email rendering\n\nSee [docs](https://example.com)",
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
        excerpt = result["results"][0]["release_notes_excerpt"]
        self.assertIsNotNone(excerpt)
        self.assertIn("Highlights", excerpt)
        self.assertIn("Added smarter sync", excerpt)
        self.assertNotIn("[docs]", excerpt)

    def test_repo_context_tracks_stars_forks_and_deltas(self):
        self.write_config(["owner/repo"])
        first = FakeChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "first",
                    "prerelease": False,
                    "draft": False,
                    "rate_limit": {},
                }
            },
            repo_info={
                "owner/repo": {
                    "description": "Useful repo",
                    "stargazers_count": 100,
                    "forks_count": 20,
                    "open_issues_count": 7,
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
                    "body": "second",
                    "prerelease": False,
                    "draft": False,
                    "rate_limit": {},
                }
            },
            repo_info={
                "owner/repo": {
                    "description": "Useful repo",
                    "stargazers_count": 104,
                    "forks_count": 22,
                    "open_issues_count": 8,
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
        )
        result = second.check_repos()
        item = result["results"][0]
        self.assertEqual(item["stars"], 104)
        self.assertEqual(item["forks"], 22)
        self.assertEqual(item["stars_delta"], 4)
        self.assertEqual(item["forks_delta"], 2)
        self.assertEqual(item["open_issues"], 8)

    def test_repo_context_tracks_advisory_signal(self):
        self.write_config(["owner/repo"])
        checker = FakeChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-10T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "stable",
                    "prerelease": False,
                    "draft": False,
                    "rate_limit": {},
                }
            },
            advisories={
                "owner/repo": [
                    {"ghsa_id": "GHSA-aaaa-bbbb-cccc"},
                    {"ghsa_id": "GHSA-dddd-eeee-ffff"},
                ]
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
        )
        result = checker.check_repos()
        item = result["results"][0]
        self.assertTrue(item["has_security_advisories"])
        self.assertEqual(item["advisories_count"], 2)


if __name__ == "__main__":
    unittest.main()
