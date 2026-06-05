"""HTML + weasyprint CV renderer.

Populates the in-repo HTML/CSS template (templates/html/cv.html) from a cv.json
dict, embeds the bundled fonts as base64, and renders to PDF via weasyprint —
pure Python, no browser. pdftotext reads the output in correct reading order.

Design system (matches the Pinaka LSAT marketing pages): IBM Plex Sans for
headings + body, IBM Plex Mono for section eyebrows / dates / labels, a zinc
grey scale (heading #09090b, body #3f3f46, muted #71717a) with a single indigo
accent (#6366f1) and 1px hairline rules. ATS-safe: single column, standard
section headings, real selectable text, no tables for layout.

The renderer is tolerant: any section with no content is omitted, so a thin
cv.json and a rich one both render cleanly. palette/font args are accepted for
call-site compatibility but the look is fixed by the template.
"""

from __future__ import annotations

import base64
import html as _html
import json
from pathlib import Path
from typing import Any

from matchbox.core.db import PROJECT_ROOT

TEMPLATE = PROJECT_ROOT / "src" / "matchbox" / "templates" / "html" / "cv.html"
FONTS_DIR = PROJECT_ROOT / "shared" / "fonts"

# Bundled font files, embedded as base64 (no system-font dependency).
_FONT_FILES = {
    "__SANS_REG_B64__": "IBMPlexSans-Regular.ttf",
    "__SANS_SB_B64__": "IBMPlexSans-SemiBold.ttf",
    "__MONO_REG_B64__": "IBMPlexMono-Regular.ttf",
    "__MONO_SB_B64__": "IBMPlexMono-SemiBold.ttf",
}


def _esc(s: Any) -> str:
    return _html.escape(str(s))


def _b64(name: str) -> str:
    return base64.b64encode((FONTS_DIR / name).read_bytes()).decode("ascii")


def _section(title: str, body: str) -> str:
    if not body.strip():
        return ""
    return (
        f'<section class="section"><div class="section-header">{_esc(title)}</div>{body}</section>'
    )


def _split_contact(contact: list[str]) -> dict[str, str]:
    out = {"email": "", "phone": "", "linkedin": "", "github": "", "location": ""}
    rest: list[str] = []
    for c in contact:
        cl = c.lower()
        if "@" in c and not out["email"]:
            out["email"] = c
        elif "linkedin" in cl and not out["linkedin"]:
            out["linkedin"] = c
        elif "github" in cl and not out["github"]:
            out["github"] = c
        elif (c.strip().startswith("+") or c.strip()[:1].isdigit()) and not out["phone"]:
            out["phone"] = c
        else:
            rest.append(c)
    if rest:
        out["location"] = rest[0]
    return out


def _experience_html(experiences: list[dict[str, Any]]) -> str:
    full = [e for e in experiences if not e.get("earlier")]
    earlier = [e for e in experiences if e.get("earlier")]
    blocks: list[str] = []
    for e in full:
        bullets = "".join(f"<li>{_esc(b)}</li>" for b in e.get("bullets", []))
        loc = e.get("location")
        loc_html = f'<div class="entry-location">{_esc(loc)}</div>' if loc else ""
        dates = f'{_esc(e.get("start_date", ""))} to {_esc(e.get("end_date", ""))}'
        blocks.append(
            '<div class="entry"><div class="entry-header">'
            f'<div class="entry-title">{_esc(e.get("role", ""))}'
            f'<span class="entry-company">, {_esc(e.get("company", ""))}</span></div>'
            f'<div class="entry-dates">{dates}</div></div>'
            f'{loc_html}<ul class="entry-bullets">{bullets}</ul></div>'
        )
    if earlier:
        parts = [
            f'{_esc(e.get("company", ""))}, {_esc(e.get("role", ""))} '
            f'({_esc(e.get("location", ""))}, {_esc(e.get("start_date", ""))} '
            f'to {_esc(e.get("end_date", ""))}).'
            for e in earlier
        ]
        blocks.append('<div class="earlier"><strong>Earlier:</strong> ' + " ".join(parts) + "</div>")
    return "".join(blocks)


def cv_json_to_html(cv: dict[str, Any], *, palette: str = "slate", font: str = "ibm-plex") -> str:
    prof: dict[str, Any] = cv.get("profile", {})
    parts = _split_contact(list(prof.get("contact", [])))
    location = parts["location"] or str(prof.get("location", ""))
    visa = str(prof.get("visa_line") or prof.get("headline") or "")

    links: list[str] = []
    if parts["email"]:
        links.append(f'<a href="mailto:{_esc(parts["email"])}">{_esc(parts["email"])}</a>')
    if parts["phone"]:
        links.append(_esc(parts["phone"]))
    if parts["linkedin"]:
        links.append(f'<a href="https://{_esc(parts["linkedin"])}">{_esc(parts["linkedin"])}</a>')
    if parts["github"]:
        links.append(f'<a href="https://{_esc(parts["github"])}">{_esc(parts["github"])}</a>')
    sep = '<span class="sep">/</span>'
    line2 = _esc(location) + (f' {sep} {_esc(visa)}' if visa else "")
    header = (
        '<header class="header">'
        f'<div class="name">{_esc(prof.get("name", ""))}</div>'
        f'<div class="header-meta">{line2}</div>'
        f'<div class="header-meta">{(" " + sep + " ").join(links)}</div>'
        "</header>"
    )

    summary = _section(
        "Summary",
        f'<div class="summary">{_esc(cv["summary"])}</div>' if cv.get("summary") else "",
    )
    comps = cv.get("competencies") or []
    comp_html = (
        '<div class="competencies">'
        + "".join(f'<span class="competency">{_esc(c)}</span>' for c in comps)
        + "</div>"
        if comps
        else ""
    )
    competencies = _section("Core Competencies", comp_html)
    experience = _section("Experience", _experience_html(cv.get("experiences", [])))

    proj_html = ""
    for p in cv.get("projects", []):
        url = f' <a href="{_esc(p["url"])}">{_esc(p["url"])}</a>' if p.get("url") else ""
        proj_html += (
            '<div class="entry"><div class="entry-header">'
            f'<div class="entry-title">{_esc(p.get("name", ""))}</div></div>'
            f'<div class="entry-description">{_esc(p.get("text", ""))}{url}</div></div>'
        )
    projects = _section("Projects", proj_html)

    edu_html = ""
    for ed in cv.get("education", []):
        dates = _esc(ed["dates"]) if ed.get("dates") else _esc(ed.get("end_date", ""))
        edu_html += (
            '<div class="education-entry"><div>'
            f'<span class="degree">{_esc(ed.get("degree", ""))}</span> '
            f'<span class="school">{_esc(ed.get("school", ""))}</span></div>'
            f'<div class="dates">{dates}</div></div>'
        )
    education = _section("Education", edu_html)

    skills_html = "".join(
        f'<div class="skills-row"><span class="label">{_esc(s.get("category", ""))}:</span> '
        f'{_esc(", ".join(s.get("items", [])))}</div>'
        for s in cv.get("skills", [])
    )
    skills = _section("Skills", skills_html)

    body = "\n".join(
        x for x in (header, summary, competencies, experience, projects, education, skills) if x
    )

    tpl = TEMPLATE.read_text(encoding="utf-8")
    subs = {"{{NAME}}": _esc(prof.get("name", "")), "{{BODY}}": body}
    subs.update({ph: _b64(fn) for ph, fn in _FONT_FILES.items()})
    for key, val in subs.items():
        tpl = tpl.replace(key, val)
    return tpl


def render_cv_pdf(
    cv_json_path: Path,
    out_path: Path,
    *,
    palette: str = "slate",
    font: str = "ibm-plex",
) -> None:
    """Render cv.json to a PDF via the HTML template + weasyprint."""
    from weasyprint import HTML  # type: ignore[import-untyped]

    cv = json.loads(cv_json_path.read_text(encoding="utf-8"))
    html_str = cv_json_to_html(cv, palette=palette, font=font)
    (cv_json_path.parent / "cv.html").write_text(html_str, encoding="utf-8")
    HTML(string=html_str, base_url=str(cv_json_path.parent)).write_pdf(str(out_path))
