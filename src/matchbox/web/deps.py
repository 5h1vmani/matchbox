"""FastAPI dependencies."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends

from matchbox.core.db import connect
from matchbox.core.migrations import migrate


def get_conn() -> Iterator[sqlite3.Connection]:
    """Yield a sqlite3 connection scoped to the request.

    The DB is migrated lazily on first request; subsequent requests skip.
    Localhost-only single-user app, so the per-request open/close cost
    is irrelevant. WAL mode keeps writers from blocking readers.
    """
    conn = connect()
    try:
        migrate(conn)
        yield conn
    finally:
        conn.close()


ConnDep = Annotated[sqlite3.Connection, Depends(get_conn)]
