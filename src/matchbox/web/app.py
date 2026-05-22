"""FastAPI application — the local web UI.

Binds 127.0.0.1 only (ADR-0005, no auth, no remote access). Real routes live
in the `routes/` subpackage and are mounted here.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from matchbox.web.deps import ConnDep
from matchbox.web.routes import (
    inbox,
    library,
    onboarding,
    profile,
    review,
    review_run,
    sources,
    targets,
)

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Matchbox",
        version="0.3.0",
        docs_url=None,
        redoc_url=None,
    )

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(inbox.router)
    app.include_router(library.router)
    app.include_router(onboarding.router)
    app.include_router(profile.router)
    app.include_router(review.router)
    app.include_router(review_run.router)
    app.include_router(sources.router)
    app.include_router(targets.router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def root(conn: ConnDep) -> RedirectResponse:
        """If we have any library state, go to /library. Else /onboarding."""
        if onboarding.profile_exists(conn):
            return RedirectResponse(url="/library", status_code=302)
        return RedirectResponse(url="/onboarding", status_code=302)

    return app


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()
