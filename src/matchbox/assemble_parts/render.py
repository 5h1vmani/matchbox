"""PDF rendering, text extraction, and the run_job palette/font lookup.
Extracted from assemble.py."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pypdf import PdfReader


def _render_pdf(cv_json_path: Path, out_path: Path, palette: str, font: str) -> int:
    """Render the CV from cv.json to PDF.

    Uses the in-repo HTML/CSS template plus weasyprint (pure Python, no
    browser): the v0.1 layout, and pdftotext reads it in correct order. The
    populated HTML is written beside cv.json so the artifact dir stays
    self-contained and re-renderable.

    Returns the page count of the rendered PDF.
    """
    from matchbox.render_html import render_cv_pdf

    return render_cv_pdf(cv_json_path, out_path, palette=palette, font=font)


def _extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _palette_and_font_for(
    conn: sqlite3.Connection,
    run_id: str,
    job_id: int,
) -> tuple[str, str]:
    row = conn.execute(
        "SELECT palette, font FROM run_job WHERE run_id = ? AND job_id = ?",
        (run_id, job_id),
    ).fetchone()
    if row is None:
        return "slate", "source-serif"
    return row["palette"], row["font"]
