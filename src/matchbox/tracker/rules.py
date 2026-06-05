"""Pure tracker rules — ported from the design (store.jsx / Today.jsx / §07).

Stage flow, default next actions, staleness, monogram colours, and the date
helpers that bridge the persisted ISO dates and the view-model's relative
`daysAgo` / `due` integers. SSOT for the Python side.
"""

from __future__ import annotations

from datetime import date, timedelta

# Linear progression; `rejected` ("Closed") is off-flow and terminal.
FLOW = ["saved", "applied", "phone", "onsite", "offer"]

# Structured rejection categories captured at close. Anything outside this set
# (or simply not captured) is treated as "unknown" by the rejection-reason
# rollup -- we never infer a cause.
CLOSE_REASONS = (
    "role_filled",
    "not_a_fit",
    "comp",
    "location",
    "timing",
    "ghosted",
    "withdrew",
    "other",
    "unknown",
)

STAGE_LABELS = {
    "saved": "Saved",
    "applied": "Applied",
    "phone": "Phone screen",
    "onsite": "Onsite",
    "offer": "Offer",
    "rejected": "Closed",
}

# (kind, label, due_days, time)
DefaultAction = tuple[str, str, int | None, str | None]


def stage_label(stage: str) -> str:
    return STAGE_LABELS.get(stage, stage)


def default_action_for(stage: str) -> DefaultAction | None:
    # These are reminders -- a due-date computed on read (`due_from`), not a
    # scheduled task (there is no scheduler). The applied follow-up sits at +7d.
    return {
        "applied": ("followup", "Send follow-up", 7, None),
        "phone": ("prep", "Prep screening notes", 2, None),
        "onsite": ("interview", "Onsite interview", 3, "13:00"),
        "offer": ("offer", "Respond to offer", 5, None),
    }.get(stage)


# Deterministic monogram palette (bg, fg), matching the design's swatches.
MONO = [
    ("#ede8e8", "#574747"),
    ("#e7f0ea", "#2f6b46"),
    ("#eceaf3", "#5b4b86"),
    ("#f1ece4", "#8a5a1f"),
    ("#e7eef2", "#2f5d72"),
    ("#f2e9ea", "#86304a"),
    ("#eef1e6", "#566b2f"),
    ("#efe9e9", "#6b4a4a"),
]


def mono_for(company: str) -> dict[str, str]:
    """Stable monogram colours derived from the company name."""
    bg, fg = MONO[sum(ord(c) for c in company) % len(MONO)]
    return {"bg": bg, "fg": fg}


def today() -> date:
    return date.today()


def _d(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def days_since(s: str | None) -> int | None:
    """Whole days between an ISO date/timestamp and today (>=0 in the past)."""
    d = _d(s)
    return (today() - d).days if d is not None else None


def due_from(s: str | None) -> int | None:
    """next_action_at -> due in days from today (negative = overdue)."""
    d = _d(s)
    return (d - today()).days if d is not None else None


def date_in(days: int | None) -> str | None:
    """due in days -> ISO date string (None passes through)."""
    return (today() + timedelta(days=days)).isoformat() if days is not None else None


def shift(s: str | None, days: int) -> str:
    """Push a date (or today, if absent) out by `days`, as an ISO date."""
    base = _d(s) or today()
    return (base + timedelta(days=days)).isoformat()


def is_stale(stage: str, next_due: int | None, updated_days: int | None) -> bool:
    """Going-cold rule (handoff §07): active, no imminent action, untouched."""
    active = stage in ("applied", "phone", "onsite")
    imminent = next_due is not None and next_due <= 3
    return active and not imminent and (updated_days or 0) >= 11
