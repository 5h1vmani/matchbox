"""FastAPI factory + uvicorn entry point.

Run:
    matchbox-web                                # default port 8765
    uvicorn matchbox.web.app:create_app --factory --reload
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from matchbox.web.config import Settings
from matchbox.web.deps import get_settings, list_profiles, shell_context
from matchbox.web.filters import register as register_filters
from matchbox.web.render import render
from matchbox.web.routes import bulk, files, jobs, pages, palette, profile, system

log = logging.getLogger(__name__)


def _templates(settings: Settings) -> Jinja2Templates:
    tpl = Jinja2Templates(directory=str(settings.templates_dir))
    register_filters(tpl.env)
    tpl.env.globals["app_name"] = "Matchbox"
    return tpl


def create_app() -> FastAPI:
    settings = get_settings()
    settings.static_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title="Matchbox",
        description="Precision job application pipeline.",
        version="0.3.0",
        docs_url="/api/docs" if settings.debug else None,
        redoc_url=None,
    )

    app.state.settings = settings
    app.state.templates = _templates(settings)

    app.mount(
        "/static",
        StaticFiles(directory=str(settings.static_dir)),
        name="static",
    )

    app.include_router(pages.router)
    app.include_router(jobs.router, prefix="/p/{profile}/jobs", tags=["jobs"])
    app.include_router(bulk.router, prefix="/p/{profile}/bulk", tags=["bulk"])
    app.include_router(profile.router, prefix="/p/{profile}/profile", tags=["profile"])
    app.include_router(palette.router, prefix="/p/{profile}/palette", tags=["palette"])
    app.include_router(files.router, prefix="/p/{profile}/files", tags=["files"])
    app.include_router(system.router, prefix="/system", tags=["system"])

    @app.get("/", include_in_schema=False)
    async def root(request: Request) -> RedirectResponse:
        profiles = list_profiles(settings)
        if not profiles:
            return RedirectResponse(url="/system/welcome", status_code=302)
        target = settings.default_profile if settings.default_profile in profiles else profiles[0]
        return RedirectResponse(url=f"/p/{target}/inbox", status_code=302)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(HTTPException)
    async def http_exception(request: Request, exc: HTTPException) -> Response:
        # HTMX requests: return the detail as a small HTML fragment so the
        # client error handler can surface a toast. Browser navigations to a
        # full page get a styled error page.
        is_htmx = request.headers.get("HX-Request") == "true"
        accept = request.headers.get("accept") or ""
        if is_htmx or "text/html" not in accept:
            return Response(
                content=str(exc.detail),
                status_code=exc.status_code,
                media_type="text/plain",
            )
        return _render_error(request, exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> Response:
        msg = "Invalid request."
        if request.headers.get("HX-Request") == "true":
            return Response(content=msg, status_code=422, media_type="text/plain")
        return _render_error(request, 422, msg)

    def _render_error(request: Request, status: int, message: str) -> HTMLResponse:
        ctx = shell_context(get_settings(), None, "")
        ctx.update(status=status, message=message)
        return render(request, "pages/error.html", ctx, status_code=status)

    return app


def run() -> None:
    """Entry point for the `matchbox-web` script."""
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    log.warning(
        "Matchbox web has no auth and no CSRF protection — bind to 127.0.0.1 only. "
        "If you need remote access, put it behind a reverse proxy with auth."
    )
    uvicorn.run(
        "matchbox.web.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=8765,
        reload=False,
    )
