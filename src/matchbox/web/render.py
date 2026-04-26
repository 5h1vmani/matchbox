"""Template rendering helper — single typed entry point for all routes.

Routes call `render(request, "path/to/template.html", {...})` instead of
poking at `request.app.state.templates` directly. Keeps:
  - return type clean for mypy strict
  - template lookup centralised (easier to swap engines later)
  - one place to inject globally available context
"""

from __future__ import annotations

import json
from typing import Any, Literal, cast

from fastapi import Request
from fastapi.responses import HTMLResponse

ToastLevel = Literal["info", "success", "error"]


def render(
    request: Request,
    template: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
    toast: str | None = None,
    toast_level: ToastLevel = "info",
    undo_url: str | None = None,
    undo_payload: dict[str, str] | None = None,
) -> HTMLResponse:
    """Render a Jinja template. Optional `toast=` triggers a client-side
    notification via the `HX-Trigger` header — single SSOT instead of
    inlining OOB swaps in every detail-panel template.

    `undo_url` + `undo_payload` make the toast actionable: the client renders
    an "Undo" button that POSTs the payload to that URL.
    """
    ctx = context or {}
    response = request.app.state.templates.TemplateResponse(
        request, template, ctx, status_code=status_code
    )
    typed = cast(HTMLResponse, response)
    if toast:
        trigger: dict[str, Any] = {
            "matchbox:toast": {
                "message": toast,
                "level": toast_level,
            }
        }
        if undo_url:
            trigger["matchbox:toast"]["undo"] = {
                "url": undo_url,
                "payload": undo_payload or {},
            }
        typed.headers["HX-Trigger"] = json.dumps(trigger)
    return typed
