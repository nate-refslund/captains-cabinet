-- cabinet-memory-content-tsv.sql — Lexical full-text substrate for cabinet_memory.
-- Adds a generated tsvector over `content` plus a GIN index, enabling hybrid
-- (vector + full-text) retrieval with no second write path: the column keeps
-- itself in sync (GENERATED ALWAYS ... STORED), so existing writers need no
-- changes.
--
-- Additive + idempotent (ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS).
-- The base schema (cabinet/sql/cabinet_memory.sql) carries the IDENTICAL
-- statements since 2026-07-07, so fresh deployments converge without this
-- migration; keep both in lockstep if the column definition ever changes.
-- Note: the column-add rewrites the table once to backfill (verified cheap:
-- max(length(content)) ~66KB, well under the tsvector 1MB limit).
--
-- Apply:
--   psql "$NEON_CONNECTION_STRING" -f cabinet/migrations/cabinet-memory-content-tsv.sql

ALTER TABLE cabinet_memory
  ADD COLUMN IF NOT EXISTS content_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_cm_tsv
  ON cabinet_memory USING GIN (content_tsv);

-- Sanity verification (idempotent):
-- SELECT count(*) FROM cabinet_memory
--   WHERE content_tsv @@ plainto_tsquery('english', 'officer');
