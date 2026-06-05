-- Matchbox v0.4 migration 002: the evidence graph.
-- See docs/v0.4-design.md section 4. Additive only; v0.3 tables untouched.
-- The data backfill (bullet/project -> claim + rendering) runs as the
-- Python step registered for version 2 in migrations.py, after this DDL.
--
-- Conventions match schema.sql: INTEGER PK, _json columns json_valid()-guarded,
-- ISO-8601 UTC TEXT timestamps, booleans as INTEGER 0/1 with CHECK, enums as
-- TEXT with CHECK lists.

-- The atomic, sourced, verifiable unit of a person's history. Root of truth;
-- replaces the free-floating text in `bullet`.
CREATE TABLE IF NOT EXISTS claim (
    id             INTEGER PRIMARY KEY,
    experience_id  INTEGER REFERENCES experience(id) ON DELETE CASCADE,  -- null for profile-level claims
    kind           TEXT NOT NULL CHECK (kind IN
                       ('accomplishment', 'responsibility', 'skill_use', 'credential')),
    assertion      TEXT NOT NULL,            -- canonical, neutral statement of fact (NOT CV-phrased)
    situation      TEXT,                     -- STAR decomposition, all optional, filled by elicitation
    task           TEXT,
    action         TEXT,
    result         TEXT,
    metric_value   TEXT,                     -- "40%", "12", "$2M" — TEXT keeps units
    metric_kind    TEXT,                     -- "percent_reduction", "team_size", ...
    verification   TEXT NOT NULL DEFAULT 'unverified' CHECK (verification IN
                       ('unverified', 'self_attested', 'artifact_backed', 'reference_backed')),
    confidence     REAL,                     -- 0..1, model-estimated extraction confidence
    defensibility  INTEGER CHECK (defensibility IS NULL OR defensibility BETWEEN 0 AND 5),
    needs_detail   INTEGER NOT NULL DEFAULT 0 CHECK (needs_detail IN (0, 1)),  -- elicitation flag
    source_file    TEXT,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    verified_at    TEXT,
    verified_by    TEXT                      -- subject identity that confirmed (invariant I3)
);
CREATE INDEX IF NOT EXISTS idx_claim_experience ON claim(experience_id);
CREATE INDEX IF NOT EXISTS idx_claim_verification ON claim(verification);

-- External corroboration for a claim. A claim with >=1 artifact/reference row
-- can be promoted past 'self_attested'.
CREATE TABLE IF NOT EXISTS evidence (
    id          INTEGER PRIMARY KEY,
    claim_id    INTEGER NOT NULL REFERENCES claim(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN
                    ('artifact_url', 'document', 'reference', 'metric_source')),
    detail      TEXT NOT NULL,               -- URL, file path, reference name+contact
    captured_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_evidence_claim ON evidence(claim_id);

-- A phrasing of a claim for a target. The ONLY text that may reach a document
-- (invariant I1). Bound to claim_id so it cannot assert a fact outside the claim.
CREATE TABLE IF NOT EXISTS rendering (
    id           INTEGER PRIMARY KEY,
    claim_id     INTEGER NOT NULL REFERENCES claim(id) ON DELETE CASCADE,
    job_id       INTEGER REFERENCES job(id) ON DELETE CASCADE,  -- null = generic/default phrasing
    text         TEXT NOT NULL,              -- CV-ready sentence; voice-rules validated
    carries_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(carries_json)),
    approved     INTEGER NOT NULL DEFAULT 0 CHECK (approved IN (0, 1)),  -- containment gate (I2)
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_rendering_claim ON rendering(claim_id);
CREATE INDEX IF NOT EXISTS idx_rendering_job ON rendering(job_id);
