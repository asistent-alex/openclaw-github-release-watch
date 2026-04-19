#!/usr/bin/env python3
"""Unit tests for GitHub Release Watch checker."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
        self.assertEqual(digest["subject"], "GitHub Release Watch — No new releases today")
        self.assertIn("GitHub Releases Monitor", digest["body"])
        self.assertIn("owner/repo", digest["body"])

    def test_digest_subject_uses_release_count_when_updates_exist(self):
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
        second.check_repos()

        digest = second.generate_digest(check_first=False)
        self.assertEqual(digest["subject"], "🆕 GitHub Release Watch — 1 new release")

    def test_digest_subject_handles_no_config(self):
        checker = GitHubReleaseChecker(
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
        )
        digest = checker.generate_digest(check_first=False)
        self.assertTrue(digest["ok"])
        self.assertEqual(
            digest["subject"],
            "GitHub Release Watch — No repositories configured",
        )

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
        self.assertIn("Added smarter sync", excerpt)
        self.assertIn("Fixed email rendering", excerpt)
        self.assertNotIn("Highlights", excerpt)
        self.assertNotIn("[docs]", excerpt)
        self.assertNotIn("https://example.com", excerpt)

    def test_release_notes_excerpt_strips_changelog_noise(self):
        self.write_config(["owner/repo"])
        checker = FakeChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-10T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "## What's Changed\n- Fix AI chat threads query firing for users without AI permissions by @thomtrp in https://github.com/twentyhq/twenty/pull/19507\n- i18n - translations by @github-actions[bot] in https://github.com/twentyhq/twenty/pull/19510\n\nThanks @someone!",
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
        self.assertNotIn("What's Changed", excerpt)
        self.assertNotIn("https://github.com", excerpt)
        self.assertNotIn("by @", excerpt)
        self.assertNotIn("Thanks @", excerpt)
        self.assertIn("Fix AI chat threads query firing", excerpt)

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

    def test_release_attention_scores_high_for_breaking_major_security_release(self):
        self.write_config(["owner/repo"])
        first = FakeChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.2.0",
                    "name": "v1.2.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.2.0",
                    "body": "Routine release",
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
                    "tag_name": "v2.0.0",
                    "name": "v2.0.0",
                    "published_at": "2026-04-10T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v2.0.0",
                    "body": "Breaking change. Migration guide included. Security fix for GHSA-123.",
                    "prerelease": False,
                    "draft": False,
                    "rate_limit": {},
                }
            },
            advisories={"owner/repo": [{"ghsa_id": "GHSA-1234-5678-9012"}]},
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
        )
        result = second.check_repos()
        item = result["results"][0]
        self.assertEqual(item["release_attention"], "high")
        self.assertIn("major version change", item["release_attention_reasons"])
        self.assertIn("security advisories present", item["release_attention_reasons"])
        self.assertEqual(item["release_attention_action"], "review before upgrade")

    def test_repo_trend_uses_bounded_history_and_accelerating_label(self):
        self.write_config(["owner/repo"])
        # GitHub release history (newest-first, as returned by the API)
        # Mix of major and minor so it doesn't trigger "noisy" but does show accelerating cadence
        release_history = [
            {"tag_name": "v2.3.0", "published_at": "2026-04-28T00:00:00Z"},
            {"tag_name": "v2.2.0", "published_at": "2026-04-25T00:00:00Z"},
            {"tag_name": "v2.1.0", "published_at": "2026-04-20T00:00:00Z"},
            {"tag_name": "v2.0.0", "published_at": "2026-04-10T00:00:00Z"},
            {"tag_name": "v1.1.0", "published_at": "2026-02-10T00:00:00Z"},
            {"tag_name": "v1.0.0", "published_at": "2026-01-01T00:00:00Z"},
        ]
        checker = FakeChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v2.3.0",
                    "name": "v2.3.0",
                    "published_at": "2026-04-28T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v2.3.0",
                    "body": "Minor release",
                    "prerelease": False,
                    "draft": False,
                    "rate_limit": {},
                }
            },
            release_history={"owner/repo": release_history},
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
        )
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "schema_version": "1.0.0",
                    "repos": {
                        "owner/repo": {
                            "latest_tag": "v2.2.0",
                            "history": []
                        }
                    }
                },
                handle,
            )

        result = checker.check_repos()
        item = result["results"][0]
        self.assertEqual(item["repo_trend"], "accelerating")

    def test_repo_info_is_cached_between_calls(self):
        self.write_config(["owner/repo"])
        checker = GitHubReleaseChecker(
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
        )
        checker._attach_cache({"api_cache": {}})
        response = {
            "ok": True,
            "status": 200,
            "data": {"description": "Cached repo", "stargazers_count": 5},
            "rate_limit": {},
        }
        with patch.object(checker, "_request_json", return_value=response) as mock_request:
            first = checker.get_repo_info("owner/repo")
            second = checker.get_repo_info("owner/repo")
        self.assertEqual(first.get("description"), "Cached repo")
        self.assertEqual(second.get("description"), "Cached repo")
        self.assertEqual(mock_request.call_count, 1)

    def test_repo_trend_marks_noisy_with_many_low_impact_releases(self):
        self.write_config(["owner/repo"])
        # GitHub release history: many minor/patch releases with inconsistent cadence
        # Intervals: 40, 45, 35, 50, 30 → recent_avg=40, previous_avg=40 (not accel/slowing)
        # Spread of last 4 = 20 > 7 (not stable) → falls through to noisy check
        # All minor/patch → should be noisy
        release_history = [
            {"tag_name": "v1.5.0", "published_at": "2026-05-01T00:00:00Z"},
            {"tag_name": "v1.4.3", "published_at": "2026-03-11T00:00:00Z"},
            {"tag_name": "v1.4.2", "published_at": "2026-01-20T00:00:00Z"},
            {"tag_name": "v1.4.1", "published_at": "2025-12-16T00:00:00Z"},
            {"tag_name": "v1.4.0", "published_at": "2025-11-01T00:00:00Z"},
            {"tag_name": "v1.3.0", "published_at": "2025-09-22T00:00:00Z"},
        ]
        checker = FakeChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.5.0",
                    "name": "v1.5.0",
                    "published_at": "2026-05-01T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.5.0",
                    "body": "Patch cleanup",
                    "prerelease": False,
                    "draft": False,
                    "rate_limit": {},
                }
            },
            release_history={"owner/repo": release_history},
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
        )
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "schema_version": "1.0.0",
                    "repos": {
                        "owner/repo": {
                            "latest_tag": "v1.4.0",
                            "history": []
                        }
                    }
                },
                handle,
            )

        result = checker.check_repos()
        item = result["results"][0]
        self.assertEqual(item["repo_trend"], "noisy")


if __name__ == "__main__":
    unittest.main()
