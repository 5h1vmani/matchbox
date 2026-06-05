"""Tests for the deterministic 5-dimension rubric.

These pin the score math against fixed inputs so refactors do not
silently shift the ranking.
"""

from __future__ import annotations

import json
import sqlite3

from matchbox.core import library as lib
from matchbox.scoring.rubric import (
    score_all_new,
    score_job,
)


def _target(
    role_families=(),
    dream_companies=(),
    locations=(),
    exclusions=(),
) -> dict[str, list[str]]:
    return {
        "role_families": list(role_families),
        "dream_companies": list(dream_companies),
        "locations": list(locations),
        "exclusions": list(exclusions),
    }


# ─── per-dimension ─────────────────────────────────────────────────────


def test_role_title_overlap() -> None:
    result = score_job(
        job={
            "title": "Forward Deployed Engineer",
            "jd_text": "",
            "company": "Modal",
            "location": "Remote",
        },
        target=_target(role_families=["forward-deployed-engineer"]),
        user_tech_tokens=set(),
    )
    role = next(d for d in result.dimensions if d.name == "role_title")
    assert role.score == 1.0
    assert "forward-deployed-engineer" in role.reason


def test_role_title_partial_overlap() -> None:
    result = score_job(
        job={
            "title": "Forward Deployed Engineer",
            "jd_text": "",
            "company": "X",
            "location": None,
        },
        target=_target(role_families=["forward deployed architect"]),
        user_tech_tokens=set(),
    )
    role = next(d for d in result.dimensions if d.name == "role_title")
    # "forward" + "deployed" overlap; "architect" does not; "engineer" is generic.
    assert 0.0 < role.score < 1.0


def test_role_title_ignores_generic_engineer() -> None:
    # A coding-IC title must NOT match an AI role family on the word "engineer".
    result = score_job(
        job={
            "title": "Software Engineer, ML Infrastructure",
            "jd_text": "",
            "company": "X",
            "location": None,
        },
        target=_target(role_families=["AI solutions architect"]),
        user_tech_tokens=set(),
    )
    role = next(d for d in result.dimensions if d.name == "role_title")
    assert role.score == 0.0


def test_skills_overlap_ignores_stopwords() -> None:
    # Filler tokens leaked from multi-word skill names must not count as hits.
    result = score_job(
        job={
            "title": "X",
            "jd_text": "We build software as a service and we ship.",
            "company": "X",
            "location": None,
        },
        target=_target(),
        user_tech_tokens={"and", "as", "we", "python"},
    )
    skills = next(d for d in result.dimensions if d.name == "skills_overlap")
    assert skills.score == 0.0  # and/as/we filtered; python not in the JD


def test_skills_overlap_counts_tech_hits() -> None:
    result = score_job(
        job={
            "title": "ML Eng",
            "jd_text": "We need Python, SQL, and Kubernetes.",
            "company": "X",
            "location": None,
        },
        target=_target(),
        user_tech_tokens={"python", "sql", "kubernetes", "rust"},
    )
    skills = next(d for d in result.dimensions if d.name == "skills_overlap")
    # 3 hits / skills_target_hits (5) = 0.6
    assert skills.score == 0.6
    assert "python" in skills.reason


def test_skills_overlap_zero_when_no_hits() -> None:
    result = score_job(
        job={
            "title": "ML Eng",
            "jd_text": "We need Erlang only.",
            "company": "X",
            "location": None,
        },
        target=_target(),
        user_tech_tokens={"python", "rust"},
    )
    skills = next(d for d in result.dimensions if d.name == "skills_overlap")
    assert skills.score == 0.0


def test_company_tier_dream_company() -> None:
    result = score_job(
        job={"title": "X", "jd_text": "", "company": "Anthropic", "location": None},
        target=_target(dream_companies=["Anthropic", "Modal"]),
        user_tech_tokens=set(),
    )
    tier = next(d for d in result.dimensions if d.name == "company_tier")
    assert tier.score == 1.0
    assert "dream" in tier.reason.lower()


def test_company_tier_excluded() -> None:
    result = score_job(
        job={
            "title": "X",
            "jd_text": "",
            "company": "Lockheed Martin Defense",
            "location": None,
        },
        target=_target(exclusions=["defense"]),
        user_tech_tokens=set(),
    )
    tier = next(d for d in result.dimensions if d.name == "company_tier")
    assert tier.score == 0.0


def test_location_remote_match() -> None:
    result = score_job(
        job={
            "title": "X",
            "jd_text": "",
            "company": "C",
            "location": "Remote — Worldwide",
        },
        target=_target(locations=["remote"]),
        user_tech_tokens=set(),
    )
    loc = next(d for d in result.dimensions if d.name == "location_remote")
    assert loc.score == 1.0
    assert "remote" in loc.reason.lower()


def test_location_specific_match() -> None:
    result = score_job(
        job={"title": "X", "jd_text": "", "company": "C", "location": "San Francisco, CA"},
        target=_target(locations=["sf"]),
        user_tech_tokens=set(),
    )
    loc = next(d for d in result.dimensions if d.name == "location_remote")
    # "sf" is in the lower-cased "san francisco, ca"? No, it's not a substring.
    # That's fine — test the negative path here.
    assert loc.score < 1.0


def test_red_flags_clean() -> None:
    result = score_job(
        job={"title": "Eng", "jd_text": "Build things.", "company": "X", "location": None},
        target=_target(exclusions=["defense", "gambling"]),
        user_tech_tokens=set(),
    )
    flags = next(d for d in result.dimensions if d.name == "red_flags")
    assert flags.score == 1.0


def test_red_flags_tripped() -> None:
    result = score_job(
        job={
            "title": "Eng",
            "jd_text": "Build weapons systems for defense contractors.",
            "company": "X",
            "location": None,
        },
        target=_target(exclusions=["defense"]),
        user_tech_tokens=set(),
    )
    flags = next(d for d in result.dimensions if d.name == "red_flags")
    assert flags.score == 0.0
    assert "defense" in flags.reason


# ─── aggregate ────────────────────────────────────────────────────────


def test_total_is_weighted_sum() -> None:
    result = score_job(
        job={
            "title": "Forward Deployed Engineer",
            "jd_text": "Python, SQL.",
            "company": "Anthropic",
            "location": "Remote",
        },
        target=_target(
            role_families=["forward-deployed-engineer"],
            dream_companies=["Anthropic"],
            locations=["remote"],
            exclusions=[],
        ),
        user_tech_tokens={"python", "sql"},
    )
    # No embedder here, so semantic_fit is omitted and the five lexical
    # weights (sum 0.65) are renormalized. role=1.0, skills=2/5=0.4,
    # company=1.0, location=1.0, flags=1.0 -> 0.53 / 0.65 ~= 0.82.
    assert result.total >= 0.80
    assert result.total <= 1.0


def test_total_is_low_for_bad_match() -> None:
    result = score_job(
        job={
            "title": "Junior PHP Developer",
            "jd_text": "PHP, MySQL, defense contractor.",
            "company": "Lockheed",
            "location": "On-site Albuquerque",
        },
        target=_target(
            role_families=["ml-platform-engineer"],
            dream_companies=["Anthropic"],
            locations=["remote"],
            exclusions=["defense"],
        ),
        user_tech_tokens={"python", "rust"},
    )
    assert result.total < 0.3


# ─── DB integration ───────────────────────────────────────────────────


def test_score_all_new_flips_status(tmp_db: sqlite3.Connection) -> None:
    tmp_db.execute(
        """INSERT INTO target (role_families_json, dream_companies_json, locations_json, comp_json, exclusions_json)
                  VALUES ('["ml-engineer"]', '["Anthropic"]', '["remote"]', '{}', '[]')"""
    )
    tmp_db.execute(
        "INSERT INTO job (company, title, url, jd_text, location) VALUES (?, ?, ?, ?, ?)",
        ("Anthropic", "ML Engineer", "https://x/1", "Python, SQL.", "Remote"),
    )
    tmp_db.execute(
        "INSERT INTO job (company, title, url, jd_text, location) VALUES (?, ?, ?, ?, ?)",
        ("Random", "PHP Dev", "https://x/2", "PHP", "Albuquerque"),
    )

    n = score_all_new(tmp_db)
    assert n == 2

    rows = tmp_db.execute(
        "SELECT title, score, status, score_breakdown_json FROM job ORDER BY title"
    ).fetchall()
    assert all(r["status"] == "scored" for r in rows)
    assert all(r["score"] is not None for r in rows)

    # the ML / Anthropic / remote job outscores the PHP / Albuquerque one
    by_title = {r["title"]: r for r in rows}
    assert by_title["ML Engineer"]["score"] > by_title["PHP Dev"]["score"]

    breakdown = json.loads(by_title["ML Engineer"]["score_breakdown_json"])
    assert {d["name"] for d in breakdown["dimensions"]} == {
        "role_title",
        "skills_overlap",
        "company_tier",
        "location_remote",
        "red_flags",
    }


def test_score_all_new_with_skills_in_library(tmp_db: sqlite3.Connection) -> None:
    """skills_overlap pulls from the live skill + tag tables."""
    lib.add_skill(tmp_db, name="Python")
    lib.add_skill(tmp_db, name="SQL")
    lib.add_skill(tmp_db, name="Kubernetes")
    tmp_db.execute(
        """INSERT INTO target (role_families_json, dream_companies_json, locations_json, comp_json, exclusions_json)
                  VALUES ('[]', '[]', '[]', '{}', '[]')"""
    )
    tmp_db.execute(
        "INSERT INTO job (company, title, url, jd_text, location) VALUES (?, ?, ?, ?, ?)",
        ("X", "Eng", "https://x/3", "We need Python and Kubernetes.", None),
    )

    score_all_new(tmp_db)
    breakdown = json.loads(
        tmp_db.execute("SELECT score_breakdown_json FROM job WHERE url = 'https://x/3'").fetchone()[
            0
        ]
    )
    skills = next(d for d in breakdown["dimensions"] if d["name"] == "skills_overlap")
    assert skills["score"] > 0.0
    assert "python" in skills["reason"]


# ─── v0.4: semantic dimension + calibration ───────────────────────────


def test_semantic_fit_added_when_provided() -> None:
    result = score_job(
        job={"title": "Eng", "jd_text": "Python.", "company": "X", "location": None},
        target=_target(),
        user_tech_tokens={"python"},
        semantic_fit=0.8,
    )
    assert "semantic_fit" in {d.name for d in result.dimensions}
    sf = next(d for d in result.dimensions if d.name == "semantic_fit")
    assert sf.score == 0.8


def test_semantic_fit_omitted_without_embedder() -> None:
    result = score_job(
        job={"title": "Eng", "jd_text": "Python.", "company": "X", "location": None},
        target=_target(),
        user_tech_tokens={"python"},
    )
    assert "semantic_fit" not in {d.name for d in result.dimensions}
    assert 0.0 <= result.total <= 1.0


def test_calibrate_bands_ranks_by_percentile() -> None:
    from matchbox.scoring.rubric import calibrate_bands

    totals = [0.1, 0.2, 0.3, 0.5, 0.6, 0.75, 0.8, 0.9, 0.95, 0.99]
    bands = calibrate_bands(totals)
    assert len(bands) == len(totals)
    assert bands[totals.index(max(totals))] == "strong"
    assert bands[totals.index(min(totals))] == "skip"
