"""Profile schema migration chain.

Each function migrates a profile dict from version N to N+1.
Migrations are idempotent and non-destructive — they add, rename, or
restructure fields; they never drop data.

Usage (called automatically by person.py):
    from matchbox.core.migrations import migrate_profile
    data = migrate_profile(raw_yaml_dict)
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

CURRENT_VERSION = 1


def migrate_profile(data: dict[str, Any]) -> dict[str, Any]:
    """Run all pending migrations in order. Returns the updated dict."""
    meta = data.setdefault("_meta", {})
    version = int(meta.get("schema_version", 0))

    if version == CURRENT_VERSION:
        return data

    if version > CURRENT_VERSION:
        raise ValueError(
            f"Profile schema_version {version} is newer than this Matchbox "
            f"installation (max supported: {CURRENT_VERSION}). "
            "Upgrade Matchbox."
        )

    chain = {
        0: _v0_to_v1,
    }

    for v in range(version, CURRENT_VERSION):
        if v in chain:
            log.info("Migrating profile from schema v%d to v%d", v, v + 1)
            data = chain[v](data)
            data["_meta"]["schema_version"] = v + 1

    return data


# ──────────────────────────────────────────────
# Migration functions
# ──────────────────────────────────────────────

def _v0_to_v1(data: dict[str, Any]) -> dict[str, Any]:
    """
    v0 → v1: initial Matchbox v0.2 schema.
    Profiles created by migrate_atma_to_profile.py start at v1.
    This handles the edge case where a profile was written without _meta.
    Nothing to transform — just stamp the version.
    """
    data.setdefault("_meta", {})
    data["_meta"]["schema_version"] = 1
    return data
