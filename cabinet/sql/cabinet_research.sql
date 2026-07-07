-- Cabinet Research — pgvector store for research briefs
-- Substrate for the research scripts (cabinet/scripts/):
--   embed-research.sh     INSERTs (title, topic, content, summary, embedding, tags, officer, decay_rate)
--   search-research.sh    reads   (title, embedding, created_at, decay_rate, usage_status, summary)
--   supersede-research.sh sets    (usage_status = 'superseded', updated_at)
-- cabinet-id-neon-phase1b.sql additionally stamps cabinet_id; the column and
-- its index are included here with identical names/defaults so either apply
-- order converges to the same schema.
--
-- Target: Neon PostgreSQL (or any PG with pgvector >= 0.5.0).
-- Connection via $NEON_CONNECTION_STRING.
--
-- Run once per Cabinet deployment:
--   psql "$NEON_CONNECTION_STRING" -f cabinet/sql/cabinet_research.sql

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS cabinet_research (
  id BIGSERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  topic TEXT,                               -- derived from brief filename by embed-research.sh
  content TEXT NOT NULL,
  summary TEXT,                             -- short excerpt shown in search results
  embedding VECTOR(1024),                   -- voyage-4-large
  tags TEXT[] DEFAULT '{}',
  officer VARCHAR(16),                      -- embedding officer ($OFFICER_NAME, default cro)
  decay_rate VARCHAR(32) DEFAULT 'fast-moving',   -- evergreen | fast-moving | time-sensitive
  usage_status VARCHAR(32) DEFAULT 'new',   -- 'superseded' set by supersede-research.sh
  cabinet_id TEXT NOT NULL DEFAULT 'main',  -- multi-cabinet stamping (cabinet-id-neon-phase1b.sql)
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vector similarity search (cosine distance) — search-research.sh top-5
CREATE INDEX IF NOT EXISTS idx_cr_embed
  ON cabinet_research USING hnsw (embedding vector_cosine_ops);

-- Officer-scoped / recency queries
CREATE INDEX IF NOT EXISTS idx_cr_officer
  ON cabinet_research(officer, created_at DESC);

-- Live-brief filter used by search-research.sh (usage_status != 'superseded')
CREATE INDEX IF NOT EXISTS idx_cr_status
  ON cabinet_research(usage_status);

-- Same name/shape as cabinet-id-neon-phase1b.sql so either apply order converges
CREATE INDEX IF NOT EXISTS cabinet_research_cabinet_idx
  ON cabinet_research(cabinet_id);
