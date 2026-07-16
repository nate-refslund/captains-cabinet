-- 046-embedding-meta.sql — EMBED-SEAM provenance (R4, 2026-07-12)
--
-- One row recording the embedding provider / model / dims the cabinet_memory
-- store was actually built WITH. The retrieval library (cabinet/scripts/lib/
-- memory.sh) reads the active contract from the EMBED_PROVIDER / EMBED_MODEL /
-- EMBED_DIMS seam, resolved process-env > cabinet/.env > compiled default
-- (voyage / voyage-4-large / 1024) — the cabinet-doctor probe resolves its
-- compare side through the SAME chain, so the two can never disagree on a
-- .env-configured seam (2026-07-15). This table is
-- the persisted counterpart so cabinet-doctor can detect DRIFT between the
-- configured seam and what the store was embedded with — a dims change means a
-- full re-embed backfill, and a silent mismatch corrupts vector search.
--
-- Stamped by memory_embedding_stamp() (memory.sh) at deploy/bootstrap — NOT on
-- the read path. Deploy paths stamp --if-absent (2026-07-15): the FIRST stamp
-- is the provenance and a restart never overwrites it — an unconditional
-- upsert would re-bless a config flip and erase the doctor's drift WARN. The
-- bare upsert re-stamp is reserved for the re-embed organ / a captain closing
-- drift after a verified full backfill. Additive + idempotent: safe to apply
-- to an existing estate (an unstamped store simply has no row until the first
-- stamp; the doctor treats "no row" as "not yet stamped", never as an error).
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
