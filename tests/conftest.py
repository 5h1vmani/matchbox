"""Shared pytest fixtures."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from matchbox.core.db import connect
from matchbox.core.migrations import migrate

# Keep the suite offline and lexical: the web scoring route must never
# trigger the fastembed model download during tests.
os.environ.setdefault("MATCHBOX_DISABLE_SEMANTIC", "1")


@pytest.fixture()
def tmp_db(tmp_path: Path) -> sqlite3.Connection:
    """A migrated, isolated SQLite DB at tmp_path/matchbox.db."""
    conn = connect(tmp_path / "matchbox.db")
    migrate(conn)
    return conn
