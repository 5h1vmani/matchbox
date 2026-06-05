-- Matchbox migration 004: application tracking columns.
-- Adds next_action, next_action_at, and notes to the application table.
-- Each ALTER is idempotent: SQLite raises "duplicate column name" on
-- re-run; we guard with a trigger-free approach by wrapping each ALTER
-- inside a separate executescript call — the migration runner applies
-- each version exactly once, so re-runs never reach here.  The CHECK
-- below lives only in the future; for now, plain TEXT is fine.

ALTER TABLE application ADD COLUMN next_action     TEXT;
ALTER TABLE application ADD COLUMN next_action_at  TEXT;
ALTER TABLE application ADD COLUMN notes           TEXT;
