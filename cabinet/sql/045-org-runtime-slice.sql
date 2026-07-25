-- cabinet/sql/045-org-runtime-slice.sql
-- Outcome-to-OVI vertical slice.
--
-- Framework-level schema for the organization runtime, keyed by LANE. The
-- source of truth is `org_events`: every projection below must be rebuildable
-- from append-only events. This file is idempotent and additive.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================================
-- LANE-KEY RENAME (2026-07-25): product_slug -> lane_slug.
--
-- The column never carried product data. Every row this repo has ever
-- written holds the deployment's own lane key, and the dashboard says so in
-- code (cabinet/dashboard/src/lib/world/course.ts). The old name was the
-- last structural trace of a runtime built for ONE software product; a
-- cabinet run by a law firm or a bakery keys the same rows by lane.
--
-- Guarded and idempotent. On a fresh database every statement below is a
-- no-op. On a database created before the rename, each table's legacy
-- column is renamed IN PLACE (a catalog-only operation: no rewrite, no data
-- movement, and Postgres carries the rename into every dependent index,
-- primary key and foreign key automatically), and the four indexes whose
-- NAMES carried the old word are dropped so the definitions further down
-- recreate them under their lane names.
-- =============================================================
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'org_events', 'captain_outcomes', 'missions', 'claude_native_tasks',
    'org_roles', 'role_memory_bindings', 'role_eval_results',
    'role_evolution_recommendations', 'role_hats', 'role_lineage_events',
    'ovi_weeks', 'learning_digests'
  ] LOOP
    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = t AND column_name = 'product_slug')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                        WHERE table_schema = current_schema()
                          AND table_name = t AND column_name = 'lane_slug')
    THEN
      EXECUTE format('ALTER TABLE %I RENAME COLUMN product_slug TO lane_slug', t);
    END IF;
  END LOOP;
END $$;

DROP INDEX IF EXISTS idx_org_events_product_created;
DROP INDEX IF EXISTS idx_captain_outcomes_product_state;
DROP INDEX IF EXISTS idx_org_roles_product_state;
DROP INDEX IF EXISTS idx_learning_digests_product_week;

-- =============================================================
-- org_events: central append-only ledger
-- =============================================================
CREATE TABLE IF NOT EXISTS org_events (
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type TEXT NOT NULL,
  lane_slug TEXT NOT NULL,
  aggregate_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  actor TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'cli',
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  supersedes_event_id UUID REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_org_events_lane_created
  ON org_events(lane_slug, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_org_events_aggregate
  ON org_events(lane_slug, aggregate_type, aggregate_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_org_events_type
  ON org_events(event_type, created_at DESC);

CREATE OR REPLACE FUNCTION prevent_org_events_mutation()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'org_events is append-only; append a superseding event instead';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_org_events_update ON org_events;
CREATE TRIGGER trg_prevent_org_events_update
  BEFORE UPDATE ON org_events
  FOR EACH ROW EXECUTE FUNCTION prevent_org_events_mutation();

DROP TRIGGER IF EXISTS trg_prevent_org_events_delete ON org_events;
CREATE TRIGGER trg_prevent_org_events_delete
  BEFORE DELETE ON org_events
  FOR EACH ROW EXECUTE FUNCTION prevent_org_events_mutation();

-- =============================================================
-- Outcome projections
-- =============================================================
CREATE TABLE IF NOT EXISTS captain_outcomes (
  outcome_id TEXT PRIMARY KEY,
  lane_slug TEXT NOT NULL,
  title TEXT NOT NULL,
  metric_name TEXT NOT NULL,
  target_value NUMERIC NOT NULL,
  current_value NUMERIC NOT NULL DEFAULT 0,
  unit TEXT NOT NULL DEFAULT 'points',
  state TEXT NOT NULL CHECK (state IN ('proposed', 'ratified', 'superseded')),
  proposed_by TEXT NOT NULL,
  ratified_by TEXT,
  proposed_event_id UUID REFERENCES org_events(event_id),
  ratified_event_id UUID REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_captain_outcomes_lane_state
  ON captain_outcomes(lane_slug, state, updated_at DESC);

CREATE TABLE IF NOT EXISTS missions (
  mission_id TEXT PRIMARY KEY,
  outcome_id TEXT NOT NULL REFERENCES captain_outcomes(outcome_id),
  lane_slug TEXT NOT NULL,
  title TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('compiled', 'in_progress', 'verified', 'superseded')),
  compiled_event_id UUID REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS work_graph_nodes (
  node_id TEXT PRIMARY KEY,
  mission_id TEXT NOT NULL REFERENCES missions(mission_id),
  title TEXT NOT NULL,
  owner_role TEXT NOT NULL,
  acceptance_criteria TEXT NOT NULL DEFAULT '',
  evidence_required TEXT NOT NULL DEFAULT '',
  verifier_role TEXT NOT NULL DEFAULT '',
  risk_level TEXT NOT NULL DEFAULT 'medium',
  rollback_note TEXT NOT NULL DEFAULT '',
  budget_note TEXT NOT NULL DEFAULT '',
  captain_attention_estimate NUMERIC NOT NULL DEFAULT 0,
  status TEXT NOT NULL CHECK (status IN ('queue', 'wip', 'verified')),
  verified_value NUMERIC NOT NULL DEFAULT 0,
  verification_summary TEXT,
  completion_event_id UUID REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_work_graph_nodes_mission_status
  ON work_graph_nodes(mission_id, status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_work_graph_nodes_mission_node
  ON work_graph_nodes(mission_id, node_id);

ALTER TABLE work_graph_nodes
  ADD COLUMN IF NOT EXISTS acceptance_criteria TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS evidence_required TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS verifier_role TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS risk_level TEXT NOT NULL DEFAULT 'medium',
  ADD COLUMN IF NOT EXISTS rollback_note TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS budget_note TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS captain_attention_estimate NUMERIC NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS work_graph_edges (
  edge_id TEXT PRIMARY KEY,
  mission_id TEXT NOT NULL REFERENCES missions(mission_id),
  from_node_id TEXT NOT NULL REFERENCES work_graph_nodes(node_id),
  to_node_id TEXT NOT NULL REFERENCES work_graph_nodes(node_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================
-- Claude Code native task projection
-- =============================================================
CREATE TABLE IF NOT EXISTS claude_native_tasks (
  lane_slug TEXT NOT NULL,
  task_id TEXT NOT NULL,
  session_id TEXT,
  transcript_path TEXT,
  cwd TEXT,
  task_subject TEXT NOT NULL DEFAULT '',
  task_description TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK (status IN ('created', 'completed')),
  actor TEXT NOT NULL,
  teammate_name TEXT,
  team_name TEXT,
  mission_id TEXT,
  node_id TEXT,
  owner_role TEXT,
  acceptance_criteria TEXT,
  evidence_required TEXT,
  verifier_role TEXT,
  risk_level TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_event_id UUID REFERENCES org_events(event_id),
  completed_event_id UUID REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  PRIMARY KEY (lane_slug, task_id)
);

CREATE INDEX IF NOT EXISTS idx_claude_native_tasks_mission
  ON claude_native_tasks(lane_slug, mission_id, node_id);

CREATE INDEX IF NOT EXISTS idx_claude_native_tasks_status
  ON claude_native_tasks(lane_slug, status, updated_at DESC);

-- =============================================================
-- Durable adaptive roles, hats, and mission assignments
-- =============================================================
CREATE TABLE IF NOT EXISTS org_roles (
  lane_slug TEXT NOT NULL,
  role_slug TEXT NOT NULL,
  role_name TEXT NOT NULL,
  charter TEXT NOT NULL,
  current_focus TEXT NOT NULL DEFAULT '',
  authority_level TEXT NOT NULL DEFAULT 'mission_executor',
  capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
  state TEXT NOT NULL CHECK (state IN ('active', 'inactive', 'retired')) DEFAULT 'active',
  version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
  officer_session_slug TEXT,
  defined_event_id UUID NOT NULL REFERENCES org_events(event_id),
  latest_event_id UUID NOT NULL REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (lane_slug, role_slug)
);

CREATE INDEX IF NOT EXISTS idx_org_roles_lane_state
  ON org_roles(lane_slug, state, role_slug);

CREATE TABLE IF NOT EXISTS role_memory_bindings (
  binding_id TEXT PRIMARY KEY,
  lane_slug TEXT NOT NULL,
  role_slug TEXT NOT NULL,
  memory_path TEXT NOT NULL,
  memory_kind TEXT NOT NULL DEFAULT 'tier2',
  bound_event_id UUID NOT NULL REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  FOREIGN KEY (lane_slug, role_slug) REFERENCES org_roles(lane_slug, role_slug)
);

CREATE INDEX IF NOT EXISTS idx_role_memory_bindings_role
  ON role_memory_bindings(lane_slug, role_slug, created_at DESC);

CREATE TABLE IF NOT EXISTS role_eval_results (
  eval_id TEXT PRIMARY KEY,
  lane_slug TEXT NOT NULL,
  role_slug TEXT NOT NULL,
  mission_id TEXT REFERENCES missions(mission_id),
  hat_id TEXT,
  eval_name TEXT NOT NULL,
  score NUMERIC NOT NULL CHECK (score >= 0 AND score <= 1),
  passed BOOLEAN NOT NULL,
  evidence TEXT NOT NULL,
  recorded_event_id UUID NOT NULL REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  FOREIGN KEY (lane_slug, role_slug) REFERENCES org_roles(lane_slug, role_slug)
);

CREATE INDEX IF NOT EXISTS idx_role_eval_results_role_created
  ON role_eval_results(lane_slug, role_slug, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_role_eval_results_hat
  ON role_eval_results(lane_slug, role_slug, hat_id)
  WHERE hat_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS role_evolution_recommendations (
  recommendation_id TEXT PRIMARY KEY,
  lane_slug TEXT NOT NULL,
  role_slug TEXT NOT NULL,
  recommendation_type TEXT NOT NULL CHECK (
    recommendation_type IN (
      'promote_hat_to_capability',
      'adjust_charter',
      'retire_role_review',
      'continue_current_role'
    )
  ),
  hat_id TEXT,
  basis TEXT NOT NULL,
  recommended_event_id UUID NOT NULL REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  FOREIGN KEY (lane_slug, role_slug) REFERENCES org_roles(lane_slug, role_slug)
);

CREATE INDEX IF NOT EXISTS idx_role_evolution_recommendations_role_created
  ON role_evolution_recommendations(lane_slug, role_slug, created_at DESC);

CREATE TABLE IF NOT EXISTS role_hats (
  hat_id TEXT PRIMARY KEY,
  lane_slug TEXT NOT NULL,
  role_slug TEXT NOT NULL,
  hat_name TEXT NOT NULL,
  purpose TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('active', 'retired')) DEFAULT 'active',
  created_event_id UUID REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  FOREIGN KEY (lane_slug, role_slug) REFERENCES org_roles(lane_slug, role_slug)
);

CREATE INDEX IF NOT EXISTS idx_role_hats_role_state
  ON role_hats(lane_slug, role_slug, state);

CREATE TABLE IF NOT EXISTS mission_role_assignments (
  assignment_id TEXT PRIMARY KEY,
  mission_id TEXT NOT NULL REFERENCES missions(mission_id),
  hat_id TEXT NOT NULL REFERENCES role_hats(hat_id),
  node_id TEXT REFERENCES work_graph_nodes(node_id),
  assigned_to_role TEXT NOT NULL,
  assignment_event_id UUID REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_mission_role_assignments_mission_node
    FOREIGN KEY (mission_id, node_id) REFERENCES work_graph_nodes(mission_id, node_id)
);

CREATE TABLE IF NOT EXISTS role_lineage_events (
  lineage_id TEXT PRIMARY KEY,
  lane_slug TEXT NOT NULL,
  role_slug TEXT NOT NULL,
  hat_id TEXT REFERENCES role_hats(hat_id),
  event_id UUID NOT NULL REFERENCES org_events(event_id),
  event_kind TEXT NOT NULL,
  note TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_role_lineage_events_role
    FOREIGN KEY (lane_slug, role_slug) REFERENCES org_roles(lane_slug, role_slug)
);

CREATE INDEX IF NOT EXISTS idx_role_lineage_role_created
  ON role_lineage_events(lane_slug, role_slug, created_at DESC);

DROP TRIGGER IF EXISTS trg_prevent_role_lineage_update ON role_lineage_events;
DROP TRIGGER IF EXISTS trg_prevent_role_lineage_delete ON role_lineage_events;

ALTER TABLE role_lineage_events
  ADD COLUMN IF NOT EXISTS lane_slug TEXT;

UPDATE role_lineage_events AS lineage
   SET lane_slug = events.lane_slug
  FROM org_events AS events
 WHERE lineage.lane_slug IS NULL
   AND lineage.event_id = events.event_id;

ALTER TABLE role_lineage_events
  ALTER COLUMN lane_slug SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conrelid = 'role_lineage_events'::regclass
       AND conname = 'fk_role_lineage_events_role'
  ) THEN
    ALTER TABLE role_lineage_events
      ADD CONSTRAINT fk_role_lineage_events_role
      FOREIGN KEY (lane_slug, role_slug)
      REFERENCES org_roles(lane_slug, role_slug);
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conrelid = 'mission_role_assignments'::regclass
       AND conname = 'fk_mission_role_assignments_mission_node'
  ) THEN
    ALTER TABLE mission_role_assignments
      ADD CONSTRAINT fk_mission_role_assignments_mission_node
      FOREIGN KEY (mission_id, node_id)
      REFERENCES work_graph_nodes(mission_id, node_id);
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conrelid = 'role_eval_results'::regclass
       AND conname = 'fk_role_eval_results_hat'
  ) THEN
    ALTER TABLE role_eval_results
      ADD CONSTRAINT fk_role_eval_results_hat
      FOREIGN KEY (hat_id)
      REFERENCES role_hats(hat_id);
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conrelid = 'role_evolution_recommendations'::regclass
       AND conname = 'fk_role_evolution_recommendations_hat'
  ) THEN
    ALTER TABLE role_evolution_recommendations
      ADD CONSTRAINT fk_role_evolution_recommendations_hat
      FOREIGN KEY (hat_id)
      REFERENCES role_hats(hat_id);
  END IF;
END $$;

CREATE OR REPLACE FUNCTION prevent_org_history_mutation()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'organizational history is append-only; append a superseding event instead';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_role_lineage_update ON role_lineage_events;
CREATE TRIGGER trg_prevent_role_lineage_update
  BEFORE UPDATE ON role_lineage_events
  FOR EACH ROW EXECUTE FUNCTION prevent_org_history_mutation();

DROP TRIGGER IF EXISTS trg_prevent_role_lineage_delete ON role_lineage_events;
CREATE TRIGGER trg_prevent_role_lineage_delete
  BEFORE DELETE ON role_lineage_events
  FOR EACH ROW EXECUTE FUNCTION prevent_org_history_mutation();

DROP TRIGGER IF EXISTS trg_prevent_role_memory_update ON role_memory_bindings;
CREATE TRIGGER trg_prevent_role_memory_update
  BEFORE UPDATE ON role_memory_bindings
  FOR EACH ROW EXECUTE FUNCTION prevent_org_history_mutation();

DROP TRIGGER IF EXISTS trg_prevent_role_memory_delete ON role_memory_bindings;
CREATE TRIGGER trg_prevent_role_memory_delete
  BEFORE DELETE ON role_memory_bindings
  FOR EACH ROW EXECUTE FUNCTION prevent_org_history_mutation();

DROP TRIGGER IF EXISTS trg_prevent_role_eval_update ON role_eval_results;
CREATE TRIGGER trg_prevent_role_eval_update
  BEFORE UPDATE ON role_eval_results
  FOR EACH ROW EXECUTE FUNCTION prevent_org_history_mutation();

DROP TRIGGER IF EXISTS trg_prevent_role_eval_delete ON role_eval_results;
CREATE TRIGGER trg_prevent_role_eval_delete
  BEFORE DELETE ON role_eval_results
  FOR EACH ROW EXECUTE FUNCTION prevent_org_history_mutation();

DROP TRIGGER IF EXISTS trg_prevent_role_recommendation_update ON role_evolution_recommendations;
CREATE TRIGGER trg_prevent_role_recommendation_update
  BEFORE UPDATE ON role_evolution_recommendations
  FOR EACH ROW EXECUTE FUNCTION prevent_org_history_mutation();

DROP TRIGGER IF EXISTS trg_prevent_role_recommendation_delete ON role_evolution_recommendations;
CREATE TRIGGER trg_prevent_role_recommendation_delete
  BEFORE DELETE ON role_evolution_recommendations
  FOR EACH ROW EXECUTE FUNCTION prevent_org_history_mutation();

-- =============================================================
-- OVI and learning-digest projections
-- =============================================================
CREATE TABLE IF NOT EXISTS ovi_weeks (
  lane_slug TEXT NOT NULL,
  week_start DATE NOT NULL,
  verified_outcome_value NUMERIC NOT NULL,
  burden_index NUMERIC NOT NULL CHECK (burden_index > 0),
  ovi NUMERIC NOT NULL,
  trend_vs_prior NUMERIC,
  components JSONB NOT NULL DEFAULT '{}'::jsonb,
  published_event_id UUID REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (lane_slug, week_start)
);

CREATE TABLE IF NOT EXISTS learning_digests (
  digest_id TEXT PRIMARY KEY,
  lane_slug TEXT NOT NULL,
  week_start DATE NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  sanitized BOOLEAN NOT NULL DEFAULT true,
  published_event_id UUID REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_learning_digests_lane_week
  ON learning_digests(lane_slug, week_start DESC);
