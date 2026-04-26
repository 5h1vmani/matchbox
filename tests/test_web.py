"""Web layer tests — route smoke tests, security guards, filter parsing.

Uses the demo profile (committed). Tests run against a freshly-seeded DB so
they're deterministic regardless of local state.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from matchbox.web.app import create_app
from matchbox.web.config import Settings
from matchbox.web.demo import seed_demo_profile
from matchbox.web.routes.jobs import parse_filters


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings.load()


@pytest.fixture(scope="module")
def seeded(settings: Settings) -> int:
    """Force-seed the demo profile so tests have data to query."""
    db_path = settings.profile_dir("demo") / "db.sqlite"
    if db_path.exists():
        db_path.unlink()
    return seed_demo_profile(settings, count=30, force=True)


@pytest.fixture()
def client(seeded: int) -> TestClient:
    return TestClient(create_app())


# ──────────────────────────────────────────────
# Smoke
# ──────────────────────────────────────────────


class TestRoutes:
    def test_root_redirects_to_inbox(self, client: TestClient) -> None:
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 302
        assert "/inbox" in (r.headers.get("location") or "")

    def test_healthz(self, client: TestClient) -> None:
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_welcome_renders(self, client: TestClient) -> None:
        r = client.get("/system/welcome")
        assert r.status_code == 200
        assert "Welcome to Matchbox" in r.text

    def test_inbox_renders_with_jobs(self, client: TestClient) -> None:
        r = client.get("/p/demo/inbox")
        assert r.status_code == 200
        assert "Inbox" in r.text or "shown" in r.text
        # Demo seed inserts 30 jobs.
        assert "data-job-id" in r.text

    def test_rows_partial_no_shell(self, client: TestClient) -> None:
        r = client.get("/p/demo/jobs")
        assert r.status_code == 200
        # Partial — should not include the full HTML shell.
        assert "<html" not in r.text.lower()
        assert "data-job-id" in r.text

    def test_insights_renders(self, client: TestClient) -> None:
        r = client.get("/p/demo/insights")
        assert r.status_code == 200
        assert "Funnel" in r.text
        assert "Cost" in r.text

    def test_profile_renders(self, client: TestClient) -> None:
        r = client.get("/p/demo/profile")
        assert r.status_code == 200
        assert "scoring weights" in r.text.lower()

    def test_settings_renders(self, client: TestClient) -> None:
        r = client.get("/p/demo/settings")
        assert r.status_code == 200
        assert "Anthropic API key" in r.text


# ──────────────────────────────────────────────
# Per-job HTMX endpoints
# ──────────────────────────────────────────────


def _first_job_id(client: TestClient) -> int:
    import re

    r = client.get("/p/demo/jobs")
    m = re.search(r'data-job-id="(\d+)"', r.text)
    assert m is not None, "expected at least one job in seeded demo"
    return int(m.group(1))


class TestJobActions:
    def test_star_toggles_and_returns_row(self, client: TestClient) -> None:
        jid = _first_job_id(client)
        r1 = client.post(f"/p/demo/jobs/{jid}/star")
        assert r1.status_code == 200
        assert f"row-{jid}" in r1.text

    def test_detail_renders(self, client: TestClient) -> None:
        jid = _first_job_id(client)
        r = client.get(f"/p/demo/jobs/{jid}/detail")
        assert r.status_code == 200
        assert "Score" in r.text
        assert "Log outcome" in r.text

    def test_change_state(self, client: TestClient) -> None:
        jid = _first_job_id(client)
        r = client.post(f"/p/demo/jobs/{jid}/state", data={"new_state": "queued_for_tailor"})
        assert r.status_code == 200
        assert "queued for tailor" in r.text or "queued_for_tailor" in r.text

    def test_invalid_state_rejected(self, client: TestClient) -> None:
        jid = _first_job_id(client)
        r = client.post(f"/p/demo/jobs/{jid}/state", data={"new_state": "bogus"})
        assert r.status_code == 400

    def test_log_response(self, client: TestClient) -> None:
        jid = _first_job_id(client)
        r = client.post(f"/p/demo/jobs/{jid}/response", data={"response_type": "interview"})
        assert r.status_code == 200

    def test_invalid_response_rejected(self, client: TestClient) -> None:
        jid = _first_job_id(client)
        r = client.post(f"/p/demo/jobs/{jid}/response", data={"response_type": "bogus"})
        assert r.status_code == 400

    def test_detail_404_for_unknown_job(self, client: TestClient) -> None:
        r = client.get("/p/demo/jobs/99999999/detail")
        assert r.status_code == 404


# ──────────────────────────────────────────────
# Security
# ──────────────────────────────────────────────


class TestSecurity:
    def test_invalid_profile_name_blocked_by_pattern(self, client: TestClient) -> None:
        # Path traversal attempt at the profile slug.
        r = client.get("/p/.../inbox")
        assert r.status_code == 422  # FastAPI path validator

    def test_unknown_profile_404(self, client: TestClient) -> None:
        r = client.get("/p/nosuchprofile/inbox")
        assert r.status_code == 404

    def test_path_traversal_in_filename_blocked(self, client: TestClient) -> None:
        # Even a valid profile + valid job_id can't traverse out.
        r = client.get("/p/demo/files/1/..%2F..%2Fpasswd")
        # Either 404 (FileResponse refused) or 422 (regex on filename).
        assert r.status_code in (404, 422)

    def test_filename_pattern_rejects_non_pdf(self, client: TestClient) -> None:
        r = client.get("/p/demo/files/1/profile.yaml")
        assert r.status_code == 422


# ──────────────────────────────────────────────
# Filter parsing
# ──────────────────────────────────────────────


class TestParseFilters:
    def test_empty_qs(self) -> None:
        f = parse_filters("")
        assert f["_states"] is None
        assert f["_min_score"] is None
        assert f["_order_key"] == "score"

    def test_dict_qs(self) -> None:
        f = parse_filters("state=applied&min_score=3.5&q=engineer&order=newest&starred=1")
        assert f["_states"] == ["applied"]
        assert f["_min_score"] == 3.5
        assert f["_role_search"] == "engineer"
        assert f["_starred"] is True
        assert f["_order_by"] == "discovered_date DESC"

    def test_invalid_state_dropped(self) -> None:
        f = parse_filters("state=applied&state=not_a_state")
        assert f["_states"] == ["applied"]

    def test_invalid_order_falls_back(self) -> None:
        f = parse_filters("order=evil")
        assert f["_order_key"] == "evil"  # echoed for UI
        assert f["_order_by"] == "total_score DESC"  # but routed to safe default


# ──────────────────────────────────────────────
# Demo seed idempotency
# ──────────────────────────────────────────────


class TestDemoSeed:
    def test_seed_inserts_requested_count(self, settings: Settings) -> None:
        db_path = settings.profile_dir("demo") / "db.sqlite"
        if db_path.exists():
            db_path.unlink()
        n = seed_demo_profile(settings, count=12, force=True)
        assert n == 12

    def test_seed_skips_when_populated(self, settings: Settings) -> None:
        # The previous test left rows; calling without force must skip silently.
        n = seed_demo_profile(settings, count=12, force=False)
        assert n == 0
