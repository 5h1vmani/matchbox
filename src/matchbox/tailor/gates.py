"""Quality gates — deterministic Python checks, zero LLM cost.

Gates run on generated text (bullets, cover paragraphs) before PDF render.
All violations are collected and surfaced together rather than failing fast,
so the operator sees the full picture and can decide to override or re-generate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from matchbox.core.exceptions import GateFailureError
from matchbox.core.schema import VoiceRules


@dataclass(frozen=True)
class GateViolation:
    gate: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.gate}] {self.detail}"


# ──────────────────────────────────────────────
# Individual gate checks
# ──────────────────────────────────────────────


def check_bullet_length(bullet: str, voice: VoiceRules) -> list[GateViolation]:
    words = bullet.split()
    n = len(words)
    violations: list[GateViolation] = []
    if n < voice.quality_gates.min_word_count_cv_bullet:
        violations.append(
            GateViolation(
                "bullet_too_short",
                f"{n} words (min {voice.quality_gates.min_word_count_cv_bullet}): {bullet[:60]!r}",
            )
        )
    if n > voice.quality_gates.max_word_count_cv_bullet:
        violations.append(
            GateViolation(
                "bullet_too_long",
                f"{n} words (max {voice.quality_gates.max_word_count_cv_bullet}): {bullet[:60]!r}",
            )
        )
    return violations


def check_banned_words(text: str, voice: VoiceRules) -> list[GateViolation]:
    text_lower = text.lower()
    return [
        GateViolation("banned_word", f"found {w!r} in text")
        for w in voice.banned_words
        if re.search(r"\b" + re.escape(w.lower()) + r"\b", text_lower)
    ]


def check_banned_openers(text: str, voice: VoiceRules) -> list[GateViolation]:
    """Cover letter opener check — first 120 characters only."""
    prefix = text[:120].lower()
    return [
        GateViolation("banned_opener", f"starts with {op!r}")
        for op in voice.banned_openers
        if prefix.startswith(op.lower())
    ]


def check_required_signals(text: str, voice: VoiceRules) -> list[GateViolation]:
    """Check quantified claims and named entities per 150 words."""
    words = text.split()
    if not words:
        return []
    chunks = max(1, len(words) // 150)
    violations: list[GateViolation] = []

    # Numbers: digits, percentages, monetary values
    number_matches = re.findall(r"\b\d[\d,\.]*\s*(?:%|k|M|B|LPA|CCU|ms|s)?\b", text)
    numbers_per_chunk = len(number_matches) / chunks
    if numbers_per_chunk < voice.required_signals.min_numbers_per_150_words:
        violations.append(
            GateViolation(
                "insufficient_numbers",
                f"{len(number_matches)} numbers found, need "
                f"{voice.required_signals.min_numbers_per_150_words * chunks:.0f}+",
            )
        )
    return violations


def check_no_em_dashes(text: str, voice: VoiceRules) -> list[GateViolation]:
    if voice.no_em_dashes and "—" in text:
        return [GateViolation("em_dash", "em dash found — replace with comma or semicolon")]
    return []


def check_no_contractions(text: str, voice: VoiceRules) -> list[GateViolation]:
    if not voice.no_contractions:
        return []
    pattern = r"\b(?:don't|can't|won't|I'm|I've|I'd|it's|there's|we're|we've|they're|you're)\b"
    found = re.findall(pattern, text, re.IGNORECASE)
    if found:
        return [GateViolation("contraction", f"contractions found: {', '.join(set(found))}")]
    return []


# ──────────────────────────────────────────────
# Aggregated runners
# ──────────────────────────────────────────────


def run_bullet_gates(bullet: str, voice: VoiceRules) -> list[GateViolation]:
    """All gates applicable to a single CV bullet."""
    violations: list[GateViolation] = []
    violations.extend(check_bullet_length(bullet, voice))
    violations.extend(check_banned_words(bullet, voice))
    violations.extend(check_no_em_dashes(bullet, voice))
    violations.extend(check_no_contractions(bullet, voice))
    return violations


def run_cover_gates(cover_text: str, voice: VoiceRules) -> list[GateViolation]:
    """All gates applicable to a cover letter body."""
    violations: list[GateViolation] = []
    violations.extend(check_banned_words(cover_text, voice))
    violations.extend(check_banned_openers(cover_text, voice))
    violations.extend(check_required_signals(cover_text, voice))
    violations.extend(check_no_em_dashes(cover_text, voice))
    violations.extend(check_no_contractions(cover_text, voice))
    return violations


def run_all_gates(
    bullets: Sequence[str],
    cover_text: str,
    voice: VoiceRules,
    *,
    raise_on_fail: bool = False,
) -> list[GateViolation]:
    """Run all bullet + cover gates. Returns combined violation list."""
    violations: list[GateViolation] = []
    for bullet in bullets:
        violations.extend(run_bullet_gates(bullet, voice))
    violations.extend(run_cover_gates(cover_text, voice))

    if raise_on_fail and violations:
        msg = "\n".join(str(v) for v in violations)
        raise GateFailureError(f"{len(violations)} gate violation(s):\n{msg}")

    return violations
