"""Matchbox v0.2 Streamlit UI — pipeline dashboard.

Run:  streamlit run src/matchbox/ui/ui.py
      streamlit run src/matchbox/ui/ui.py -- --profile shiva
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import streamlit as st

# Allow running directly from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from matchbox.core import db
from matchbox.core.schema import Job


# ──────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────

st.set_page_config(
    page_title="Matchbox",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

_STYLE = """
<style>
    .block-container { padding-top: 1.5rem; }
    .metric-container { border-left: 3px solid #4CAF50; padding-left: 0.75rem; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
</style>
"""
st.markdown(_STYLE, unsafe_allow_html=True)


# ──────────────────────────────────────────────
# Sidebar — profile selector + navigation
# ──────────────────────────────────────────────


def _available_profiles() -> list[str]:
    root = Path(__file__).resolve().parents[4]
    people = root / "people"
    if not people.exists():
        return []
    return sorted(d.name for d in people.iterdir() if d.is_dir() and (d / "profile.yaml").exists())


with st.sidebar:
    st.title("🎯 Matchbox")
    profiles = _available_profiles()
    if not profiles:
        st.error("No profiles found under people/")
        st.stop()

    profile = st.selectbox("Profile", profiles, index=0)
    page = st.radio(
        "View",
        ["Pipeline", "Analytics", "Follow-ups", "Scan history"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("v0.2 — precision pipeline")


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

_STATE_COLORS = {
    "evaluated": "#888",
    "queued_for_tailor": "#9C27B0",
    "tailored": "#2196F3",
    "applied": "#FF9800",
    "responded": "#03A9F4",
    "interview": "#8BC34A",
    "offer": "#4CAF50",
    "rejected": "#F44336",
    "discarded": "#9E9E9E",
    "skip": "#616161",
    "cooling": "#795548",
}

_TIER_COLORS = {
    "bespoke": "🔴",
    "template": "🟡",
    "canonical": "🟢",
    "skip": "⚫",
}


def _score_bar(score: float | None) -> str:
    if score is None:
        return "—"
    filled = round((score / 5.0) * 10)
    return "█" * filled + "░" * (10 - filled) + f" {score:.1f}"


def _badge(state: str) -> str:
    color = _STATE_COLORS.get(state, "#888")
    return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:4px;font-size:0.75rem">{state}</span>'


# ──────────────────────────────────────────────
# Page: Pipeline
# ──────────────────────────────────────────────


def page_pipeline(profile: str) -> None:
    st.header("Pipeline")

    col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
    with col_f1:
        state_filter = st.multiselect(
            "State",
            options=sorted(_STATE_COLORS.keys()),
            default=[],
            placeholder="All states",
        )
    with col_f2:
        tier_filter = st.multiselect(
            "Tier",
            options=["bespoke", "template", "canonical", "skip"],
            default=[],
            placeholder="All tiers",
        )
    with col_f3:
        min_score = st.number_input("Min score", min_value=0.0, max_value=5.0, value=0.0, step=0.5)
    with col_f4:
        starred_only = st.checkbox("Starred only")
    with col_f5:
        role_search = st.text_input("Role search", placeholder="e.g. engineer")

    jobs = db.list_jobs(
        profile,
        state=state_filter or None,
        min_score=min_score if min_score > 0 else None,
        is_starred=True if starred_only else None,
        role_search=role_search or None,
        limit=500,
        order_by="total_score DESC",
    )

    if tier_filter:
        jobs = [j for j in jobs if j.tier in tier_filter]

    st.caption(f"{len(jobs)} job(s)")

    if not jobs:
        st.info("No jobs match the current filters.")
        return

    for job in jobs:
        _render_job_row(profile, job)


def _render_job_row(profile: str, job: Job) -> None:
    tier_icon = _TIER_COLORS.get(job.tier or "skip", "⚫")
    star = "⭐" if job.is_starred else ""
    with st.expander(
        f"{tier_icon} {star} **{job.company}** — {job.role}  "
        f"`{job.state}` · score {job.total_score or 0:.1f}",
        expanded=False,
    ):
        c1, c2, c3 = st.columns([2, 2, 3])
        with c1:
            st.markdown(f"**Location:** {job.location or '—'}")
            st.markdown(f"**ATS:** {job.ats_source or '—'}")
            st.markdown(f"**Tier:** {job.tier or '—'}")
            st.markdown(f"**Geo:** {job.mode or '—'}")
        with c2:
            st.markdown(f"**Dream tier:** {job.dream_tier or '—'}")
            st.markdown(f"**Applied:** {job.applied_date or '—'}")
            st.markdown(f"**Response:** {job.response_type or '—'} {job.response_date or ''}")
            if job.tailor_cost_usd:
                st.markdown(f"**Tailor cost:** ${job.tailor_cost_usd:.4f}")
        with c3:
            st.markdown("**Scores:**")
            st.code(
                f"cv_match     {job.cv_match_score or 0:.2f}\n"
                f"mission_fit  {job.company_mission_fit_score or 0:.2f}\n"
                f"role_fit     {job.role_mission_fit_score or 0:.2f}\n"
                f"comp         {job.comp_score or 0:.2f}\n"
                f"cultural     {job.cultural_score or 0:.2f}\n"
                f"red_flags    {job.red_flags_score or 0:.2f}\n"
                f"─────────────────────\n"
                f"total        {job.total_score or 0:.2f}",
                language=None,
            )

        btn_cols = st.columns(5)
        with btn_cols[0]:
            if job.url:
                st.link_button("Open JD", job.url, use_container_width=True)
        with btn_cols[1]:
            if st.button("⭐ Toggle star", key=f"star_{job.id}"):
                db.toggle_star(profile, job.id)  # type: ignore[arg-type]
                st.rerun()
        with btn_cols[2]:
            if job.state in ("tailored", "queued_for_tailor") and st.button(
                "Mark applied", key=f"apply_{job.id}"
            ):
                db.update_job_state(profile, job.id, "applied")  # type: ignore[arg-type]
                st.rerun()
        with btn_cols[3]:
            if job.cv_path and Path(job.cv_path).exists():
                with open(job.cv_path, "rb") as f:
                    st.download_button(
                        "Download CV", f, file_name=Path(job.cv_path).name, key=f"cv_{job.id}"
                    )
        with btn_cols[4]:
            if job.cover_path and Path(job.cover_path).exists():
                with open(job.cover_path, "rb") as f:
                    st.download_button(
                        "Download Cover",
                        f,
                        file_name=Path(job.cover_path).name,
                        key=f"cov_{job.id}",
                    )

        if job.user_notes:
            st.caption(f"Notes: {job.user_notes}")


# ──────────────────────────────────────────────
# Page: Analytics
# ──────────────────────────────────────────────


def page_analytics(profile: str) -> None:
    from matchbox.outcome.analytics import get_funnel, get_tier_cost_summary

    st.header("Analytics")
    funnel = get_funnel(profile)
    tier_costs = get_tier_cost_summary(profile)

    # Funnel metrics
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Evaluated", funnel["evaluated"])
    m2.metric("Applied", funnel["applied"], f"{funnel['applied_rate']}%")
    m3.metric("Responded", funnel["responded"], f"{funnel['response_rate']}%")
    m4.metric("Interview", funnel["interview"], f"{funnel['interview_rate']}%")
    m5.metric("Offer", funnel["offer"], f"{funnel['offer_rate']}%")

    st.divider()

    # Cost summary
    c1, c2, c3 = st.columns(3)
    c1.metric("Total cost", f"${funnel['total_cost_usd']:.2f}")
    c2.metric("Cost / application", f"${funnel['cost_per_application']:.2f}")
    c3.metric("Avg score", f"{funnel['avg_score']:.2f} / 5.00")

    # Tier breakdown
    if tier_costs:
        st.subheader("Cost by tier")
        import pandas as pd

        rows = [
            {"Tier": t, "Jobs": v["count"], "Total $": v["total_usd"], "Avg $": v["avg_usd"]}
            for t, v in sorted(tier_costs.items())
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Score distribution
    st.subheader("Score distribution")
    jobs = db.list_jobs(profile, limit=2000)
    scored = [j.total_score for j in jobs if j.total_score is not None]
    if scored:
        import pandas as pd

        st.bar_chart(pd.Series(scored).value_counts(bins=10).sort_index())
    else:
        st.info("No scored jobs yet.")

    # State breakdown
    st.subheader("Jobs by state")
    stats = db.get_stats(profile)
    state_data = {
        k.replace("count_", ""): v for k, v in stats.items() if k.startswith("count_") and v > 0
    }
    if state_data:
        import pandas as pd

        st.bar_chart(pd.Series(state_data).sort_values(ascending=False))


# ──────────────────────────────────────────────
# Page: Follow-ups
# ──────────────────────────────────────────────


def page_followups(profile: str) -> None:
    from matchbox.outcome.followup import get_followup_candidates

    st.header("Follow-ups")

    c1, c2 = st.columns(2)
    days_applied = c1.slider("Applied, no response after (days)", 5, 30, 10)
    days_responded = c2.slider("Responded, no interview after (days)", 3, 21, 7)

    candidates = get_followup_candidates(
        profile,
        days_since_applied=days_applied,
        days_since_response=days_responded,
    )

    if not candidates:
        st.success("No follow-up actions needed right now.")
        return

    st.warning(f"{len(candidates)} job(s) need attention")
    for row in candidates:
        with st.expander(f"**{row['company']}** — {row['role']} · {row['followup_reason']}"):
            st.markdown(f"State: `{row['state']}`  URL: {row.get('url', '—')}")
            if row.get("url"):
                st.link_button("Open JD", row["url"])


# ──────────────────────────────────────────────
# Page: Scan history
# ──────────────────────────────────────────────


def page_scan_history(profile: str) -> None:
    st.header("Scan history")
    runs = db.get_scan_history(profile, limit=50)

    if not runs:
        st.info("No scans recorded yet. Run: matchbox scan {profile}")
        return

    import pandas as pd

    rows = []
    for r in runs:
        rows.append(
            {
                "ID": r.id,
                "Started": r.started_at[:16] if r.started_at else "",
                "Mode": r.mode or "—",
                "Country": r.country or "all",
                "Status": r.status,
                "Raw": r.raw_candidates,
                "Survivors": r.filtered_survivors,
                "Scored": r.scored_count,
                "Skip": r.skip_count,
                "Trial": "✓" if r.is_trial else "",
                "Cost $": f"{r.cost_usd:.4f}",
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ──────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────

if page == "Pipeline":
    page_pipeline(profile)
elif page == "Analytics":
    page_analytics(profile)
elif page == "Follow-ups":
    page_followups(profile)
elif page == "Scan history":
    page_scan_history(profile)
