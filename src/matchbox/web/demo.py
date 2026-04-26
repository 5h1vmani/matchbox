"""Demo profile seeding — synthetic but realistic jobs so cold-start has UX.

Idempotent: skips if demo DB already has rows. Run via the welcome page or
the `matchbox seed-demo` CLI command.
"""

from __future__ import annotations

import datetime as _dt
import logging
import random

from matchbox.core import db
from matchbox.web.config import Settings

log = logging.getLogger(__name__)


_COMPANIES = [
    ("Anthropic", "AI safety lab", "san-francisco", "us", "ai_safety"),
    ("Stripe", "Payments infra", "remote-uk", "uk", "fintech"),
    ("Linear", "Issue tracking", "remote", "us", "saas"),
    ("Vercel", "Frontend cloud", "remote", "us", "devtools"),
    ("Replit", "Cloud IDE", "remote", "us", "devtools"),
    ("Modal", "Serverless GPU", "remote", "us", "infra"),
    ("Cohere", "Enterprise LLMs", "remote-uk", "uk", "ai_apps"),
    ("Hugging Face", "ML platform", "remote", "us", "ai_apps"),
    ("Notion", "Productivity", "remote", "us", "productivity"),
    ("Datadog", "Observability", "london", "uk", "infra"),
    ("Monzo", "Neobank", "london", "uk", "fintech"),
    ("Wise", "Cross-border payments", "london", "uk", "fintech"),
    ("Razorpay", "Payments India", "bangalore", "india", "fintech"),
    ("Zerodha", "Brokerage", "bangalore", "india", "fintech"),
    ("Atlan", "Data catalog", "remote-india", "india", "data"),
    ("Postman", "API platform", "bangalore", "india", "devtools"),
    ("Hasura", "GraphQL backend", "bangalore", "india", "devtools"),
    ("Cred", "Credit cards", "bangalore", "india", "fintech"),
    ("Browserbase", "Headless browsers", "remote", "us", "ai_apps"),
    ("Mercor", "AI hiring", "remote", "us", "ai_apps"),
]

_ROLES = [
    ("Solutions Architect", "solutions_architect_startups"),
    ("Forward Deployed Engineer", "forward_deployed_engineer"),
    ("Applied AI Engineer", "applied_ai_engineer"),
    ("Founding Engineer", "founding_engineer"),
    ("AI Product Lead", "ai_product_lead"),
    ("Developer Advocate", "devrel_ai"),
    ("AI Implementation Consultant", "consultant_ai"),
    ("Senior ML Engineer", "applied_ai_engineer"),
    ("Staff Solutions Engineer", "solutions_architect_startups"),
    ("Customer Engineer", "forward_deployed_engineer"),
]


def seed_demo_profile(settings: Settings, *, count: int = 30, force: bool = False) -> int:
    """Populate people/demo/db.sqlite with synthetic jobs. Returns insert count."""
    profile = "demo"
    if not (settings.profile_dir(profile) / "profile.yaml").exists():
        raise FileNotFoundError(
            f"people/{profile}/profile.yaml missing. Demo profile not committed?"
        )

    db.init_db(profile)
    existing = db.get_stats(profile).get("count_evaluated", 0)
    if existing and not force:
        log.info("demo already seeded (%d evaluated jobs); skipping", existing)
        return 0

    rng = random.Random(42)  # deterministic
    today = _dt.date.today()
    run_id = db.create_scan_run(profile, mode="demo-seed", country=None)

    inserted = 0
    for i in range(count):
        company, blurb, location, country, _sector = rng.choice(_COMPANIES)
        role, family = rng.choice(_ROLES)
        score = round(rng.uniform(1.5, 4.8), 2)
        tier = (
            "bespoke"
            if score >= 4.0
            else "template"
            if score >= 3.0
            else "canonical"
            if score >= 2.0
            else "skip"
        )
        days_ago = rng.randint(0, 14)
        discovered = (today - _dt.timedelta(days=days_ago)).isoformat()
        state = rng.choices(
            ["evaluated", "queued_for_tailor", "tailored", "applied", "responded", "interview"],
            weights=[55, 10, 10, 15, 6, 4],
        )[0]

        jid = db.insert_job(
            profile,
            run_id,
            company=company,
            role=role,
            url=f"https://jobs.example.com/{company.lower().replace(' ', '-')}/{i:04d}",
            discovered_date=discovered,
            location=location,
            country=country,
            mode="remote" if "remote" in location else "hybrid",
            ats_source=rng.choice(["greenhouse", "lever", "ashby", "workable"]),
            jd_summary=f"{role} at {company} — {blurb}.",
            cv_match_score=round(rng.uniform(2.0, 5.0), 2),
            company_mission_fit_score=round(rng.uniform(2.0, 5.0), 2),
            role_mission_fit_score=round(rng.uniform(2.0, 5.0), 2),
            comp_score=3.0,
            cultural_score=round(rng.uniform(2.5, 4.5), 2),
            red_flags_score=round(rng.uniform(3.0, 5.0), 2),
            total_score=score,
            state=state,
            role_family=family,
        )
        # update tier separately since insert_job doesn't take it
        db.update_job(profile, jid, tier=tier)
        inserted += 1

    db.complete_scan_run(
        profile,
        run_id,
        raw_candidates=count,
        filtered_survivors=count,
        scored_count=count,
        status="success",
        notes="synthetic demo data",
    )
    log.info("seeded %d demo jobs", inserted)
    return inserted
