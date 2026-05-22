"""Jinja filters — formatting helpers used across templates.

Single source of truth for human-facing formatting (money, dates, scores).
Templates never format these inline.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from jinja2 import Environment


def usd(value: float | None, *, precision: int = 2) -> str:
    if value is None:
        return "—"
    return f"${value:,.{precision}f}"


def score(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


def pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}%"


def relative_time(value: str | None) -> str:
    """Convert ISO timestamp/date to '3d ago' / '2h ago' / 'just now'."""
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            d = date.fromisoformat(value)
            dt = datetime(d.year, d.month, d.day, tzinfo=UTC)
        except ValueError:
            return value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    days = seconds // 86400
    if days < 30:
        return f"{days}d ago"
    if days < 365:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"


def short_date(value: str | None) -> str:
    if not value:
        return "—"
    return value[:10]


_TIER_CLASSES = {
    "bespoke": "bg-rose-100 text-rose-800 ring-rose-200",
    "template": "bg-amber-100 text-amber-800 ring-amber-200",
    "canonical": "bg-emerald-100 text-emerald-800 ring-emerald-200",
    "skip": "bg-slate-100 text-slate-600 ring-slate-200",
}

_STATE_CLASSES = {
    "evaluated": "bg-slate-100 text-slate-700 ring-slate-200",
    "queued_for_tailor": "bg-violet-100 text-violet-800 ring-violet-200",
    "tailored": "bg-sky-100 text-sky-800 ring-sky-200",
    "applied": "bg-orange-100 text-orange-800 ring-orange-200",
    "responded": "bg-cyan-100 text-cyan-800 ring-cyan-200",
    "interview": "bg-lime-100 text-lime-800 ring-lime-200",
    "offer": "bg-emerald-100 text-emerald-900 ring-emerald-300",
    "rejected": "bg-rose-100 text-rose-800 ring-rose-200",
    "discarded": "bg-zinc-100 text-zinc-600 ring-zinc-200",
    "skip": "bg-zinc-100 text-zinc-600 ring-zinc-200",
    "cooling": "bg-stone-100 text-stone-700 ring-stone-200",
}


def tier_class(tier: str | None) -> str:
    return _TIER_CLASSES.get(tier or "skip", _TIER_CLASSES["skip"])


def state_class(state: str | None) -> str:
    return _STATE_CLASSES.get(state or "evaluated", _STATE_CLASSES["evaluated"])


def score_color(value: float | None) -> str:
    """Tailwind text/bg color matched to score band."""
    if value is None:
        return "text-slate-400"
    if value >= 4.0:
        return "text-emerald-600"
    if value >= 3.0:
        return "text-sky-600"
    if value >= 2.0:
        return "text-amber-600"
    return "text-slate-500"


def register(env: Environment) -> None:
    env.filters["usd"] = usd
    env.filters["score"] = score
    env.filters["pct"] = pct
    env.filters["relative_time"] = relative_time
    env.filters["short_date"] = short_date
    env.filters["tier_class"] = tier_class
    env.filters["state_class"] = state_class
    env.filters["score_color"] = score_color
    env.globals["remove_qs_param"] = remove_qs_param


def remove_qs_param(qs: str, param: str, value: str = "") -> str:
    """Build a query string with (param, value) removed.

    If value is empty, all values for `param` are stripped.
    Used by the inbox filter chips to make each chip individually removable.
    """
    from urllib.parse import parse_qsl, urlencode

    pairs = parse_qsl(qs.lstrip("?"), keep_blank_values=False)
    if value:
        pairs = [(k, v) for k, v in pairs if not (k == param and v == value)]
    else:
        pairs = [(k, v) for k, v in pairs if k != param]
    return ("?" + urlencode(pairs)) if pairs else ""
