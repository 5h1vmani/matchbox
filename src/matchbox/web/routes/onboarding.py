"""Onboarding helpers — inbox file staging.

The Jinja onboarding UI has been archived; the React Intake screen drives staging
through `onboarding_api` (JSON), which reuses the helpers below. The app only
stages files into `inbox/`; the actual parsing is the brain's job (the user runs
"ingest my files" in Claude Code).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from matchbox.core.db import PROJECT_ROOT

INBOX_DIR = PROJECT_ROOT / "inbox"
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
ALLOWED_EXTS = {".pdf", ".docx", ".doc", ".txt", ".md", ".json", ".html", ".rtf"}

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def _sanitize(name: str) -> str:
    """Strip path components and replace anything outside [A-Za-z0-9._-]."""
    leaf = Path(name).name
    safe = _SAFE_NAME.sub("_", leaf)
    return safe or "untitled"


def _staged_files() -> list[dict[str, object]]:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for p in sorted(INBOX_DIR.iterdir()):
        if p.name.startswith("."):
            continue
        try:
            rel = str(p.relative_to(PROJECT_ROOT))
        except ValueError:
            # Patched INBOX (tests) lives outside the project root.
            rel = f"inbox/{p.name}"
        rows.append({"name": p.name, "size": p.stat().st_size, "rel_path": rel})
    return rows


def profile_exists(conn: sqlite3.Connection) -> bool:
    """True if the user has any library state (profile row or experiences)."""
    has_profile = conn.execute("SELECT 1 FROM profile LIMIT 1").fetchone() is not None
    has_experiences = conn.execute("SELECT 1 FROM experience LIMIT 1").fetchone() is not None
    return has_profile or has_experiences
