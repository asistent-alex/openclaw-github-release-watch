#!/usr/bin/env python3
"""Tests for GitHub release asset support."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'modules'))

from release_watch.checker import GitHubReleaseChecker


class FakeAssetChecker(GitHubReleaseChecker):
    """Test helper with injected API responses including assets."""

    def __init__(self, responses, *args, **kwargs):
        self._responses = responses
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


class TestAssetSupport(unittest.TestCase):
    """Tests for release asset parsing, tracking, and rendering."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "github-config.json"
        self.state_path = Path(self.temp_dir.name) / "github-state.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_config(self, repos):
        payload = {
            "enabled": True,
            "repos": repos,
            "state_path": str(self.state_path),
        }
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    def test_assets_disabled_by_default(self):
        """Without --assets, asset fields should not be populated."""
        self.write_config(["owner/repo"])
        checker = FakeAssetChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "Stable",
                    "prerelease": False,
                    "draft": False,
                    "assets": [
                        {"name": "app.tar.gz", "size": 1024000, "download_count": 42, "browser_download_url": "https://example.com/app.tar.gz"},
                    ],
                    "rate_limit": {},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
            assets=False,
        )
        result = checker.check_repos()
        item = result["results"][0]
        self.assertNotIn("assets", item)
        self.assertFalse(checker.assets)

    def test_assets_enabled_populates_asset_fields(self):
        """With --assets, asset metadata should be tracked in state and results."""
        self.write_config(["owner/repo"])
        checker = FakeAssetChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "Stable",
                    "prerelease": False,
                    "draft": False,
                    "assets": [
                        {"name": "app.tar.gz", "size": 1024000, "download_count": 42, "browser_download_url": "https://example.com/app.tar.gz"},
                        {"name": "app.deb", "size": 512000, "download_count": 7, "browser_download_url": "https://example.com/app.deb"},
                    ],
                    "rate_limit": {},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
            assets=True,
        )
        result = checker.check_repos()
        item = result["results"][0]
        self.assertIn("assets", item)
        self.assertEqual(len(item["assets"]), 2)
        self.assertEqual(item["assets"][0]["name"], "app.tar.gz")
        self.assertEqual(item["assets"][0]["size"], 1024000)
        self.assertEqual(item["assets"][0]["download_count"], 42)
        self.assertEqual(item["assets"][0]["browser_download_url"], "https://example.com/app.tar.gz")

    def test_assets_changed_detected(self):
        """When assets change between runs, assets_changed should be True."""
        self.write_config(["owner/repo"])
        first = FakeAssetChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "Stable",
                    "prerelease": False,
                    "draft": False,
                    "assets": [
                        {"name": "app.tar.gz", "size": 1024000, "download_count": 42, "browser_download_url": "https://example.com/app.tar.gz"},
                    ],
                    "rate_limit": {},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
            assets=True,
        )
        first.check_repos()

        second = FakeAssetChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "Stable",
                    "prerelease": False,
                    "draft": False,
                    "assets": [
                        {"name": "app.tar.gz", "size": 1024000, "download_count": 42, "browser_download_url": "https://example.com/app.tar.gz"},
                        {"name": "app.deb", "size": 512000, "download_count": 7, "browser_download_url": "https://example.com/app.deb"},
                    ],
                    "rate_limit": {},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
            assets=True,
        )
        result = second.check_repos()
        item = result["results"][0]
        self.assertTrue(item["assets_changed"])

    def test_assets_unchanged_false(self):
        """When assets are identical between runs, assets_changed should be False."""
        self.write_config(["owner/repo"])
        first = FakeAssetChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "Stable",
                    "prerelease": False,
                    "draft": False,
                    "assets": [
                        {"name": "app.tar.gz", "size": 1024000, "download_count": 42, "browser_download_url": "https://example.com/app.tar.gz"},
                    ],
                    "rate_limit": {},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
            assets=True,
        )
        first.check_repos()

        second = FakeAssetChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "Stable",
                    "prerelease": False,
                    "draft": False,
                    "assets": [
                        {"name": "app.tar.gz", "size": 1024000, "download_count": 42, "browser_download_url": "https://example.com/app.tar.gz"},
                    ],
                    "rate_limit": {},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
            assets=True,
        )
        result = second.check_repos()
        item = result["results"][0]
        self.assertFalse(item["assets_changed"])

    def test_assets_size_change_detected(self):
        """When asset size changes, assets_changed should be True."""
        self.write_config(["owner/repo"])
        first = FakeAssetChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "Stable",
                    "prerelease": False,
                    "draft": False,
                    "assets": [
                        {"name": "app.tar.gz", "size": 1024000, "download_count": 42, "browser_download_url": "https://example.com/app.tar.gz"},
                    ],
                    "rate_limit": {},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
            assets=True,
        )
        first.check_repos()

        second = FakeAssetChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "Stable",
                    "prerelease": False,
                    "draft": False,
                    "assets": [
                        {"name": "app.tar.gz", "size": 2048000, "download_count": 42, "browser_download_url": "https://example.com/app.tar.gz"},
                    ],
                    "rate_limit": {},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
            assets=True,
        )
        result = second.check_repos()
        item = result["results"][0]
        self.assertTrue(item["assets_changed"])

    def test_empty_assets_list(self):
        """Repos without assets should have empty assets list, not break."""
        self.write_config(["owner/repo"])
        checker = FakeAssetChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "Stable",
                    "prerelease": False,
                    "draft": False,
                    "assets": [],
                    "rate_limit": {},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
            assets=True,
        )
        result = checker.check_repos()
        item = result["results"][0]
        self.assertEqual(item["assets"], [])
        self.assertFalse(item["assets_changed"])

    def test_no_assets_key_in_response(self):
        """GitHub API may omit assets key; handle gracefully."""
        self.write_config(["owner/repo"])
        checker = FakeAssetChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "Stable",
                    "prerelease": False,
                    "draft": False,
                    "rate_limit": {},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
            assets=True,
        )
        result = checker.check_repos()
        item = result["results"][0]
        self.assertEqual(item["assets"], [])
        self.assertFalse(item["assets_changed"])

    def test_assets_in_digest_lines(self):
        """With --assets, digest lines should include asset summary."""
        self.write_config(["owner/repo"])
        checker = FakeAssetChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "Stable",
                    "prerelease": False,
                    "draft": False,
                    "assets": [
                        {"name": "app.tar.gz", "size": 1024000, "download_count": 42, "browser_download_url": "https://example.com/app.tar.gz"},
                    ],
                    "rate_limit": {},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
            assets=True,
        )
        result = checker.check_repos()
        digest = checker.generate_digest(check_first=False)
        body = digest["body"]
        self.assertIn("assets:", body)
        self.assertIn("app.tar.gz", body)

    def test_assets_not_in_digest_without_flag(self):
        """Without --assets, digest lines should not mention assets."""
        self.write_config(["owner/repo"])
        checker = FakeAssetChecker(
            responses={
                "owner/repo": {
                    "ok": True,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": "2026-04-09T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                    "body": "Stable",
                    "prerelease": False,
                    "draft": False,
                    "assets": [
                        {"name": "app.tar.gz", "size": 1024000, "download_count": 42, "browser_download_url": "https://example.com/app.tar.gz"},
                    ],
                    "rate_limit": {},
                }
            },
            config_path=self.config_path,
            state_path=self.state_path,
            token="test",
            assets=False,
        )
        checker.check_repos()
        digest = checker.generate_digest(check_first=False)
        body = digest["body"]
        self.assertNotIn("assets:", body)

    def test_human_size_formatting(self):
        """Human-readable size formatting works for bytes, KB, MB, GB."""
        checker = GitHubReleaseChecker.__new__(GitHubReleaseChecker)
        self.assertEqual(checker._human_size(512), "512B")
        self.assertEqual(checker._human_size(1024), "1KB")
        self.assertEqual(checker._human_size(1536), "1.5KB")
        self.assertEqual(checker._human_size(1024 * 1024), "1MB")
        self.assertEqual(checker._human_size(1024 * 1024 * 1024), "1GB")
        self.assertEqual(checker._human_size(2 * 1024 * 1024 * 1024), "2GB")


if __name__ == "__main__":
    unittest.main()
