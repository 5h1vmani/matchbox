"""Shared text utilities.

The tokenizer is intentionally narrow: lowercase, split on every
non-alphanumeric character, no stemming. It is the same function the
scoring rubric and the BM25 index use, so consistency between "did the
matcher see this token?" and "did the scorer see this token?" is
free.
"""

from __future__ import annotations

import re
from html import unescape

TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase, split on every non-alphanumeric, no stemming.

    "Forward-Deployed Engineer · K8s" → ["forward", "deployed", "engineer", "k8s"].
    """
    return TOKEN_RE.findall(text.lower())


# ── HTML → readable plain text ───────────────────────────────────────────────
#
# Job descriptions arrive as HTML. The old strip collapsed *all* whitespace
# (newlines included) and turned every tag into a space, so paragraphs and
# bullet lists fused into one unreadable wall of text. This keeps block
# boundaries: <br> and block-level closes become newlines, <li> becomes a "• "
# bullet on its own line, and only spaces/tabs are collapsed -- newlines survive
# so a reader (and `rules.jd_paragraphs`) can split the text back into paragraphs
# and lists.

_BR_RE = re.compile(r"(?i)<br\s*/?>")
_LI_RE = re.compile(r"(?i)<li[^>]*>")
# Block-level closing tags that should end a paragraph. NOTE: </li> is absent on
# purpose -- bullets stay one-newline apart so they group as a single list.
_BLOCK_END_RE = re.compile(
    r"(?i)</(?:p|div|section|article|header|footer|ul|ol|tr|table|blockquote|h[1-6])>"
)
_TAG_RE = re.compile(r"<[^>]+>")
_INLINE_WS_RE = re.compile(r"[ \t\f\v\r]+")
_SPACE_AROUND_NL_RE = re.compile(r" *\n *")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def strip_html(html: str | None) -> str:
    """HTML → readable plain text, preserving paragraph and list structure.

    Block closes and <br> become newlines, <li> becomes a "• " bullet, remaining
    (inline) tags drop to spaces. Spaces and tabs collapse but newlines stay, so
    a list or multi-paragraph description survives as separate lines instead of
    one fused block. Replaces the old whitespace-flattening strip.
    """
    if not html:
        return ""
    t = unescape(html)
    t = _BR_RE.sub("\n", t)
    t = _LI_RE.sub("\n• ", t)
    t = _BLOCK_END_RE.sub("\n\n", t)
    t = _TAG_RE.sub(" ", t)  # any remaining (inline) tags -> space
    t = _INLINE_WS_RE.sub(" ", t)  # collapse spaces/tabs, keep newlines
    t = _SPACE_AROUND_NL_RE.sub("\n", t)  # trim spaces hugging a newline
    t = _MULTI_NL_RE.sub("\n\n", t)  # at most one blank line between blocks
    return t.strip()
