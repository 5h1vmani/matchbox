"""
matchbox/ui/ui.py — Streamlit UI for reviewing the Matchbox pipeline.

Run with:
    cd <repo root>
    python3 -m streamlit run matchbox/ui/ui.py --server.port 8501

The UI is read + state-update only. It NEVER invokes Claude or any scoring/
tailoring logic directly. When a user queues a job for tailoring, this file
writes to queue/tailor-queue.yml; the user then runs `/tailor --batch` (or
pastes matchbox/workflows/tailor.md into any Sonnet session).

Design principles
-----------------
- Single responsibility. Display + state transitions only.
- Least privilege. Imports db + ui_theme, nothing else from matchbox.
- DRY. Filter options from db.get_distinct_values, visual tokens from ui_theme.
- SSOT. Every source-of-truth read is one function call.

UI model
--------
One unified view. Each row is a bordered card. Cards render a compact
summary by default; clicking "Details" expands full details in-place.
By default the list is deduped to one card per company (plus a sibling
expander for the rest). A toggle at the top lets you unlock dedup and
see every matching row.

No emojis. Lucide SVG icons everywhere visuals are possible. Button
labels are plain English so a new user can understand them cold.
"""

from __future__ import annotations

import csv
import io
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Ensure matchbox is on the path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import streamlit as st
import yaml

from matchbox.shared import db
from matchbox.ui import ui_theme

# ============================================================
# Page config + theme injection (must happen first)
# ============================================================

st.set_page_config(
    page_title="Matchbox Pipeline",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)
ui_theme.inject()

PROFILES_FILE = REPO_ROOT / "matchbox" / "profiles.yml"


# ============================================================
# Profile + config readers
# ============================================================

def load_profiles() -> dict:
    """Return profiles dict from matchbox/profiles.yml."""
    if not PROFILES_FILE.exists():
        return {"profiles": {"shiva": {"full_name": "Shiva Padakanti", "enabled": True}}, "default": "shiva"}
    with PROFILES_FILE.open() as f:
        return yaml.safe_load(f)


@st.cache_data(ttl=30)
def load_profile_settings(profile: str) -> dict:
    """Read atma/people/{profile}/wiki/profile.yml. Cached 30s."""
    path = REPO_ROOT / "atma" / "people" / profile / "wiki" / "profile.yml"
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def company_tier(company: str, dream_tiers: dict) -> str | None:
    """Return tier key or None. Case-insensitive match."""
    if not dream_tiers or not company:
        return None
    needle = company.strip().lower()
    for tier_key in ("tier_1_dream", "tier_2_target", "tier_3_watchlist"):
        names = dream_tiers.get(tier_key) or []
        for n in names:
            if isinstance(n, str) and n.strip().lower() == needle:
                return tier_key
    return None


def role_family_rank(role_family: str | None, prefs: dict | None) -> int:
    """Lower rank = higher preference. Unmatched sorts last."""
    if not role_family or not prefs:
        return 9999
    for rank, fam in sorted(prefs.items()):
        try:
            if fam == role_family:
                return int(rank)
        except (TypeError, ValueError):
            continue
    return 9999


# ============================================================
# Tailor queue helpers (SSOT: queue/tailor-queue.yml)
# ============================================================

def queue_path(profile: str) -> Path:
    return REPO_ROOT / "matchbox" / "people" / profile / "queue" / "tailor-queue.yml"


def load_queue(profile: str) -> list[dict]:
    p = queue_path(profile)
    if not p.exists():
        return []
    with p.open() as f:
        data = yaml.safe_load(f) or {}
    return data.get("queue", [])


def save_queue(profile: str, queue: list[dict]) -> None:
    p = queue_path(profile)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        yaml.safe_dump({
            "queue": queue,
            "last_updated": datetime.now().isoformat(timespec="seconds"),
        }, f, default_flow_style=False, sort_keys=False)


def queue_count_for_company(profile: str, company: str) -> int:
    """How many jobs from `company` are already queued for tailor?"""
    company_lower = company.strip().lower()
    queue = load_queue(profile)
    if not queue:
        return 0
    count = 0
    for q in queue:
        j = db.get_job(profile, q["job_id"])
        if j and j.get("company", "").strip().lower() == company_lower:
            count += 1
    return count


def add_to_queue(profile: str, job_id: int, with_cover: bool) -> None:
    queue = load_queue(profile)
    if any(q["job_id"] == job_id for q in queue):
        for q in queue:
            if q["job_id"] == job_id:
                q["with_cover"] = with_cover
                q["queued_at"] = datetime.now().isoformat(timespec="seconds")
    else:
        queue.append({
            "job_id": job_id,
            "with_cover": with_cover,
            "queued_at": datetime.now().isoformat(timespec="seconds"),
        })
    save_queue(profile, queue)
    db.update_job_state(profile, job_id, "queued_for_tailor",
                        note=f"queued via UI (with_cover={with_cover})")


def remove_from_queue(profile: str, job_id: int) -> None:
    queue = load_queue(profile)
    queue = [q for q in queue if q["job_id"] != job_id]
    save_queue(profile, queue)
    db.update_job_state(profile, job_id, "evaluated", note="removed from tailor queue")


# ============================================================
# Display helpers
# ============================================================

def link_health_data(job: dict) -> tuple[str, str]:
    """Return (variant, label) for a link health badge."""
    status = job.get("url_http_status")
    last = job.get("url_last_checked")
    if status is None or last is None:
        return "default", "link unchecked"
    if status == 0:
        return "warn", "network error"
    if 200 <= status < 400:
        return "success", f"live {status}"
    if status in (404, 410):
        return "danger", f"gone {status}"
    return "warn", f"http {status}"


def tier_badge_label(tier_key: str) -> str:
    return {
        "tier_1_dream":       "tier 1 dream",
        "tier_2_target":      "tier 2 target",
        "tier_3_watchlist":   "tier 3 watchlist",
        "tier_4_exploratory": "tier 4 explore",
    }.get(tier_key, tier_key)


def _escape(s: Any) -> str:
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def row_summary_html(job: dict, dream_tiers: dict) -> str:
    """Render the card's summary middle-column (title + badges) as HTML."""
    tier = job.get("dream_tier") or company_tier(job.get("company", ""), dream_tiers)

    badges: list[str] = []
    rec = job.get("recommendation")
    if rec:
        v = {"APPLY": "success", "REVIEW": "warn", "SKIP": "danger"}.get(rec, "default")
        badges.append(ui_theme.badge(rec.lower(), v))
    state = job.get("state")
    if state:
        state_variant = "accent" if state in {"evaluated", "queued_for_tailor", "tailored"} else "default"
        state_icon = {
            "evaluated":          "file-text",
            "queued_for_tailor":  "list",
            "tailored":           "check",
            "applied":            "send",
            "responded":          "mail",
            "interview":          "briefcase",
            "offer":              "sparkles",
            "rejected":           "x",
            "discarded":          "x",
            "skip":               "minus",
            "cooling":            "snowflake",
        }.get(state)
        badges.append(ui_theme.badge(state, state_variant, icon_name=state_icon))
    if tier:
        badges.append(ui_theme.badge(tier_badge_label(tier), "accent"))
    lv, ll = link_health_data(job)
    badges.append(ui_theme.badge(ll, lv, icon_name="link"))
    if job.get("exclusion_triggered"):
        badges.append(ui_theme.badge("excluded: " + job["exclusion_triggered"],
                                      "danger", icon_name="flag"))
    if job.get("is_starred"):
        badges.append(ui_theme.badge("starred", "accent", icon_name="star-filled"))

    title = f"{_escape(job.get('company',''))} &mdash; {_escape(job.get('role',''))}"
    sub_bits = [f"#{job.get('id')}"]
    if job.get("country"):    sub_bits.append(str(job["country"]))
    if job.get("location"):   sub_bits.append(_escape(job["location"]))
    if job.get("mode"):       sub_bits.append(str(job["mode"]))
    if job.get("role_family"):sub_bits.append(str(job["role_family"]))
    sub = " &middot; ".join(sub_bits)

    return (
        f'<div class="mb-row-title">{title}</div>'
        f'<div class="mb-row-sub">{sub}</div>'
        f'<div style="margin-top:8px">{ " ".join(badges) }</div>'
    )


# ============================================================
# Sidebar
# ============================================================

profiles_data = load_profiles()
available_profiles = [k for k, v in profiles_data.get("profiles", {}).items() if v.get("enabled")]
default_profile = profiles_data.get("default", available_profiles[0] if available_profiles else "shiva")

with st.sidebar:
    st.markdown("### Profile")
    profile = st.selectbox(
        "Active profile",
        available_profiles,
        index=available_profiles.index(default_profile) if default_profile in available_profiles else 0,
    )

    # Pull distinct filter options once per render
    countries_with_counts = db.get_distinct_values(profile, "country")
    modes_with_counts     = db.get_distinct_values(profile, "mode")
    companies_with_counts = db.get_distinct_values(profile, "company")
    state_counts = {s: n for s, n in db.get_distinct_values(profile, "state")}
    rec_counts   = {r: n for r, n in db.get_distinct_values(profile, "recommendation")}

    profile_settings = load_profile_settings(profile)
    dream_tiers = profile_settings.get("dream_tiers", {})
    role_prefs  = profile_settings.get("role_family_preference", {})
    exclusions  = profile_settings.get("exclusions", {})

    def _labelled(vcs: list[tuple[str, int]]) -> dict[str, str]:
        return {v: f"{v} ({n})" for v, n in vcs}

    country_labels = _labelled(countries_with_counts)
    mode_labels    = _labelled(modes_with_counts)
    company_labels = _labelled(companies_with_counts)

    # --- Filters header + Reset ---
    st.markdown("---")
    h_cols = st.columns([3, 2])
    h_cols[0].markdown("### Filters")
    if h_cols[1].button("Reset filters", help="Clear all filters to defaults",
                        use_container_width=True):
        for k in list(st.session_state.keys()):
            if k.startswith("flt_"):
                del st.session_state[k]
        st.rerun()

    score_range = st.slider("Score range", 0.0, 5.0, (3.5, 5.0), 0.1, key="flt_score")

    country_filter = st.multiselect(
        "Country",
        options=[v for v, _ in countries_with_counts], default=[],
        format_func=lambda v: country_labels.get(v, v), key="flt_country",
        help="Options auto-derive from the DB; new countries appear as scans find them.",
    )

    mode_filter = st.multiselect(
        "Mode", options=[v for v, _ in modes_with_counts], default=[],
        format_func=lambda v: mode_labels.get(v, v), key="flt_mode",
    )

    tier_options = [k for k in ("tier_1_dream", "tier_2_target", "tier_3_watchlist", "tier_4_exploratory")
                    if dream_tiers.get(k)]
    if tier_options:
        tier_filter = st.multiselect(
            "Dream tier", options=tier_options, default=[],
            format_func=tier_badge_label, key="flt_tier",
        )
    else:
        tier_filter = []

    state_filter = st.multiselect(
        "State", options=sorted(db.VALID_STATES),
        default=["evaluated", "queued_for_tailor", "tailored", "applied"],
        format_func=lambda v: f"{v} ({state_counts.get(v, 0)})", key="flt_state",
    )

    rec_filter = st.multiselect(
        "Recommendation", options=["APPLY", "REVIEW", "SKIP"], default=[],
        format_func=lambda v: f"{v} ({rec_counts.get(v, 0)})", key="flt_rec",
    )

    recency_days = st.selectbox(
        "Discovered in last", options=[0, 1, 3, 7, 14, 30, 90], index=0,
        format_func=lambda d: "any time" if d == 0 else f"{d} day(s)", key="flt_recency",
    )

    starred_only = st.checkbox("Starred only", value=False, key="flt_starred")

    has_cv_filter = st.radio("Has CV", options=["any", "yes", "no"], horizontal=True, key="flt_has_cv")

    sort_by = st.selectbox(
        "Sort by",
        options=[
            "starred_first", "total_score DESC", "total_score ASC",
            "cv_match DESC", "role_mission DESC",
            "discovered_date DESC", "company ASC", "state ASC", "created_at DESC",
        ], index=0, key="flt_sort",
    )

    company_search = (st.text_input("Company contains", key="flt_company_txt").strip() or None)
    role_search    = (st.text_input("Role contains",    key="flt_role_txt").strip() or None)

    # --- Advanced scoring ---
    with st.expander("Advanced scoring filters", expanded=False):
        st.caption("Sub-score floors. Leave at 0 to ignore. "
                   "Useful for hidden gems: high CV match but low total.")
        min_cv_match          = st.slider("Min CV match",            0.0, 5.0, 0.0, 0.5, key="flt_cv")
        min_company_mission   = st.slider("Min company mission fit", 0.0, 5.0, 0.0, 0.5, key="flt_cmf")
        min_role_mission      = st.slider("Min role mission fit",    0.0, 5.0, 0.0, 0.5, key="flt_rmf")
        min_comp              = st.slider("Min compensation",        0.0, 5.0, 0.0, 0.5, key="flt_comp")
        min_cultural          = st.slider("Min cultural",            0.0, 5.0, 0.0, 0.5, key="flt_cult")
        min_red_flags         = st.slider("Min red flags (5=clean)", 0.0, 5.0, 0.0, 0.5, key="flt_rf")
        if st.button("Apply hidden-gems preset",
                     help="Sets CV match >= 4.0 AND total score < 4.0",
                     use_container_width=True):
            st.session_state["flt_cv"] = 4.0
            st.session_state["flt_score"] = (0.0, 4.0)
            st.rerun()

    st.markdown("---")
    st.markdown("### Company filters")

    included_companies = st.multiselect(
        "Include only (empty = all)",
        options=[v for v, _ in companies_with_counts], default=[],
        format_func=lambda v: company_labels.get(v, v), key="flt_inc_co",
    )

    hot_companies = db.get_hot_companies(profile, days=14)
    hide_cooling = st.checkbox(
        f"Hide cooling companies ({', '.join(hot_companies) if hot_companies else 'none'})",
        value=bool(hot_companies), key="flt_hide_cool",
        help="Companies with 3+ applications in the last 14 days.",
    )

    excluded_companies = st.multiselect(
        "Exclude specific companies",
        options=[v for v, _ in companies_with_counts],
        default=hot_companies if hide_cooling else [],
        format_func=lambda v: company_labels.get(v, v), key="flt_exc_co",
    )

    # --- Queue + link health + exclusions summary ---
    st.markdown("---")
    st.markdown("### Tailor queue")
    current_queue = load_queue(profile)
    st.metric("Queued for tailor", len(current_queue))
    if current_queue:
        st.caption(f"Run `/tailor --batch --profile {profile}` in Claude Code to process.")

    st.markdown("---")
    st.markdown("### Link health")
    check_limit = st.number_input("Max URLs to check", 10, 500, 50, 10)
    if st.button("Check stale links now"):
        with st.spinner(f"Checking up to {check_limit} URLs..."):
            summary = db.bulk_check_urls(profile, stale_hours=24, limit=int(check_limit))
        st.success(
            f"Checked {summary['checked']}: "
            f"{summary['live']} live, {summary['dead']} gone, {summary['error']} network errors"
        )

    if exclusions:
        st.markdown("---")
        st.markdown("### Sector exclusions")
        for sector, policy in exclusions.items():
            default = policy.get("global_default", "include") if isinstance(policy, dict) else "include"
            overrides = policy.get("overrides", {}) if isinstance(policy, dict) else {}
            if default == "exclude":
                line = f"{sector}"
                if overrides:
                    incl = [k for k, v in overrides.items() if v == "include"]
                    if incl:
                        line += f" (allowed in {', '.join(incl)})"
                st.caption(line)


# ============================================================
# Top bar: title + stats + info strip
# ============================================================

st.markdown('<h1 class="mb-page-title">Matchbox Pipeline</h1>', unsafe_allow_html=True)
st.markdown(
    f'<div class="mb-page-sub">Profile: <strong>{profile}</strong> &middot; '
    f'Last refresh: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>',
    unsafe_allow_html=True,
)

# Info strip: explain in one line what the main actions do (addresses the
# "what does Submit do?" confusion).
st.markdown(
    f'<div class="mb-info-strip">'
    f'{ui_theme.icon("info", 16)} '
    f'<span><strong>Log Applied</strong> updates the DB to "applied" — it does '
    f'not submit to the company portal or write to Atma. For the Atma log, '
    f'run <code>/apply --id N --profile {profile}</code> after actually submitting.'
    f'</span></div>',
    unsafe_allow_html=True,
)

# Summary stats bar
stats = db.get_stats(profile)
stat_cols = st.columns(7)
stat_cols[0].metric("Evaluated", stats.get("count_evaluated", 0))
stat_cols[1].metric("Queued",    stats.get("count_queued_for_tailor", 0))
stat_cols[2].metric("Tailored",  stats.get("count_tailored", 0))
stat_cols[3].metric("Applied",   stats.get("count_applied", 0))
stat_cols[4].metric("Interview", stats.get("count_interview", 0))
stat_cols[5].metric("Offer",     stats.get("count_offer", 0))
stat_cols[6].metric("Cost $",    f"{stats.get('total_cost_usd', 0):.2f}")

if stats.get("hot_companies"):
    st.warning(f"Cooling (3+ apps in 14 days): {', '.join(stats['hot_companies'])}")


# ============================================================
# Query the DB
# ============================================================

def build_query_kwargs() -> dict[str, Any]:
    kw: dict[str, Any] = {
        "min_score": score_range[0],
        "max_score": score_range[1],
        "order_by":  sort_by,
        "limit":     500,
    }
    if state_filter:          kw["state"] = state_filter
    if country_filter:        kw["country"] = country_filter
    if mode_filter:           kw["mode"] = mode_filter
    if rec_filter:            kw["recommendation"] = rec_filter
    if tier_filter:           kw["dream_tier"] = tier_filter
    if has_cv_filter == "yes":  kw["has_cv"] = True
    elif has_cv_filter == "no": kw["has_cv"] = False
    if starred_only:          kw["is_starred"] = True
    if company_search:        kw["company_search"] = company_search
    if role_search:           kw["role_search"] = role_search
    if min_cv_match > 0:        kw["min_cv_match"] = min_cv_match
    if min_company_mission > 0: kw["min_company_mission"] = min_company_mission
    if min_role_mission > 0:    kw["min_role_mission"] = min_role_mission
    if min_comp > 0:            kw["min_comp"] = min_comp
    if min_cultural > 0:        kw["min_cultural"] = min_cultural
    if min_red_flags > 0:       kw["min_red_flags"] = min_red_flags
    if recency_days and recency_days > 0:
        cutoff = (datetime.now() - timedelta(days=recency_days)).date().isoformat()
        kw["since_date"] = cutoff
    return kw


jobs = db.list_jobs(profile, **build_query_kwargs())

if included_companies:
    jobs = [j for j in jobs if j["company"] in included_companies]
if excluded_companies:
    before = len(jobs)
    jobs = [j for j in jobs if j["company"] not in excluded_companies]
    hidden = before - len(jobs)
    if hidden:
        st.caption(f"Hiding {hidden} jobs from excluded companies.")

# Within-company stable sort: starred first, then role-family preference, then score
jobs.sort(key=lambda j: (
    -(j.get("is_starred") or 0),
    role_family_rank(j.get("role_family"), role_prefs),
    -(j.get("total_score") or 0.0),
))


# ============================================================
# Results header + density + dedup toggles + CSV
# ============================================================

results_cols = st.columns([2, 2, 1, 1])
with results_cols[0]:
    st.markdown(f"**{len(jobs)} jobs** match current filters")
    active_bits = []
    if country_filter:     active_bits.append("country=" + ",".join(country_filter))
    if mode_filter:        active_bits.append("mode=" + ",".join(mode_filter))
    if tier_filter:        active_bits.append("tier=" + ",".join(tier_filter))
    if included_companies: active_bits.append(f"only {len(included_companies)} co(s)")
    if recency_days > 0:   active_bits.append(f"last {recency_days}d")
    if starred_only:       active_bits.append("starred only")
    if active_bits:
        st.caption("Active: " + " · ".join(active_bits))

with results_cols[1]:
    dedup_per_company = st.checkbox(
        "One card per company",
        value=True, key="dedup_per_co",
        help="Group multiple roles at the same company into one primary card. "
             "Click 'Expand N siblings' to see the others in place.",
    )

with results_cols[2]:
    st.markdown(" ")
    if st.button("Expand all", use_container_width=True,
                 help="Open details and siblings on every visible card"):
        st.session_state["expanded_ids"]    = {j["id"] for j in jobs}
        st.session_state["siblings_open_co"] = {j["company"] for j in jobs}
        st.rerun()

with results_cols[3]:
    if jobs:
        buf = io.StringIO()
        cols = ["id", "company", "role", "country", "mode", "total_score",
                "recommendation", "state", "dream_tier", "role_family",
                "url", "url_http_status", "discovered_date", "is_starred"]
        w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(jobs)
        st.download_button(
            "Download CSV",
            data=buf.getvalue(),
            file_name=f"matchbox-{profile}-{datetime.now().strftime('%Y%m%d-%H%M')}.csv",
            mime="text/csv", use_container_width=True,
        )

if not jobs:
    st.info("No jobs match current filters. Try Reset filters, relax the date range, or scan more.")
    st.stop()


# ============================================================
# Group by company (for dedup + sibling expand)
# ============================================================

by_company: dict[str, list[dict]] = {}
for j in jobs:
    by_company.setdefault(j["company"], []).append(j)

if dedup_per_company:
    # One primary per company; siblings nested inside
    primaries = [(co, rows[0], rows[1:]) for co, rows in by_company.items()]
else:
    # Every row as its own primary, no siblings
    primaries = [(j["company"], j, []) for j in jobs]


# ============================================================
# Per-card render
# ============================================================

SESS_EXP = "expanded_ids"           # set of job ids whose Details are shown
SESS_SIB = "siblings_open_co"       # set of company names whose siblings are shown
SESS_CAP = "confirm_cap"            # dict job_id -> "cv" | "both" (pending queue-cap confirmation)


def is_expanded(job_id: int) -> bool:
    return job_id in st.session_state.get(SESS_EXP, set())


def toggle_expanded(job_id: int) -> None:
    s = st.session_state.setdefault(SESS_EXP, set())
    if job_id in s: s.discard(job_id)
    else:           s.add(job_id)


def siblings_open(company: str) -> bool:
    return company in st.session_state.get(SESS_SIB, set())


def toggle_siblings(company: str) -> None:
    s = st.session_state.setdefault(SESS_SIB, set())
    if company in s: s.discard(company)
    else:            s.add(company)


def render_action_row(job: dict, *, key_prefix: str) -> None:
    """Render the button row under a card summary. All labels plain text."""
    jid = job["id"]
    cols = st.columns([1, 1, 1.2, 1.4, 1, 0.8])

    is_starred = bool(job.get("is_starred"))
    if cols[0].button("Unstar" if is_starred else "Star",
                      key=f"{key_prefix}_star_{jid}",
                      use_container_width=True,
                      help="Pin this job to the top of the list"):
        db.toggle_star(profile, jid); st.rerun()

    if job.get("state") == "queued_for_tailor":
        if cols[1].button("Unqueue", key=f"{key_prefix}_unq_{jid}",
                          use_container_width=True,
                          help="Remove from tailor queue and revert to evaluated"):
            remove_from_queue(profile, jid); st.rerun()
        cols[2].write("")
    else:
        if cols[1].button("Queue CV", key=f"{key_prefix}_qcv_{jid}",
                          use_container_width=True,
                          help="Add to tailor queue for CV-only tailoring"):
            if queue_count_for_company(profile, job["company"]) >= 3:
                st.session_state.setdefault(SESS_CAP, {})[jid] = "cv"
            else:
                add_to_queue(profile, jid, with_cover=False)
            st.rerun()
        if cols[2].button("Queue CV+Cover", key=f"{key_prefix}_qboth_{jid}",
                          use_container_width=True,
                          help="Add to tailor queue for CV + cover letter"):
            if queue_count_for_company(profile, job["company"]) >= 3:
                st.session_state.setdefault(SESS_CAP, {})[jid] = "both"
            else:
                add_to_queue(profile, jid, with_cover=True)
            st.rerun()

    if job.get("state") in ("tailored", "evaluated", "queued_for_tailor"):
        if cols[3].button("Log Applied (DB only)",
                          key=f"{key_prefix}_sub_{jid}",
                          type="primary", use_container_width=True,
                          help=("Sets DB state to 'applied' and stamps applied_date. "
                                "Does not submit to any portal. Does not write to "
                                "Atma log.md — run /apply --id N for that.")):
            db.update_job_state(profile, jid, "applied", note="logged via UI")
            st.success(
                f"Logged #{jid} as applied in the DB. Now (1) actually submit "
                f"on the company portal if you haven't, and (2) run "
                f"`/apply --id {jid} --profile {profile}` in Claude Code to "
                f"write the Atma log entry."
            )
            st.rerun()
    else:
        cols[3].write("")

    if cols[4].button("Details" if not is_expanded(jid) else "Hide details",
                      key=f"{key_prefix}_det_{jid}", use_container_width=True,
                      help="Show/hide sub-scores, report, links, and submit notes"):
        toggle_expanded(jid); st.rerun()

    # Tiny link icon button (open JD in new tab) — rendered as a markdown link
    cols[5].markdown(
        f'<a href="{_escape(job.get("url",""))}" target="_blank" '
        f'style="display:inline-flex;align-items:center;gap:4px;'
        f'font-size:0.8rem;color:var(--mb-accent-600);text-decoration:none;">'
        f'{ui_theme.icon("external-link", 14)} Open JD</a>',
        unsafe_allow_html=True,
    )

    # Per-company cap confirmation dialog
    pending = st.session_state.get(SESS_CAP, {}).get(jid)
    if pending:
        st.warning(
            f"You already have 3 or more queued for **{job['company']}**. "
            f"Queue this 4th anyway?"
        )
        cc = st.columns([1, 1, 4])
        if cc[0].button("Yes, queue", key=f"{key_prefix}_capyes_{jid}"):
            add_to_queue(profile, jid, with_cover=(pending == "both"))
            st.session_state[SESS_CAP].pop(jid, None)
            st.rerun()
        if cc[1].button("Cancel", key=f"{key_prefix}_capno_{jid}"):
            st.session_state[SESS_CAP].pop(jid, None)
            st.rerun()


def render_details_block(job: dict) -> None:
    """The expanded-details area that appears below the card summary."""
    st.markdown("---")

    # Six sub-score metrics
    dim_cols = st.columns(6)
    dim_cols[0].metric("CV",        f"{job.get('cv_match_score') or 0:.1f}")
    dim_cols[1].metric("Co mission",f"{job.get('company_mission_fit_score') or 0:.1f}")
    dim_cols[2].metric("Role mission", f"{job.get('role_mission_fit_score') or 0:.1f}")
    dim_cols[3].metric("Comp",      f"{job.get('comp_score') or 0:.1f}")
    dim_cols[4].metric("Culture",   f"{job.get('cultural_score') or 0:.1f}")
    dim_cols[5].metric("Red flags (5=clean)", f"{job.get('red_flags_score') or 0:.1f}")

    # Meta row
    meta_bits = []
    if job.get("location"):    meta_bits.append(f"**Location:** {_escape(job['location'])}")
    if job.get("comp_stated"): meta_bits.append(f"**Comp:** {_escape(job['comp_stated'])}")
    if job.get("visa_sponsorship"): meta_bits.append(f"**Visa:** {_escape(job['visa_sponsorship'])}")
    if job.get("legitimacy"):  meta_bits.append(f"**Legitimacy:** {_escape(job['legitimacy'])}")
    if meta_bits:
        st.markdown(" &nbsp; · &nbsp; ".join(meta_bits), unsafe_allow_html=True)

    if job.get("exclusion_triggered"):
        st.error(f"Sector exclusion: {job['exclusion_triggered']}")

    if job.get("user_notes"):
        st.info(f"Notes: {job['user_notes']}")

    # Links row
    link_cols = st.columns([1, 1, 1, 1, 3])
    if job.get("report_path"):
        rabs = REPO_ROOT / job["report_path"]
        if rabs.exists():
            link_cols[0].markdown(
                f'<a href="{rabs.as_uri()}" target="_blank">View report</a>',
                unsafe_allow_html=True,
            )
    if job.get("cv_path"):
        cvabs = REPO_ROOT / job["cv_path"]
        if cvabs.exists():
            link_cols[1].markdown(
                f'<a href="{cvabs.as_uri()}" target="_blank">View CV PDF</a>',
                unsafe_allow_html=True,
            )
    if job.get("cover_path"):
        covabs = REPO_ROOT / job["cover_path"]
        if covabs.exists():
            link_cols[2].markdown(
                f'<a href="{covabs.as_uri()}" target="_blank">View cover PDF</a>',
                unsafe_allow_html=True,
            )
    if st.button("Re-check link", key=f"det_relink_{job['id']}",
                 help="Re-issue HEAD/GET to see if this URL is still live"):
        status = db.check_url(profile, job["id"])
        st.toast(f"HTTP {status}" if status else "Network error")
        st.rerun()

    # State override + save
    state_col, save_col = st.columns([4, 1])
    with state_col:
        new_state = st.selectbox(
            "Override state",
            options=sorted(db.VALID_STATES),
            index=sorted(db.VALID_STATES).index(job.get("state", "evaluated")),
            key=f"det_state_{job['id']}",
            help="Set the pipeline state manually. Mostly used for responded/interview/rejected/offer.",
        )
    with save_col:
        st.markdown(" ")
        if new_state != job.get("state"):
            if st.button("Save state", key=f"det_savestate_{job['id']}",
                         use_container_width=True):
                db.update_job_state(profile, job["id"], new_state)
                st.rerun()

    # Submission notes (only relevant if still pre-applied)
    if job.get("state") in ("tailored", "evaluated", "queued_for_tailor"):
        st.markdown("**Optional note when logging as applied** "
                    "(saved to user_notes, not sent anywhere):")
        sub_cols = st.columns([4, 1])
        with sub_cols[0]:
            notes = st.text_input(
                "Submission notes",
                key=f"det_subnotes_{job['id']}",
                placeholder="e.g. Applied via Greenhouse. Referral from Priya.",
                label_visibility="collapsed",
            )
        with sub_cols[1]:
            if st.button("Save note + Log Applied",
                         key=f"det_submit_{job['id']}",
                         type="primary", use_container_width=True):
                note = f"logged via UI | {notes}" if notes else "logged via UI"
                db.update_job_state(profile, job["id"], "applied", note=note)
                st.success(
                    f"Logged #{job['id']} applied. Still required: run "
                    f"`/apply --id {job['id']} --profile {profile}` in Claude "
                    f"Code to write the Atma log.md entry."
                )
                st.rerun()


def render_card(job: dict, *, key_prefix: str, show_sibling_button: int = 0,
                company: str | None = None) -> None:
    """Render one bordered card: summary row + action row + optional details + optional siblings."""
    with st.container(border=True):
        top = st.columns([1, 6.5, 3])

        # Score tile
        with top[0]:
            st.markdown(ui_theme.score_tile(job.get("total_score")),
                        unsafe_allow_html=True)

        # Summary (title + subtitle + badges)
        with top[1]:
            st.markdown(row_summary_html(job, dream_tiers), unsafe_allow_html=True)

        # Action buttons
        with top[2]:
            render_action_row(job, key_prefix=key_prefix)

        # Inline Details block
        if is_expanded(job["id"]):
            render_details_block(job)

        # Sibling expand button
        if show_sibling_button > 0 and company:
            label = (f"Hide {show_sibling_button} other role(s) at {company}"
                     if siblings_open(company)
                     else f"Expand {show_sibling_button} other role(s) at {company}")
            if st.button(label, key=f"{key_prefix}_sibs_{job['id']}",
                         use_container_width=True):
                toggle_siblings(company); st.rerun()


# ============================================================
# Render loop — paginated primaries, with inline sibling expand
# ============================================================

TOP_N_STEP = 25
shown_n = int(st.session_state.get("visible_n", TOP_N_STEP))
visible = primaries[:shown_n]

for co, primary, siblings in visible:
    render_card(primary, key_prefix="p", show_sibling_button=len(siblings), company=co)

    # Nested siblings as compact cards under the primary
    if siblings and siblings_open(co):
        st.markdown('<div class="mb-sibling-wrap">', unsafe_allow_html=True)
        for sib in siblings:
            render_card(sib, key_prefix=f"s_{co}", show_sibling_button=0, company=None)
        st.markdown('</div>', unsafe_allow_html=True)

remaining = len(primaries) - shown_n
if remaining > 0:
    if st.button(f"Show {min(TOP_N_STEP, remaining)} more "
                 f"({remaining} remaining) ",
                 use_container_width=True, type="secondary"):
        st.session_state["visible_n"] = shown_n + TOP_N_STEP
        st.rerun()


# ============================================================
# Bottom: scan history
# ============================================================

with st.expander("Recent scan runs", expanded=False):
    history = db.get_scan_history(profile, limit=10)
    if history:
        st.dataframe([
            {
                "Run ID": h["id"], "Mode": h.get("mode"), "Country": h.get("country"),
                "Started": h.get("started_at"), "Scored": h.get("scored_count"),
                "Apply": h.get("apply_count"), "Review": h.get("review_count"),
                "Cost $": round(h.get("cost_usd") or 0, 2), "Status": h.get("status"),
                "Trial": "yes" if h.get("is_trial") else "",
            } for h in history
        ], hide_index=True)
    else:
        st.caption(f"No scans yet. Run `/marathon --profile {profile} --trial "
                   f"--modes dream --countries india` to start.")

st.markdown("---")
st.caption(
    "Matchbox UI · read + state-update only. Canonical task definitions live in "
    "`matchbox/workflows/*.md`; paste `matchbox/MASTER.md` into any Sonnet session "
    "to drive Matchbox without Claude Code."
)
