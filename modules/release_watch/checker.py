"""
GitHub release checker for MSP workflows.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error, request

from exchange.logger import get_logger
from .config import DEFAULT_STATE_PATH, load_github_config

_logger = get_logger()

GITHUB_API_VERSION = "2026-03-10"


class GitHubReleaseChecker:
    """Check latest releases for configured GitHub repositories."""

    def __init__(
        self,
        config_path: Optional[Path] = None,
        state_path: Optional[Path] = None,
        token: Optional[str] = None,
        repo_overrides: Optional[List[str]] = None,
    ):
        self.config = load_github_config(config_path=config_path, repo_overrides=repo_overrides)
        self.state_path = Path(state_path or self.config.get("state_path") or DEFAULT_STATE_PATH)
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
            "User-Agent": "openclaw-github-release-watch",
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
                    "rate_limit": {
                        "limit": response.headers.get("X-RateLimit-Limit"),
                        "remaining": response.headers.get("X-RateLimit-Remaining"),
                        "reset": response.headers.get("X-RateLimit-Reset"),
                        "retry_after": response.headers.get("Retry-After"),
                    },
                }
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
            return {
                "ok": False,
                "status": exc.code,
                "error": body or str(exc),
                "rate_limit": {
                    "limit": exc.headers.get("X-RateLimit-Limit") if exc.headers else None,
                    "remaining": exc.headers.get("X-RateLimit-Remaining") if exc.headers else None,
                    "reset": exc.headers.get("X-RateLimit-Reset") if exc.headers else None,
                    "retry_after": exc.headers.get("Retry-After") if exc.headers else None,
                },
            }
        except Exception as exc:  # pragma: no cover - safety net
            return {"ok": False, "status": None, "error": str(exc), "rate_limit": {}}

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {"schema_version": "1.0.0", "repos": {}}
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if not isinstance(raw, dict):
                raise ValueError("state must be a dict")
            if "repos" not in raw or not isinstance(raw["repos"], dict):
                raw["repos"] = {}
            raw.setdefault("schema_version", "1.0.0")
            return raw
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            _logger.warning(f"Failed to load GitHub checker state: {exc}")
            return {"schema_version": "1.0.0", "repos": {}}

    def _save_state(self, state: Dict[str, Any]) -> None:
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)

    def get_latest_release(self, repo: str) -> Dict[str, Any]:
        """Fetch latest published release for a repository."""
        result = self._request_json(f"https://api.github.com/repos/{repo}/releases/latest")
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
            "prerelease": bool(data.get("prerelease", False)),
            "draft": bool(data.get("draft", False)),
            "rate_limit": result.get("rate_limit", {}),
        }

    def check_repos(self) -> Dict[str, Any]:
        """Run release checks for configured repositories."""
        repos = self.config.get("repos", [])
        timestamp = datetime.now(timezone.utc).isoformat()
        if not self.config.get("enabled") or not repos:
            return {
                "ok": True,
                "enabled": False,
                "timestamp": timestamp,
                "count": 0,
                "updates": 0,
                "failures": 0,
                "results": [],
                "message": "No GitHub repositories configured",
            }

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
                repo_state = {
                    **previous,
                    "last_checked": timestamp,
                    "status": "error",
                    "error": release.get("error"),
                }
                state["repos"][repo] = repo_state
                results.append({
                    "repo": repo,
                    "status": "error",
                    "error": release.get("error"),
                    "rate_limit": release.get("rate_limit", {}),
                })
                continue

            previous_tag = previous.get("latest_tag")
            latest_tag = release.get("tag_name")
            if not previous_tag:
                status = "first_seen"
            elif previous_tag != latest_tag:
                status = "updated"
                updates += 1
            else:
                status = "unchanged"

            repo_state = {
                "latest_tag": latest_tag,
                "previous_tag": previous_tag if status == "updated" else previous.get("previous_tag"),
                "published_at": release.get("published_at"),
                "html_url": release.get("html_url"),
                "name": release.get("name"),
                "prerelease": release.get("prerelease", False),
                "draft": release.get("draft", False),
                "last_checked": timestamp,
                "status": status,
                "error": None,
            }

            # Fetch additional metadata: repo description and recent release history to compute average interval
            try:
                repo_info = self.get_repo_info(repo)
                repo_state["description"] = repo_info.get("description") if isinstance(repo_info, dict) else None
            except Exception:
                repo_state["description"] = None

            try:
                history = self.get_release_history(repo, per_page=50)
                # history: list of dicts with 'published_at' ISO timestamps
                dates = [h.get("published_at") for h in history if h.get("published_at")]
                # compute average days between consecutive releases (most recent first)
                if len(dates) >= 2:
                    parsed = []
                    for d in dates:
                        try:
                            parsed.append(datetime.fromisoformat(d.replace("Z", "+00:00")))
                        except Exception:
                            pass
                    if len(parsed) >= 2:
                        deltas = []
                        for i in range(len(parsed) - 1):
                            delta = (parsed[i] - parsed[i + 1]).total_seconds() / 86400.0
                            if delta >= 0:
                                deltas.append(delta)
                        if deltas:
                            avg_interval = sum(deltas) / len(deltas)
                            repo_state["avg_release_interval_days"] = round(avg_interval, 1)
                        else:
                            repo_state["avg_release_interval_days"] = None
                    else:
                        repo_state["avg_release_interval_days"] = None
                else:
                    repo_state["avg_release_interval_days"] = None

                # days since last release
                try:
                    if repo_state.get("published_at"):
                        last = datetime.fromisoformat(repo_state["published_at"].replace("Z", "+00:00"))
                        delta_days = (datetime.now(timezone.utc) - last).total_seconds() / 86400.0
                        repo_state["days_since_last_release"] = round(delta_days, 1)
                    else:
                        repo_state["days_since_last_release"] = None
                except Exception:
                    repo_state["days_since_last_release"] = None
            except Exception:
                repo_state["avg_release_interval_days"] = None
                repo_state["days_since_last_release"] = None

            state["repos"][repo] = repo_state
            results.append({"repo": repo, "status": status, **repo_state, "rate_limit": release.get("rate_limit", {})})

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
        updates = sum(1 for repo_state in repos.values() if repo_state.get("status") == "updated")
        failures = sum(1 for repo_state in repos.values() if repo_state.get("status") == "error")
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
                "body": "No GitHub repositories are configured for monitoring.",
                "results": [],
                "categories": [],
            }

        lines = ["GitHub Releases Monitor", "======================", ""]
        if snapshot.get("results"):
            for item in snapshot["results"]:
                status = item.get("status", "unknown")
                repo = item.get("repo")
                if status == "updated":
                    lines.append(
                        f"🆕 {repo}: {item.get('previous_tag')} -> {item.get('latest_tag')}"
                    )
                elif status == "error":
                    lines.append(f"⚠️ {repo}: {item.get('error')}")
                elif status == "first_seen":
                    lines.append(f"👀 {repo}: first seen at {item.get('latest_tag')}")
                else:
                    lines.append(f"✅ {repo}: {item.get('latest_tag')}")
        else:
            lines.append("No tracked repositories yet.")

        subject = (
            f"🆕 GitHub Releases - {snapshot.get('updates', 0)} update(s)"
            if snapshot.get("updates", 0) > 0
            else "GitHub Releases Daily Digest"
        )
        return {
            "ok": True,
            "has_updates": snapshot.get("updates", 0) > 0,
            "subject": subject,
            "body": "\n".join(lines),
            "results": snapshot.get("results", []),
            "categories": snapshot.get("categories", []),
            "failures": snapshot.get("failures", 0),
            "updates": snapshot.get("updates", 0),
        }

    def get_status_snapshot(self) -> Dict[str, Any]:
        """Return a snapshot with per-repo entries from saved state."""
        state = self._load_state()
        results = []
        for repo, repo_state in state.get("repos", {}).items():
            results.append({"repo": repo, **repo_state})
        return {
            "ok": True,
            "enabled": bool(self.config.get("enabled")),
            "results": results,
            "categories": self.config.get("categories", []),
            "updates": sum(1 for item in results if item.get("status") == "updated"),
            "failures": sum(1 for item in results if item.get("status") == "error"),
            "last_run": state.get("last_run"),
        }

    def get_release_history(self, repo: str, per_page: int = 50) -> List[Dict[str, Any]]:
        """Fetch recent releases for a repository (up to per_page). Returns list of release dicts."""
        result = self._request_json(f"https://api.github.com/repos/{repo}/releases?per_page={per_page}")
        if not result.get("ok"):
            return []
        return result.get("data", [])

    def get_repo_info(self, repo: str) -> Dict[str, Any]:
        """Fetch repository info (description, etc.)."""
        result = self._request_json(f"https://api.github.com/repos/{repo}")
        if not result.get("ok"):
            return {}
        return result.get("data", {})
