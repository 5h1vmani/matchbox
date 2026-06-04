-- Matchbox migration 005: application tracker pipeline model.
--
-- Evolves `application` into the richer per-user pipeline row the v1 tracker
-- dashboard needs (design handoff §05), and remaps the legacy status taxonomy
-- to the design's stages. The migration runner applies each version exactly
-- once, so these ALTERs/INSERTs never re-run.
--
-- Stage remap:  draft->saved  applied->applied  interview->phone (split
-- phone/onsite can't be inferred -> default phone)  offer->offer
-- rejected/withdrawn->rejected ("Closed", reopenable).
--
-- The legacy `status` and single-text `notes` columns are kept for rollback
-- safety and dropped in a later migration once the SPA is the only writer.

-- New scalar columns on the pipeline row.
ALTER TABLE application ADD COLUMN stage             TEXT;
ALTER TABLE application ADD COLUMN salary            TEXT;
ALTER TABLE application ADD COLUMN source            TEXT;
ALTER TABLE application ADD COLUMN starred           INTEGER NOT NULL DEFAULT 0 CHECK (starred IN (0, 1));
ALTER TABLE application ADD COLUMN has_draft         INTEGER NOT NULL DEFAULT 0 CHECK (has_draft IN (0, 1));
ALTER TABLE application ADD COLUMN updated_at        TEXT;
ALTER TABLE application ADD COLUMN next_action_kind  TEXT;
ALTER TABLE application ADD COLUMN next_action_time  TEXT;

-- Backfill the stage from the legacy status.
UPDATE application SET stage = CASE status
    WHEN 'draft'     THEN 'saved'
    WHEN 'applied'   THEN 'applied'
    WHEN 'interview' THEN 'phone'
    WHEN 'offer'     THEN 'offer'
    WHEN 'rejected'  THEN 'rejected'
    WHEN 'withdrawn' THEN 'rejected'
    ELSE 'saved'
  END
  WHERE stage IS NULL;

-- Seed updated_at so staleness has something to work from.
UPDATE application
   SET updated_at = COALESCE(response_at, applied_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
   WHERE updated_at IS NULL;

-- Child tables: notes (timestamped list), contacts (people), events (history).
CREATE TABLE IF NOT EXISTS app_note (
    id              INTEGER PRIMARY KEY,
    application_id  INTEGER NOT NULL REFERENCES application(id) ON DELETE CASCADE,
    text            TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_app_note_app ON app_note(application_id);

CREATE TABLE IF NOT EXISTS app_contact (
    id              INTEGER PRIMARY KEY,
    application_id  INTEGER NOT NULL REFERENCES application(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    role            TEXT,
    initials        TEXT
);
CREATE INDEX IF NOT EXISTS idx_app_contact_app ON app_contact(application_id);

CREATE TABLE IF NOT EXISTS app_event (
    id              INTEGER PRIMARY KEY,
    application_id  INTEGER NOT NULL REFERENCES application(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,  -- saved|applied|reply|screen|onsite|offer|rejected|note|advanced|followup
    text            TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_app_event_app ON app_event(application_id);

-- Migrate the legacy single-text note into the notes list.
INSERT INTO app_note (application_id, text, created_at)
  SELECT id, notes, COALESCE(updated_at, applied_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    FROM application
   WHERE notes IS NOT NULL AND trim(notes) <> '';

-- Synthesize an "applied" history event so the timeline is not empty.
INSERT INTO app_event (application_id, kind, text, created_at)
  SELECT id, 'applied', 'Applied', applied_at
    FROM application
   WHERE applied_at IS NOT NULL;
