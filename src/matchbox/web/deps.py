"""FastAPI dependencies.

The active profile is resolved per request so the dashboard can switch users
without a restart. Precedence: an explicit `MATCHBOX_DB` path override (used by
CLIs and tests) wins; otherwise the `mb_profile` cookie (validated against the
known profiles); otherwise `MATCHBOX_PROFILE` / the default.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from matchbox.core.db import connect, db_path, list_profiles, profile_slug
from matchbox.core.migrations import migrate

ACTIVE_PROFILE_COOKIE = "mb_profile"


def active_profile(request: Request) -> str:
    """The profile this request operates on."""
    if os.environ.get("MATCHBOX_DB"):
        # Explicit path override: the cookie cannot redirect it.
        return profile_slug()
    cookie = request.cookies.get(ACTIVE_PROFILE_COOKIE)
    if cookie and cookie in set(list_profiles()):
        return cookie
    return profile_slug()


ProfileDep = Annotated[str, Depends(active_profile)]


def get_conn(profile: ProfileDep) -> Iterator[sqlite3.Connection]:
    """Yield a sqlite3 connection scoped to the active profile + request.

    The DB is migrated lazily on first use. Localhost-only single-user app, so
    the per-request open/close cost is irrelevant. WAL keeps writers from
    blocking readers.
    """
    conn = connect(db_path(profile))
    try:
        migrate(conn)
        yield conn
    finally:
        conn.close()


ConnDep = Annotated[sqlite3.Connection, Depends(get_conn)]
