#!/usr/bin/env python3
"""CLI entrypoint for GitHub Release Watch."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
MODULES_DIR = SKILL_ROOT / "modules"

sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(MODULES_DIR))

imm_romania_path = os.environ.get("IMM_ROMANIA_PATH")
if imm_romania_path:
    imm_root = Path(imm_romania_path).expanduser().resolve()
else:
    imm_root = Path.home() / ".openclaw" / "skills" / "imm-romania"

imm_modules = imm_root / "modules"
if imm_modules.exists() and str(imm_modules) not in sys.path:
    sys.path.append(str(imm_modules))
if imm_root.exists() and str(imm_root) not in sys.path:
    sys.path.append(str(imm_root))

from release_watch.checker import GitHubReleaseChecker


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GitHub Release Watch",
        epilog=(
            "Examples:\n"
            "  python3 scripts/release-watch.py repos\n"
            "  python3 scripts/release-watch.py check --config data/github-release-watch-repos.example.json\n"
            "  python3 scripts/release-watch.py digest --check --config data/github-release-watch-repos.example.json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    repos_cmd = subparsers.add_parser("repos", help="Show configured repositories")
    repos_cmd.add_argument("--config", help="Optional config path")
    repos_cmd.add_argument("--state", help="Optional state path")
    repos_cmd.add_argument("--repo", action="append", help="Override repo (repeatable)")

    check_cmd = subparsers.add_parser("check", help="Run release check")
    check_cmd.add_argument("--config", help="Optional config path")
    check_cmd.add_argument("--state", help="Optional state path")
    check_cmd.add_argument("--repo", action="append", help="Override repo (repeatable)")

    status_cmd = subparsers.add_parser("status", help="Show saved checker status")
    status_cmd.add_argument("--config", help="Optional config path")
    status_cmd.add_argument("--state", help="Optional state path")
    status_cmd.add_argument("--repo", action="append", help="Override repo (repeatable)")

    digest_cmd = subparsers.add_parser("digest", help="Generate digest from saved or fresh state")
    digest_cmd.add_argument("--config", help="Optional config path")
    digest_cmd.add_argument("--state", help="Optional state path")
    digest_cmd.add_argument("--repo", action="append", help="Override repo (repeatable)")
    digest_cmd.add_argument("--check", action="store_true", help="Refresh before generating digest")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    checker = GitHubReleaseChecker(
        config_path=args.config if hasattr(args, "config") else None,
        state_path=args.state if hasattr(args, "state") else None,
        repo_overrides=args.repo if hasattr(args, "repo") else None,
    )

    if args.command == "repos":
        print(json.dumps({
            "ok": True,
            "enabled": checker.config.get("enabled", False),
            "recipient": checker.config.get("recipient"),
            "repos": checker.config.get("repos", []),
            "config_path": checker.config.get("config_path"),
            "state_path": str(checker.state_path),
        }, indent=2))
    elif args.command == "check":
        print(json.dumps(checker.check_repos(), indent=2))
    elif args.command == "status":
        print(json.dumps(checker.get_status(), indent=2))
    elif args.command == "digest":
        print(json.dumps(checker.generate_digest(check_first=args.check), indent=2))
    else:
        print(json.dumps({"ok": False, "error": "Unknown command"}, indent=2))


if __name__ == "__main__":
    main()
