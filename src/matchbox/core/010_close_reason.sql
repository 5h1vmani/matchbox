-- Matchbox migration 010: structured close reason (rejection learning).
--
-- One nullable column on `application`. Captured at close (via set_stage /
-- log_response); a deterministic GROUP BY turns it into honest categories.
-- Uncaptured closures stay NULL and read as "unknown" -- never inferred.
ALTER TABLE application ADD COLUMN close_reason TEXT;
