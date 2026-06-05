-- Matchbox migration 006: discovery decisions + watchlist.
--
-- Adds the per-job discovery decision state the Discovery surfaces need
-- (integration spec §6) and a `watchlist` table for companies worth watching
-- with no eligible role today. The migration runner applies each version
-- exactly once, so these ALTERs never re-run.
--
-- Decision lifecycle (derived membership, never persisted as a flag):
--   discovery_decision  null | tracked | dismissed | tailoring | watch
--   skipped_on          ISO date; if == today, the role drops from today's queue
--   freshness           open | closing | closed  (defaults to open at read time;
--                       populated out-of-band by the render-based verify_open job)
--   closes_at           ISO datetime of the application deadline, when known
--
-- inQueue   = decision is null AND eligibility != 'ineligible'
--             AND freshness != 'closed' AND skipped_on != today
-- inSetAside= decision is null AND (eligibility == 'ineligible' OR freshness == 'closed')

ALTER TABLE job ADD COLUMN discovery_decision TEXT;  -- null|tracked|dismissed|tailoring|watch
ALTER TABLE job ADD COLUMN skipped_on         TEXT;  -- ISO date; == today drops from today's queue
ALTER TABLE job ADD COLUMN freshness          TEXT;  -- open|closing|closed (default open at read time)
ALTER TABLE job ADD COLUMN closes_at          TEXT;  -- ISO datetime of the deadline, when known

CREATE TABLE IF NOT EXISTS watchlist (
    id          INTEGER PRIMARY KEY,
    company     TEXT NOT NULL UNIQUE,
    note        TEXT,
    status      TEXT NOT NULL DEFAULT 'watching',  -- watching | active
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
