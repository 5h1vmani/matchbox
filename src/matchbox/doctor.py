"""First-run environment diagnosis: `matchbox-doctor`.

A fresh clone can fail in five unrelated ways (old Python, no Pango for
weasyprint, no node, SPA not built, no claude CLI). The doctor turns those
stack traces into a one-screen checklist, so setup problems are diagnosed
before any feature is exercised. Only hard requirements fail the exit code;
everything else is reported as optional with the command that fixes it.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from dataclasses import dataclass

_GREEN = "\x1b[32m"
_RED = "\x1b[31m"
_RESET = "\x1b[0m"


@dataclass(slots=True)
class Check:
    name: str
    ok: bool
    required: bool
    detail: str


def _tool_version(executable: str) -> str:
    """`<executable> --version`, never raising (the check text degrades instead)."""
    try:
        proc = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return "version unknown"
    return proc.stdout.strip() or "version unknown"


def _check_python() -> Check:
    version = ".".join(str(part) for part in sys.version_info[:3])
    return Check(
        name="python",
        ok=sys.version_info >= (3, 12),
        required=True,
        detail=f"{version} (need >= 3.12)",
    )


def _check_pdf_backend() -> Check:
    from matchbox.pdf_backend import _weasyprint_importable, select_backend

    weasyprint_ok = _weasyprint_importable()
    playwright_ok = importlib.util.find_spec("playwright") is not None
    ok = weasyprint_ok or playwright_ok
    if ok:
        detail = f"backend: {select_backend()}"
    else:
        detail = (
            "no backend: install weasyprint system libraries (Pango/Cairo) "
            'or pip install "matchbox[chromium]" + playwright install chromium'
        )
    return Check(name="pdf rendering", ok=ok, required=True, detail=detail)


def _check_node_npm() -> Check:
    node = shutil.which("node")
    npm = shutil.which("npm")
    if node and npm:
        detail = f"node {_tool_version(node)}, npm {_tool_version(npm)}"
    else:
        detail = "not on PATH; only needed to build the SPA (https://nodejs.org)"
    return Check(name="node + npm", ok=bool(node and npm), required=False, detail=detail)


def _check_spa_built() -> Check:
    from matchbox.web import app as web_app

    index = web_app.STATIC_DIR / "app" / "index.html"
    if index.exists():
        detail = f"built: {index}"
    else:
        detail = "not built; run: cd frontend && npm install && npm run build"
    return Check(name="spa built", ok=index.exists(), required=False, detail=detail)


def _check_claude_cli() -> Check:
    path = shutil.which("claude")
    if path:
        detail = f"{path} (no-key reasoning fallback available)"
    else:
        detail = "not on PATH; the claude CLI is the no-key reasoning fallback"
    return Check(name="claude cli", ok=path is not None, required=False, detail=detail)


def _check_profile() -> Check:
    # db_path()/profile_slug() are pure path math; connect() would CREATE the
    # DB as a side effect, which a diagnostic must never do.
    from matchbox.core.db import db_path, profile_slug

    slug = profile_slug()
    path = db_path()
    if path.exists():
        detail = f"profile '{slug}': {path}"
    else:
        detail = f"profile '{slug}': no DB yet at {path} (created on first ingest)"
    return Check(name="active profile", ok=path.exists(), required=False, detail=detail)


def checks() -> list[Check]:
    return [
        _check_python(),
        _check_pdf_backend(),
        _check_node_npm(),
        _check_spa_built(),
        _check_claude_cli(),
        _check_profile(),
    ]


def main() -> int:
    color = sys.stdout.isatty()
    failed_required = False
    for check in checks():
        status = "ok     " if check.ok else "MISSING"
        if color:
            status = f"{_GREEN if check.ok else _RED}{status}{_RESET}"
        suffix = "" if check.required or check.ok else " [optional]"
        print(f"{status} {check.name}: {check.detail}{suffix}")
        if check.required and not check.ok:
            failed_required = True
    return 1 if failed_required else 0


if __name__ == "__main__":
    raise SystemExit(main())
