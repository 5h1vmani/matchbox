"""FastAPI application — the local web UI.

Binds 127.0.0.1 only (ADR-0005, no auth, no remote access). Real routes live
in the `routes/` subpackage and are mounted here.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from matchbox.core.logging import configure_logging
from matchbox.web.routes import (
    agent_tasks,
    ai,
    answers,
    api,
    artifacts,
    discovery,
    insights,
    interviews,
    jobs,
    library_api,
    library_crud,
    offers,
    onboarding_api,
    packet,
    profile_api,
    review_api,
    review_run,
    sources_api,
    targets_api,
)

STATIC_DIR = Path(__file__).parent / "static"

# Shown instead of a raw 503 when the SPA bundle has not been built yet.
_SPA_MISSING_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Matchbox — one more step</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 34rem; margin: 14vh auto;
         padding: 0 1.5rem; color: #27272a; line-height: 1.6; }
  h1 { font-size: 1.3rem; color: #09090b; }
  pre { background: #f4f4f5; border: 1px solid #e4e4e7; border-radius: 6px;
        padding: 0.8rem 1rem; overflow-x: auto; }
  p.small { color: #52525b; font-size: 0.9rem; }
</style></head><body>
<h1>Almost there — the web UI just needs one build</h1>
<p>The server is running fine; the browser bundle has not been built yet.
Run this once from the repo root, then refresh this page:</p>
<pre>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</pre>
<p class="small">No npm? Install Node.js from nodejs.org first, or run
<code>./scripts/setup.sh</code> which does all of this for you.
The JSON API and the CLIs already work without this step.</p>
</body></html>"""


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="Matchbox",
        version="0.4.0",
        docs_url=None,
        redoc_url=None,
    )

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(agent_tasks.router)
    app.include_router(ai.router)
    app.include_router(answers.router)
    app.include_router(api.router)
    app.include_router(artifacts.router)
    app.include_router(discovery.router)
    app.include_router(insights.router)
    app.include_router(interviews.router)
    app.include_router(jobs.router)
    app.include_router(library_api.router)
    app.include_router(library_crud.router)
    app.include_router(offers.router)
    app.include_router(onboarding_api.router)
    app.include_router(packet.router)
    app.include_router(profile_api.router)
    app.include_router(review_api.router)
    app.include_router(review_run.router)
    app.include_router(sources_api.router)
    app.include_router(targets_api.router)

    spa_index = STATIC_DIR / "app" / "index.html"

    def _spa() -> Response:
        """Serve the built single-page app (the shell switches on the URL path).

        When the bundle is missing, answer with a human-readable page instead of
        raw JSON: a newcomer following the quickstart reads "503" as broken, not
        as "run one more command"."""
        if not spa_index.exists():
            return HTMLResponse(status_code=503, content=_SPA_MISSING_PAGE)
        return FileResponse(str(spa_index))

    @app.get("/tracker", include_in_schema=False)
    def tracker() -> Response:
        """Serve the React applications-tracker SPA (built from frontend/)."""
        return _spa()

    @app.get("/discover", include_in_schema=False)
    @app.get("/discover/{rest:path}", include_in_schema=False)
    def discover(rest: str = "") -> Response:
        """Serve the React Discovery SPA (same bundle; main.tsx renders the
        Discovery shell for /discover paths)."""
        return _spa()

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def root() -> Response:
        """Home: the unified React SPA. Client-side routing owns every surface,
        including onboarding (the SPA opens Intake for a brand-new library)."""
        return _spa()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_catchall(full_path: str) -> Response:
        """Serve the React SPA for any unmatched GET path so client-side routing
        owns /apply, /library, /onboarding, /review, etc. Real routes (API, the
        remaining Jinja pages, /static, sandboxed file serving) are registered
        first and still win; this only catches what they do not."""
        if full_path.startswith(("api/", "static/", "runs/")) or full_path == "healthz":
            raise HTTPException(status_code=404, detail="not found")
        return _spa()

    return app


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()
