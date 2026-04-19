"""
GitHub Release Watch configuration helpers.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "data" / "github-release-watch-repos.json"
DEFAULT_STATE_PATH = Path(__file__).parent.parent.parent / "data" / "github-release-watch-state.json"
DEFAULT_VIEWER_STARRED_LIMIT = 30


def _normalize_repos(repos: Optional[List[str]]) -> List[str]:
    """Normalize and deduplicate owner/repo values."""
    if not repos:
        return []

    normalized: List[str] = []
    seen = set()
    for repo in repos:
        value = str(repo).strip()
        if not value or "/" not in value:
            continue
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _normalize_interesting_repos(items: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Normalize non-release ecosystem repos kept outside the main watcher."""
    if not items:
        return []

    normalized: List[Dict[str, Any]] = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        repo = str(item.get("repo") or "").strip()
        if not repo or "/" not in repo or repo in seen:
            continue
        seen.add(repo)
        normalized.append(
            {
                "repo": repo,
                "label": str(item.get("label") or repo.split("/")[-1]).strip(),
                "kind": str(item.get("kind") or "ecosystem").strip(),
                "reason": str(item.get("reason") or "").strip(),
            }
        )
    return normalized


def _normalize_viewer_starred(raw: Any) -> Dict[str, Any]:
    """Normalize authenticated viewer-starred settings."""
    config: Dict[str, Any] = {
        "enabled": False,
        "limit": DEFAULT_VIEWER_STARRED_LIMIT,
        "sort": "created",
        "direction": "desc",
    }

    if raw in (None, False):
        return config

    if raw is True:
        config["enabled"] = True
        return config

    if not isinstance(raw, dict):
        return config

    config["enabled"] = bool(raw.get("enabled", True))

    try:
        limit = int(raw.get("limit", DEFAULT_VIEWER_STARRED_LIMIT))
    except (TypeError, ValueError):
        limit = DEFAULT_VIEWER_STARRED_LIMIT
    config["limit"] = max(1, min(limit, 100))

    sort = str(raw.get("sort") or "created").strip().lower()
    if sort not in {"created", "updated"}:
        sort = "created"
    config["sort"] = sort

    direction = str(raw.get("direction") or "desc").strip().lower()
    if direction not in {"asc", "desc"}:
        direction = "desc"
    config["direction"] = direction
    return config


def load_github_config(
    config_path: Optional[Path] = None,
    repo_overrides: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Load GitHub checker configuration.

    Priority:
    1. explicit repo overrides
    2. JSON config file
    3. GITHUB_RELEASE_WATCH_REPOS env var (comma-separated)
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    config: Dict[str, Any] = {
        "enabled": False,
        "recipient": os.environ.get("GITHUB_RELEASE_WATCH_RECIPIENT"),
        "repos": [],
        "interesting_repos": [],
        "viewer_starred": _normalize_viewer_starred(None),
        "config_path": str(path),
        "state_path": str(DEFAULT_STATE_PATH),
    }

    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if isinstance(raw, dict):
                config["enabled"] = bool(raw.get("enabled", True))
                config["recipient"] = raw.get("recipient") or config["recipient"]
                config["state_path"] = str(raw.get("state_path") or DEFAULT_STATE_PATH)
                config["repos"] = _normalize_repos(raw.get("repos", []))
                config["interesting_repos"] = _normalize_interesting_repos(raw.get("interesting_repos", []))
                config["categories"] = raw.get("categories", [])
                config["viewer_starred"] = _normalize_viewer_starred(raw.get("viewer_starred"))
        except (json.JSONDecodeError, OSError):
            config["enabled"] = False
            config["error"] = f"Failed to load config from {path}"

    env_repos = os.environ.get("GITHUB_RELEASE_WATCH_REPOS")
    if env_repos and not config["repos"]:
        config["repos"] = _normalize_repos(env_repos.split(","))
        config["enabled"] = True

    if repo_overrides:
        config["repos"] = _normalize_repos(repo_overrides)
        config["enabled"] = True

    if not config["repos"] and not config.get("viewer_starred", {}).get("enabled"):
        config["enabled"] = False

    return config
