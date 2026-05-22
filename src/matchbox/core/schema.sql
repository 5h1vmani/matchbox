-- Matchbox v0.3 schema. One source of truth.
--
-- Conventions:
--   - All ids are INTEGER PRIMARY KEY (sqlite rowid aliases).
--   - JSON-shaped columns end in _json and are guarded by json_valid().
--   - Timestamps are ISO-8601 UTC TEXT.
--   - Booleans are stored as INTEGER 0/1 (guarded by CHECK).
--   - Enum-typed columns are TEXT with CHECK lists.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS migration (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- ─── profile + targets ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS profile (
    id          INTEGER PRIMARY KEY,
    full_name   TEXT NOT NULL,
    email       TEXT,
    phone       TEXT,
    location    TEXT,
    links_json  TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(links_json)),
    headline    TEXT
);

CREATE TABLE IF NOT EXISTS target (
    id                   INTEGER PRIMARY KEY,
    role_families_json   TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(role_families_json)),
    dream_companies_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(dream_companies_json)),
    locations_json       TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(locations_json)),
    comp_json            TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(comp_json)),
    exclusions_json      TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(exclusions_json))
);

-- ─── library: experiences + bullets + projects + skills + summaries ───

CREATE TABLE IF NOT EXISTS experience (
    id          INTEGER PRIMARY KEY,
    company     TEXT NOT NULL,
    role        TEXT NOT NULL,
    start_date  TEXT,
    end_date    TEXT,
    location    TEXT,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bullet (
    id               INTEGER PRIMARY KEY,
    experience_id    INTEGER NOT NULL REFERENCES experience(id) ON DELETE CASCADE,
    text             TEXT NOT NULL,
    has_metric       INTEGER NOT NULL DEFAULT 0 CHECK (has_metric IN (0, 1)),
    facts_verified   INTEGER NOT NULL DEFAULT 0 CHECK (facts_verified IN (0, 1)),
    source_file      TEXT,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_bullet_experience ON bullet(experience_id);
CREATE INDEX IF NOT EXISTS idx_bullet_verified ON bullet(facts_verified);

CREATE TABLE IF NOT EXISTS project (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    text            TEXT NOT NULL,
    url             TEXT,
    facts_verified  INTEGER NOT NULL DEFAULT 0 CHECK (facts_verified IN (0, 1))
);

CREATE TABLE IF NOT EXISTS skill (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    category     TEXT,
    proficiency  TEXT CHECK (proficiency IS NULL OR proficiency IN ('working', 'fluent', 'expert'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_skill_name ON skill(lower(name));

CREATE TABLE IF NOT EXISTS summary_variant (
    id     INTEGER PRIMARY KEY,
    label  TEXT NOT NULL,
    text   TEXT NOT NULL
);

-- ─── tags + polymorphic item_tag + embeddings ─────────────────────────

CREATE TABLE IF NOT EXISTS tag (
    id     INTEGER PRIMARY KEY,
    facet  TEXT NOT NULL CHECK (facet IN ('role_family', 'tech', 'seniority', 'impact')),
    value  TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tag_facet_value ON tag(facet, value);

CREATE TABLE IF NOT EXISTS item_tag (
    item_type  TEXT NOT NULL CHECK (item_type IN ('bullet', 'project', 'skill', 'summary_variant')),
    item_id    INTEGER NOT NULL,
    tag_id     INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
    PRIMARY KEY (item_type, item_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_item_tag_tag ON item_tag(tag_id);
CREATE INDEX IF NOT EXISTS idx_item_tag_item ON item_tag(item_type, item_id);

CREATE TABLE IF NOT EXISTS embedding (
    item_type       TEXT NOT NULL CHECK (item_type IN ('bullet', 'project', 'skill', 'summary_variant', 'requirement')),
    item_id         INTEGER NOT NULL,
    model_version   TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    vector          BLOB NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (item_type, item_id, model_version)
);
CREATE INDEX IF NOT EXISTS idx_embedding_hash ON embedding(content_hash);

-- ─── discovery + jobs ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ats_source (
    id        INTEGER PRIMARY KEY,
    ats_type  TEXT NOT NULL CHECK (ats_type IN ('greenhouse', 'lever', 'ashby', 'workable', 'smartrecruiters', 'recruitee', 'teamtailor', 'personio', 'breezy', 'jazzhr')),
    slug      TEXT NOT NULL,
    company   TEXT NOT NULL,
    country   TEXT,
    sector    TEXT,
    enabled   INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    last_ok_at      TEXT,
    last_error      TEXT,
    last_attempt_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ats_source_type_slug ON ats_source(ats_type, slug);

CREATE TABLE IF NOT EXISTS job (
    id                    INTEGER PRIMARY KEY,
    source                INTEGER REFERENCES ats_source(id) ON DELETE SET NULL,
    company               TEXT NOT NULL,
    title                 TEXT NOT NULL,
    location              TEXT,
    url                   TEXT NOT NULL,
    apply_url             TEXT,
    jd_text               TEXT NOT NULL,
    requirements_json     TEXT CHECK (requirements_json IS NULL OR json_valid(requirements_json)),
    requirements_model    TEXT,
    requirements_jd_hash  TEXT,
    posted_at             TEXT,
    fetched_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    status                TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'scored', 'selected', 'tailored', 'applied', 'skipped', 'rejected')),
    score                 REAL,
    score_breakdown_json  TEXT CHECK (score_breakdown_json IS NULL OR json_valid(score_breakdown_json))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_job_url ON job(url);
CREATE INDEX IF NOT EXISTS idx_job_status ON job(status);

-- ─── runs + applications ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS run (
    id          TEXT PRIMARY KEY,                          -- YYYY-MM-DD-NNN
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    status      TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'error'))
);

CREATE TABLE IF NOT EXISTS run_job (
    run_id      TEXT    NOT NULL REFERENCES run(id) ON DELETE CASCADE,
    job_id      INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    want_cv     INTEGER NOT NULL DEFAULT 1 CHECK (want_cv IN (0, 1)),
    want_cover  INTEGER NOT NULL DEFAULT 0 CHECK (want_cover IN (0, 1)),
    palette     TEXT    NOT NULL DEFAULT 'slate',
    font        TEXT    NOT NULL DEFAULT 'source-serif',
    PRIMARY KEY (run_id, job_id)
);

CREATE TABLE IF NOT EXISTS application (
    id             INTEGER PRIMARY KEY,
    job_id         INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    run_id         TEXT    REFERENCES run(id) ON DELETE SET NULL,
    cv_path        TEXT,
    cover_path     TEXT,
    status         TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'applied', 'interview', 'offer', 'rejected', 'withdrawn')),
    applied_at     TEXT,
    response_type  TEXT,
    response_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_application_job ON application(job_id);
CREATE INDEX IF NOT EXISTS idx_application_status ON application(status);

-- ─── settings ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS setting (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
