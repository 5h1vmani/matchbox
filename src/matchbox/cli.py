"""Matchbox CLI — typer-based entry point.

Commands:
  scan              Run daily ATS scan for a profile
  tailor            Generate tailored CV + cover for a queued job
  apply             Mark a job as applied
  score-job         Score a job by ID or URL
  log-response      Record interview / rejection / offer
  analytics         Show conversion funnel and cost breakdown
  rebuild-canonicals Regenerate all canonical PDFs
  init-profile      Create a new person directory with starter files
  seed-demo         Populate demo profile with synthetic jobs
  web               Start the web dashboard (FastAPI + HTMX)
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich import print as rprint
from rich.table import Table

app = typer.Typer(
    name="matchbox",
    help="Matchbox v0.2 — precision job pipeline",
    add_completion=False,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


# ──────────────────────────────────────────────
# scan
# ──────────────────────────────────────────────


@app.command()
def scan(
    profile: str = typer.Argument(..., help="Person name (e.g. shiva)"),
    country: str | None = typer.Option(
        None, "--country", "-c", help="Filter by country (uk/india/us)"
    ),
    trial: bool = typer.Option(False, "--trial", help="Mark scan run as trial"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Probe only, skip DB writes"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Probe ATS boards, score jobs, insert new ones into the DB."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    from matchbox.discovery.scan_daily import run_daily_scan

    rprint(f"[bold]Scanning[/bold] profile={profile} country={country or 'all'} trial={trial}")
    result = run_daily_scan(profile, country=country, trial=trial, dry_run=dry_run)
    rprint(
        f"[green]Done[/green] run_id={result.run_id} "
        f"raw={result.raw} inserted={result.inserted} "
        f"dupes={result.skipped_dupe} excluded={result.excluded}"
    )
    if result.inserted and not dry_run:
        rprint(
            f"\n[dim]Next:[/dim] [bold]matchbox web[/bold] "
            f"(or open the inbox at /p/{profile}/inbox)"
        )


# ──────────────────────────────────────────────
# tailor
# ──────────────────────────────────────────────


@app.command()
def tailor(
    profile: str = typer.Argument(..., help="Person name"),
    job_id: int = typer.Argument(..., help="Job ID to tailor"),
    model: str = typer.Option("claude-sonnet-4-6", "--model", "-m"),
    gate_mode: str = typer.Option("warn", "--gate-mode", help="warn | raise | skip"),
) -> None:
    """Generate tailored CV + cover letter for a specific job."""
    from matchbox.core import db
    from matchbox.core.person import load_person
    from matchbox.tailor.paths import tailor_job

    job = db.get_job(profile, job_id)
    if job is None:
        rprint(f"[red]Job {job_id} not found for profile {profile}[/red]")
        raise typer.Exit(1)

    person = load_person(profile)
    rprint(f"[bold]Tailoring[/bold] job_id={job_id} tier={job.tier} company={job.company}")

    app_result = tailor_job(job, person, model=model, gate_mode=gate_mode)
    if app_result is None:
        rprint("[yellow]Tailor returned None (skip tier or gate_mode=skip)[/yellow]")
        raise typer.Exit(0)

    rprint(
        f"[green]Tailored[/green] tier={app_result.tier} geo={app_result.geo} "
        f"cost=${app_result.cost_usd:.4f}"
    )
    rprint(f"  CV:    {app_result.cv_path}")
    if app_result.cover_path:
        rprint(f"  Cover: {app_result.cover_path}")


# ──────────────────────────────────────────────
# apply
# ──────────────────────────────────────────────


@app.command()
def apply(
    profile: str = typer.Argument(...),
    job_id: int = typer.Argument(...),
    note: str | None = typer.Option(None, "--note", "-n"),
) -> None:
    """Mark a job as applied and record today's date."""
    from matchbox.core import db

    db.update_job_state(profile, job_id, "applied", note=note)
    rprint(f"[green]Applied[/green] job_id={job_id}")


# ──────────────────────────────────────────────
# score-job
# ──────────────────────────────────────────────


@app.command()
def score_job(
    profile: str = typer.Argument(...),
    job_id: int = typer.Argument(...),
) -> None:
    """Re-score a job and print dimension breakdown."""
    from matchbox.core import db
    from matchbox.core.person import load_person
    from matchbox.scoring.rubric import score_job as _score

    job = db.get_job(profile, job_id)
    if job is None:
        rprint(f"[red]Job {job_id} not found[/red]")
        raise typer.Exit(1)

    person = load_person(profile)
    scored = _score(job, person, jd_text=job.jd_text or "")

    table = Table(title=f"Score — {scored.company} | {scored.role}")
    table.add_column("Dimension")
    table.add_column("Score", justify="right")
    table.add_row("cv_match", f"{scored.cv_match_score:.2f}")
    table.add_row("company_mission", f"{scored.company_mission_fit_score:.2f}")
    table.add_row("role_mission", f"{scored.role_mission_fit_score:.2f}")
    table.add_row("comp", f"{scored.comp_score:.2f}")
    table.add_row("cultural", f"{scored.cultural_score:.2f}")
    table.add_row("red_flags", f"{scored.red_flags_score:.2f}")
    table.add_row("[bold]total[/bold]", f"[bold]{scored.total_score:.2f}[/bold]")
    rprint(table)
    rprint(f"tier={scored.tier or 'unset'}  dream_tier={scored.dream_tier or 'none'}")

    # Persist updated scores
    db.update_job(
        profile,
        job_id,
        cv_match_score=scored.cv_match_score,
        company_mission_fit_score=scored.company_mission_fit_score,
        role_mission_fit_score=scored.role_mission_fit_score,
        comp_score=scored.comp_score,
        cultural_score=scored.cultural_score,
        red_flags_score=scored.red_flags_score,
        total_score=scored.total_score,
        dream_tier=scored.dream_tier,
    )


# ──────────────────────────────────────────────
# log-response
# ──────────────────────────────────────────────


@app.command()
def log_response(
    profile: str = typer.Argument(...),
    job_id: int = typer.Argument(...),
    response_type: str = typer.Argument(
        ..., help="interview | rejection | offer | ghosted | other"
    ),
    response_date: str | None = typer.Option(
        None, "--date", "-d", help="ISO date (default: today)"
    ),
    note: str | None = typer.Option(None, "--note", "-n"),
) -> None:
    """Record an outcome response (interview invite, rejection, offer, etc.)."""
    from matchbox.outcome.response import log_response as _log

    rid = _log(profile, job_id, response_type=response_type, response_date=response_date, note=note)
    rprint(f"[green]Logged[/green] response_id={rid} type={response_type} job_id={job_id}")


# ──────────────────────────────────────────────
# analytics
# ──────────────────────────────────────────────


@app.command()
def analytics(
    profile: str = typer.Argument(...),
) -> None:
    """Show conversion funnel and tier cost breakdown."""
    from matchbox.outcome.analytics import get_funnel, get_tier_cost_summary

    funnel = get_funnel(profile)
    tier_costs = get_tier_cost_summary(profile)

    rprint(f"\n[bold]Funnel — {profile}[/bold]")
    table = Table()
    table.add_column("Stage")
    table.add_column("Count", justify="right")
    table.add_column("Rate", justify="right")
    table.add_row("Evaluated", str(funnel["evaluated"]), "—")
    table.add_row("Applied", str(funnel["applied"]), f"{funnel['applied_rate']}%")
    table.add_row("Responded", str(funnel["responded"]), f"{funnel['response_rate']}%")
    table.add_row("Interview", str(funnel["interview"]), f"{funnel['interview_rate']}%")
    table.add_row("Offer", str(funnel["offer"]), f"{funnel['offer_rate']}%")
    rprint(table)

    rprint(
        f"\nTotal cost: [bold]${funnel['total_cost_usd']:.2f}[/bold]  "
        f"Cost/application: [bold]${funnel['cost_per_application']:.2f}[/bold]  "
        f"Avg score: [bold]{funnel['avg_score']:.2f}[/bold]"
    )

    if tier_costs:
        rprint("\n[bold]Cost by tier[/bold]")
        tc_table = Table()
        tc_table.add_column("Tier")
        tc_table.add_column("Count", justify="right")
        tc_table.add_column("Total USD", justify="right")
        tc_table.add_column("Avg USD", justify="right")
        for tier_name, tc in sorted(tier_costs.items()):
            tc_table.add_row(
                tier_name,
                str(tc["count"]),
                f"${tc['total_usd']:.4f}",
                f"${tc['avg_usd']:.4f}",
            )
        rprint(tc_table)


# ──────────────────────────────────────────────
# rebuild-canonicals
# ──────────────────────────────────────────────


@app.command()
def rebuild_canonicals(
    profile: str = typer.Argument(...),
) -> None:
    """Regenerate all geo-variant canonical PDFs for a profile."""
    from matchbox.tailor.paths import rebuild_canonicals as _rebuild

    rprint(f"[bold]Rebuilding canonicals[/bold] for {profile}…")
    results = _rebuild(profile)
    for geo, path in results.items():
        rprint(f"  {geo}: {path}")
    rprint("[green]Done[/green]")


# ──────────────────────────────────────────────
# init-profile
# ──────────────────────────────────────────────


@app.command()
def init_profile(
    name: str = typer.Argument(..., help="Person directory name (lowercase, no spaces)"),
) -> None:
    """Create a new person directory with starter YAML files."""
    root = Path(__file__).resolve().parents[3]
    person_dir = root / "people" / name

    if person_dir.exists():
        rprint(f"[yellow]Directory already exists: {person_dir}[/yellow]")
        raise typer.Exit(1)

    person_dir.mkdir(parents=True)
    (person_dir / "output").mkdir()

    profile_stub = f"""\
_meta:
  schema_version: 1
  last_updated: {_today()}
  matchbox_version: 0.2.0

candidate:
  full_name: {name.title()}
  email: ""
  phone: ""
  location: ""
  linkedin: ""
  github: ""

targets:
  primary_roles: []
  dream_tiers:
    tier_1_dream: []
    tier_2_target: []
    tier_3_watchlist: []
    tier_4_exploratory: []

filters:
  title_positive: []
  title_negative: []
  exclusions: {{}}

compensation:
  india:  {{target: "", minimum: ""}}
  uk:     {{target: "", minimum: ""}}

constraints:
  visa_status: ""
  remote_preference: "remote-first"
  notice_period: "30 days"

scoring:
  cv_match_weight: 0.25
  company_mission_fit_weight: 0.15
  role_mission_fit_weight: 0.15
  tech_stack_weight: 0.20
  seniority_weight: 0.15
  location_remote_weight: 0.10

work_history: []
skills: []
projects: []
role_family_preference: {{}}
"""

    voice_stub = """\
_meta:
  schema_version: 1

# Per-profile voice overrides. Lists append to shared/voice-rules.yaml.
banned_words: []
banned_openers: []
costly_signal_patterns: []
opener_patterns: []
"""

    (person_dir / "profile.yaml").write_text(profile_stub, encoding="utf-8")
    (person_dir / "voice.yaml").write_text(voice_stub, encoding="utf-8")
    (person_dir / "stories.md").write_text(
        f"# {name.title()} Stories\n\n<!-- STAR+R format -->\n", encoding="utf-8"
    )
    (person_dir / "log.md").write_text(
        f"# {name.title()} Application Log\n\n<!-- auto-updated by matchbox log-response -->\n",
        encoding="utf-8",
    )

    rprint(f"[green]Created[/green] {person_dir}")
    rprint("  Edit profile.yaml and stories.md, then run: matchbox scan {name}")


def _today() -> str:
    from datetime import date

    return date.today().isoformat()


# ──────────────────────────────────────────────
# seed-demo
# ──────────────────────────────────────────────


@app.command("seed-demo")
def seed_demo(
    count: int = typer.Option(30, "--count", "-n", help="Number of synthetic jobs"),
    force: bool = typer.Option(False, "--force", help="Re-seed even if demo already populated"),
) -> None:
    """Populate people/demo/db.sqlite with synthetic jobs for trying the UI."""
    from matchbox.web.config import Settings
    from matchbox.web.demo import seed_demo_profile

    inserted = seed_demo_profile(Settings.load(), count=count, force=force)
    if inserted:
        rprint(f"[green]Seeded[/green] {inserted} demo jobs into people/demo/db.sqlite")
    else:
        rprint("[yellow]Demo already populated[/yellow] (use --force to re-seed)")
    rprint("Start the dashboard:  [bold]matchbox web[/bold]")


# ──────────────────────────────────────────────
# web
# ──────────────────────────────────────────────


@app.command()
def web(
    host: str = typer.Option("127.0.0.1", "--host", "-h"),
    port: int = typer.Option(8765, "--port", "-p"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes"),
) -> None:
    """Start the FastAPI + HTMX dashboard at http://HOST:PORT."""
    import uvicorn

    rprint(f"[bold]Matchbox[/bold] starting on http://{host}:{port}")
    uvicorn.run(
        "matchbox.web.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    app()
