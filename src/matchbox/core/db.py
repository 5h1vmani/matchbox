"""SQLite connection helper. WAL mode, foreign keys on, sqlite3.Row factory.

One DB per profile at `people/<slug>/matchbox.db`. The active profile is
chosen by `MATCHBOX_PROFILE` (defaults to `demo`); the path can be
overridden directly by `MATCHBOX_DB`.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROFILE = "demo"


def profile_slug() -> str:
    return os.environ.get("MATCHBOX_PROFILE", DEFAULT_PROFILE)


def db_path(profile: str | None = None) -> Path:
    """Resolve the SQLite DB path for the given profile.

    `MATCHBOX_DB` wins outright; otherwise we use `people/<profile>/matchbox.db`.
    """
    override = os.environ.get("MATCHBOX_DB")
    if override:
        return Path(override).expanduser().resolve()
    slug = profile or profile_slug()
    return PROJECT_ROOT / "people" / slug / "matchbox.db"


def list_profiles() -> list[str]:
    """Discover profiles: subdirs of `people/` that hold a `matchbox.db`.

    Names starting with `_` are reserved (e.g. a future shared discovery DB).
    """
    base = PROJECT_ROOT / "people"
    if not base.exists():
        return []
    return sorted(
        child.name
        for child in base.iterdir()
        if child.is_dir() and not child.name.startswith("_") and (child / "matchbox.db").exists()
    )


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open a connection with WAL, foreign keys, and Row results."""
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        target,
        isolation_level=None,  # autocommit; we use explicit transactions
        detect_types=sqlite3.PARSE_DECLTYPES,
        # FastAPI runs sync routes + the get_conn dependency in anyio's thread
        # pool, which may create the connection on one pool thread and use/close
        # it on another. Each request owns its own short-lived connection and
        # never shares it across threads concurrently, so disabling the
        # same-thread guard is safe (and required, or every other request 500s
        # with "SQLite objects created in a thread can only be used in that same
        # thread").
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Wrap a block in BEGIN/COMMIT, rolling back on exception."""
    conn.execute("BEGIN")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
