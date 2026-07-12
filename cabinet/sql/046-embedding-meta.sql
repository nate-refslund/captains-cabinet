-- 046-embedding-meta.sql — EMBED-SEAM provenance (R4, 2026-07-12)
--
-- One row recording the embedding provider / model / dims the cabinet_memory
-- store was actually built WITH. The retrieval library (cabinet/scripts/lib/
-- memory.sh) reads the active contract from the EMBED_PROVIDER / EMBED_MODEL /
-- EMBED_DIMS env seam (defaults: voyage / voyage-4-large / 1024); this table is
-- the persisted counterpart so cabinet-doctor can detect DRIFT between the
-- configured seam and what the store was embedded with — a dims change means a
-- full re-embed backfill, and a silent mismatch corrupts vector search.
--
-- Stamped by memory_embedding_stamp() (memory.sh) at deploy/bootstrap — NOT on
-- the read path. Additive + idempotent: safe to apply to an existing estate
-- (an unstamped store simply has no row until the first stamp; the doctor
-- treats "no row" as "not yet stamped", never as an error).
--
-- Target: Neon PostgreSQL. Applied by cabinet-bootstrap.sh schema_apply_list
-- and load-preset.sh (existing cabinets). Closes operative-egg-ledger:1938.

CREATE TABLE IF NOT EXISTS cabinet_embedding_meta (
  id         INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),  -- singleton row
  provider   TEXT        NOT NULL,
  model      TEXT        NOT NULL,
  dims       INT         NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
