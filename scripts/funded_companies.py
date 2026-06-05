"""Funded-company intake + ATS poll for the matchbox job search.

Persists EVERY gathered funded company in `funded_company` (names are never
lost, even when no roles are found), resolves each to its ATS, polls the
ATS-reachable ones for India / remote-India lane-fit roles, inserts those roles
into `job`, and writes the candidate job ids for the eligibility judge.

Subcommands:
  init                       create the funded_company table
  ingest --file f.json       insert/dedup companies from a gather JSON
  poll [--out candidates.json] [--guess]
                             probe each company's ATS, store India/lane roles
  stats                      print coverage counts
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from matchbox.core.db import connect, transaction  # type: ignore[import-untyped]
from matchbox.discovery.base import JobRecord  # type: ignore[import-untyped]
from matchbox.discovery.runner import _upsert_jobs, probe  # type: ignore[import-untyped]

DDL = """
CREATE TABLE IF NOT EXISTS funded_company (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  name_key TEXT NOT NULL UNIQUE,
  round TEXT, amount TEXT, funded_at TEXT, sector TEXT, hq TEXT,
  careers_url TEXT, source_url TEXT,
  ats_type TEXT, ats_slug TEXT,
  polled INTEGER NOT NULL DEFAULT 0,
  roles_total INTEGER DEFAULT 0,
  roles_india_fit INTEGER DEFAULT 0,
  note TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_funded_polled ON funded_company(polled);
"""

_ATS = [
    ("greenhouse", re.compile(r"(?:boards|job-boards)\.greenhouse\.io/([A-Za-z0-9_-]+)")),
    ("greenhouse", re.compile(r"([A-Za-z0-9_-]+)\.greenhouse\.io")),
    ("lever", re.compile(r"jobs\.lever\.co/([A-Za-z0-9_-]+)")),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_-]+)")),
    ("smartrecruiters", re.compile(r"smartrecruiters\.com/([A-Za-z0-9_-]+)")),
    ("recruitee", re.compile(r"([A-Za-z0-9_-]+)\.recruitee\.com")),
]

_CITIES = ("bangalore", "bengaluru", "mumbai", "hyderabad", "delhi", "gurgaon", "gurugram",
           "pune", "chennai", "noida", "kolkata", "ahmedabad", "india")
_LANE = ("solution", "sales engineer", "pre-sales", "presales", "forward deployed",
         "forward-deployed", "technical account", "customer success", "customer engineer",
         "product manager", "ai product", "finance", "fp&a", "strategy", "partnership",
         "gtm", "founding", "developer advocate", "developer relations", "devrel",
         "consultant", "implementation", "architect", "growth", "account manager")
_CODING_OUT = ("software engineer", "backend", "frontend", "full stack", "fullstack",
               "ml engineer", "machine learning", "research engineer", "researcher",
               "data engineer", "infrastructure engineer", "platform engineer", "sre",
               "devops", "sdet", "ios ", "android", "security engineer", "systems engineer",
               "applied scientist", "data scientist", "qa engineer", "firmware")


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def parse_ats(url: str | None) -> tuple[str | None, str | None]:
    if not url:
        return (None, None)
    for ats, pat in _ATS:
        m = pat.search(url)
        if m and m.group(1).lower() not in ("www", "jobs", "boards", "careers"):
            return (ats, m.group(1))
    return (None, None)


def _india_or_remote(loc: str, title: str, jd: str) -> bool:
    locl = (loc or "").lower()
    blob = f"{locl} {title.lower()} {jd.lower()}"
    if "indiana" in locl:
        locl = locl.replace("indiana", "")
    india = any(c in f"{locl} {title.lower()} {jd[:400].lower()}" for c in _CITIES)
    remote = "remote" in blob
    return india or remote


def _lane_fit(title: str) -> bool:
    t = title.lower()
    if any(c in t for c in _CODING_OUT):
        return False
    return any(k in t for k in _LANE)


def cmd_init() -> None:
    c = connect()
    c.executescript(DDL)  # executescript manages its own commit
    c.commit()
    print("funded_company table ready")
    c.close()


def cmd_ingest(path: str | None, dir_: str | None) -> None:
    rows: list[dict[str, Any]] = []
    if dir_:
        for f in sorted(glob.glob(os.path.join(dir_, "*.json"))):
            try:
                with open(f, encoding="utf-8") as fh:
                    data = json.loads(fh.read())
                rows += data if isinstance(data, list) else [data]
            except Exception:
                continue
    elif path:
        with open(path, encoding="utf-8") as fh:
            rows = json.loads(fh.read())
    c = connect()
    cmd = (
        "INSERT INTO funded_company (name,name_key,round,amount,funded_at,sector,hq,"
        "careers_url,source_url,ats_type,ats_slug) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(name_key) DO UPDATE SET "
        "careers_url=COALESCE(funded_company.careers_url, excluded.careers_url), "
        "ats_type=COALESCE(funded_company.ats_type, excluded.ats_type), "
        "ats_slug=COALESCE(funded_company.ats_slug, excluded.ats_slug), "
        "round=COALESCE(funded_company.round, excluded.round), "
        "amount=COALESCE(funded_company.amount, excluded.amount)"
    )
    c.executescript(DDL)  # ensure table exists (manages its own commit)
    c.commit()
    n = 0
    with transaction(c):
        for r in rows:
            name = (r.get("name") or "").strip()
            if not name:
                continue
            ats, slug = parse_ats(r.get("careers_url"))
            c.execute(cmd, (name, _key(name), r.get("round"), r.get("amount"),
                            r.get("date") or r.get("funded_at"), r.get("sector"), r.get("hq"),
                            r.get("careers_url"), r.get("source_url"), ats, slug))
            n += 1
    total = c.execute("SELECT COUNT(*) FROM funded_company").fetchone()[0]
    print(json.dumps({"ingested": n, "total_in_db": total}))
    c.close()


def _probe_company(row: dict[str, Any], guess: bool) -> tuple[int, list[JobRecord]]:
    """Return (total_roles_seen, [JobRecord]) for India/lane-fit roles."""
    ats, slug = row["ats_type"], row["ats_slug"]
    tries: list[tuple[str, str]] = []
    if ats and slug:
        tries.append((ats, slug))
    elif guess:
        g = _key(row["name"])
        if g:
            tries += [("ashby", g), ("greenhouse", g), ("lever", g)]
    fits: list[JobRecord] = []
    total = 0
    for at, sl in tries:
        try:
            jobs = probe(at, sl, row["name"])
        except Exception:
            continue
        total += len(jobs)
        for j in jobs:
            if _lane_fit(j.title or "") and _india_or_remote(j.location or "", j.title or "", j.jd_text or ""):
                fits.append(j)
        if jobs:
            # found the right ATS; record it
            row["_found_ats"] = (at, sl)
            break
    return total, fits


def cmd_poll(out: str | None, guess: bool) -> None:
    c = connect()
    rows = [dict(r) for r in c.execute(
        "SELECT * FROM funded_company WHERE polled = 0"
    ).fetchall()]
    print(f"polling {len(rows)} companies (guess={guess}) ...", file=sys.stderr)

    results: dict[int, tuple[int, list[JobRecord]]] = {}
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = {ex.submit(_probe_company, r, guess): r for r in rows}
        for f in as_completed(futs):
            r = futs[f]
            try:
                results[r["id"]] = f.result()
            except Exception:
                results[r["id"]] = (0, [])

    all_fit_jobs: list[JobRecord] = []
    for r in rows:
        total, fits = results.get(r["id"], (0, []))
        all_fit_jobs.extend(fits)

    # insert fit roles into job (INSERT OR IGNORE by url)
    inserted = 0
    with transaction(c):
        if all_fit_jobs:
            inserted = _upsert_jobs(c, None, all_fit_jobs)
        for r in rows:
            total, fits = results.get(r["id"], (0, []))
            fa = r.get("_found_ats")
            c.execute(
                "UPDATE funded_company SET polled=1, roles_total=?, roles_india_fit=?, "
                "ats_type=COALESCE(ats_type,?), ats_slug=COALESCE(ats_slug,?) WHERE id=?",
                (total, len(fits), fa[0] if fa else None, fa[1] if fa else None, r["id"]),
            )

    # candidate job ids = the India/lane roles we just have in `job`
    urls = [j.url for j in all_fit_jobs]
    cand_ids: list[int] = []
    if urls:
        q = "SELECT id FROM job WHERE url IN ({})".format(",".join("?" for _ in urls))
        cand_ids = [r[0] for r in c.execute(q, urls).fetchall()]
    summary = {
        "companies_polled": len(rows),
        "with_ats": sum(1 for r in rows if results.get(r["id"], (0, []))[0] > 0 or r.get("_found_ats")),
        "fit_roles_found": len(all_fit_jobs),
        "new_jobs_inserted": inserted,
        "candidate_job_ids": cand_ids,
    }
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(summary))
    brief = {k: v for k, v in summary.items() if k != "candidate_job_ids"}
    brief["n_candidates"] = len(cand_ids)
    print(json.dumps(brief))
    c.close()


def cmd_stats() -> None:
    c = connect()
    row = c.execute(
        "SELECT COUNT(*) total, SUM(polled) polled, SUM(CASE WHEN ats_type IS NOT NULL THEN 1 END) with_ats, "
        "SUM(roles_india_fit) india_fit FROM funded_company"
    ).fetchone()
    print(json.dumps({"total": row[0], "polled": row[1], "with_ats": row[2], "india_fit_roles": row[3]}))
    c.close()


def cmd_save_verdicts(path: str) -> None:
    """Persist eligibility verdicts [{id,status,geo_ok,reason}] into each job's
    score_breakdown_json. Deterministic — no LLM needed (the workflow returns
    the verdicts; this just writes them)."""
    with open(path, encoding="utf-8") as fh:
        verdicts = json.loads(fh.read())
    c = connect()
    written = 0
    with transaction(c):
        for v in verdicts:
            jid = v.get("id")
            if jid is None:
                continue
            row = c.execute("SELECT score_breakdown_json FROM job WHERE id=?", (jid,)).fetchone()
            if not row:
                continue
            try:
                sbj = json.loads(row["score_breakdown_json"]) if row["score_breakdown_json"] else {}
            except Exception:
                sbj = {}
            sbj["eligibility"] = {
                "status": v.get("status"), "geo_ok": v.get("geo_ok"), "reason": v.get("reason"),
            }
            c.execute("UPDATE job SET score_breakdown_json=? WHERE id=?", (json.dumps(sbj), jid))
            written += 1
    print(json.dumps({"written": written}))
    c.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    ig = sub.add_parser("ingest")
    ig.add_argument("--file")
    ig.add_argument("--dir")
    po = sub.add_parser("poll")
    po.add_argument("--out")
    po.add_argument("--guess", action="store_true")
    sub.add_parser("stats")
    sv = sub.add_parser("save-verdicts")
    sv.add_argument("--file", required=True)
    a = ap.parse_args()
    if a.cmd == "init":
        cmd_init()
    elif a.cmd == "ingest":
        cmd_ingest(a.file, a.dir)
    elif a.cmd == "poll":
        cmd_poll(a.out, a.guess)
    elif a.cmd == "stats":
        cmd_stats()
    elif a.cmd == "save-verdicts":
        cmd_save_verdicts(a.file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
