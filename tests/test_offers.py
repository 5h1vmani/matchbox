"""Tests for the offer module (Phase 5: Close).

Pattern mirrors tests/test_agent_tasks.py:
    conn = connect(tmp_path / "x.db"); migrate(conn)
"""

from __future__ import annotations

from pathlib import Path

from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.offers import repo
from matchbox.offers.benchmark import benchmark

# ── helpers ──────────────────────────────────────────────────────────────────

def _db(tmp_path: Path):  # noqa: ANN202 - test helper
    conn = connect(tmp_path / "offers_test.db")
    migrate(conn)
    return conn


_job_counter: list[int] = [0]


def _seed_job(conn, *, salary_min=None, salary_max=None, currency="USD", role_family=None) -> int:
    """Insert a minimal job row (all NOT NULL columns required) and return its id.

    A counter ensures unique URLs across multiple calls within a test.
    """
    _job_counter[0] += 1
    n = _job_counter[0]
    cur = conn.execute(
        "INSERT INTO job (company, title, url, jd_text, salary_min, salary_max, salary_currency, role_family) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"Acme Corp {n}",
            "Engineer",
            f"https://example.com/job/{n}",
            "Do stuff",
            salary_min,
            salary_max,
            currency,
            role_family,
        ),
    )
    return int(cur.lastrowid or 0)


def _seed_application(conn, job_id: int) -> int:
    """Insert a minimal application row and return its id."""
    cur = conn.execute(
        "INSERT INTO application (job_id, stage) VALUES (?, ?)",
        (job_id, "offer"),
    )
    return int(cur.lastrowid or 0)


# ── lifecycle tests ───────────────────────────────────────────────────────────

def test_create_list_set_status(tmp_path: Path) -> None:
    conn = _db(tmp_path)

    job_id = _seed_job(conn, salary_min=100_000, salary_max=130_000)
    app_id = _seed_application(conn, job_id)

    oid = repo.create(
        conn,
        app_id,
        base=120_000.0,
        bonus=10_000.0,
        equity="0.1%",
        currency="USD",
        location="Remote",
        notes="Good offer",
    )
    assert isinstance(oid, int) and oid > 0

    offers = repo.list_for_app(conn, app_id)
    assert len(offers) == 1
    o = offers[0]
    assert o["id"] == oid
    assert o["applicationId"] == app_id
    assert o["base"] == 120_000.0
    assert o["bonus"] == 10_000.0
    assert o["totalComp"] == 130_000.0
    assert o["equity"] == "0.1%"
    assert o["currency"] == "USD"
    assert o["status"] == "received"

    updated = repo.set_status(conn, oid, "accepted")
    assert updated is not None
    assert updated["status"] == "accepted"
    assert updated["id"] == oid

    conn.close()


def test_get_and_update(tmp_path: Path) -> None:
    conn = _db(tmp_path)

    job_id = _seed_job(conn)
    app_id = _seed_application(conn, job_id)
    oid = repo.create(conn, app_id, base=90_000.0)

    fetched = repo.get(conn, oid)
    assert fetched is not None
    assert fetched["base"] == 90_000.0
    assert fetched["totalComp"] == 90_000.0  # bonus is None so totalComp = base + 0

    patched = repo.update(conn, oid, bonus=5_000.0, notes="Counter offer")
    assert patched is not None
    assert patched["bonus"] == 5_000.0
    assert patched["totalComp"] == 95_000.0
    assert patched["notes"] == "Counter offer"

    conn.close()


def test_list_all(tmp_path: Path) -> None:
    conn = _db(tmp_path)

    job_id = _seed_job(conn)
    app1 = _seed_application(conn, job_id)
    app2 = _seed_application(conn, job_id)

    repo.create(conn, app1, base=100_000.0)
    repo.create(conn, app2, base=110_000.0)

    all_offers = repo.list_all(conn)
    assert len(all_offers) == 2

    conn.close()


def test_total_comp_none_when_base_none(tmp_path: Path) -> None:
    conn = _db(tmp_path)

    job_id = _seed_job(conn)
    app_id = _seed_application(conn, job_id)
    oid = repo.create(conn, app_id)  # no base

    o = repo.get(conn, oid)
    assert o is not None
    assert o["base"] is None
    assert o["totalComp"] is None

    conn.close()


def test_set_status_invalid_raises(tmp_path: Path) -> None:
    conn = _db(tmp_path)

    job_id = _seed_job(conn)
    app_id = _seed_application(conn, job_id)
    oid = repo.create(conn, app_id, base=80_000.0)

    import pytest
    with pytest.raises(ValueError, match="invalid status"):
        repo.set_status(conn, oid, "pending")  # not a valid offer status

    conn.close()


# ── benchmark: empty pool ─────────────────────────────────────────────────────

def test_benchmark_empty(tmp_path: Path) -> None:
    conn = _db(tmp_path)

    result = benchmark(conn, base=100_000.0)

    assert result["percentile"] is None
    assert result["confidence"] == "none"
    assert result["sampleSize"] == 0
    assert result["median"] is None

    conn.close()


def test_benchmark_no_salary_rows(tmp_path: Path) -> None:
    """Jobs exist but none have salary data — same as empty."""
    conn = _db(tmp_path)

    _seed_job(conn)  # no salary_min / salary_max

    result = benchmark(conn, base=100_000.0)

    assert result["percentile"] is None
    assert result["confidence"] == "none"
    assert result["sampleSize"] == 0

    conn.close()


# ── benchmark: seeded pool ────────────────────────────────────────────────────

def test_benchmark_with_jobs(tmp_path: Path) -> None:
    conn = _db(tmp_path)

    # Seed 10 jobs with salary_min required; vary the midpoints
    midpoints = [80_000, 90_000, 100_000, 110_000, 120_000,
                 130_000, 140_000, 150_000, 160_000, 170_000]
    for mid in midpoints:
        _seed_job(conn, salary_min=mid - 5_000, salary_max=mid + 5_000, currency="USD")

    # Base right at median (125_000 is between 120_000 and 130_000)
    result = benchmark(conn, base=125_000.0, currency="USD")

    assert result["sampleSize"] == 10
    assert result["confidence"] == "medium"
    assert isinstance(result["percentile"], int)
    assert 0 <= result["percentile"] <= 100
    assert result["median"] is not None
    assert result["currency"] == "USD"
    # v1.2: an honest interquartile range + a basis line drawn from the own pool.
    assert result["range"]["low"] < result["median"] < result["range"]["high"]
    assert "10 roles in your own pool" in result["basis"]
    assert "USD" in result["basis"]

    conn.close()


def test_benchmark_role_family_filter(tmp_path: Path) -> None:
    conn = _db(tmp_path)

    # 5 backend jobs + 3 frontend jobs
    for _ in range(5):
        _seed_job(conn, salary_min=100_000, salary_max=120_000, currency="USD", role_family="backend")
    for _ in range(3):
        _seed_job(conn, salary_min=90_000, salary_max=110_000, currency="USD", role_family="frontend")

    result = benchmark(conn, base=110_000.0, role_family="backend", currency="USD")
    assert result["sampleSize"] == 5
    assert result["confidence"] == "low"  # n < 8

    result_fe = benchmark(conn, base=100_000.0, role_family="frontend", currency="USD")
    assert result_fe["sampleSize"] == 3
    assert result_fe["confidence"] == "low"

    conn.close()


def test_benchmark_percentile_correctness(tmp_path: Path) -> None:
    """All midpoints below base -> percentile 100; all above -> percentile 0."""
    conn = _db(tmp_path)

    for mn in [50_000, 60_000, 70_000, 80_000, 90_000,
               95_000, 97_000, 98_000, 99_000]:
        _seed_job(conn, salary_min=mn, salary_max=mn + 2_000, currency="USD")

    # base above all midpoints
    high = benchmark(conn, base=200_000.0, currency="USD")
    assert high["percentile"] == 100

    # base below all midpoints
    low = benchmark(conn, base=10_000.0, currency="USD")
    assert low["percentile"] == 0

    conn.close()
