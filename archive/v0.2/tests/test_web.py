"""Web layer tests — route smoke tests, security guards, filter parsing.

Uses the demo profile (committed). Tests run against a freshly-seeded DB so
they're deterministic regardless of local state.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from matchbox.core.schema import Job
from matchbox.web.app import create_app
from matchbox.web.config import Settings
from matchbox.web.demo import seed_demo_profile
from matchbox.web.profile_view import preview_rescore, update_weights
from matchbox.web.routes.jobs import parse_filters
from matchbox.web.tailor_view import alternative_tier, estimate


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

    def test_state_change_emits_toast_header(self, client: TestClient) -> None:
        jid = _first_job_id(client)
        r = client.post(f"/p/demo/jobs/{jid}/state", data={"new_state": "applied"})
        assert r.status_code == 200
        trigger = r.headers.get("HX-Trigger")
        assert trigger and "matchbox:toast" in trigger
        assert "log when you hear back" in trigger.lower()

    def test_destructive_state_offers_undo(self, client: TestClient) -> None:
        jid = _first_job_id(client)
        r = client.post(
            f"/p/demo/jobs/{jid}/state",
            data={"new_state": "discarded", "prev_state": "evaluated"},
        )
        assert r.status_code == 200
        trigger = r.headers.get("HX-Trigger") or ""
        assert "undo" in trigger.lower()
        assert "/state" in trigger
        assert "evaluated" in trigger

    def test_jd_full_partial(self, client: TestClient) -> None:
        jid = _first_job_id(client)
        r = client.get(f"/p/demo/jobs/{jid}/jd")
        assert r.status_code == 200
        # No <html> shell — pure partial.
        assert "<html" not in r.text.lower()

    def test_responses_partial(self, client: TestClient) -> None:
        jid = _first_job_id(client)
        r = client.get(f"/p/demo/jobs/{jid}/responses")
        assert r.status_code == 200
        assert "<html" not in r.text.lower()


# ──────────────────────────────────────────────
# Security
# ──────────────────────────────────────────────


class TestAccessibility:
    """Lightweight a11y smoke checks. Catches regressions in markup that
    the focus-trap and screen-reader story depend on."""

    def test_skip_link_present(self, client: TestClient) -> None:
        r = client.get("/p/demo/inbox")
        assert r.status_code == 200
        assert "#main-content" in r.text
        assert "Skip to main content" in r.text

    def test_main_landmark_present(self, client: TestClient) -> None:
        r = client.get("/p/demo/inbox")
        assert 'id="main-content"' in r.text
        assert 'role="main"' in r.text

    def test_palette_has_focus_trap(self, client: TestClient) -> None:
        r = client.get("/p/demo/inbox")
        assert "data-focus-trap" in r.text  # at least the palette + help modals
        assert 'role="dialog"' in r.text
        assert 'aria-modal="true"' in r.text

    def test_bulk_tailor_progress_has_focus_trap(self, client: TestClient) -> None:
        from matchbox.core import db
        from matchbox.web import tasks

        # Render the progress modal directly via an in-memory task so we
        # don't need to actually run the LLM.
        ids = [j.id for j in db.list_jobs("demo", limit=1)]
        if not ids:
            pytest.skip("no jobs seeded")
        # Manually construct a Task and request the polling endpoint.
        t = tasks.create("bulk_tailor", [tasks.TaskItem(label="X — Y")])
        try:
            r = client.get(f"/p/demo/bulk/tailor/{t.id}")
            assert r.status_code == 200
            assert "data-focus-trap" in r.text
            assert 'role="dialog"' in r.text
        finally:
            tasks._TASKS.pop(t.id, None)


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
        assert f["states"] is None
        assert f["min_score"] is None
        assert f["order_key"] == "score"

    def test_dict_qs(self) -> None:
        f = parse_filters("state=applied&min_score=3.5&q=engineer&order=newest&starred=1")
        assert f["states"] == ["applied"]
        assert f["min_score"] == 3.5
        assert f["role_search"] == "engineer"
        assert f["starred"] is True
        assert f["order_by"] == "discovered_date DESC"

    def test_invalid_state_dropped(self) -> None:
        f = parse_filters("state=applied&state=not_a_state")
        assert f["states"] == ["applied"]

    def test_invalid_order_falls_back(self) -> None:
        f = parse_filters("order=evil")
        assert f["order_key"] == "evil"  # echoed for UI
        assert f["order_by"] == "total_score DESC"  # but routed to safe default


# ──────────────────────────────────────────────
# Tailor — cost estimate + preview routes (no LLM call)
# ──────────────────────────────────────────────


def _job_with_tier(tier: str) -> Job:
    return Job(
        profile_name="demo",
        company="X",
        role="Y",
        url="https://example.com/x",
        tier=tier,
    )


class TestTailorEstimate:
    def test_bespoke_requires_llm_and_confirmation(self) -> None:
        e = estimate(_job_with_tier("bespoke"))
        assert e.requires_llm is True
        assert e.high_usd >= 10.0
        assert e.needs_confirmation(threshold_usd=1.0) is True

    def test_template_under_threshold(self) -> None:
        e = estimate(_job_with_tier("template"))
        assert e.requires_llm is True
        assert e.high_usd < 1.0
        assert e.needs_confirmation(threshold_usd=1.0) is False

    def test_canonical_is_free(self) -> None:
        e = estimate(_job_with_tier("canonical"))
        assert e.requires_llm is False
        assert e.midpoint_usd == 0.0

    def test_alternative_tier_chain(self) -> None:
        assert alternative_tier("bespoke") == "template"
        assert alternative_tier("template") == "canonical"
        assert alternative_tier("canonical") == "skip"
        assert alternative_tier("skip") is None
        assert alternative_tier("invalid") is None

    def test_tailor_preview_renders(self, client: TestClient) -> None:
        jid = _first_job_id(client)
        r = client.get(f"/p/demo/jobs/{jid}/tailor/preview")
        assert r.status_code == 200
        assert "tailor" in r.text.lower()

    def test_expensive_tailor_requires_confirmation(self, client: TestClient) -> None:
        from matchbox.core import db

        bespoke = next(
            (j for j in db.list_jobs("demo", limit=500) if j.tier == "bespoke"),
            None,
        )
        if bespoke is None:
            pytest.skip("no bespoke-tier job in seed")
        # POST without confirmed=1 must be rejected with 412 Precondition Failed.
        r = client.post(f"/p/demo/jobs/{bespoke.id}/tailor")
        assert r.status_code == 412


# ──────────────────────────────────────────────
# Demo seed idempotency
# ──────────────────────────────────────────────


class TestProfileEditor:
    @pytest.fixture()
    def demo_yaml_backup(self, settings: Settings) -> str:
        """Snapshot demo profile.yaml so write tests can roll back."""
        path = settings.profile_dir("demo") / "profile.yaml"
        original = path.read_text(encoding="utf-8")
        yield original
        path.write_text(original, encoding="utf-8")

    def test_update_weights_writes_atomically(
        self, settings: Settings, demo_yaml_backup: str
    ) -> None:
        result = update_weights(
            settings,
            "demo",
            {"cv_match_weight": 0.42, "comp_weight": 0.13},
        )
        assert result["cv_match_weight"] == 0.42
        assert result["comp_weight"] == 0.13
        # Other fields preserved.
        assert "company_mission_fit_weight" in result
        # File was actually rewritten.
        text = (settings.profile_dir("demo") / "profile.yaml").read_text(encoding="utf-8")
        assert "0.42" in text

    def test_update_weights_migrates_legacy_aliases(
        self, settings: Settings, demo_yaml_backup: str
    ) -> None:
        # Hand-write a profile.yaml with the OLD weight names to simulate
        # an existing real-user profile, then save canonical values and
        # confirm the legacy keys are gone.
        path = settings.profile_dir("demo") / "profile.yaml"
        legacy_text = (
            path.read_text(encoding="utf-8")
            .replace("comp_weight: 0.20", "tech_stack_weight: 0.20")
            .replace("cultural_weight: 0.10", "seniority_weight: 0.10")
            .replace("red_flags_weight: 0.15", "location_remote_weight: 0.15")
        )
        path.write_text(legacy_text, encoding="utf-8")

        update_weights(settings, "demo", {"comp_weight": 0.30})
        text = path.read_text(encoding="utf-8")
        assert "tech_stack_weight" not in text
        assert "seniority_weight" not in text
        assert "location_remote_weight" not in text
        assert "comp_weight: 0.3" in text
        assert "cultural_weight" in text  # migrated
        assert "red_flags_weight" in text  # migrated

    def test_update_weights_rejects_unknown_field(
        self, settings: Settings, demo_yaml_backup: str
    ) -> None:
        with pytest.raises(ValueError, match="unknown weight field"):
            update_weights(settings, "demo", {"evil_weight": 0.5})

    def test_update_weights_rejects_out_of_range(
        self, settings: Settings, demo_yaml_backup: str
    ) -> None:
        with pytest.raises(ValueError, match="out of range"):
            update_weights(settings, "demo", {"cv_match_weight": 1.5})
        with pytest.raises(ValueError, match="out of range"):
            update_weights(settings, "demo", {"cv_match_weight": -0.1})

    def test_save_endpoint_persists(
        self, client: TestClient, settings: Settings, demo_yaml_backup: str
    ) -> None:
        r = client.post(
            "/p/demo/profile/save",
            data={
                "cv_match_weight": 0.30,
                "company_mission_fit_weight": 0.20,
                "role_mission_fit_weight": 0.10,
                "comp_weight": 0.20,
                "cultural_weight": 0.10,
                "red_flags_weight": 0.10,
            },
        )
        assert r.status_code == 200
        assert "Saved" in r.text
        text = (settings.profile_dir("demo") / "profile.yaml").read_text(encoding="utf-8")
        assert "0.3" in text  # cv_match_weight written

    def test_save_endpoint_rejects_out_of_range(
        self, client: TestClient, demo_yaml_backup: str
    ) -> None:
        r = client.post(
            "/p/demo/profile/save",
            data={
                "cv_match_weight": 5.0,  # invalid
                "company_mission_fit_weight": 0.15,
                "role_mission_fit_weight": 0.15,
                "comp_weight": 0.20,
                "cultural_weight": 0.15,
                "red_flags_weight": 0.10,
            },
        )
        assert r.status_code == 400


class TestBulkTailor:
    def test_preview_requires_selection(self, client: TestClient) -> None:
        r = client.post("/p/demo/bulk/tailor/preview", data={})
        assert r.status_code == 400

    def test_preview_returns_modal(self, client: TestClient) -> None:
        from matchbox.core import db

        ids = [j.id for j in db.list_jobs("demo", limit=2)]
        r = client.post(
            "/p/demo/bulk/tailor/preview",
            data={"id": [str(i) for i in ids]},
        )
        assert r.status_code == 200
        assert "Bulk tailor" in r.text

    def test_execute_blocks_above_cap(self, client: TestClient) -> None:
        from matchbox.core import db

        ids = [j.id for j in db.list_jobs("demo", limit=6)]
        if len(ids) < 6:
            pytest.skip("seed has < 6 jobs")
        r = client.post(
            "/p/demo/bulk/tailor",
            data={"id": [str(i) for i in ids], "confirmed": "1"},
        )
        assert r.status_code == 400

    def test_execute_requires_confirmation_when_expensive(self, client: TestClient) -> None:
        from matchbox.core import db

        bespoke = [j for j in db.list_jobs("demo", limit=500) if j.tier == "bespoke"][:2]
        if len(bespoke) < 2:
            pytest.skip("seed has < 2 bespoke jobs")
        r = client.post(
            "/p/demo/bulk/tailor",
            data={"id": [str(j.id) for j in bespoke]},  # no confirmed=1
        )
        assert r.status_code == 412

    def test_status_404_for_unknown_task(self, client: TestClient) -> None:
        # The actual execute path requires LLM credentials; we only test the
        # status endpoint shape here.
        r = client.get("/p/demo/bulk/tailor/no_such_task")
        assert r.status_code == 404


class TestTaskTracker:
    """Pure-function tests for the in-process task tracker."""

    def test_create_and_get(self) -> None:
        from matchbox.web import tasks

        t = tasks.create("bulk_tailor", [tasks.TaskItem(label="x")])
        assert tasks.get(t.id) is t
        assert t.status == "pending"
        assert t.total == 1
        assert t.done_count == 0

    def test_update_item_and_set_status(self) -> None:
        from matchbox.web import tasks

        t = tasks.create("bulk_tailor", [tasks.TaskItem(label="a"), tasks.TaskItem(label="b")])
        tasks.update_item(t.id, 0, status="ok", detail="great")
        tasks.update_item(t.id, 1, status="failed", detail="boom")
        tasks.set_status(t.id, "done", summary={"total_cost": 0.5})
        assert t.done_count == 2
        assert t.is_terminal
        assert t.summary["total_cost"] == 0.5

    def test_cleanup_old_drops_terminal(self) -> None:
        from matchbox.web import tasks

        t = tasks.create("bulk_tailor", [])
        tasks.set_status(t.id, "done")
        # Force-age the task by rewinding completed_at.
        assert t.completed_at is not None
        t.completed_at -= 7200
        dropped = tasks.cleanup_old(max_age_seconds=3600)
        assert dropped >= 1
        assert tasks.get(t.id) is None


class TestPalette:
    def test_empty_query_returns_pages(self, client: TestClient) -> None:
        r = client.get("/p/demo/palette?q=")
        assert r.status_code == 200
        # Should at least show no-query message OR pages.
        assert "<html" not in r.text.lower()

    def test_query_returns_results(self, client: TestClient) -> None:
        r = client.get("/p/demo/palette?q=ins")
        assert r.status_code == 200
        # "ins" should match Insights page.
        assert "Insights" in r.text or "/insights" in r.text

    def test_job_search(self, client: TestClient) -> None:
        # Demo seed includes Stripe; query should surface it as a job result.
        r = client.get("/p/demo/palette?q=stripe")
        assert r.status_code == 200


class TestRescorePreview:
    def test_preview_returns_top_n_with_deltas(self, settings: Settings, seeded: int) -> None:
        from matchbox.core.schema import ScoringWeights

        # Use very different weights to force re-ordering.
        weights = ScoringWeights(
            cv_match_weight=1.0,
            company_mission_fit_weight=0.0,
            role_mission_fit_weight=0.0,
            comp_weight=0.0,
            cultural_weight=0.0,
            red_flags_weight=0.0,
        )
        result = preview_rescore("demo", weights, top_n=5)
        assert result.total_jobs > 0
        assert len(result.top) == 5
        # Each delta has consistent fields.
        for d in result.top:
            assert 0.0 <= d.new_total <= 5.0
            assert d.old_rank > 0
            assert d.new_rank > 0
            assert d.old_tier in {"bespoke", "template", "canonical", "skip"}

    def test_preview_endpoint_renders(self, client: TestClient) -> None:
        r = client.post(
            "/p/demo/profile/preview",
            data={
                "cv_match_weight": 0.30,
                "company_mission_fit_weight": 0.20,
                "role_mission_fit_weight": 0.10,
                "comp_weight": 0.20,
                "cultural_weight": 0.10,
                "red_flags_weight": 0.10,
            },
        )
        assert r.status_code == 200
        # Returns the preview partial (no html shell).
        assert "<html" not in r.text.lower()
        assert "Re-scoring" in r.text or "scored jobs" in r.text


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
