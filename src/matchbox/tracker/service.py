"""Tracker action effects — ported from designs/v1/store.jsx, in date terms.

Each action mutates the row, appends a history event, and returns the updated
view-model. Authoritative: the SPA store calls these and renders the response.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from matchbox.tracker import repo, rules

App = dict[str, Any] | None


def _set_next_action(updates: dict[str, Any], na: rules.DefaultAction | None) -> None:
    if na is None:
        updates.update(
            next_action=None, next_action_kind=None, next_action_at=None, next_action_time=None
        )
    else:
        kind, label, due, time = na
        updates.update(
            next_action=label,
            next_action_kind=kind,
            next_action_at=rules.date_in(due),
            next_action_time=time,
        )


def advance_stage(conn: sqlite3.Connection, app_id: int) -> App:
    row = repo.raw(conn, app_id)
    if row is None:
        return None
    stage = row["stage"]
    if stage not in rules.FLOW or rules.FLOW.index(stage) >= len(rules.FLOW) - 1:
        return repo.load_one(conn, app_id)
    nxt = rules.FLOW[rules.FLOW.index(stage) + 1]
    updates: dict[str, Any] = {"stage": nxt}
    _set_next_action(updates, rules.default_action_for(nxt))
    if row["applied_at"] is None:
        updates["applied_at"] = rules.today().isoformat()
    repo.update_app(conn, app_id, **updates)
    repo.add_event(conn, app_id, "advanced", "Moved to " + rules.stage_label(nxt).lower())
    return repo.load_one(conn, app_id)


def _close_reason(value: str | None) -> str | None:
    """Normalize a captured close reason to the controlled vocab (or 'other'
    when something non-empty but unrecognized is sent). None stays None ->
    reads as 'unknown' in the rollup."""
    if value is None:
        return None
    v = value.strip().lower()
    if not v:
        return None
    return v if v in rules.CLOSE_REASONS else "other"


def set_stage(
    conn: sqlite3.Connection, app_id: int, stage: str, close_reason: str | None = None
) -> App:
    row = repo.raw(conn, app_id)
    if row is None:
        return None
    if row["stage"] == stage:
        return repo.load_one(conn, app_id)
    closing = stage == "rejected"
    updates: dict[str, Any] = {"stage": stage}
    if closing:
        reason = _close_reason(close_reason)
        if reason is not None:
            updates["close_reason"] = reason
    _set_next_action(updates, None if closing else rules.default_action_for(stage))
    repo.update_app(conn, app_id, **updates)
    repo.add_event(
        conn,
        app_id,
        "rejected" if closing else "advanced",
        "Marked closed" if closing else "Moved to " + rules.stage_label(stage).lower(),
    )
    return repo.load_one(conn, app_id)


def snooze(conn: sqlite3.Connection, app_id: int, days: int = 2) -> App:
    row = repo.raw(conn, app_id)
    if row is None:
        return None
    if not row["next_action"]:
        return repo.load_one(conn, app_id)
    repo.update_app(conn, app_id, next_action_at=rules.shift(row["next_action_at"], days))
    return repo.load_one(conn, app_id)


def remind(conn: sqlite3.Connection, app_id: int, days: int) -> App:
    row = repo.raw(conn, app_id)
    if row is None:
        return None
    updates: dict[str, Any] = {"next_action_at": rules.date_in(days)}
    if not row["next_action"]:
        updates.update(
            next_action="Send follow-up", next_action_kind="followup", next_action_time=None
        )
    repo.update_app(conn, app_id, **updates)
    repo.add_event(
        conn, app_id, "note", "Reminder set for " + ("today" if days == 0 else f"in {days}d")
    )
    return repo.load_one(conn, app_id)


def mark_done(conn: sqlite3.Connection, app_id: int) -> App:
    row = repo.raw(conn, app_id)
    if row is None:
        return None
    k = row["next_action_kind"]
    verbs = {
        "followup": "Follow-up sent",
        "thanks": "Thank-you sent",
        "prep": "Prep done",
        "apply": "Applied",
        "interview": "Interview done",
    }
    verb = verbs.get(k or "", "Done")
    ev_kind = "applied" if k == "apply" else "screen" if k == "interview" else "followup"

    updates: dict[str, Any] = {"has_draft": 0}
    stage = row["stage"]
    if k == "apply":
        stage = "applied"
        updates["stage"] = "applied"
        if row["applied_at"] is None:
            updates["applied_at"] = rules.today().isoformat()
    if stage == "applied" and k == "followup":
        _set_next_action(updates, ("wait", "Waiting to hear back", None, None))
    else:
        _set_next_action(updates, None)
    repo.update_app(conn, app_id, **updates)
    repo.add_event(conn, app_id, ev_kind, verb)
    return repo.load_one(conn, app_id)


def log_response(
    conn: sqlite3.Connection, app_id: int, rtype: str, close_reason: str | None = None
) -> App:
    row = repo.raw(conn, app_id)
    if row is None:
        return None
    if rtype == "reply":
        updates: dict[str, Any] = {}
        if row["stage"] == "applied":
            updates["stage"] = "phone"
            _set_next_action(updates, rules.default_action_for("phone"))
        elif not row["next_action"]:
            _set_next_action(updates, rules.default_action_for(row["stage"]))
        if updates:
            repo.update_app(conn, app_id, **updates)
        repo.add_event(conn, app_id, "reply", "Heard back — positive")
    elif rtype == "rejected":
        updates = {"stage": "rejected"}
        reason = _close_reason(close_reason)
        if reason is not None:
            updates["close_reason"] = reason
        _set_next_action(updates, None)
        repo.update_app(conn, app_id, **updates)
        repo.add_event(conn, app_id, "rejected", "No longer moving forward")
    elif rtype == "ghosted":
        updates = {}
        _set_next_action(updates, None)
        repo.update_app(conn, app_id, **updates)
        # No bump: clearing the action should let it read as cold, per the design.
        repo.add_event(conn, app_id, "note", "Marked as no response", bump=False)
    return repo.load_one(conn, app_id)


def add_note(conn: sqlite3.Connection, app_id: int, text: str) -> App:
    if not text or not text.strip():
        return repo.load_one(conn, app_id)
    repo.add_note(conn, app_id, text.strip())
    repo.add_event(conn, app_id, "note", "Added a note")
    return repo.load_one(conn, app_id)


def toggle_star(conn: sqlite3.Connection, app_id: int) -> App:
    row = repo.raw(conn, app_id)
    if row is None:
        return None
    repo.update_app(conn, app_id, starred=0 if row["starred"] else 1)
    return repo.load_one(conn, app_id)


def submit(conn: sqlite3.Connection, app_id: int) -> App:
    """The Apply packet's Submit: move an application to `applied`, stamp
    `applied_at`, and seed the +7d follow-up reminder. Reuses the tracker rules;
    idempotent on applied_at."""
    row = repo.raw(conn, app_id)
    if row is None:
        return None
    updates: dict[str, Any] = {"stage": "applied"}
    if row["applied_at"] is None:
        updates["applied_at"] = rules.today().isoformat()
    _set_next_action(updates, rules.default_action_for("applied"))
    repo.update_app(conn, app_id, **updates)
    repo.add_event(conn, app_id, "applied", "Applied from packet")
    return repo.load_one(conn, app_id)
