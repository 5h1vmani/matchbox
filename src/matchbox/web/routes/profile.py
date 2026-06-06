"""Profile helpers.

The Jinja profile UI has been archived; the React Profile screen drives editing
through `profile_api` (JSON), which reuses the helpers below.
"""

from __future__ import annotations

import sqlite3
from typing import Any


def _load_profile(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM profile LIMIT 1").fetchone()
    if row is None:
        return {
            "full_name": "",
            "email": "",
            "phone": "",
            "location": "",
            "links_json": "[]",
            "headline": "",
        }
    return dict(row)


def _split_links(raw: str) -> list[str]:
    """One link per line, or comma-separated. Strip whitespace, drop empties."""
    parts = [p.strip() for chunk in raw.splitlines() for p in chunk.split(",")]
    return [p for p in parts if p]
