"""Tiny key/value accessor over the per-profile ``setting`` table.

SSOT for non-secret per-profile preferences (AI provider, model, on/off). The
secret key itself never lives here -- it lives in ``core.secrets`` as a 0600
file. Keeping these two apart is the least-privilege split: settings are plain
data the browser may read; the key is not.
"""

from __future__ import annotations

import sqlite3

from matchbox.core.db import transaction


def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM setting WHERE key = ?", (key,)).fetchone()
    return row["value"] if row is not None else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    with transaction(conn):
        conn.execute(
            "INSERT INTO setting (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
