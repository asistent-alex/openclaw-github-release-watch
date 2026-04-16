"""GitHub Release Watch core checker logic."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error, request

from .config import DEFAULT_STATE_PATH, load_github_config

try:  # Prefer IMM-Romania / Exchange logger when available.
    from exchange.logger import get_logger as _get_exchange_logger
except Exception:  # pragma: no cover - dependency may be absent in isolation
    _get_exchange_logger = None


GITHUB_API_VERSION = "2026-03-10"
STATE_SCHEMA_VERSION = "1.0.0"
USER_AGENT = "openclaw-github-release-watch"
NO_CONFIG_MESSAGE = "No GitHub repositories configured"
RELEASE_NOTES_MAX_LINES = 3
RELEASE_NOTES_MAX_CHARS = 280
SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")


def _build_logger() -> logging.Logger:
    if _get_exchange_logger is not None:
        try:
            return _get_exchange_logger()
        except Exception:
            pass
    return logging.getLogger("github_release_watch")


_logger = _build_logger()


class GitHubReleaseChecker:
    """Check latest releases for configured GitHub repositories."""

    def __init__(
        self,
        config_path: Optional[Path] = None,
        state_path: Optional[Path] = None,
        token: Optional[str] = None,
        repo_overrides: Optional[List[str]] = None,
    ):
        self.config = load_github_config(
            config_path=config_path,
            repo_overrides=repo_overrides,
        )
        self.state_path = Path(
            state_path or self.config.get("state_path") or DEFAULT_STATE_PATH
        )
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.token = token if token is not None else self._load_token()

    def _load_token(self) -> Optional[str]:
        """Load GitHub token from environment or OpenClaw config."""
        env_token = os.environ.get("GITHUB_TOKEN")
        if env_token:
            return env_token

        config_path = Path.home() / ".openclaw" / "openclaw.json"
        if not config_path.exists():
            return None

        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            return raw.get("env", {}).get("GITHUB_TOKEN")
        except (json.JSONDecodeError, OSError):
            return None

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": USER_AGENT,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request_json(self, url: str) -> Dict[str, Any]:
        req = request.Request(url, headers=self._headers())
        try:
            with request.urlopen(req, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return {
                    "ok": True,
                    "status": response.status,
                    "data": payload,
                    "rate_limit": self._rate_limit_from_headers(response.headers),
                }
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
            return {
                "ok": False,
                "status": exc.code,
                "error": body or str(exc),
                "rate_limit": self._rate_limit_from_headers(exc.headers),
            }
        except Exception as exc:  # pragma: no cover - safety net
            return {"ok": False, "status": None, "error": str(exc), "rate_limit": {}}

    def _rate_limit_from_headers(self, headers: Any) -> Dict[str, Any]:
        if not headers:
            return {}
        return {
            "limit": headers.get("X-RateLimit-Limit"),
            "remaining": headers.get("X-RateLimit-Remaining"),
            "reset": headers.get("X-RateLimit-Reset"),
            "retry_after": headers.get("Retry-After"),
        }

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {"schema_version": STATE_SCHEMA_VERSION, "repos": {}}
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if not isinstance(raw, dict):
                raise ValueError("state must be a dict")
            if "repos" not in raw or not isinstance(raw["repos"], dict):
                raw["repos"] = {}
            raw.setdefault("schema_version", STATE_SCHEMA_VERSION)
            return raw
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            _logger.warning(f"Failed to load GitHub checker state: {exc}")
            return {"schema_version": STATE_SCHEMA_VERSION, "repos": {}}

    def _save_state(self, state: Dict[str, Any]) -> None:
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _build_empty_check_result(self, timestamp: str) -> Dict[str, Any]:
        return {
            "ok": True,
            "enabled": False,
            "timestamp": timestamp,
            "count": 0,
            "updates": 0,
            "failures": 0,
            "results": [],
            "message": NO_CONFIG_MESSAGE,
        }

    def get_latest_release(self, repo: str) -> Dict[str, Any]:
        """Fetch latest published release for a repository."""
        result = self._request_json(
            f"https://api.github.com/repos/{repo}/releases/latest"
        )
        if not result.get("ok"):
            return {
                "ok": False,
                "repo": repo,
                "error": result.get("error", "Unknown error"),
                "status": result.get("status"),
                "rate_limit": result.get("rate_limit", {}),
            }

        data = result["data"]
        return {
            "ok": True,
            "repo": repo,
            "tag_name": data.get("tag_name"),
            "name": data.get("name") or data.get("tag_name"),
            "published_at": data.get("published_at"),
            "html_url": data.get("html_url"),
            "body": data.get("body") or "",
            "prerelease": bool(data.get("prerelease", False)),
            "draft": bool(data.get("draft", False)),
            "rate_limit": result.get("rate_limit", {}),
        }

    def get_release_history(self, repo: str, per_page: int = 50) -> List[Dict[str, Any]]:
        """Fetch recent releases for a repository."""
        result = self._request_json(
            f"https://api.github.com/repos/{repo}/releases?per_page={per_page}"
        )
        if not result.get("ok"):
            return []
        data = result.get("data", [])
        return data if isinstance(data, list) else []

    def get_repo_info(self, repo: str) -> Dict[str, Any]:
        """Fetch repository info (description, etc.)."""
        result = self._request_json(f"https://api.github.com/repos/{repo}")
        if not result.get("ok"):
            return {}
        data = result.get("data", {})
        return data if isinstance(data, dict) else {}

    def get_repo_advisories(self, repo: str, per_page: int = 10) -> List[Dict[str, Any]]:
        """Fetch repository security advisories when available."""
        result = self._request_json(
            f"https://api.github.com/repos/{repo}/security-advisories?per_page={per_page}"
        )
        if not result.get("ok"):
            return []
        data = result.get("data", [])
        return data if isinstance(data, list) else []

    def _is_supported_release(self, release: Dict[str, Any]) -> bool:
        return not bool(release.get("draft")) and not bool(release.get("prerelease"))

    def _determine_status(self, previous: Dict[str, Any], latest_tag: Optional[str]) -> str:
        previous_tag = previous.get("latest_tag")
        if not previous_tag:
            return "first_seen"
        if previous_tag != latest_tag:
            return "updated"
        return "unchanged"

    def _parse_semver(self, value: Optional[str]) -> Optional[tuple[int, int, int]]:
        if not value:
            return None
        match = SEMVER_RE.match(str(value).strip())
        if not match:
            return None
        return tuple(int(part) for part in match.groups())

    def _classify_semver_change(
        self,
        previous_tag: Optional[str],
        latest_tag: Optional[str],
    ) -> Optional[str]:
        previous = self._parse_semver(previous_tag)
        latest = self._parse_semver(latest_tag)
        if latest is None:
            return "non-semver"
        if previous is None:
            return None
        if latest[0] != previous[0]:
            return "major"
        if latest[1] != previous[1]:
            return "minor"
        if latest[2] != previous[2]:
            return "patch"
        return "same"

    def _clean_release_notes_excerpt(self, body: str) -> Optional[str]:
        if not body:
            return None
        lines = []
        for raw_line in body.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            line = re.sub(r"^[-*+]\s*", "", line)
            line = re.sub(r"^#+\s*", "", line)
            line = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", line)
            line = re.sub(r"`([^`]*)`", r"\1", line)
            if len(line) < 4:
                continue
            lines.append(line)
            if len(lines) >= RELEASE_NOTES_MAX_LINES:
                break
        if not lines:
            return None
        excerpt = " • ".join(lines)
        if len(excerpt) > RELEASE_NOTES_MAX_CHARS:
            excerpt = excerpt[: RELEASE_NOTES_MAX_CHARS - 1].rstrip() + "…"
        return excerpt

    def _build_error_result(
        self,
        repo: str,
        previous: Dict[str, Any],
        release: Dict[str, Any],
        timestamp: str,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        repo_state = {
            **previous,
            "last_checked": timestamp,
            "status": "error",
            "error": release.get("error"),
        }
        result = {
            "repo": repo,
            "status": "error",
            "error": release.get("error"),
            "rate_limit": release.get("rate_limit", {}),
        }
        return repo_state, result

    def _build_base_repo_state(
        self,
        previous: Dict[str, Any],
        release: Dict[str, Any],
        status: str,
        timestamp: str,
    ) -> Dict[str, Any]:
        previous_tag = previous.get("latest_tag")
        latest_tag = release.get("tag_name")
        previous_tag_for_state = (
            previous_tag if status == "updated" else previous.get("previous_tag")
        )
        return {
            "latest_tag": latest_tag,
            "previous_tag": previous_tag_for_state,
            "published_at": release.get("published_at"),
            "html_url": release.get("html_url"),
            "name": release.get("name"),
            "release_notes_excerpt": self._clean_release_notes_excerpt(release.get("body") or ""),
            "semver_change": self._classify_semver_change(previous_tag, latest_tag),
            "prerelease": release.get("prerelease", False),
            "draft": release.get("draft", False),
            "last_checked": timestamp,
            "status": status,
            "error": None,
        }

    def _safe_repo_context(self, repo: str, previous: Dict[str, Any]) -> Dict[str, Any]:
        context = {
            "description": None,
            "stars": None,
            "forks": None,
            "stars_delta": None,
            "forks_delta": None,
            "open_issues": None,
            "advisories_count": None,
            "has_security_advisories": None,
        }
        try:
            repo_info = self.get_repo_info(repo)
        except Exception:
            repo_info = {}

        if isinstance(repo_info, dict):
            context["description"] = repo_info.get("description")
            context["stars"] = repo_info.get("stargazers_count")
            context["forks"] = repo_info.get("forks_count")
            context["open_issues"] = repo_info.get("open_issues_count")
            previous_stars = previous.get("stars")
            previous_forks = previous.get("forks")
            if isinstance(context["stars"], int) and isinstance(previous_stars, int):
                context["stars_delta"] = context["stars"] - previous_stars
            if isinstance(context["forks"], int) and isinstance(previous_forks, int):
                context["forks_delta"] = context["forks"] - previous_forks

        try:
            advisories = self.get_repo_advisories(repo, per_page=10)
        except Exception:
            advisories = []

        if isinstance(advisories, list):
            context["advisories_count"] = len(advisories)
            context["has_security_advisories"] = len(advisories) > 0

        return context

    def _safe_release_metrics(self, repo_state: Dict[str, Any], repo: str) -> Dict[str, Any]:
        metrics = {
            "avg_release_interval_days": None,
            "days_since_last_release": None,
        }
        try:
            history = self.get_release_history(repo, per_page=50)
            dates = [item.get("published_at") for item in history if item.get("published_at")]
            metrics["avg_release_interval_days"] = self._average_release_interval_days(dates)
            metrics["days_since_last_release"] = self._days_since(repo_state.get("published_at"))
        except Exception:
            return metrics
        return metrics

    def _average_release_interval_days(self, dates: List[str]) -> Optional[float]:
        parsed = [self._parse_iso_datetime(value) for value in dates]
        parsed = [value for value in parsed if value is not None]
        if len(parsed) < 2:
            return None

        deltas = []
        for index in range(len(parsed) - 1):
            delta = (parsed[index] - parsed[index + 1]).total_seconds() / 86400.0
            if delta >= 0:
                deltas.append(delta)
        if not deltas:
            return None
        return round(sum(deltas) / len(deltas), 1)

    def _days_since(self, published_at: Optional[str]) -> Optional[float]:
        if not published_at:
            return None
        parsed = self._parse_iso_datetime(published_at)
        if parsed is None:
            return None
        delta_days = (datetime.now(timezone.utc) - parsed).total_seconds() / 86400.0
        return round(delta_days, 1)

    def _parse_iso_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    def _finalize_repo_result(
        self,
        repo: str,
        status: str,
        repo_state: Dict[str, Any],
        rate_limit: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {"repo": repo, "status": status, **repo_state, "rate_limit": rate_limit}

    def _snapshot_from_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        results = [
            {"repo": repo, **repo_state}
            for repo, repo_state in state.get("repos", {}).items()
        ]
        return {
            "ok": True,
            "enabled": bool(self.config.get("enabled")),
            "results": results,
            "categories": self.config.get("categories", []),
            "updates": sum(1 for item in results if item.get("status") == "updated"),
            "failures": sum(1 for item in results if item.get("status") == "error"),
            "last_run": state.get("last_run"),
        }

    def _build_digest_lines(self, snapshot: Dict[str, Any]) -> List[str]:
        lines = ["GitHub Releases Monitor", "======================", ""]
        results = snapshot.get("results", [])
        if not results:
            lines.append("No tracked repositories yet.")
            return lines

        for item in results:
            status = item.get("status", "unknown")
            repo = item.get("repo")
            extras = []
            if item.get("has_security_advisories"):
                extras.append(f"security={item.get('advisories_count')}")
            if item.get("stars_delta") not in (None, 0):
                extras.append(f"stars={item.get('stars_delta'):+d}")
            if item.get("forks_delta") not in (None, 0):
                extras.append(f"forks={item.get('forks_delta'):+d}")
            suffix = f" [{', '.join(extras)}]" if extras else ""
            if status == "updated":
                lines.append(
                    f"🆕 {repo}: {item.get('previous_tag')} -> {item.get('latest_tag')}{suffix}"
                )
            elif status == "error":
                lines.append(f"⚠️ {repo}: {item.get('error')}{suffix}")
            elif status == "first_seen":
                lines.append(f"👀 {repo}: first seen at {item.get('latest_tag')}{suffix}")
            else:
                lines.append(f"✅ {repo}: {item.get('latest_tag')}{suffix}")
        return lines

    def check_repos(self) -> Dict[str, Any]:
        """Run release checks for configured repositories."""
        repos = self.config.get("repos", [])
        timestamp = self._now_iso()
        if not self.config.get("enabled") or not repos:
            return self._build_empty_check_result(timestamp)

        state = self._load_state()
        results: List[Dict[str, Any]] = []
        updates = 0
        failures = 0
        latest_rate_limit: Dict[str, Any] = {}

        for repo in repos:
            previous = state["repos"].get(repo, {})
            release = self.get_latest_release(repo)
            latest_rate_limit = release.get("rate_limit", latest_rate_limit)

            if not release.get("ok"):
                failures += 1
                repo_state, result = self._build_error_result(
                    repo=repo,
                    previous=previous,
                    release=release,
                    timestamp=timestamp,
                )
                state["repos"][repo] = repo_state
                results.append(result)
                continue

            if not self._is_supported_release(release):
                continue

            status = self._determine_status(previous, release.get("tag_name"))
            if status == "updated":
                updates += 1

            repo_state = self._build_base_repo_state(
                previous=previous,
                release=release,
                status=status,
                timestamp=timestamp,
            )
            repo_state.update(self._safe_repo_context(repo, previous))
            repo_state.update(self._safe_release_metrics(repo_state, repo))

            state["repos"][repo] = repo_state
            results.append(
                self._finalize_repo_result(
                    repo=repo,
                    status=status,
                    repo_state=repo_state,
                    rate_limit=release.get("rate_limit", {}),
                )
            )

        state["last_run"] = timestamp
        self._save_state(state)

        return {
            "ok": True,
            "enabled": True,
            "timestamp": timestamp,
            "count": len(repos),
            "updates": updates,
            "failures": failures,
            "results": results,
            "categories": self.config.get("categories", []),
            "rate_limit": latest_rate_limit,
            "state_path": str(self.state_path),
        }

    def get_status(self) -> Dict[str, Any]:
        """Return current checker status from saved state."""
        state = self._load_state()
        repos = state.get("repos", {})
        updates = sum(
            1 for repo_state in repos.values() if repo_state.get("status") == "updated"
        )
        failures = sum(
            1 for repo_state in repos.values() if repo_state.get("status") == "error"
        )
        return {
            "ok": True,
            "enabled": bool(self.config.get("enabled")),
            "configured_repos": self.config.get("repos", []),
            "tracked_repos": list(repos.keys()),
            "updates": updates,
            "failures": failures,
            "last_run": state.get("last_run"),
            "state_path": str(self.state_path),
        }

    def generate_digest(self, check_first: bool = False) -> Dict[str, Any]:
        """Generate a compact digest suitable for email or chat."""
        snapshot = self.check_repos() if check_first else self.get_status_snapshot()
        if not snapshot.get("enabled"):
            return {
                "ok": True,
                "has_updates": False,
                "subject": "GitHub Releases - No repos configured",
                "body": NO_CONFIG_MESSAGE + ".",
                "results": [],
                "categories": [],
            }

        subject = (
            f"🆕 GitHub Releases - {snapshot.get('updates', 0)} update(s)"
            if snapshot.get("updates", 0) > 0
            else "GitHub Releases Daily Digest"
        )
        return {
            "ok": True,
            "has_updates": snapshot.get("updates", 0) > 0,
            "subject": subject,
            "body": "\n".join(self._build_digest_lines(snapshot)),
            "results": snapshot.get("results", []),
            "categories": snapshot.get("categories", []),
            "failures": snapshot.get("failures", 0),
            "updates": snapshot.get("updates", 0),
        }

    def get_status_snapshot(self) -> Dict[str, Any]:
        """Return a snapshot with per-repo entries from saved state."""
        state = self._load_state()
        return self._snapshot_from_state(state)
