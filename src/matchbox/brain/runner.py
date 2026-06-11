"""The in-app brain runner: ingest and tailor, end to end, over a `Completer`.

Both entry points take a `Completer` (so tests inject a fake) and a `progress`
callback ``(step, detail) -> None`` for the SSE stream. They are pure Python --
no FastAPI -- so they can run in a worker thread while the web generator drains a
queue of progress events.

The no-fabrication guarantee is NOT enforced here. This module asks the model for
JSON, validates it against the generated schema (retrying once with the errors
appended), and hands it to the SAME deterministic core the manual Claude Code
path uses: ``ingest`` for onboarding, ``save_requirements`` + ``assemble_one`` +
``polish_run`` for tailoring. Those validate every selected id against the
verified library and voice-gate the prose; a model that hallucinates an id or a
banned word is rejected there, identically to Claude Code's output.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from matchbox.assemble import AssembleResult, assemble_one, polish_run
from matchbox.assemble_parts.loaders import (
    _load_components,
    _load_job,
    _load_library_skills,
    _load_verified_projects,
)
from matchbox.assemble_parts.render import _palette_and_font_for
from matchbox.brain.llm import BrainError, Completer
from matchbox.brain.prompts import (
    ingest_prompt,
    polish_prompt,
    requirements_prompt,
    selection_prompt,
)
from matchbox.contracts import schema_errors
from matchbox.core.logging import get_logger
from matchbox.jobreqs import save_requirements
from matchbox.matching.embed import Embedder
from matchbox.onboarding.ingest_cli import ingest
from matchbox.scoring import runs as runs_mod
from matchbox.scoring.runs import JobSelection, create_run

log = get_logger(__name__)

Progress = Callable[[str, str], None]

# Inbox extensions the brain can read itself. .docx / .doc and anything else are
# skipped with a warning that names the Claude Code path (which handles them).
_TEXT_EXTS = {".txt", ".md", ".json", ".html", ".rtf"}
_PDF_EXTS = {".pdf"}


def _strip_fences(text: str) -> str:
    """Defensively strip a leading/trailing markdown code fence.

    The prompts ask for raw JSON, but models sometimes wrap it in ```json ... ```
    anyway. Trim that so json.loads sees a clean document; a model that returns
    genuine prose still fails to parse and is reported."""
    s = text.strip()
    if s.startswith("```"):
        # drop the opening fence line (``` or ```json) and the closing fence
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1 :]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def _complete_json(
    complete: Completer,
    system: str,
    user: str,
    schema_file: str,
    *,
    inject: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call the model, parse JSON, validate against `schema_file`; retry once.

    `inject` keys are forced onto the parsed payload before validation (e.g. the
    server's run_id/job_id), so the model cannot point the artifact at the wrong
    run. On a parse error or schema error the call is retried ONCE with the
    failure appended to the user prompt; a second failure raises BrainError.
    """
    attempt_user = user
    last_errors: list[str] = []
    for attempt in (1, 2):
        raw = complete(system, attempt_user)
        cleaned = _strip_fences(raw)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as e:
            last_errors = [f"response was not valid JSON: {e}"]
        else:
            if not isinstance(payload, dict):
                last_errors = ["response JSON must be an object"]
            else:
                if inject:
                    payload.update(inject)
                errors = schema_errors(schema_file, payload)
                if not errors:
                    return payload
                last_errors = errors
        if attempt == 1:
            attempt_user = (
                user + "\n\nYour previous reply was rejected. Fix these problems and reply "
                "with corrected JSON only:\n- " + "\n- ".join(last_errors)
            )
    raise BrainError(
        f"model output failed {schema_file} validation after a retry: " + "; ".join(last_errors)
    )


# ── ingest ───────────────────────────────────────────────────────────────────


def _read_inbox_files(staged: list[Path], progress: Progress) -> list[tuple[str, str]]:
    """Read staged inbox files into (name, text). PDFs via pypdf; text/markdown
    via read_text. .docx/.doc and unknown types are skipped with a warning that
    names the Claude Code path (which can parse them)."""
    out: list[tuple[str, str]] = []
    for path in staged:
        ext = path.suffix.lower()
        if ext in _TEXT_EXTS:
            try:
                out.append((path.name, path.read_text(encoding="utf-8", errors="replace")))
            except OSError as e:
                progress("read", f"skipped {path.name}: {e}")
        elif ext in _PDF_EXTS:
            try:
                from pypdf import PdfReader

                reader = PdfReader(str(path))
                text = "\n".join((p.extract_text() or "") for p in reader.pages)
                out.append((path.name, text))
            except Exception as e:  # noqa: BLE001 -- pypdf raises a variety; report and skip
                progress("read", f"skipped {path.name}: could not read PDF ({e})")
        else:
            progress(
                "read",
                f"skipped {path.name}: the in-app reader cannot parse {ext or 'this file'}. "
                "Run 'ingest my files' in Claude Code to include it.",
            )
    return out


def run_ingest(
    conn: sqlite3.Connection,
    profile: str,
    complete: Completer,
    progress: Progress,
    *,
    inbox_dir: Path | None = None,
) -> dict[str, int]:
    """Read staged inbox files, extract the library, and apply it to the DB.

    Returns the same counts dict the ingest CLI prints. Rows land unverified, so
    the user still confirms each fact at Review (identical to the Claude Code
    path). Raises BrainError when the inbox is empty/unreadable or the model
    output cannot be validated.
    """
    from matchbox.web.routes.onboarding import INBOX_DIR

    inbox = inbox_dir or INBOX_DIR
    progress("read", "reading staged files")
    staged = (
        [p for p in sorted(inbox.iterdir()) if p.is_file() and not p.name.startswith(".")]
        if inbox.exists()
        else []
    )
    files = _read_inbox_files(staged, progress)
    if not files:
        raise BrainError(
            "no readable files in the inbox. Stage a PDF, TXT, MD, JSON, HTML, or RTF "
            "file, or run 'ingest my files' in Claude Code for DOCX support."
        )

    progress("extract", f"extracting experience from {len(files)} file(s)")
    system, user = ingest_prompt(files)
    payload = _complete_json(complete, system, user, "ingest.v1.json")

    progress("save", "writing rows to the library (unverified)")
    counts = ingest(payload, conn)
    progress(
        "done",
        f"ingested {counts.get('bullets', 0)} bullets across "
        f"{counts.get('experiences', 0)} roles -- confirm them at Review",
    )
    return counts


# ── tailor ─────────────────────────────────────────────────────────────────


def _selected_bullet_texts(result: AssembleResult, components: list[Any]) -> list[dict[str, Any]]:
    """(id, text) for the bullets assemble actually selected -- the polish inputs."""
    by_id = {c.id: c.text for c in components}
    return [
        {"id": cid, "text": by_id[cid]} for cid in result.selected_component_ids if cid in by_id
    ]


def run_tailor(
    conn: sqlite3.Connection,
    profile: str,
    job_id: int,
    complete: Completer,
    progress: Progress,
    *,
    embedder: Embedder | None = None,
) -> dict[str, Any]:
    """Extract requirements, select, assemble, and (when needed) polish one job.

    Steps, each emitting progress:
    1. load the job (BrainError if missing or no jd_text)
    2. requirements -> save_requirements
    3. create_run (one job, want_cv)
    4. selection -> assemble_one (retry once on a rejected id / voice gate)
    5. polish only when keyword presence has misses (tolerate rejection)
    6. write status.json so the file-watching UI updates

    Returns {run_id, cv_path, gaps, keyword_misses, polish_applied}.
    """
    progress("load", f"loading job {job_id}")
    try:
        job = _load_job(conn, job_id)
    except LookupError as e:
        raise BrainError(f"job {job_id} not found") from e
    jd_text = str(job.get("jd_text") or "").strip()
    if not jd_text:
        raise BrainError(f"job {job_id} has no JD text to tailor against")
    title = str(job.get("title") or "")
    company = str(job.get("company") or "")

    # 2. Requirements.
    progress("requirements", "extracting JD requirements")
    sys_r, usr_r = requirements_prompt(job_id, title, company, jd_text)
    reqs = _complete_json(
        complete, sys_r, usr_r, "job-requirements.v1.json", inject={"job_id": job_id}
    )
    save_requirements(conn, job_id, reqs)

    # 3. Run.
    progress("run", "creating the tailoring run")
    run_id, _wq = create_run(
        conn,
        selections=[JobSelection(job_id=job_id, want_cv=True, want_cover=False)],
    )
    palette, font = _palette_and_font_for(conn, run_id, job_id)

    # 4. Selection -> assemble. The brain sees verified bullets/projects/skills
    # WITH ids; assemble_one validates every id against the verified library.
    components, _raw = _load_components(conn)
    bullets = [{"id": c.id, "text": c.text} for c in components]
    # Attach company/role for the model's context (assemble validates by id only).
    comp_meta = {
        r["id"]: {"company": r.get("company"), "role": r.get("role")} for r in _raw.values()
    }
    for b in bullets:
        meta = comp_meta.get(b["id"], {})
        b["company"] = meta.get("company")
        b["role"] = meta.get("role")
    projects = [
        {"id": pid, "name": p["name"], "text": p["text"]}
        for pid, p in _load_verified_projects(conn).items()
    ]
    skills = [
        {"id": sid, "name": s["name"], "category": s.get("category")}
        for sid, s in _load_library_skills(conn).items()
    ]
    req_items = reqs.get("requirements", [])

    progress("select", "selecting verified bullets and drafting the summary")
    sys_s, usr_s = selection_prompt(
        run_id, job_id, title, company, bullets, projects, skills, req_items
    )
    inject = {"run_id": run_id, "job_id": job_id}
    selection = _complete_json(complete, sys_s, usr_s, "selection.v1.json", inject=inject)

    progress("assemble", "rendering the CV")
    try:
        result = assemble_one(
            conn=conn,
            run_id=run_id,
            job_id=job_id,
            palette=palette,
            font=font,
            embedder=embedder,
            selection=selection,
        )
    except ValueError as first_err:
        # An unverified/unknown id or a voice-gated summary. Retry ONCE, telling
        # the model exactly what the core rejected.
        progress("select", f"selection rejected ({first_err}); retrying once")
        retry_user = (
            usr_s + "\n\nThe deterministic core REJECTED your previous selection with this "
            f"error:\n{first_err}\nReturn a corrected selection.v1.json using only ids "
            "from the input and a summary with no em-dashes or contractions."
        )
        selection = _complete_json(complete, sys_s, retry_user, "selection.v1.json", inject=inject)
        result = assemble_one(
            conn=conn,
            run_id=run_id,
            job_id=job_id,
            palette=palette,
            font=font,
            embedder=embedder,
            selection=selection,
        )

    keyword_misses = [str(kp["requirement"]) for kp in result.keyword_presence if not kp["present"]]
    polish_applied = 0

    # 5. Polish only when there are keyword misses to carry.
    if keyword_misses:
        progress("polish", f"aligning {len(keyword_misses)} missing keyword(s)")
        sys_p, usr_p = polish_prompt(
            run_id,
            job_id,
            keyword_misses,
            _selected_bullet_texts(result, components),
        )
        try:
            polish_payload = _complete_json(complete, sys_p, usr_p, "polish.v1.json", inject=inject)
            summary = polish_run(
                conn=conn,
                run_id=run_id,
                job_id=job_id,
                palette=palette,
                font=font,
                payload=polish_payload,
            )
            polish_applied = len(summary.get("applied", []))
            # Refresh misses from the post-polish keyword presence.
            after = summary.get("keyword_presence_after", [])
            keyword_misses = [str(kp["requirement"]) for kp in after if not kp.get("present")]
            progress("polish", f"applied {polish_applied} reword(s)")
        except (BrainError, ValueError) as e:
            # Polish is best-effort: a rejected/invalid polish must not fail the
            # run -- the CV already rendered. Report and move on.
            progress("polish", f"polish skipped ({e})")

    # 6. Status file so the file-watching UI re-renders.
    cv_path_rel = _rel_to_root(result.cv_path)
    _write_status(run_id, job_id, cv_path_rel, result.gaps)

    progress(
        "done",
        f"CV ready with {len(result.gaps)} uncovered must-have(s)",
    )
    return {
        "run_id": run_id,
        "cv_path": cv_path_rel,
        "gaps": result.gaps,
        "keyword_misses": keyword_misses,
        "polish_applied": polish_applied,
    }


def _rel_to_root(path: Path) -> str:
    """Express an artifact path relative to the runs dir's parent (the repo root)
    when possible, with forward slashes, matching how status paths are written
    elsewhere."""
    root = runs_mod.RUNS_DIR.parent
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _write_status(run_id: str, job_id: int, cv_path: str, gaps: list[str]) -> None:
    """Write runs/<run-id>/status.json via the contracts.Status model.

    Validated by pydantic before it lands so the file-watching UI never reads a
    malformed status. Marks this single-job run done with cv_status done."""
    from matchbox.contracts import Status, StatusJob

    status = Status(
        schema_version=1,
        run_id=run_id,
        status="done",
        jobs=[
            StatusJob(
                job_id=job_id,
                cv_status="done",
                cover_status="skipped",
                cv_path=cv_path,
                gaps=gaps,
                notes="Tailored in-app via the BYOK brain.",
            )
        ],
    )
    out = runs_mod.RUNS_DIR / run_id / "status.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(status.model_dump_json(indent=2), encoding="utf-8")
