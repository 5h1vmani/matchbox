"""Sources helpers.

The Jinja sources UI has been archived; the React Sources screen drives source
management + scanning through `sources_api` (JSON), which reuses the helpers
below. `_get_source` still raises an HTTP 404 so the JSON router surfaces a
clean error.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from fastapi import HTTPException

from matchbox.core.settings import get_setting
from matchbox.discovery.pollers import POLLERS

ATS_TYPES = sorted(POLLERS.keys())


def _list_sources(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT s.*,
               (SELECT COUNT(*) FROM job j WHERE j.source = s.id) AS job_count
          FROM ats_source s
         ORDER BY s.company, s.slug
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _get_source(conn: sqlite3.Connection, source_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM ats_source WHERE id = ?", (source_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no such source: {source_id}")
    return dict(row)


def _adzuna_config(conn: sqlite3.Connection) -> dict[str, Any]:
    """The user's Adzuna BYO-key config, stored in `setting`. Empty if unset."""
    value = get_setting(conn, "adzuna")
    if value is None:
        return {}
    try:
        cfg = json.loads(value)
    except (ValueError, TypeError):
        return {}
    return cfg if isinstance(cfg, dict) else {}
