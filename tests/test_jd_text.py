"""HTML → readable plain text (core.text.strip_html) and JD paragraph splitting
(discovery_api.rules.jd_paragraphs). The pair is what makes the JD drawer
readable instead of a single fused block."""

from __future__ import annotations

from matchbox.core.text import strip_html
from matchbox.discovery_api.rules import jd_lead, jd_paragraphs


def test_strip_html_preserves_paragraphs() -> None:
    out = strip_html("<p>First para.</p><p>Second para.</p>")
    assert out == "First para.\n\nSecond para."
    assert jd_paragraphs(out) == ["First para.", "Second para."]


def test_strip_html_turns_list_items_into_bullets() -> None:
    out = strip_html("<p>We want:</p><ul><li>Python</li><li>SQL</li></ul>")
    # Bullets stay one newline apart so the reader groups them into one list.
    assert "• Python\n• SQL" in out
    paras = jd_paragraphs(out)
    assert "We want:" in paras[0]
    assert any("• Python" in p and "• SQL" in p for p in paras)


def test_strip_html_br_becomes_newline() -> None:
    assert strip_html("a<br>b") == "a\nb"
    assert strip_html("a<br/>b") == "a\nb"


def test_strip_html_unescapes_entities_and_drops_inline_tags() -> None:
    assert strip_html("R&amp;D with <b>impact</b>") == "R&D with impact"


def test_strip_html_collapses_spaces_but_keeps_breaks() -> None:
    assert strip_html("<p>one   two</p>\n\n\n<p>three</p>") == "one two\n\nthree"


def test_strip_html_empty() -> None:
    assert strip_html(None) == ""
    assert strip_html("") == ""


def test_jd_paragraphs_reparagraphs_legacy_flat_block() -> None:
    # Legacy rows were stored as one structureless block by the old stripper.
    flat = (
        "We are hiring a backend engineer. Responsibilities: build APIs and own "
        "services. Requirements: 5 years Python and strong SQL."
    )
    paras = jd_paragraphs(flat)
    assert len(paras) == 3
    assert paras[0].startswith("We are hiring")
    assert paras[1].startswith("Responsibilities:")
    assert paras[2].startswith("Requirements:")


def test_jd_paragraphs_does_not_oversplit_plain_prose() -> None:
    # No "Label:" sections -> one paragraph (no false breaks on common words).
    text = "A short role description with skills in python and sql, nothing else."
    assert jd_paragraphs(text) == [text]


def test_jd_lead_is_first_paragraph_only() -> None:
    assert jd_lead("Line one.\n\nLine two.\n\nLine three.") == "Line one."
    # A flat block (no newlines) returns the whole block cheaply -- the teaser
    # trims it; it must NOT pay for full reparagraphing.
    flat = "Who we are We build things and ship fast every single day in the team."
    assert jd_lead(flat) == flat
    assert jd_lead("") == ""
    assert jd_lead(None) == ""


def test_jd_paragraphs_splits_colonless_headers() -> None:
    # The real-world legacy case: section headers with no colon, no newlines.
    flat = (
        "Who we are We are a small team. About the role You will own the product "
        "and ship fast. Nice to have Experience with Python."
    )
    paras = jd_paragraphs(flat)
    assert any(p.startswith("Who we are") for p in paras)
    assert any(p.startswith("About the role") for p in paras)
    assert any(p.startswith("Nice to have") for p in paras)


def test_jd_paragraphs_never_leaves_a_wall() -> None:
    # A flattened bullet list (no sentence punctuation) must be wrapped, never
    # left as one giant paragraph.
    wall = "Own integrations end to end and " * 80  # ~2600 chars, no periods
    paras = jd_paragraphs(wall)
    assert len(paras) > 1
    assert max(len(p) for p in paras) <= 560
