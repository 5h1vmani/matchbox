-- Matchbox migration 009: the interview loop (Workspace timeline + debrief).
--
-- Rounds are MANUAL entry -- there is no calendar/ATS/email sync, so nothing
-- here is auto-populated. A debrief is a one-tap, honest self-report captured
-- after a round; it is shown side-by-side with outcomes, never dressed up as a
-- calibrated statistic. The prior debrief is carried into the next prep task as
-- assisted context (an assisted draft, not computed intelligence).

CREATE TABLE IF NOT EXISTS interview_round (
    id              INTEGER PRIMARY KEY,
    application_id  INTEGER NOT NULL REFERENCES application(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL CHECK (kind IN ('recruiter', 'hm', 'technical', 'onsite', 'values', 'other')),
    scheduled_at    TEXT,                 -- ISO; null = recorded but not dated (manual)
    status          TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'done', 'cancelled')),
    focus           TEXT,                 -- what this round centers on
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_interview_round_app ON interview_round(application_id);

-- One debrief per round (round_id UNIQUE -> upsert). sentiment is the user's own
-- read, nullable/unknown when not given -- we never infer it.
CREATE TABLE IF NOT EXISTS debrief (
    id          INTEGER PRIMARY KEY,
    round_id    INTEGER NOT NULL UNIQUE REFERENCES interview_round(id) ON DELETE CASCADE,
    sentiment   TEXT CHECK (sentiment IS NULL OR sentiment IN ('good', 'mixed', 'tough', 'unknown')),
    notes       TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
