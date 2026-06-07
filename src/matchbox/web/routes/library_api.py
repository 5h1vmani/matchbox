"""JSON library reads for grounding BYOK prose (prefix /api/library).

Separate from the HTMX-serving `library` router: this returns the verified-fact
payload the browser AI client uses as source material, never the prototype's
hardcoded strings.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from matchbox.core import library as lib
from matchbox.web.deps import ConnDep

router = APIRouter(prefix="/api/library")


@router.get("/facts")
def facts(conn: ConnDep, verified: int = 1) -> dict[str, Any]:
    """Verified facts for BYOK grounding. `?verified=1` (default) returns only
    verified bullets/projects -- the real anti-fabrication lever; `verified=0`
    returns the full library (review surfaces only)."""
    return lib.verified_facts(conn, verified=bool(verified))
