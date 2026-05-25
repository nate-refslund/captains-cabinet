-- Org-Runtime Schema — Cabinet self-organizing runtime tables
-- Idempotent: safe to re-run (CREATE TABLE IF NOT EXISTS throughout)

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- Outcomes — Captain-declared desired end states
-- ============================================================
CREATE TABLE IF NOT EXISTS outcomes (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  outcome_id VARCHAR(50) NOT NULL UNIQUE,  -- e.g. "outcome-001"
  name TEXT NOT NULL,
  description TEXT,
  measurable_criteria JSONB NOT NULL DEFAULT '[]',
  status VARCHAR(20) NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'active', 'achieved', 'retired')),
  captain_ratified BOOLEAN DEFAULT FALSE,
  ratified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- Missions — compiled from outcomes, each a unit of work
-- ============================================================
CREATE TABLE IF NOT EXISTS missions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  description TEXT,
  outcome_id UUID REFERENCES outcomes(id),
  status VARCHAR(20) NOT NULL DEFAULT 'planning'
    CHECK (status IN ('planning', 'active', 'verifying', 'complete', 'failed')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- Work Graph Nodes — tasks in a mission DAG
-- ============================================================
CREATE TABLE IF NOT EXISTS work_graph_nodes (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  mission_id UUID NOT NULL REFERENCES missions(id),
  description TEXT NOT NULL,
  assigned_role VARCHAR(20),
  status VARCHAR(20) NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'ready', 'in_progress', 'done', 'blocked', 'failed')),
  verification_criteria JSONB DEFAULT '[]',
  verification_passed BOOLEAN,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

-- ============================================================
-- Work Graph Edges — dependencies between nodes
-- ============================================================
CREATE TABLE IF NOT EXISTS work_graph_edges (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  from_node UUID NOT NULL REFERENCES work_graph_nodes(id),
  to_node UUID NOT NULL REFERENCES work_graph_nodes(id),
  UNIQUE(from_node, to_node)
);

-- ============================================================
-- OVI Weekly Snapshots — composite score over time
-- ============================================================
CREATE TABLE IF NOT EXISTS ovi_snapshots (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  snapshot_date DATE NOT NULL,
  composite_score NUMERIC(6,2) NOT NULL,
  trend_direction VARCHAR(20)
    CHECK (trend_direction IN ('improving', 'stable', 'declining')),
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ovi_snapshots_date
  ON ovi_snapshots(snapshot_date DESC);

-- ============================================================
-- OVI Components — per-component readings for each snapshot
-- ============================================================
CREATE TABLE IF NOT EXISTS ovi_components (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  snapshot_id UUID NOT NULL REFERENCES ovi_snapshots(id),
  component_name VARCHAR(100) NOT NULL,
  raw_value NUMERIC,
  normalized_value NUMERIC(5,4),
  weight NUMERIC(5,4),
  weighted_value NUMERIC(6,4),
  UNIQUE(snapshot_id, component_name)
);

-- ============================================================
-- Role Lineage Events — append-only adaptation log
-- ============================================================
CREATE TABLE IF NOT EXISTS role_lineage_events (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  role VARCHAR(20) NOT NULL,
  trigger_type VARCHAR(50) NOT NULL,
  evidence TEXT NOT NULL,
  adaptation TEXT NOT NULL,
  rationale TEXT NOT NULL,
  approved_by VARCHAR(50),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_role_lineage_role
  ON role_lineage_events(role);
CREATE INDEX IF NOT EXISTS idx_role_lineage_created
  ON role_lineage_events(created_at);

-- ============================================================
-- Learning Digest Entries — sanitized weekly digests
-- ============================================================
CREATE TABLE IF NOT EXISTS learning_digest_entries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  digest_week VARCHAR(10) NOT NULL,  -- e.g. "2026-W22"
  content_sanitized TEXT NOT NULL,
  source_count INTEGER DEFAULT 0,
  published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
