-- Matchbox migration 008: the reusable answer library (Apply packet, Questions tab).
--
-- A bank of question/answer pairs the user has written once and reuses across
-- applications. Reuses the bullet `facts_verified` gate pattern -- answers land
-- unverified from ingest and the user confirms them at /review, exactly like
-- bullets. `used_count` and `facts_verified` are both NEW columns here:
-- `summary_variant` (the nearest existing reusable-prose table) carries neither.
-- Per-company tailoring recombines only what the user wrote; it never fabricates.

CREATE TABLE IF NOT EXISTS answer (
    id              INTEGER PRIMARY KEY,
    question        TEXT NOT NULL,
    answer          TEXT NOT NULL,
    category        TEXT,                 -- e.g. why-us | strength | logistics | salary
    facts_verified  INTEGER NOT NULL DEFAULT 0 CHECK (facts_verified IN (0, 1)),
    used_count      INTEGER NOT NULL DEFAULT 0,
    source_file     TEXT,                 -- provenance: which inbox file it came from
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_answer_verified ON answer(facts_verified);
