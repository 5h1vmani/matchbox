"""In-app brain endpoints: stream an ingest or tailor run over SSE.

These drive the same deterministic core the documented Claude Code fallback uses,
but with the user's stored BYOK key, so a first-time user never needs a second
terminal. The Claude Code copy-paste handoff stays the default when no key is set
(the runner is simply never reached -- we return the BYOK 409, mirroring ai.py).

The shape mirrors ai.py: 409 when there is no key, the same `data: {...}\n\n` SSE
framing, and a sync endpoint that resolves the key/provider on the request thread
(where the sqlite connection lives) before streaming. The runner is plain Python
and blocking, so we run it in a worker thread and have the SSE generator drain a
`queue.Queue` of progress events the runner pushes via its `progress` callback;
a sentinel marks completion. One run at a time per process (a module Lock; 429
when busy) keeps a second tab from racing the first against the same library.
"""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from matchbox.brain.llm import BrainError, byok_completer
from matchbox.brain.runner import run_ingest, run_tailor
from matchbox.core import secrets
from matchbox.core.logging import get_logger
from matchbox.web.deps import ConnDep, ProfileDep

router = APIRouter(prefix="/api/brain")
log = get_logger(__name__)

# One brain run at a time per process. A non-blocking acquire lets a second
# request fail fast with 429 instead of queueing behind a long extraction.
_run_lock = threading.Lock()

# Sentinel pushed onto the progress queue when the worker thread finishes.
_DONE = object()


class IngestBody(BaseModel):
    confirm: bool = False


class TailorBody(BaseModel):
    job_id: int
    confirm: bool = False


def _sse(obj: dict[str, Any]) -> bytes:
    """Same framing ai.py uses, so the frontend SSE reader is shared."""
    return f"data: {json.dumps(obj)}\n\n".encode()


def _guard(profile: str, confirm: bool) -> None:
    """The two pre-flight gates, shared by both endpoints.

    409 when no key (the BYOK-specific status ai.py returns; the UI falls back to
    the Claude Code handoff). 400 when the cost gate (`confirm`) is not set -- the
    UI confirms before calling because a run spends the user's own API credits.
    """
    if not secrets.has_key(profile):
        raise HTTPException(status_code=409, detail="no API key configured")
    if not confirm:
        raise HTTPException(status_code=400, detail="confirm required")


def _stream(work: Any) -> StreamingResponse:
    """Run `work(progress)` in a thread and stream its progress + final event.

    `work` is a callable taking the progress callback and returning the runner's
    result dict. Progress events the runner emits are pushed onto a queue and
    re-emitted as `{"step", "detail"}` SSE frames; the run finishes with either
    `{"done": true, ...result}` or `{"error": ...}`. The module lock is held for
    the whole stream and released when the generator is exhausted (or the client
    disconnects and StreamingResponse closes it).
    """
    if not _run_lock.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="a brain run is already in progress")

    events: queue.Queue[Any] = queue.Queue()
    outcome: dict[str, Any] = {}

    def progress(step: str, detail: str) -> None:
        events.put({"step": step, "detail": detail})

    def worker() -> None:
        try:
            outcome["result"] = work(progress)
        except BrainError as e:
            outcome["error"] = str(e)
        except Exception as e:  # noqa: BLE001 -- surface any failure as an SSE error frame
            log.exception("brain run failed")
            outcome["error"] = f"{type(e).__name__}: {e}"
        finally:
            events.put(_DONE)

    def generate() -> Iterator[bytes]:
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        try:
            while True:
                event = events.get()
                if event is _DONE:
                    break
                yield _sse(event)
            thread.join()
            if "error" in outcome:
                yield _sse({"error": outcome["error"]})
            else:
                yield _sse({"done": True, **outcome.get("result", {})})
        finally:
            _run_lock.release()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/ingest")
def brain_ingest(body: IngestBody, conn: ConnDep, profile: ProfileDep) -> StreamingResponse:
    """Stream an in-app ingest of the staged inbox files."""
    _guard(profile, body.confirm)
    complete = byok_completer(conn, profile)
    return _stream(lambda progress: run_ingest(conn, profile, complete, progress))


@router.post("/tailor")
def brain_tailor(body: TailorBody, conn: ConnDep, profile: ProfileDep) -> StreamingResponse:
    """Stream an in-app tailoring run for one job."""
    _guard(profile, body.confirm)
    complete = byok_completer(conn, profile)
    return _stream(lambda progress: run_tailor(conn, profile, body.job_id, complete, progress))
