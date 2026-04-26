"""Template rendering helper — single typed entry point for all routes.

Routes call `render(request, "path/to/template.html", {...})` instead of
poking at `request.app.state.templates` directly. Keeps:
  - return type clean for mypy strict
  - template lookup centralised (easier to swap engines later)
  - one place to inject globally available context
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import Request
from fastapi.responses import HTMLResponse


def render(
    request: Request,
    template: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
) -> HTMLResponse:
    ctx = context or {}
    response = request.app.state.templates.TemplateResponse(
        request, template, ctx, status_code=status_code
    )
    return cast(HTMLResponse, response)
