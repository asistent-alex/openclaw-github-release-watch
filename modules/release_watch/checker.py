"""GitHub Release Watch core checker logic."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error, parse, request

from .config import (
    DEFAULT_STATE_PATH,
    DEFAULT_VIEWER_STARRED_LIMIT,
    load_github_config,
)

try:  # Prefer IMM-Romania / Exchange logger when available.
    from exchange.logger import get_logger as _get_exchange_logger
except Exception:  # pragma: no cover - dependency may be absent in isolation
    _get_exchange_logger = None


GITHUB_API_VERSION = "2026-03-10"
STATE_SCHEMA_VERSION = "1.1.0"
USER_AGENT = "openclaw-github-release-watch"
NO_CONFIG_MESSAGE = "No GitHub repositories configured"
RELEASE_NOTES_MAX_LINES = 3
RELEASE_NOTES_MAX_CHARS = 280
REPO_HISTORY_MAX_ITEMS = 12
RELEASE_HISTORY_LOOKBACK = 20
CACHE_TTL_SECONDS = {
    "repo_info": 6 * 3600,
    "release_history": 3 * 3600,
    "advisories": 6 * 3600,
    "viewer_starred": 30 * 60,
}
SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")
ATTENTION_KEYWORD_GROUPS = {
    "breaking": [
        "breaking",
        "breaking change",
        "breaking changes",
        "removed",
        "removal",
        "incompatible",
    ],
    "deprecation": [
        "deprecat",
        "sunset",
        "end of life",
        "eol",
        "legacy",
    ],
    "security": [
        "security",
        "vulnerability",
        "cve",
        "ghsa",
        "exploit",
        "advisory",
    ],
    "migration": [
        "migration",
        "migrate",
        "upgrade guide",
        "upgrade notes",
    ],
}


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
        self._api_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_dirty = False

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
            return {
                "schema_version": STATE_SCHEMA_VERSION,
                "repos": {},
                "viewer_starred": {},
                "api_cache": {},
            }
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if not isinstance(raw, dict):
                raise ValueError("state must be a dict")
            if "repos" not in raw or not isinstance(raw["repos"], dict):
                raw["repos"] = {}
            if "viewer_starred" not in raw or not isinstance(raw["viewer_starred"], dict):
                raw["viewer_starred"] = {}
            if "api_cache" not in raw or not isinstance(raw["api_cache"], dict):
                raw["api_cache"] = {}
            raw.setdefault("schema_version", STATE_SCHEMA_VERSION)
            return raw
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            _logger.warning(f"Failed to load GitHub checker state: {exc}")
            return {
                "schema_version": STATE_SCHEMA_VERSION,
                "repos": {},
                "viewer_starred": {},
                "api_cache": {},
            }

    def _save_state(self, state: Dict[str, Any]) -> None:
        """Write state atomically to avoid corruption from concurrent writes."""
        temp_path = Path(str(self.state_path) + ".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(state, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            # Atomic rename on POSIX; best-effort on Windows
            os.replace(temp_path, self.state_path)
        except Exception:
            # Clean up temp on failure
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    def _attach_cache(self, state: Dict[str, Any]) -> None:
        cache = state.setdefault("api_cache", {})
        if not isinstance(cache, dict):
            cache = {}
            state["api_cache"] = cache
        self._api_cache = cache
        self._cache_dirty = False

    def _cache_get(self, bucket: str, key: str) -> Any:
        entries = self._api_cache.get(bucket)
        if not isinstance(entries, dict):
            return None
        entry = entries.get(key)
        if not isinstance(entry, dict):
            return None
        expires_at = entry.get("expires_at")
        if not isinstance(expires_at, (int, float)) or expires_at <= datetime.now(timezone.utc).timestamp():
            entries.pop(key, None)
            self._cache_dirty = True
            return None
        return entry.get("data")

    def _cache_set(self, bucket: str, key: str, data: Any, ttl_seconds: int) -> Any:
        entries = self._api_cache.setdefault(bucket, {})
        if not isinstance(entries, dict):
            entries = {}
            self._api_cache[bucket] = entries
        entries[key] = {
            "expires_at": datetime.now(timezone.utc).timestamp() + ttl_seconds,
            "data": data,
        }
        self._cache_dirty = True
        return data

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
            "viewer_starred": [],
            "message": NO_CONFIG_MESSAGE,
        }

    def _build_skipped_result(
        self,
        repo: str,
        previous: Dict[str, Any],
        release: Dict[str, Any],
        timestamp: str,
        reason: str,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Record a skipped release (prerelease/draft) so the repo stays visible."""
        repo_state = {
            **previous,
            "last_checked": timestamp,
            "status": reason,
            "latest_tag": release.get("tag_name"),
            "published_at": release.get("published_at"),
            "html_url": release.get("html_url"),
            "name": release.get("name"),
            "prerelease": release.get("prerelease", False),
            "draft": release.get("draft", False),
            "release_notes_excerpt": None,
            "semver_change": None,
            "error": None,
        }
        result = {
            "repo": repo,
            "status": reason,
            "latest_tag": release.get("tag_name"),
            "html_url": release.get("html_url"),
            "rate_limit": release.get("rate_limit", {}),
        }
        return repo_state, result

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
        cache_key = f"{repo}:{per_page}"
        cached = self._cache_get("release_history", cache_key)
        if isinstance(cached, list):
            return cached
        result = self._request_json(
            f"https://api.github.com/repos/{repo}/releases?per_page={per_page}"
        )
        if not result.get("ok"):
            return []
        data = result.get("data", [])
        normalized = data if isinstance(data, list) else []
        return self._cache_set("release_history", cache_key, normalized, CACHE_TTL_SECONDS["release_history"])

    def get_repo_info(self, repo: str) -> Dict[str, Any]:
        """Fetch repository info (description, etc.)."""
        cached = self._cache_get("repo_info", repo)
        if isinstance(cached, dict):
            return cached
        result = self._request_json(f"https://api.github.com/repos/{repo}")
        if not result.get("ok"):
            return {}
        data = result.get("data", {})
        normalized = data if isinstance(data, dict) else {}
        return self._cache_set("repo_info", repo, normalized, CACHE_TTL_SECONDS["repo_info"])

    def get_repo_advisories(self, repo: str, per_page: int = 10) -> List[Dict[str, Any]]:
        """Fetch repository security advisories when available."""
        cache_key = f"{repo}:{per_page}"
        cached = self._cache_get("advisories", cache_key)
        if isinstance(cached, list):
            return cached
        result = self._request_json(
            f"https://api.github.com/repos/{repo}/security-advisories?per_page={per_page}"
        )
        if not result.get("ok"):
            return []
        data = result.get("data", [])
        normalized = data if isinstance(data, list) else []
        return self._cache_set("advisories", cache_key, normalized, CACHE_TTL_SECONDS["advisories"])

    def get_authenticated_user(self) -> Dict[str, Any]:
        """Fetch the authenticated GitHub user."""
        cached = self._cache_get("viewer_starred", "authenticated_user")
        if isinstance(cached, dict):
            return cached
        result = self._request_json("https://api.github.com/user")
        if not result.get("ok"):
            return {
                "ok": False,
                "error": result.get("error", "Unknown error"),
                "status": result.get("status"),
                "rate_limit": result.get("rate_limit", {}),
            }
        data = result.get("data", {})
        normalized = {
            "ok": True,
            "login": data.get("login"),
            "name": data.get("name"),
            "html_url": data.get("html_url"),
            "avatar_url": data.get("avatar_url"),
        }
        return self._cache_set("viewer_starred", "authenticated_user", normalized, CACHE_TTL_SECONDS["viewer_starred"])

    def get_viewer_starred_repos(
        self,
        *,
        limit: Optional[int] = None,
        sort: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch repositories starred by the authenticated GitHub user."""
        viewer_settings = self.config.get("viewer_starred", {})
        resolved_limit = max(1, min(int(limit or viewer_settings.get("limit") or DEFAULT_VIEWER_STARRED_LIMIT), 100))
        resolved_sort = str(sort or viewer_settings.get("sort") or "created").strip().lower()
        if resolved_sort not in {"created", "updated"}:
            resolved_sort = "created"
        resolved_direction = str(direction or viewer_settings.get("direction") or "desc").strip().lower()
        if resolved_direction not in {"asc", "desc"}:
            resolved_direction = "desc"

        cache_key = f"starred:{resolved_limit}:{resolved_sort}:{resolved_direction}"
        cached = self._cache_get("viewer_starred", cache_key)
        if isinstance(cached, dict):
            return cached

        user_info = self.get_authenticated_user()
        if not user_info.get("ok"):
            return {
                "ok": False,
                "error": user_info.get("error", "Authenticated GitHub user unavailable"),
                "status": user_info.get("status"),
                "rate_limit": user_info.get("rate_limit", {}),
                "items": [],
            }

        items: List[Dict[str, Any]] = []
        page = 1
        per_page = min(100, resolved_limit)
        latest_rate_limit: Dict[str, Any] = {}

        while len(items) < resolved_limit:
            query = parse.urlencode(
                {
                    "sort": resolved_sort,
                    "direction": resolved_direction,
                    "per_page": per_page,
                    "page": page,
                }
            )
            result = self._request_json(f"https://api.github.com/user/starred?{query}")
            latest_rate_limit = result.get("rate_limit", latest_rate_limit)
            if not result.get("ok"):
                return {
                    "ok": False,
                    "error": result.get("error", "Failed to fetch authenticated starred repositories"),
                    "status": result.get("status"),
                    "rate_limit": latest_rate_limit,
                    "items": [],
                }

            data = result.get("data", [])
            if not isinstance(data, list) or not data:
                break

            for repo_info in data:
                if not isinstance(repo_info, dict):
                    continue
                full_name = str(repo_info.get("full_name") or "").strip()
                if not full_name or "/" not in full_name:
                    continue
                items.append(
                    {
                        "repo": full_name,
                        "name": repo_info.get("name") or full_name.split("/")[-1],
                        "description": repo_info.get("description"),
                        "html_url": repo_info.get("html_url") or f"https://github.com/{full_name}",
                        "stars": repo_info.get("stargazers_count"),
                        "forks": repo_info.get("forks_count"),
                        "language": repo_info.get("language"),
                        "topics": repo_info.get("topics") if isinstance(repo_info.get("topics"), list) else [],
                        "private": bool(repo_info.get("private", False)),
                        "archived": bool(repo_info.get("archived", False)),
                        "pushed_at": repo_info.get("pushed_at"),
                        "updated_at": repo_info.get("updated_at"),
                    }
                )
                if len(items) >= resolved_limit:
                    break
            if len(data) < per_page:
                break
            page += 1

        payload = {
            "ok": True,
            "login": user_info.get("login"),
            "name": user_info.get("name"),
            "html_url": user_info.get("html_url"),
            "avatar_url": user_info.get("avatar_url"),
            "sort": resolved_sort,
            "direction": resolved_direction,
            "limit": resolved_limit,
            "items": items[:resolved_limit],
            "rate_limit": latest_rate_limit,
        }
        return self._cache_set("viewer_starred", cache_key, payload, CACHE_TTL_SECONDS["viewer_starred"])

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
        noisy_headings = {
            "what's changed",
            "whats changed",
            "what's new",
            "whats new",
            "changes",
            "patch changes",
            "highlights",
        }

        for raw_line in body.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            line = re.sub(r"^[-*+]\s*", "", line)
            line = re.sub(r"^#+\s*", "", line)
            line = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", line)
            line = re.sub(r"`([^`]*)`", r"\1", line)
            line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
            line = re.sub(r"\*(.*?)\*", r"\1", line)
            line = re.sub(r"\bby\s+@[A-Za-z0-9_.-]+\b", "", line)
            line = re.sub(r"\bin\s+https?://\S+", "", line)
            line = re.sub(r"https?://\S+", "", line)
            line = re.sub(r"\s*\(#\d+\)", "", line)
            line = re.sub(r"\s{2,}", " ", line).strip(" -–—:•")

            lowered = line.lower()
            if lowered in noisy_headings:
                continue
            if lowered.startswith("thanks @"):
                continue
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
            history = self.get_release_history(repo, per_page=RELEASE_HISTORY_LOOKBACK)
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

    def _keyword_flags(self, text: str) -> Dict[str, bool]:
        lowered = text.lower()
        return {
            name: any(keyword in lowered for keyword in keywords)
            for name, keywords in ATTENTION_KEYWORD_GROUPS.items()
        }

    def _release_attention(self, repo_state: Dict[str, Any]) -> Dict[str, Any]:
        score = 0
        reasons: List[str] = []
        semver_change = repo_state.get("semver_change")
        keyword_flags = self._keyword_flags(
            " ".join(
                filter(
                    None,
                    [
                        str(repo_state.get("name") or ""),
                        str(repo_state.get("release_notes_excerpt") or ""),
                    ],
                )
            )
        )

        if semver_change == "major":
            score += 3
            reasons.append("major version change")
        elif semver_change == "minor":
            score += 2
            reasons.append("minor version change")
        elif semver_change == "patch":
            score += 1
            reasons.append("patch version change")

        if keyword_flags.get("breaking"):
            score += 3
            reasons.append("breaking-change language detected")
        if keyword_flags.get("deprecation"):
            score += 2
            reasons.append("deprecation language detected")
        if keyword_flags.get("security"):
            score += 2
            reasons.append("security language detected")
        if repo_state.get("has_security_advisories"):
            score += 3
            reasons.append("security advisories present")
        if keyword_flags.get("migration"):
            score += 1
            reasons.append("migration guidance language detected")

        if repo_state.get("status") == "first_seen" and score == 0:
            score = 1
            reasons.append("first observed release")

        if score >= 6:
            attention = "high"
            action = "review before upgrade"
        elif score >= 3:
            attention = "medium"
            action = "watch closely"
        else:
            attention = "low"
            action = "ignore for now"

        priority_order = {
            "security advisories present": 0,
            "breaking-change language detected": 1,
            "major version change": 2,
            "deprecation language detected": 3,
            "security language detected": 4,
            "migration guidance language detected": 5,
            "minor version change": 6,
            "patch version change": 7,
            "first observed release": 8,
        }
        reasons = sorted(reasons, key=lambda value: priority_order.get(value, 99))

        return {
            "release_attention": attention,
            "release_attention_score": score,
            "release_attention_reasons": reasons[:3],
            "release_attention_action": action,
            "release_attention_flags": keyword_flags,
        }

    def _history_event(self, repo_state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "checked_at": repo_state.get("last_checked"),
            "published_at": repo_state.get("published_at"),
            "status": repo_state.get("status"),
            "latest_tag": repo_state.get("latest_tag"),
            "semver_change": repo_state.get("semver_change"),
            "release_attention": repo_state.get("release_attention"),
            "release_attention_score": repo_state.get("release_attention_score"),
        }

    def _updated_history(self, previous: Dict[str, Any], repo_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        history = previous.get("history", [])
        if not isinstance(history, list):
            history = []
        event = self._history_event(repo_state)
        last_event = history[-1] if history else None
        if not isinstance(last_event, dict) or last_event.get("latest_tag") != event.get("latest_tag"):
            history = history + [event]
        else:
            history = history[:-1] + [event]
        return history[-REPO_HISTORY_MAX_ITEMS:]

    def _repo_trend(self, repo: str) -> Dict[str, Any]:
        """Compute repo trend from actual GitHub release history."""
        try:
            releases = self.get_release_history(repo, per_page=RELEASE_HISTORY_LOOKBACK)
        except Exception:
            return {"repo_trend": "stable", "repo_trend_reason": "could not fetch release history"}

        if not isinstance(releases, list) or len(releases) < 3:
            return {"repo_trend": "new", "repo_trend_reason": "not enough GitHub releases yet"}

        valid_dates: List[datetime] = []
        for rel in releases:
            if not isinstance(rel, dict):
                continue
            pub = rel.get("published_at")
            if pub:
                dt = self._parse_iso_datetime(pub)
                if dt is not None:
                    valid_dates.append(dt)

        if len(valid_dates) < 3:
            return {"repo_trend": "new", "repo_trend_reason": "not enough dated GitHub releases"}

        valid_dates.sort()
        intervals: List[float] = []
        for i in range(1, len(valid_dates)):
            delta = (valid_dates[i] - valid_dates[i - 1]).total_seconds() / 86400.0
            if delta >= 0:
                intervals.append(delta)

        tags = [rel.get("tag_name", "") for rel in releases if isinstance(rel, dict) and rel.get("tag_name")]
        tags_chrono = list(reversed(tags))
        semver_list = []
        for i in range(1, len(tags_chrono)):
            change = self._classify_semver_change(tags_chrono[i - 1], tags_chrono[i])
            if change:
                semver_list.append(change)

        recent_semvers = semver_list[-5:] if semver_list else []
        major_count = sum(1 for s in recent_semvers if s == "major")
        minor_patch_count = sum(1 for s in recent_semvers if s in {"minor", "patch"})

        if major_count >= 2:
            return {"repo_trend": "volatile", "repo_trend_reason": "multiple major releases recently"}

        if len(intervals) >= 3:
            recent = intervals[-2:]
            previous = intervals[:-2]
            recent_avg = sum(recent) / len(recent)
            previous_avg = sum(previous) / len(previous) if previous else recent_avg
            if recent_avg < previous_avg * 0.7:
                return {"repo_trend": "accelerating", "repo_trend_reason": "release cadence is speeding up"}
            if recent_avg > previous_avg * 1.3:
                return {"repo_trend": "slowing", "repo_trend_reason": "release cadence is slowing down"}
            if len(intervals) >= 4 and max(intervals[-4:]) - min(intervals[-4:]) <= 7:
                return {"repo_trend": "stable", "repo_trend_reason": "release cadence looks consistent"}

        if minor_patch_count >= 4:
            return {"repo_trend": "noisy", "repo_trend_reason": "many low-impact releases recently"}

        return {"repo_trend": "stable", "repo_trend_reason": "history does not indicate unusual movement"}

    def _finalize_repo_result(
        self,
        repo: str,
        status: str,
        repo_state: Dict[str, Any],
        rate_limit: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {"repo": repo, "status": status, **repo_state, "rate_limit": rate_limit}

    def _interesting_repo_items(self, exclude_repos: Optional[set[str]] = None) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        excluded = exclude_repos or set()
        for item in self.config.get("interesting_repos", []):
            if not isinstance(item, dict):
                continue
            repo = str(item.get("repo") or "").strip()
            if not repo or repo in excluded:
                continue
            repo_info = self.get_repo_info(repo)
            items.append(
                {
                    "repo": repo,
                    "label": item.get("label") or repo.split("/")[-1],
                    "kind": item.get("kind") or "ecosystem",
                    "reason": item.get("reason") or "",
                    "description": repo_info.get("description") if isinstance(repo_info, dict) else None,
                    "stars": repo_info.get("stargazers_count") if isinstance(repo_info, dict) else None,
                    "forks": repo_info.get("forks_count") if isinstance(repo_info, dict) else None,
                    "html_url": repo_info.get("html_url") if isinstance(repo_info, dict) else f"https://github.com/{repo}",
                    "homepage": repo_info.get("homepage") if isinstance(repo_info, dict) else None,
                    "updated_at": repo_info.get("updated_at") if isinstance(repo_info, dict) else None,
                    "release_tracking": "not-release-tracked",
                }
            )
        return items

    def _viewer_starred_items(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        snapshot = state.get("viewer_starred", {})
        items = snapshot.get("items", []) if isinstance(snapshot, dict) else []
        return items if isinstance(items, list) else []

    def _build_viewer_starred_entry(self, repo: str, previous: Dict[str, Any], raw: Dict[str, Any], tracked_repos: set[str]) -> Dict[str, Any]:
        repo_info = self.get_repo_info(repo)
        merged = {**raw}
        if isinstance(repo_info, dict):
            merged["description"] = repo_info.get("description") or merged.get("description")
            merged["stars"] = repo_info.get("stargazers_count", merged.get("stars"))
            merged["forks"] = repo_info.get("forks_count", merged.get("forks"))
            merged["open_issues"] = repo_info.get("open_issues_count")
            merged["homepage"] = repo_info.get("homepage")
            merged["topics"] = repo_info.get("topics") if isinstance(repo_info.get("topics"), list) else merged.get("topics", [])
            merged["language"] = repo_info.get("language") or merged.get("language")
            merged["private"] = bool(repo_info.get("private", merged.get("private", False)))
            merged["archived"] = bool(repo_info.get("archived", merged.get("archived", False)))
            merged["pushed_at"] = repo_info.get("pushed_at") or merged.get("pushed_at")
            merged["updated_at"] = repo_info.get("updated_at") or merged.get("updated_at")

        latest_release = self.get_latest_release(repo)
        merged["tracked"] = repo in tracked_repos
        merged["status"] = "tracked" if merged["tracked"] else "starred"
        merged["has_releases"] = bool(latest_release.get("ok"))
        merged["latest_tag"] = latest_release.get("tag_name") if latest_release.get("ok") else None
        merged["latest_release_name"] = latest_release.get("name") if latest_release.get("ok") else None
        merged["latest_release_url"] = latest_release.get("html_url") if latest_release.get("ok") else None
        merged["release_notes_excerpt"] = self._clean_release_notes_excerpt(latest_release.get("body") or "") if latest_release.get("ok") else None
        merged["days_since_last_push"] = self._days_since(merged.get("pushed_at"))
        merged["email_priority"] = 0 if merged["tracked"] else (1 if merged["has_releases"] else 2)
        previous_stars = previous.get("stars") if isinstance(previous, dict) else None
        previous_forks = previous.get("forks") if isinstance(previous, dict) else None
        if isinstance(merged.get("stars"), int) and isinstance(previous_stars, int):
            merged["stars_delta"] = merged["stars"] - previous_stars
        else:
            merged["stars_delta"] = None
        if isinstance(merged.get("forks"), int) and isinstance(previous_forks, int):
            merged["forks_delta"] = merged["forks"] - previous_forks
        else:
            merged["forks_delta"] = None
        if not str(merged.get("description") or "").strip():
            merged["description"] = None
        return merged

    def _refresh_viewer_starred(self, state: Dict[str, Any], timestamp: str, tracked_repos: set[str]) -> tuple[Dict[str, Any], Dict[str, Any]]:
        settings = self.config.get("viewer_starred", {})
        previous_snapshot = state.get("viewer_starred", {})
        previous_items = previous_snapshot.get("items", []) if isinstance(previous_snapshot, dict) else []
        previous_by_repo = {
            item.get("repo"): item
            for item in previous_items
            if isinstance(item, dict) and item.get("repo")
        }

        if not settings.get("enabled"):
            snapshot = {
                "enabled": False,
                "last_checked": timestamp,
                "limit": settings.get("limit", DEFAULT_VIEWER_STARRED_LIMIT),
                "items": [],
                "count": 0,
            }
            state["viewer_starred"] = snapshot
            return snapshot, {"enabled": False, "items": [], "count": 0}

        starred = self.get_viewer_starred_repos(
            limit=settings.get("limit"),
            sort=settings.get("sort"),
            direction=settings.get("direction"),
        )
        if not starred.get("ok"):
            snapshot = {
                "enabled": True,
                "login": previous_snapshot.get("login"),
                "name": previous_snapshot.get("name"),
                "limit": settings.get("limit", DEFAULT_VIEWER_STARRED_LIMIT),
                "items": previous_items if isinstance(previous_items, list) else [],
                "count": len(previous_items) if isinstance(previous_items, list) else 0,
                "last_checked": timestamp,
                "error": starred.get("error"),
            }
            state["viewer_starred"] = snapshot
            return snapshot, snapshot

        items = []
        for raw in starred.get("items", []):
            if not isinstance(raw, dict):
                continue
            repo = raw.get("repo")
            if not repo:
                continue
            items.append(self._build_viewer_starred_entry(repo, previous_by_repo.get(repo, {}), raw, tracked_repos))

        items.sort(key=lambda item: (item.get("email_priority", 9), str(item.get("repo") or "").lower()))
        untracked_items = [item for item in items if not item.get("tracked")]
        shown_in_email = untracked_items[:10]
        snapshot = {
            "enabled": True,
            "login": starred.get("login"),
            "name": starred.get("name"),
            "html_url": starred.get("html_url"),
            "avatar_url": starred.get("avatar_url"),
            "sort": starred.get("sort"),
            "direction": starred.get("direction"),
            "limit": starred.get("limit"),
            "count": len(items),
            "untracked_count": len(untracked_items),
            "email_count": len(shown_in_email),
            "tracked_count": sum(1 for item in items if item.get("tracked")),
            "with_releases_count": sum(1 for item in untracked_items if item.get("has_releases")),
            "without_releases_count": sum(1 for item in untracked_items if not item.get("has_releases")),
            "items": items,
            "items_for_email": shown_in_email,
            "last_checked": timestamp,
            "error": None,
            "rate_limit": starred.get("rate_limit", {}),
        }
        state["viewer_starred"] = snapshot
        return snapshot, snapshot

    def _snapshot_from_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        results = [
            {"repo": repo, **repo_state}
            for repo, repo_state in state.get("repos", {}).items()
        ]
        viewer_starred_summary = state.get("viewer_starred", {})
        viewer_starred_items = self._viewer_starred_items(state)
        if isinstance(viewer_starred_summary, dict):
            viewer_starred_items = viewer_starred_summary.get("items_for_email", viewer_starred_items)
        starred_repos = {
            item.get("repo")
            for item in viewer_starred_items
            if isinstance(item, dict) and item.get("repo")
        }
        return {
            "ok": True,
            "enabled": bool(self.config.get("enabled")),
            "results": results,
            "viewer_starred": viewer_starred_items,
            "viewer_starred_summary": viewer_starred_summary,
            "categories": self.config.get("categories", []),
            "interesting_repos": self._interesting_repo_items(exclude_repos=starred_repos),
            "updates": sum(1 for item in results if item.get("status") == "updated"),
            "failures": sum(1 for item in results if item.get("status") == "error"),
            "last_run": state.get("last_run"),
        }

    def _build_digest_lines(self, snapshot: Dict[str, Any]) -> List[str]:
        lines = ["GitHub Releases Monitor", "======================", ""]
        results = snapshot.get("results", [])
        if results:
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
                if item.get("release_attention"):
                    extras.append(f"attention={item.get('release_attention')}")
                if item.get("repo_trend"):
                    extras.append(f"trend={item.get('repo_trend')}")
                suffix = f" [{', '.join(extras)}]" if extras else ""
                if status == "updated":
                    lines.append(
                        f"🆕 {repo}: {item.get('previous_tag')} -> {item.get('latest_tag')}{suffix}"
                    )
                elif status == "error":
                    lines.append(f"⚠️ {repo}: {item.get('error')}{suffix}")
                elif status == "first_seen":
                    lines.append(f"👀 {repo}: first seen at {item.get('latest_tag')}{suffix}")
                elif status == "skipped_prerelease":
                    lines.append(f"⏭️ {repo}: {item.get('latest_tag')} (pre-release){suffix}")
                elif status == "skipped_draft":
                    lines.append(f"⏭️ {repo}: {item.get('latest_tag')} (draft){suffix}")
                else:
                    lines.append(f"✅ {repo}: {item.get('latest_tag')}{suffix}")
        else:
            lines.append("No tracked repositories yet.")

        viewer_starred = snapshot.get("viewer_starred", [])
        if viewer_starred:
            lines.extend(["", "Starred Projects Radar", "----------------------"])
            for item in viewer_starred:
                repo = item.get("repo")
                labels = []
                if item.get("has_releases"):
                    labels.append(f"release={item.get('latest_tag') or 'yes'}")
                else:
                    labels.append("no-releases")
                if item.get("days_since_last_push") is not None:
                    labels.append(f"push={item.get('days_since_last_push')}d")
                suffix = f" [{' , '.join(labels)}]" if labels else ""
                lines.append(f"📡 {repo}{suffix}")
        return lines

    def check_repos(self) -> Dict[str, Any]:
        """Run release checks for configured repositories."""
        repos = self.config.get("repos", [])
        viewer_starred_enabled = bool(self.config.get("viewer_starred", {}).get("enabled"))
        timestamp = self._now_iso()
        if not self.config.get("enabled") and not viewer_starred_enabled:
            return self._build_empty_check_result(timestamp)

        state = self._load_state()
        self._attach_cache(state)
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
                repo_state, result = self._build_skipped_result(
                    repo=repo,
                    previous=previous,
                    release=release,
                    timestamp=timestamp,
                    reason="skipped_prerelease" if release.get("prerelease") else "skipped_draft",
                )
                state["repos"][repo] = repo_state
                results.append(result)
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
            repo_state.update(self._release_attention(repo_state))
            repo_state["history"] = self._updated_history(previous, repo_state)
            repo_state.update(self._repo_trend(repo))

            state["repos"][repo] = repo_state
            results.append(
                self._finalize_repo_result(
                    repo=repo,
                    status=status,
                    repo_state=repo_state,
                    rate_limit=release.get("rate_limit", {}),
                )
            )

        viewer_starred_snapshot, viewer_starred_output = self._refresh_viewer_starred(
            state,
            timestamp,
            tracked_repos=set(repos),
        )
        if viewer_starred_snapshot.get("error"):
            failures += 1
        latest_rate_limit = viewer_starred_snapshot.get("rate_limit", latest_rate_limit)

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
            "viewer_starred": viewer_starred_output.get("items_for_email", viewer_starred_output.get("items", [])),
            "viewer_starred_summary": viewer_starred_snapshot,
            "categories": self.config.get("categories", []),
            "interesting_repos": self._interesting_repo_items(exclude_repos={
                item.get("repo")
                for item in viewer_starred_output.get("items", [])
                if isinstance(item, dict) and item.get("repo")
            }),
            "rate_limit": latest_rate_limit,
            "state_path": str(self.state_path),
        }

    def get_status(self) -> Dict[str, Any]:
        """Return current checker status from saved state."""
        state = self._load_state()
        repos = state.get("repos", {})
        viewer_starred_snapshot = state.get("viewer_starred", {})
        updates = sum(
            1 for repo_state in repos.values() if repo_state.get("status") == "updated"
        )
        failures = sum(
            1 for repo_state in repos.values() if repo_state.get("status") == "error"
        )
        if isinstance(viewer_starred_snapshot, dict) and viewer_starred_snapshot.get("error"):
            failures += 1
        return {
            "ok": True,
            "enabled": bool(self.config.get("enabled")),
            "configured_repos": self.config.get("repos", []),
            "tracked_repos": list(repos.keys()),
            "viewer_starred_enabled": bool(self.config.get("viewer_starred", {}).get("enabled")),
            "viewer_starred_count": viewer_starred_snapshot.get("count", 0) if isinstance(viewer_starred_snapshot, dict) else 0,
            "viewer_starred_login": viewer_starred_snapshot.get("login") if isinstance(viewer_starred_snapshot, dict) else None,
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
                "subject": "GitHub Release Watch — No repositories configured",
                "body": NO_CONFIG_MESSAGE + ".",
                "results": [],
                "viewer_starred": [],
                "categories": [],
            }

        updates = snapshot.get("updates", 0)
        if updates > 0:
            release_label = "new release" if updates == 1 else "new releases"
            subject = f"🆕 GitHub Release Watch — {updates} {release_label}"
        else:
            subject = "GitHub Release Watch — No new releases today"
        return {
            "ok": True,
            "has_updates": snapshot.get("updates", 0) > 0,
            "subject": subject,
            "body": "\n".join(self._build_digest_lines(snapshot)),
            "results": snapshot.get("results", []),
            "viewer_starred": snapshot.get("viewer_starred", []),
            "viewer_starred_summary": snapshot.get("viewer_starred_summary", {}),
            "categories": snapshot.get("categories", []),
            "interesting_repos": snapshot.get("interesting_repos", []),
            "failures": snapshot.get("failures", 0),
            "updates": snapshot.get("updates", 0),
            "top_attention": [
                item for item in snapshot.get("results", [])
                if item.get("release_attention") in {"high", "medium"}
            ],
        }

    def get_status_snapshot(self) -> Dict[str, Any]:
        """Return a snapshot with per-repo entries from saved state."""
        state = self._load_state()
        self._attach_cache(state)
        snapshot = self._snapshot_from_state(state)
        if self._cache_dirty:
            self._save_state(state)
        return snapshot
