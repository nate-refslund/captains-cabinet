-- cabinet/sql/045-org-runtime-slice.sql
-- Outcome-to-OVI vertical slice.
--
-- Framework-level schema for the single-product organization runtime. The
-- source of truth is `org_events`: every projection below must be rebuildable
-- from append-only events. This file is idempotent and additive.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================================
-- org_events: central append-only ledger
-- =============================================================
CREATE TABLE IF NOT EXISTS org_events (
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type TEXT NOT NULL,
  product_slug TEXT NOT NULL,
  aggregate_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  actor TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'cli',
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  supersedes_event_id UUID REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_org_events_product_created
  ON org_events(product_slug, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_org_events_aggregate
  ON org_events(product_slug, aggregate_type, aggregate_id, created_at DESC);

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
  product_slug TEXT NOT NULL,
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

CREATE INDEX IF NOT EXISTS idx_captain_outcomes_product_state
  ON captain_outcomes(product_slug, state, updated_at DESC);

CREATE TABLE IF NOT EXISTS missions (
  mission_id TEXT PRIMARY KEY,
  outcome_id TEXT NOT NULL REFERENCES captain_outcomes(outcome_id),
  product_slug TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS work_graph_edges (
  edge_id TEXT PRIMARY KEY,
  mission_id TEXT NOT NULL REFERENCES missions(mission_id),
  from_node_id TEXT NOT NULL REFERENCES work_graph_nodes(node_id),
  to_node_id TEXT NOT NULL REFERENCES work_graph_nodes(node_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================
-- Durable adaptive roles, hats, and mission assignments
-- =============================================================
CREATE TABLE IF NOT EXISTS org_roles (
  product_slug TEXT NOT NULL,
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
  PRIMARY KEY (product_slug, role_slug)
);

CREATE INDEX IF NOT EXISTS idx_org_roles_product_state
  ON org_roles(product_slug, state, role_slug);

CREATE TABLE IF NOT EXISTS role_memory_bindings (
  binding_id TEXT PRIMARY KEY,
  product_slug TEXT NOT NULL,
  role_slug TEXT NOT NULL,
  memory_path TEXT NOT NULL,
  memory_kind TEXT NOT NULL DEFAULT 'tier2',
  bound_event_id UUID NOT NULL REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  FOREIGN KEY (product_slug, role_slug) REFERENCES org_roles(product_slug, role_slug)
);

CREATE INDEX IF NOT EXISTS idx_role_memory_bindings_role
  ON role_memory_bindings(product_slug, role_slug, created_at DESC);

CREATE TABLE IF NOT EXISTS role_eval_results (
  eval_id TEXT PRIMARY KEY,
  product_slug TEXT NOT NULL,
  role_slug TEXT NOT NULL,
  mission_id TEXT REFERENCES missions(mission_id),
  hat_id TEXT,
  eval_name TEXT NOT NULL,
  score NUMERIC NOT NULL CHECK (score >= 0 AND score <= 1),
  passed BOOLEAN NOT NULL,
  evidence TEXT NOT NULL,
  recorded_event_id UUID NOT NULL REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  FOREIGN KEY (product_slug, role_slug) REFERENCES org_roles(product_slug, role_slug)
);

CREATE INDEX IF NOT EXISTS idx_role_eval_results_role_created
  ON role_eval_results(product_slug, role_slug, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_role_eval_results_hat
  ON role_eval_results(product_slug, role_slug, hat_id)
  WHERE hat_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS role_evolution_recommendations (
  recommendation_id TEXT PRIMARY KEY,
  product_slug TEXT NOT NULL,
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
  FOREIGN KEY (product_slug, role_slug) REFERENCES org_roles(product_slug, role_slug)
);

CREATE INDEX IF NOT EXISTS idx_role_evolution_recommendations_role_created
  ON role_evolution_recommendations(product_slug, role_slug, created_at DESC);

CREATE TABLE IF NOT EXISTS role_hats (
  hat_id TEXT PRIMARY KEY,
  product_slug TEXT NOT NULL,
  role_slug TEXT NOT NULL,
  hat_name TEXT NOT NULL,
  purpose TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('active', 'retired')) DEFAULT 'active',
  created_event_id UUID REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  FOREIGN KEY (product_slug, role_slug) REFERENCES org_roles(product_slug, role_slug)
);

CREATE INDEX IF NOT EXISTS idx_role_hats_role_state
  ON role_hats(product_slug, role_slug, state);

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
  product_slug TEXT NOT NULL,
  role_slug TEXT NOT NULL,
  hat_id TEXT REFERENCES role_hats(hat_id),
  event_id UUID NOT NULL REFERENCES org_events(event_id),
  event_kind TEXT NOT NULL,
  note TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_role_lineage_events_role
    FOREIGN KEY (product_slug, role_slug) REFERENCES org_roles(product_slug, role_slug)
);

CREATE INDEX IF NOT EXISTS idx_role_lineage_role_created
  ON role_lineage_events(product_slug, role_slug, created_at DESC);

DROP TRIGGER IF EXISTS trg_prevent_role_lineage_update ON role_lineage_events;
DROP TRIGGER IF EXISTS trg_prevent_role_lineage_delete ON role_lineage_events;

ALTER TABLE role_lineage_events
  ADD COLUMN IF NOT EXISTS product_slug TEXT;

UPDATE role_lineage_events AS lineage
   SET product_slug = events.product_slug
  FROM org_events AS events
 WHERE lineage.product_slug IS NULL
   AND lineage.event_id = events.event_id;

ALTER TABLE role_lineage_events
  ALTER COLUMN product_slug SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conrelid = 'role_lineage_events'::regclass
       AND conname = 'fk_role_lineage_events_role'
  ) THEN
    ALTER TABLE role_lineage_events
      ADD CONSTRAINT fk_role_lineage_events_role
      FOREIGN KEY (product_slug, role_slug)
      REFERENCES org_roles(product_slug, role_slug);
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
  product_slug TEXT NOT NULL,
  week_start DATE NOT NULL,
  verified_outcome_value NUMERIC NOT NULL,
  burden_index NUMERIC NOT NULL CHECK (burden_index > 0),
  ovi NUMERIC NOT NULL,
  trend_vs_prior NUMERIC,
  components JSONB NOT NULL DEFAULT '{}'::jsonb,
  published_event_id UUID REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (product_slug, week_start)
);

CREATE TABLE IF NOT EXISTS learning_digests (
  digest_id TEXT PRIMARY KEY,
  product_slug TEXT NOT NULL,
  week_start DATE NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  sanitized BOOLEAN NOT NULL DEFAULT true,
  published_event_id UUID REFERENCES org_events(event_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_learning_digests_product_week
  ON learning_digests(product_slug, week_start DESC);
