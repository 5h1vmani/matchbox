-- Matchbox v0.4 migration 003: geography tagging on jobs.
-- See docs/product-thesis.md (Discovery architecture). Additive only.
-- Lets discovery tag a job's country and remote status, and the inbox
-- filter by "Remote", a specific country, or both. The data model is
-- country-agnostic; only source integrations are sequenced.

ALTER TABLE job ADD COLUMN country TEXT;
ALTER TABLE job ADD COLUMN remote INTEGER NOT NULL DEFAULT 0 CHECK (remote IN (0, 1));

CREATE INDEX IF NOT EXISTS idx_job_country ON job(country);
CREATE INDEX IF NOT EXISTS idx_job_remote ON job(remote);
