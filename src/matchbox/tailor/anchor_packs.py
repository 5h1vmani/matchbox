"""Anchor packs — pre-approved bullet variants indexed by role family and tag.

Anchor packs live in people/{name}/anchor-packs.yaml.
Falls back to profile.yaml work_history bullets if the file is missing.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from matchbox.core.schema import Person, WorkBullet

log = logging.getLogger(__name__)
_yaml = YAML()


def _anchor_pack_path(person_name: str) -> Path:
    root = Path(__file__).resolve().parents[4]
    return root / "people" / person_name / "anchor-packs.yaml"


def load_anchor_pack(person_name: str, role_family: str) -> list[WorkBullet]:
    """
    Load pre-approved bullets for a role family from anchor-packs.yaml.

    Returns an empty list (not an error) if the file or role_family is missing;
    callers should fall back to profile.yaml bullets.
    """
    path = _anchor_pack_path(person_name)
    if not path.exists():
        log.debug("anchor-packs.yaml not found for %s, falling back to profile", person_name)
        return []

    with path.open() as fh:
        data: dict[str, Any] = _yaml.load(fh) or {}

    families: dict[str, Any] = data.get("role_families", {})
    family_data = families.get(role_family, {})
    raw_bullets: list[dict[str, Any]] = family_data.get("bullets", [])

    bullets: list[WorkBullet] = []
    for rb in raw_bullets:
        if isinstance(rb, str):
            bullets.append(WorkBullet(text=rb))
        elif isinstance(rb, dict):
            bullets.append(WorkBullet.model_validate(rb))
    return bullets


def select_bullets(
    person: Person,
    role_family: str | None,
    *,
    tags: list[str] | None = None,
    max_per_role: int | None = None,
) -> list[WorkBullet]:
    """
    Select bullets for a role family, optionally filtered by tags.

    Priority:
    1. anchor-packs.yaml bullets matching the role_family (and tags if given)
    2. All profile.yaml work_history bullets as fallback

    max_per_role caps bullets per work entry when falling back to profile bullets.
    """
    if role_family:
        pack = load_anchor_pack(person.name, role_family)
        if pack:
            if tags:
                tags_lower = {t.lower() for t in tags}
                filtered = [b for b in pack if any(t.lower() in tags_lower for t in b.tags)]
                return filtered if filtered else pack
            return pack

    # Fallback: flatten all profile bullets, optionally filter by tags
    all_bullets: list[WorkBullet] = []
    cap = max_per_role or 5
    for entry in person.profile.work_history:
        bullets = entry.bullets[:cap]
        if tags:
            tags_lower = {t.lower() for t in tags}
            bullets = [b for b in bullets if any(t.lower() in tags_lower for t in b.tags)]
        all_bullets.extend(bullets)
    return all_bullets
