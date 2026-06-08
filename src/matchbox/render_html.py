"""HTML + weasyprint CV and cover-letter renderer.

Populates the in-repo HTML/CSS template (templates/html/cv.html) from a cv.json
dict, embeds the bundled fonts as base64, and renders to PDF via weasyprint —
pure Python, no browser. pdftotext reads the output in correct reading order.

Design system (matches the Pinaka LSAT marketing pages): IBM Plex Sans for
headings + body, IBM Plex Mono for section eyebrows / dates / labels, a zinc
grey scale (heading #09090b, body #27272a, muted #52525b) with 1px hairline
rules. Body and muted text both clear WCAG AAA (>=7:1) on white. ATS-safe:
single column, standard section headings, real selectable text, no layout tables.

The renderer is tolerant: any section with no content is omitted, so a thin
cv.json and a rich one both render cleanly. palette/font args are accepted for
call-site compatibility but the look is fixed by the template.

render_cover_pdf renders a plain-text cover letter body (cover.txt) to PDF
using the same fonts, colours, and page size as render_cv_pdf. No Typst needed.
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
        dates = f"{_esc(e.get('start_date', ''))} to {_esc(e.get('end_date', ''))}"
        blocks.append(
            '<div class="entry"><div class="entry-header">'
            f'<div class="entry-title">{_esc(e.get("role", ""))}'
            f'<span class="entry-company">, {_esc(e.get("company", ""))}</span></div>'
            f'<div class="entry-dates">{dates}</div></div>'
            f'{loc_html}<ul class="entry-bullets">{bullets}</ul></div>'
        )
    if earlier:
        parts = [
            f"{_esc(e.get('company', ''))}, {_esc(e.get('role', ''))} "
            f"({_esc(e.get('location', ''))}, {_esc(e.get('start_date', ''))} "
            f"to {_esc(e.get('end_date', ''))})."
            for e in earlier
        ]
        blocks.append(
            '<div class="earlier"><strong>Earlier:</strong> ' + " ".join(parts) + "</div>"
        )
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
    line2 = _esc(location) + (f" {sep} {_esc(visa)}" if visa else "")
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
        f"{_esc(', '.join(s.get('items', [])))}</div>"
        for s in cv.get("skills", [])
    )
    skills = _section("Skills", skills_html)

    # Skills before Education: for an experienced candidate the recruiter and the
    # ATS want the stack before the degrees. Education sits last.
    body = "\n".join(
        x for x in (header, summary, competencies, experience, projects, skills, education) if x
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
    from weasyprint import HTML

    cv = json.loads(cv_json_path.read_text(encoding="utf-8"))
    html_str = cv_json_to_html(cv, palette=palette, font=font)
    (cv_json_path.parent / "cv.html").write_text(html_str, encoding="utf-8")
    HTML(string=html_str, base_url=str(cv_json_path.parent)).write_pdf(str(out_path))


# ─── cover-letter renderer ────────────────────────────────────────────────────

_COVER_CSS = """\
@font-face {{ font-family:'IBM Plex Sans'; font-style:normal; font-weight:400; src:url(data:font/ttf;base64,{sans_reg}) format('truetype'); }}
@font-face {{ font-family:'IBM Plex Sans'; font-style:normal; font-weight:600; src:url(data:font/ttf;base64,{sans_sb}) format('truetype'); }}
@font-face {{ font-family:'IBM Plex Mono'; font-style:normal; font-weight:400; src:url(data:font/ttf;base64,{mono_reg}) format('truetype'); }}
@font-face {{ font-family:'IBM Plex Mono'; font-style:normal; font-weight:600; src:url(data:font/ttf;base64,{mono_sb}) format('truetype'); }}

* {{ margin:0; padding:0; box-sizing:border-box; }}
@page {{ size:A4; margin:20mm 20mm 20mm 20mm; }}
html, body {{
  font-family:'IBM Plex Sans', system-ui, sans-serif; font-size:12.5px; line-height:1.6;
  color:#3f3f46; background:#ffffff; -webkit-font-smoothing:antialiased;
}}
.page {{ max-width:100%; }}
.sender-name {{ font-weight:600; font-size:18px; letter-spacing:-0.01em; color:#09090b; margin-bottom:3px; }}
.sender-contact {{
  font-family:'IBM Plex Mono'; font-size:10px; color:#696970; margin-bottom:16px;
  border-bottom:1px solid #e4e4e7; padding-bottom:14px;
}}
.sender-contact .sep {{ color:#d4d4d8; margin:0 6px; }}
.cover-date {{ font-family:'IBM Plex Mono'; font-size:10px; color:#696970; margin-bottom:14px; }}
.recipient {{ margin-bottom:14px; }}
.recipient p {{ font-size:12.5px; color:#3f3f46; line-height:1.5; }}
.salutation {{ margin-bottom:12px; font-size:12.5px; color:#3f3f46; }}
.body p {{ font-size:12.5px; color:#3f3f46; line-height:1.65; margin-bottom:12px; text-align:left; }}
.closing {{ margin-top:16px; }}
.closing .closing-line {{ font-size:12.5px; color:#3f3f46; margin-bottom:20px; }}
.closing .sig-name {{ font-weight:600; font-size:13px; color:#09090b; }}
@media print {{
  html, body {{ background:#ffffff; -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
}}
"""


def cover_data_to_html(
    *,
    body_text: str,
    profile: dict[str, Any],
    palette: str = "slate",
    font: str = "ibm-plex",
) -> str:
    """Build a standalone HTML string for a cover letter.

    ``body_text`` is the raw plain-text body (blank lines separate paragraphs).
    ``profile`` must have at minimum ``candidate_name``; optionally ``contact``
    (list[str]), ``date``, ``recipient`` (list[str]), ``salutation``, ``closing``.

    palette and font args are accepted for call-site compatibility but the visual
    style is fixed to match the CV template.
    """
    css = _COVER_CSS.format(
        sans_reg=_b64("IBMPlexSans-Regular.ttf"),
        sans_sb=_b64("IBMPlexSans-SemiBold.ttf"),
        mono_reg=_b64("IBMPlexMono-Regular.ttf"),
        mono_sb=_b64("IBMPlexMono-SemiBold.ttf"),
    )

    name = _esc(profile.get("candidate_name", ""))

    # Contact line — join with separator
    contact_items: list[str] = list(profile.get("contact", []))
    sep = '<span class="sep">/</span>'
    contact_html = (" " + sep + " ").join(_esc(c) for c in contact_items) if contact_items else ""

    date_html = (
        f'<div class="cover-date">{_esc(profile.get("date", ""))}</div>'
        if profile.get("date")
        else ""
    )

    recipient_lines: list[str] = list(profile.get("recipient", []))
    recipient_html = (
        '<div class="recipient">'
        + "".join(f"<p>{_esc(line)}</p>" for line in recipient_lines)
        + "</div>"
        if recipient_lines
        else ""
    )

    salutation_html = (
        f'<div class="salutation">{_esc(profile.get("salutation", ""))}</div>'
        if profile.get("salutation")
        else ""
    )

    # Split body on blank lines → paragraphs
    paragraphs = [p.strip() for p in body_text.split("\n\n") if p.strip()]
    body_html = (
        '<div class="body">' + "".join(f"<p>{_esc(para)}</p>" for para in paragraphs) + "</div>"
    )

    closing = _esc(profile.get("closing", "Sincerely,"))
    closing_html = (
        '<div class="closing">'
        f'<div class="closing-line">{closing}</div>'
        f'<div class="sig-name">{name}</div>'
        "</div>"
    )

    body_block = "\n".join(
        x
        for x in (
            f'<div class="sender-name">{name}</div>',
            f'<div class="sender-contact">{contact_html}</div>' if contact_html else "",
            date_html,
            recipient_html,
            salutation_html,
            body_html,
            closing_html,
        )
        if x
    )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="UTF-8">\n'
        f"  <title>{name} — Cover Letter</title>\n"
        f"  <style>{css}</style>\n"
        "</head>\n"
        "<body>\n"
        '  <div class="page">\n'
        f"{body_block}\n"
        "  </div>\n"
        "</body>\n"
        "</html>\n"
    )


def render_cover_pdf(
    cover_txt_path_or_text: Path | str,
    out_path: Path,
    *,
    profile: dict[str, Any],
    palette: str = "slate",
    font: str = "ibm-plex",
) -> None:
    """Render a cover letter to PDF via the HTML template + weasyprint.

    ``cover_txt_path_or_text`` is either a Path to a .txt file or the raw body
    string. ``profile`` supplies candidate_name, contact, date, recipient,
    salutation, closing (mirrors the shape assemble_cover builds for Typst).

    A sibling cover.html is written beside out_path for inspection.
    """
    from weasyprint import HTML

    if isinstance(cover_txt_path_or_text, Path):
        body_text = cover_txt_path_or_text.read_text(encoding="utf-8")
    else:
        body_text = cover_txt_path_or_text

    html_str = cover_data_to_html(body_text=body_text, profile=profile, palette=palette, font=font)
    (out_path.parent / "cover.html").write_text(html_str, encoding="utf-8")
    HTML(string=html_str, base_url=str(out_path.parent)).write_pdf(str(out_path))
