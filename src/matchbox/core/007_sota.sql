-- Matchbox migration 007: SOTA foundation (the offer-accepted arc).
--
-- Purely ADDITIVE: new columns + new tables + in-SQL backfills from existing
-- rows. No drops, no rewrites -- safe on a DB at any prior version (the runner
-- applies 1..7 in order, so watchlist (006) exists before this runs). The
-- destructive lean-up (retire one PDF renderer, drop legacy application.status/
-- notes) is deferred to a later migration once their readers are gone.
--
-- What this enables, by phase:
--   Find/Judge  -> job carries salary, seniority, employment_type, eligibility
--                  signals, a dedup key, and a company FK (Tier-1 API + Tier-2
--                  regex fill these; no LLM at pool scale).
--   Judge       -> `requirement` makes coverage a real relational query and
--                  matches the existing embedding item_type 'requirement'.
--   Apply/Adv   -> `artifact` holds every generated output (cv|cover|prep|
--                  followup|thankyou|counter), not just two fixed path slots.
--   Close       -> `offer` for comparison + benchmark + the accepted terminal.
--   Learn       -> application snapshots the predicted fit at apply-time so
--                  calibration can compare prediction vs outcome.
--   Loop        -> `agent_task` is the queue the agent drains (replaces the
--                  work-queue.json copy-paste hand-off).

-- ── companies ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS company (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    size          TEXT,                 -- e.g. "11-50", "5000+"
    stage         TEXT,                 -- seed | a | b | c | public | bootstrapped
    industry      TEXT,
    hq_location   TEXT,
    url           TEXT,
    notes         TEXT,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- ── job: ad-data enrichment for honest judging + comp + dedupe ────────────────
ALTER TABLE job ADD COLUMN company_id        INTEGER REFERENCES company(id) ON DELETE SET NULL;
ALTER TABLE job ADD COLUMN salary_min        REAL;
ALTER TABLE job ADD COLUMN salary_max        REAL;
ALTER TABLE job ADD COLUMN salary_currency   TEXT;     -- ISO 4217: INR, USD, EUR
ALTER TABLE job ADD COLUMN salary_period     TEXT;     -- year | month | day | hour
ALTER TABLE job ADD COLUMN employment_type   TEXT;     -- full_time | contract | internship | part_time
ALTER TABLE job ADD COLUMN seniority         TEXT;     -- intern | junior | mid | senior | staff | lead | principal
ALTER TABLE job ADD COLUMN min_years_exp     INTEGER;
ALTER TABLE job ADD COLUMN role_family       TEXT;     -- backend | frontend | ml | data | pm | design | ...
-- Eligibility signals (Tier-2 deterministic regex fills these; null = unknown).
ALTER TABLE job ADD COLUMN sponsorship          TEXT;  -- offered | none | unknown
ALTER TABLE job ADD COLUMN citizenship_required INTEGER CHECK (citizenship_required IS NULL OR citizenship_required IN (0, 1));
ALTER TABLE job ADD COLUMN clearance_required   INTEGER CHECK (clearance_required IS NULL OR clearance_required IN (0, 1));
ALTER TABLE job ADD COLUMN remote_scope         TEXT;  -- where remote is allowed, e.g. "india", "us-only", "worldwide"
ALTER TABLE job ADD COLUMN dedup_key            TEXT;  -- canonical url, else company|title|location

CREATE INDEX IF NOT EXISTS idx_job_dedup   ON job(dedup_key);
CREATE INDEX IF NOT EXISTS idx_job_company  ON job(company_id);

-- ── structured requirements (relational coverage) ────────────────────────────
CREATE TABLE IF NOT EXISTS requirement (
    id            INTEGER PRIMARY KEY,
    job_id        INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL CHECK (kind IN ('must', 'nice', 'responsibility')),
    text          TEXT NOT NULL,
    keywords_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(keywords_json)),
    variants_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(variants_json)),
    sort_order    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_requirement_job ON requirement(job_id);

-- ── artifacts: every generated output, not two fixed path slots ───────────────
CREATE TABLE IF NOT EXISTS artifact (
    id              INTEGER PRIMARY KEY,
    application_id  INTEGER NOT NULL REFERENCES application(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL CHECK (kind IN ('cv', 'cover', 'prep', 'followup', 'thankyou', 'counter')),
    path            TEXT,                 -- for file artifacts (cv.pdf, cover.pdf)
    body            TEXT,                 -- for text artifacts (prep brief, drafts)
    status          TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'final', 'sent')),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_artifact_app ON artifact(application_id);

-- ── offers: the close ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS offer (
    id              INTEGER PRIMARY KEY,
    application_id  INTEGER NOT NULL REFERENCES application(id) ON DELETE CASCADE,
    base            REAL,
    bonus           REAL,
    equity          TEXT,                 -- free text: "0.1%", "1000 RSUs/4yr"
    currency        TEXT,
    location        TEXT,
    received_at     TEXT,
    status          TEXT NOT NULL DEFAULT 'received' CHECK (status IN ('received', 'negotiating', 'accepted', 'declined')),
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_offer_app ON offer(application_id);

-- ── agent_task: the loop spine (dashboard writes intents, agent drains) ───────
CREATE TABLE IF NOT EXISTS agent_task (
    id              INTEGER PRIMARY KEY,
    kind            TEXT NOT NULL,        -- extract_reqs | tailor | prep | draft_followup | negotiate | ...
    job_id          INTEGER REFERENCES job(id) ON DELETE CASCADE,
    application_id  INTEGER REFERENCES application(id) ON DELETE CASCADE,
    payload_json    TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(payload_json)),
    state           TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'claimed', 'done', 'failed')),
    result_json     TEXT CHECK (result_json IS NULL OR json_valid(result_json)),
    error           TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    claimed_at      TEXT,
    done_at         TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_task_state ON agent_task(state);

-- ── application: snapshot the prediction so Learn can calibrate ───────────────
-- (`stage` is a free TEXT column since 005; the new 'accepted' terminal needs
--  no schema change -- it is enforced in tracker rules, not the DB.)
ALTER TABLE application ADD COLUMN predicted_band  TEXT;   -- skip | weak | stretch | strong, at apply time
ALTER TABLE application ADD COLUMN predicted_score REAL;

-- ── voice: the per-user captured style (default voice lives in shared/) ───────
CREATE TABLE IF NOT EXISTS voice_profile (
    id            INTEGER PRIMARY KEY,
    style_md      TEXT NOT NULL,          -- learned positive style (not the banned-word gate)
    learned_from  TEXT,                   -- provenance: which files it was distilled from
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- ── target: explicit, queryable work-authorization for the eligibility filter ─
ALTER TABLE target ADD COLUMN work_auth_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(work_auth_json));
-- shape: {"citizenships": ["IN"], "needs_sponsorship": true, "has_clearance": false}

-- ── backfills from existing data (deterministic, pure SQL) ────────────────────
-- One company row per distinct employer seen in jobs and the watchlist.
INSERT OR IGNORE INTO company (name)
    SELECT DISTINCT company FROM job
     WHERE company IS NOT NULL AND trim(company) <> '';
INSERT OR IGNORE INTO company (name)
    SELECT DISTINCT company FROM watchlist
     WHERE company IS NOT NULL AND trim(company) <> '';
UPDATE job
   SET company_id = (SELECT id FROM company WHERE company.name = job.company)
 WHERE company_id IS NULL;

-- Canonical dedup key for existing rows: the url when present, else a
-- normalized company|title|location triple.
UPDATE job
   SET dedup_key = lower(trim(
         CASE WHEN url IS NOT NULL AND trim(url) <> '' THEN url
              ELSE company || '|' || title || '|' || coalesce(location, '') END))
 WHERE dedup_key IS NULL;
