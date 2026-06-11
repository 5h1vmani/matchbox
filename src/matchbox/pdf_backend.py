"""HTML -> PDF rendering backend, selectable for cross-platform support.

weasyprint (the default on macOS and Linux) renders with system Pango/Cairo/GDK
libraries. Those are painful to install on Windows, so a Playwright/Chromium
backend is available that needs NO system libraries:

    pip install "matchbox[chromium]"
    playwright install chromium
    MATCHBOX_PDF_BACKEND=chromium matchbox-web    # or let auto-selection pick it

Selection (``MATCHBOX_PDF_BACKEND``): ``weasyprint``, ``chromium``, or ``auto``
(default). ``auto`` uses weasyprint when it imports cleanly -- which only happens
when its native libraries are present -- and falls back to chromium otherwise,
exactly the Windows-without-GTK case. Fonts are embedded as base64 in the HTML,
so neither backend needs network access or system fonts.
"""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path


@cache
def _weasyprint_importable() -> bool:
    """True only when weasyprint imports AND its native Pango/Cairo libraries
    load. Importing it is the test: a pip-installed weasyprint with no GTK (the
    Windows default) raises OSError here, so auto-selection skips it."""
    try:
        import weasyprint  # noqa: F401  (the import itself loads the native libs)
    except Exception:
        return False
    return True


def select_backend() -> str:
    """Resolve the backend from ``MATCHBOX_PDF_BACKEND`` (weasyprint|chromium|auto)."""
    choice = os.environ.get("MATCHBOX_PDF_BACKEND", "auto").strip().lower()
    if choice in {"weasyprint", "chromium"}:
        return choice
    return "weasyprint" if _weasyprint_importable() else "chromium"


def _weasyprint_pdf(html: str, out_path: Path, base_url: str) -> int:
    from weasyprint import HTML

    document = HTML(string=html, base_url=base_url).render()
    document.write_pdf(str(out_path))
    return len(document.pages)


def _chromium_pdf(html: str, out_path: Path, base_url: str) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as e:  # pragma: no cover - exercised only on Windows installs
        raise RuntimeError(
            "the chromium PDF backend needs Playwright: "
            'pip install "matchbox[chromium]" then "playwright install chromium"'
        ) from e
    from pypdf import PdfReader

    with sync_playwright() as p:  # pragma: no cover - needs a chromium binary
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="networkidle")
            page.pdf(path=str(out_path), format="A4", print_background=True)
        finally:
            browser.close()
    return len(PdfReader(str(out_path)).pages)


def html_to_pdf(html: str, out_path: Path, *, base_url: str) -> int:
    """Render an HTML string to a PDF file and return the page count.

    The backend is chosen by ``select_backend()``. ``base_url`` resolves relative
    resources (unused today since fonts are embedded, but passed through so the
    contract is correct if that ever changes)."""
    if select_backend() == "chromium":
        return _chromium_pdf(html, out_path, base_url)
    return _weasyprint_pdf(html, out_path, base_url)
