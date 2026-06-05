"""Library CRUD: experiences, bullets, projects, skills, summary variants, tags.

These functions are the *only* place SQL touches the library tables. Web
routes call them; tests call them; nothing else writes those rows directly.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from matchbox.core.models import (
    Bullet,
    Experience,
    Facet,
    ItemType,
    Proficiency,
    Project,
    Skill,
    SummaryVariant,
    Tag,
    TaggedItem,
)

# ─── row mappers ──────────────────────────────────────────────────────


def _experience(row: sqlite3.Row) -> Experience:
    return Experience(
        id=row["id"],
        company=row["company"],
        role=row["role"],
        start_date=row["start_date"],
        end_date=row["end_date"],
        location=row["location"],
        sort_order=row["sort_order"],
    )


def _bullet(row: sqlite3.Row) -> Bullet:
    return Bullet(
        id=row["id"],
        experience_id=row["experience_id"],
        text=row["text"],
        has_metric=bool(row["has_metric"]),
        facts_verified=bool(row["facts_verified"]),
        source_file=row["source_file"],
        created_at=row["created_at"],
    )


def _project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        text=row["text"],
        url=row["url"],
        facts_verified=bool(row["facts_verified"]),
    )


def _skill(row: sqlite3.Row) -> Skill:
    return Skill(
        id=row["id"],
        name=row["name"],
        category=row["category"],
        proficiency=row["proficiency"],
    )


def _summary(row: sqlite3.Row) -> SummaryVariant:
    return SummaryVariant(id=row["id"], label=row["label"], text=row["text"])


def _tag(row: sqlite3.Row) -> Tag:
    return Tag(id=row["id"], facet=row["facet"], value=row["value"])


# ─── experiences ──────────────────────────────────────────────────────


def list_experiences(conn: sqlite3.Connection) -> list[Experience]:
    rows = conn.execute(
        "SELECT * FROM experience ORDER BY sort_order, COALESCE(end_date, ''), id"
    ).fetchall()
    return [_experience(r) for r in rows]


def add_experience(
    conn: sqlite3.Connection,
    *,
    company: str,
    role: str,
    start_date: str | None = None,
    end_date: str | None = None,
    location: str | None = None,
    sort_order: int = 0,
) -> Experience:
    cur = conn.execute(
        """
        INSERT INTO experience (company, role, start_date, end_date, location, sort_order)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (company, role, start_date, end_date, location, sort_order),
    )
    assert cur.lastrowid is not None
    return get_experience(conn, cur.lastrowid)


def get_experience(conn: sqlite3.Connection, experience_id: int) -> Experience:
    row = conn.execute("SELECT * FROM experience WHERE id = ?", (experience_id,)).fetchone()
    if row is None:
        raise LookupError(f"experience {experience_id} not found")
    return _experience(row)


# ─── bullets ──────────────────────────────────────────────────────────


def list_bullets(conn: sqlite3.Connection, experience_id: int | None = None) -> list[Bullet]:
    if experience_id is None:
        rows = conn.execute("SELECT * FROM bullet ORDER BY experience_id, id").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM bullet WHERE experience_id = ? ORDER BY id",
            (experience_id,),
        ).fetchall()
    return [_bullet(r) for r in rows]


def add_bullet(
    conn: sqlite3.Connection,
    *,
    experience_id: int,
    text: str,
    has_metric: bool = False,
    facts_verified: bool = False,
    source_file: str | None = None,
) -> Bullet:
    cur = conn.execute(
        """
        INSERT INTO bullet (experience_id, text, has_metric, facts_verified, source_file)
        VALUES (?, ?, ?, ?, ?)
        """,
        (experience_id, text, int(has_metric), int(facts_verified), source_file),
    )
    assert cur.lastrowid is not None
    return get_bullet(conn, cur.lastrowid)


def get_bullet(conn: sqlite3.Connection, bullet_id: int) -> Bullet:
    row = conn.execute("SELECT * FROM bullet WHERE id = ?", (bullet_id,)).fetchone()
    if row is None:
        raise LookupError(f"bullet {bullet_id} not found")
    return _bullet(row)


def update_bullet(
    conn: sqlite3.Connection,
    bullet_id: int,
    *,
    text: str | None = None,
    has_metric: bool | None = None,
    facts_verified: bool | None = None,
) -> Bullet:
    fields: list[str] = []
    values: list[object] = []
    if text is not None:
        fields.append("text = ?")
        values.append(text)
    if has_metric is not None:
        fields.append("has_metric = ?")
        values.append(int(has_metric))
    if facts_verified is not None:
        fields.append("facts_verified = ?")
        values.append(int(facts_verified))
    if not fields:
        return get_bullet(conn, bullet_id)
    values.append(bullet_id)
    conn.execute(f"UPDATE bullet SET {', '.join(fields)} WHERE id = ?", values)
    return get_bullet(conn, bullet_id)


def delete_bullet(conn: sqlite3.Connection, bullet_id: int) -> None:
    conn.execute("DELETE FROM item_tag WHERE item_type = 'bullet' AND item_id = ?", (bullet_id,))
    conn.execute("DELETE FROM bullet WHERE id = ?", (bullet_id,))


# ─── projects ─────────────────────────────────────────────────────────


def list_projects(conn: sqlite3.Connection) -> list[Project]:
    rows = conn.execute("SELECT * FROM project ORDER BY id").fetchall()
    return [_project(r) for r in rows]


def add_project(
    conn: sqlite3.Connection,
    *,
    name: str,
    text: str,
    url: str | None = None,
    facts_verified: bool = False,
) -> Project:
    cur = conn.execute(
        "INSERT INTO project (name, text, url, facts_verified) VALUES (?, ?, ?, ?)",
        (name, text, url, int(facts_verified)),
    )
    assert cur.lastrowid is not None
    return get_project(conn, cur.lastrowid)


def get_project(conn: sqlite3.Connection, project_id: int) -> Project:
    row = conn.execute("SELECT * FROM project WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise LookupError(f"project {project_id} not found")
    return _project(row)


def delete_project(conn: sqlite3.Connection, project_id: int) -> None:
    conn.execute("DELETE FROM item_tag WHERE item_type = 'project' AND item_id = ?", (project_id,))
    conn.execute("DELETE FROM project WHERE id = ?", (project_id,))


# ─── skills ───────────────────────────────────────────────────────────


def list_skills(conn: sqlite3.Connection) -> list[Skill]:
    rows = conn.execute("SELECT * FROM skill ORDER BY category, name").fetchall()
    return [_skill(r) for r in rows]


def add_skill(
    conn: sqlite3.Connection,
    *,
    name: str,
    category: str | None = None,
    proficiency: Proficiency | None = None,
) -> Skill:
    cur = conn.execute(
        "INSERT INTO skill (name, category, proficiency) VALUES (?, ?, ?)",
        (name, category, proficiency),
    )
    assert cur.lastrowid is not None
    return get_skill(conn, cur.lastrowid)


def get_skill(conn: sqlite3.Connection, skill_id: int) -> Skill:
    row = conn.execute("SELECT * FROM skill WHERE id = ?", (skill_id,)).fetchone()
    if row is None:
        raise LookupError(f"skill {skill_id} not found")
    return _skill(row)


def delete_skill(conn: sqlite3.Connection, skill_id: int) -> None:
    conn.execute("DELETE FROM item_tag WHERE item_type = 'skill' AND item_id = ?", (skill_id,))
    conn.execute("DELETE FROM skill WHERE id = ?", (skill_id,))


# ─── summary variants ─────────────────────────────────────────────────


def list_summaries(conn: sqlite3.Connection) -> list[SummaryVariant]:
    rows = conn.execute("SELECT * FROM summary_variant ORDER BY id").fetchall()
    return [_summary(r) for r in rows]


def add_summary(conn: sqlite3.Connection, *, label: str, text: str) -> SummaryVariant:
    cur = conn.execute("INSERT INTO summary_variant (label, text) VALUES (?, ?)", (label, text))
    assert cur.lastrowid is not None
    return get_summary(conn, cur.lastrowid)


def get_summary(conn: sqlite3.Connection, summary_id: int) -> SummaryVariant:
    row = conn.execute("SELECT * FROM summary_variant WHERE id = ?", (summary_id,)).fetchone()
    if row is None:
        raise LookupError(f"summary {summary_id} not found")
    return _summary(row)


def delete_summary(conn: sqlite3.Connection, summary_id: int) -> None:
    conn.execute(
        "DELETE FROM item_tag WHERE item_type = 'summary_variant' AND item_id = ?",
        (summary_id,),
    )
    conn.execute("DELETE FROM summary_variant WHERE id = ?", (summary_id,))


# ─── tags ─────────────────────────────────────────────────────────────


def list_tags(conn: sqlite3.Connection, facet: Facet | None = None) -> list[Tag]:
    if facet is None:
        rows = conn.execute("SELECT * FROM tag ORDER BY facet, value").fetchall()
    else:
        rows = conn.execute("SELECT * FROM tag WHERE facet = ? ORDER BY value", (facet,)).fetchall()
    return [_tag(r) for r in rows]


def find_or_create_tag(conn: sqlite3.Connection, *, facet: Facet, value: str) -> Tag:
    row = conn.execute("SELECT * FROM tag WHERE facet = ? AND value = ?", (facet, value)).fetchone()
    if row is not None:
        return _tag(row)
    cur = conn.execute("INSERT INTO tag (facet, value) VALUES (?, ?)", (facet, value))
    assert cur.lastrowid is not None
    return Tag(id=cur.lastrowid, facet=facet, value=value)


def attach_tag(
    conn: sqlite3.Connection,
    *,
    item_type: ItemType,
    item_id: int,
    facet: Facet,
    value: str,
) -> Tag:
    tag = find_or_create_tag(conn, facet=facet, value=value)
    conn.execute(
        "INSERT OR IGNORE INTO item_tag (item_type, item_id, tag_id) VALUES (?, ?, ?)",
        (item_type, item_id, tag.id),
    )
    return tag


def detach_tag(
    conn: sqlite3.Connection,
    *,
    item_type: ItemType,
    item_id: int,
    tag_id: int,
) -> None:
    conn.execute(
        "DELETE FROM item_tag WHERE item_type = ? AND item_id = ? AND tag_id = ?",
        (item_type, item_id, tag_id),
    )


def tags_for(conn: sqlite3.Connection, *, item_type: ItemType, item_id: int) -> list[Tag]:
    rows = conn.execute(
        """
        SELECT tag.* FROM tag
        JOIN item_tag ON item_tag.tag_id = tag.id
        WHERE item_tag.item_type = ? AND item_tag.item_id = ?
        ORDER BY tag.facet, tag.value
        """,
        (item_type, item_id),
    ).fetchall()
    return [_tag(r) for r in rows]


def items_with_tag(
    conn: sqlite3.Connection, *, tag_id: int, item_type: ItemType | None = None
) -> list[tuple[ItemType, int]]:
    if item_type is None:
        rows = conn.execute(
            "SELECT item_type, item_id FROM item_tag WHERE tag_id = ?", (tag_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT item_type, item_id FROM item_tag WHERE tag_id = ? AND item_type = ?",
            (tag_id, item_type),
        ).fetchall()
    return [(r["item_type"], r["item_id"]) for r in rows]


# ─── joined views ─────────────────────────────────────────────────────


def bullets_with_tags(
    conn: sqlite3.Connection, experience_id: int | None = None
) -> list[TaggedItem]:
    bullets = list_bullets(conn, experience_id)
    return [
        TaggedItem(kind="bullet", item=b, tags=tags_for(conn, item_type="bullet", item_id=b.id))
        for b in bullets
    ]


def projects_with_tags(conn: sqlite3.Connection) -> list[TaggedItem]:
    return [
        TaggedItem(kind="project", item=p, tags=tags_for(conn, item_type="project", item_id=p.id))
        for p in list_projects(conn)
    ]


def skills_with_tags(conn: sqlite3.Connection) -> list[TaggedItem]:
    return [
        TaggedItem(kind="skill", item=s, tags=tags_for(conn, item_type="skill", item_id=s.id))
        for s in list_skills(conn)
    ]


def summaries_with_tags(conn: sqlite3.Connection) -> list[TaggedItem]:
    return [
        TaggedItem(
            kind="summary_variant",
            item=s,
            tags=tags_for(conn, item_type="summary_variant", item_id=s.id),
        )
        for s in list_summaries(conn)
    ]


# ─── verified facts (grounding payload for BYOK prose) ─────────────────


def verified_facts(conn: sqlite3.Connection, *, verified: bool = True) -> dict[str, Any]:
    """Structured factual grounding for prose generation.

    When ``verified`` is True (the default, and the only honest mode for BYOK),
    only verified bullets and projects are returned -- this is the real
    anti-fabrication lever: the browser client is fed verified facts, never
    invented ones. Bullets carry their experience context and a stable id so
    a per-paragraph provenance pill can be shown *only where a real fact link
    exists*. Skills are the user's own explicit claims; they carry no
    verification gate, so they are always included and labelled as such.
    """
    experiences: list[dict[str, Any]] = []
    for e in list_experiences(conn):
        bullets = list_bullets(conn, e.id)
        if verified:
            bullets = [b for b in bullets if b.facts_verified]
        if not bullets:
            continue
        experiences.append(
            {
                "company": e.company,
                "role": e.role,
                "start_date": e.start_date,
                "end_date": e.end_date,
                "location": e.location,
                "bullets": [
                    {"id": b.id, "text": b.text, "has_metric": b.has_metric} for b in bullets
                ],
            }
        )

    projects = list_projects(conn)
    if verified:
        projects = [p for p in projects if p.facts_verified]

    return {
        "verified_only": verified,
        "experiences": experiences,
        "projects": [
            {"id": p.id, "name": p.name, "text": p.text, "url": p.url} for p in projects
        ],
        "skills": [{"name": s.name, "category": s.category} for s in list_skills(conn)],
    }
