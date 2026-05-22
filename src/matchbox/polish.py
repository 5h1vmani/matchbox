"""Keyword-alignment polish pass (design section 5d).

After assemble, the keyword-presence check may flag must-have terms the
selected bullets do not literally contain. The brain rephrases those
bullets to carry the missing terms — but only where the new wording is
a truthful description of the same fact. Truthfulness is the brain's
responsibility; this module enforces the rules the code can guarantee:

- The polished bullet id was among the selected_ids in the original render.
- The new text satisfies shared/voice-rules.json (banned words, banned
  openers, length bounds, em-dashes, contractions).
- After applying, the cv.pdf is re-rendered and the keyword-presence
  check is re-run.

Per the design, this pass runs by default for must-have terms the
keyword-presence check flags as missing. It is not optional cosmetic.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from matchbox.core.db import PROJECT_ROOT

VOICE_RULES_PATH = PROJECT_ROOT / "shared" / "voice-rules.json"
POLISH_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "polish.v1.json"

# Em-dash characters: standard em-dash (—) and the double-hyphen
# approximation that some editors auto-convert into one.
_EM_DASH_RE = re.compile(r"—|--")

# Common English contractions. Conservative list — false-positives ("it's
# a wrap" gets flagged) are preferred to false-negatives.
_CONTRACTION_RE = re.compile(r"\b\w+'(t|ve|re|ll|d|s|m)\b", re.IGNORECASE)


@dataclass(slots=True)
class VoiceViolation:
    rule: str
    detail: str


@dataclass(slots=True)
class BulletPolish:
    """One bullet's polish proposal, validated."""

    bullet_id: int
    new_text: str
    original_text: str | None = None
    covers: list[str] = field(default_factory=list)
    violations: list[VoiceViolation] = field(default_factory=list)


def load_voice_rules() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(VOICE_RULES_PATH.read_text(encoding="utf-8"))
    return data


def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(POLISH_SCHEMA_PATH.read_text(encoding="utf-8")))


def validate_voice(text: str, rules: dict[str, Any] | None = None) -> list[VoiceViolation]:
    """Run every voice check against `text`. Returns the list of failures
    (empty list = clean)."""
    rules = rules or load_voice_rules()
    out: list[VoiceViolation] = []
    lower = text.lower()

    # Banned words: case-insensitive substring match. We use word
    # boundaries to avoid catching legitimate roots ("robust" should
    # block "robust" but not "robustly" — actually voice rules want both).
    # Use word boundary on the right side only to allow inflections.
    for word in rules.get("banned_words", []):
        if not word:
            continue
        if re.search(r"\b" + re.escape(word.lower()), lower):
            out.append(VoiceViolation(rule="banned_word", detail=word))

    # Banned openers: matches if text (trimmed) starts with one.
    # "[role]"-style placeholders in the opener pattern are treated as
    # wildcards. We substitute a token before escaping so re.escape does
    # not eat the bracket syntax.
    head = text.strip().lower()
    for opener in rules.get("banned_openers", []):
        if not opener:
            continue
        sentinel = "\x00WILDCARD\x00"
        with_wildcard = re.sub(r"\[[^\]]+\]", sentinel, opener.lower())
        escaped = re.escape(with_wildcard).replace(re.escape(sentinel), r"[^.]*")
        if re.match(escaped, head):
            out.append(VoiceViolation(rule="banned_opener", detail=opener))

    hard = rules.get("hard_rules", {})
    if hard.get("no_em_dashes") and _EM_DASH_RE.search(text):
        out.append(VoiceViolation(rule="no_em_dashes", detail="contains em dash"))
    if hard.get("no_contractions") and _CONTRACTION_RE.search(text):
        m = _CONTRACTION_RE.search(text)
        out.append(
            VoiceViolation(
                rule="no_contractions",
                detail=f"contains contraction: {m.group(0) if m else ''}",
            )
        )

    gates = rules.get("quality_gates", {})
    min_w = int(gates.get("min_word_count_cv_bullet", 0))
    max_w = int(gates.get("max_word_count_cv_bullet", 10_000))
    wc = len(text.split())
    if wc < min_w:
        out.append(VoiceViolation(rule="too_short", detail=f"{wc} words, min {min_w}"))
    if wc > max_w:
        out.append(VoiceViolation(rule="too_long", detail=f"{wc} words, max {max_w}"))

    return out


def validate_polish_payload(payload: dict[str, Any]) -> list[str]:
    """Schema-level validation. Returns plain-language errors (empty
    list = ok)."""
    errors = sorted(_validator().iter_errors(payload), key=lambda e: list(e.absolute_path))
    return [f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors]


def apply_polish_to_cv_json(
    cv_json: dict[str, Any], polished_by_id: dict[int, str]
) -> tuple[dict[str, Any], list[int]]:
    """Replace bullet texts in cv.json. Returns (new_cv_json, ids_replaced).

    Bullets in cv.json are stored as flat strings, not (id, text). We
    match by *text* against the master library to find the right slot —
    but the caller supplies bullet_id → master_text mapping via
    `original_text_by_id` if available. For v1 we do best-effort matching
    by original_text in the polish payload.
    """
    # NOTE: cv.json stores bullets as plain strings keyed only by their
    # text. The caller must do the resolution and pass us an explicit
    # mapping. This function is intentionally narrow.
    raise NotImplementedError(
        "apply_polish_to_cv_json is a placeholder. Use apply_polish() which "
        "consults the master library to map bullet ids to current text."
    )


@dataclass(slots=True)
class PolishResult:
    applied: list[BulletPolish]
    rejected: list[BulletPolish]
    cv_json_path: Path
    cv_pdf_path: Path


def apply_polish(
    *,
    conn: sqlite3.Connection,
    out_dir: Path,
    selected_ids: list[int],
    payload: dict[str, Any],
    rules: dict[str, Any] | None = None,
) -> tuple[list[BulletPolish], list[BulletPolish], dict[str, Any]]:
    """Validate the polish payload, apply truthful changes to cv.json,
    return (applied, rejected, new_cv_json). The caller re-renders the
    PDF and re-runs keyword presence.

    Truthfulness is *not* validated here — the brain owns that. The
    voice-rules.json gates form, not facts.
    """
    rules = rules or load_voice_rules()
    selected_set = set(selected_ids)

    cv_json_path = out_dir / "cv.json"
    cv_json = json.loads(cv_json_path.read_text(encoding="utf-8"))

    # Build a map id → original_text from the DB so we can find the
    # exact bullet in cv.json.
    rows = conn.execute(
        "SELECT id, text FROM bullet WHERE id IN ({})".format(",".join("?" for _ in selected_ids))
        if selected_ids
        else "SELECT id, text FROM bullet WHERE 0",
        list(selected_ids),
    ).fetchall()
    db_text_by_id = {r["id"]: r["text"] for r in rows}

    applied: list[BulletPolish] = []
    rejected: list[BulletPolish] = []

    for entry in payload.get("polished", []):
        bp = BulletPolish(
            bullet_id=entry["id"],
            new_text=entry["text"],
            original_text=entry.get("original_text"),
            covers=entry.get("covers", []),
        )

        # Gate 1: bullet was selected.
        if bp.bullet_id not in selected_set:
            bp.violations.append(
                VoiceViolation(
                    rule="not_selected",
                    detail=f"bullet {bp.bullet_id} was not in the selected set",
                )
            )
            rejected.append(bp)
            continue

        # Gate 2: voice rules.
        violations = validate_voice(bp.new_text, rules=rules)
        if violations:
            bp.violations.extend(violations)
            rejected.append(bp)
            continue

        # Apply: find the bullet's current text in cv.json by matching
        # against the DB row's text. cv.json may have already been
        # polished once — match against the master DB text *or* the
        # polish payload's original_text.
        original_db_text = db_text_by_id.get(bp.bullet_id)
        candidates = {t for t in (original_db_text, bp.original_text) if t}
        if not candidates:
            bp.violations.append(
                VoiceViolation(
                    rule="lookup_failed",
                    detail=f"could not locate bullet {bp.bullet_id} text",
                )
            )
            rejected.append(bp)
            continue

        replaced = False
        for exp in cv_json.get("experiences", []):
            bullets = exp.get("bullets", [])
            for i, t in enumerate(bullets):
                if t in candidates:
                    bullets[i] = bp.new_text
                    replaced = True
                    break
            if replaced:
                break

        if not replaced:
            bp.violations.append(
                VoiceViolation(
                    rule="not_found_in_cv",
                    detail=f"bullet {bp.bullet_id} text was not present in cv.json",
                )
            )
            rejected.append(bp)
            continue

        applied.append(bp)

    if applied:
        cv_json_path.write_text(json.dumps(cv_json, indent=2), encoding="utf-8")

    return applied, rejected, cv_json
