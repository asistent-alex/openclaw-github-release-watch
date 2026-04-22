"""GitHub Release Watch module bootstrap."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap_imm_romania_dependency() -> None:
    """Expose IMM-Romania Exchange modules on sys.path when available."""
    env_path = os.environ.get("IMM_ROMANIA_PATH")
    if env_path:
        imm_root = Path(env_path).expanduser().resolve()
    else:
        imm_root = Path.home() / ".openclaw" / "skills" / "imm-romania"

    imm_modules = imm_root / "modules"
    if imm_modules.exists() and str(imm_modules) not in sys.path:
        sys.path.append(str(imm_modules))
    if imm_root.exists() and str(imm_root) not in sys.path:
        sys.path.append(str(imm_root))


_bootstrap_imm_romania_dependency()

__version__ = "3.3.1"

from .checker import GitHubReleaseChecker

__all__ = ["GitHubReleaseChecker"]
