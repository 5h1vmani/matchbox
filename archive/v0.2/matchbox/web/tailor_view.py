"""Web-facing tailor adapter.

Wraps `matchbox.tailor.paths.tailor_job` so the UI can:
  - estimate cost before running (no LLM call)
  - capture gate violations for visual display, instead of just logging them
  - return None for skip-tier without losing the user's intent

This module is the only place the web layer touches the tailor pipeline,
keeping `web/routes/*` ignorant of LLM internals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from matchbox.core.schema import Application, Job, Person, VoiceRules
from matchbox.tailor.gates import GateViolation, run_all_gates
from matchbox.tailor.paths import tailor_job

log = logging.getLogger(__name__)


# Heuristic per-tier estimates. Sourced from README cost table; refined as
# real telemetry accumulates. Returned as (low, high) so the UI can show a
# range rather than a false-precision point estimate.
_COST_RANGE_USD: dict[str, tuple[float, float]] = {
    "bespoke": (10.0, 20.0),
    "template": (0.05, 0.30),
    "canonical": (0.0, 0.0),
    "skip": (0.0, 0.0),
}


@dataclass(frozen=True)
class CostEstimate:
    tier: str
    low_usd: float
    high_usd: float
    requires_llm: bool

    @property
    def midpoint_usd(self) -> float:
        return (self.low_usd + self.high_usd) / 2

    def needs_confirmation(self, threshold_usd: float) -> bool:
        return self.requires_llm and self.high_usd >= threshold_usd


def estimate(job: Job) -> CostEstimate:
    tier = job.tier or "canonical"
    low, high = _COST_RANGE_USD.get(tier, (0.0, 0.0))
    return CostEstimate(
        tier=tier,
        low_usd=low,
        high_usd=high,
        requires_llm=tier in ("bespoke", "template"),
    )


def alternative_tier(current: str) -> str | None:
    """Cheaper alternative the user can downgrade to. None if already cheapest."""
    chain = ["bespoke", "template", "canonical", "skip"]
    if current not in chain:
        return None
    idx = chain.index(current)
    return chain[idx + 1] if idx + 1 < len(chain) else None


@dataclass(frozen=True)
class TailorOutcome:
    application: Application | None  # None for skip tier
    violations: list[GateViolation]
    error: str | None = None


def run(
    job: Job,
    person: Person,
    *,
    tier_override: str | None = None,
    model: str = "claude-sonnet-4-6",
) -> TailorOutcome:
    """Execute a tailor with `gate_mode='warn'` and capture violations."""
    target_job = job.model_copy(update={"tier": tier_override}) if tier_override else job
    try:
        app = tailor_job(target_job, person, model=model, gate_mode="warn")
    except Exception as exc:  # noqa: BLE001 — surface error to UI, don't crash route
        log.exception("tailor failed for job_id=%s", job.id)
        return TailorOutcome(application=None, violations=[], error=str(exc))

    violations = _extract_violations(app, person.voice) if app else []
    return TailorOutcome(application=app, violations=violations)


def _extract_violations(app: Application, voice: VoiceRules) -> list[GateViolation]:
    """Re-run gates against generated content for display purposes."""
    content = app.content or {}
    bullets = [
        b for entry in content.get("selected_work_history", []) for b in entry.get("bullets", [])
    ]
    cover_text = " ".join(
        [
            content.get("cover_opening", ""),
            *content.get("cover_body", []),
            content.get("cover_closing", ""),
        ]
    )
    return run_all_gates(bullets, cover_text, voice)
