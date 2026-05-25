-- framework/events/schema.sql
-- Event ledger: the organizational black-box flight recorder.
-- Every meaningful state change emits an event. All other systems
-- derive state from events. This is the foundation.

CREATE TABLE IF NOT EXISTS org_events (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type  VARCHAR(100) NOT NULL,
    actor       VARCHAR(100) NOT NULL,  -- role slug, 'captain', or 'system'
    payload     JSONB NOT NULL DEFAULT '{}',
    parent_id   UUID REFERENCES org_events(id),  -- causal chain
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_org_events_type ON org_events(event_type);
CREATE INDEX IF NOT EXISTS idx_org_events_actor ON org_events(actor);
CREATE INDEX IF NOT EXISTS idx_org_events_created ON org_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_org_events_parent ON org_events(parent_id);
CREATE INDEX IF NOT EXISTS idx_org_events_payload ON org_events USING GIN(payload);

-- Roles: durable organizational entities with lifecycle.
-- A role is NOT a session or persona — it's an entity with charter,
-- capabilities, memory ownership, and eval history that persists
-- independently of any running process.

CREATE TABLE IF NOT EXISTS roles (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug            VARCHAR(50) NOT NULL UNIQUE,
    title           VARCHAR(200) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'suspended', 'retired')),
    charter         TEXT NOT NULL,          -- what this role is responsible for
    capabilities    TEXT[] NOT NULL DEFAULT '{}',
    authority_level VARCHAR(20) NOT NULL DEFAULT 'standard'
                        CHECK (authority_level IN ('observer', 'standard', 'elevated', 'admin')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_roles_status ON roles(status);
CREATE INDEX IF NOT EXISTS idx_roles_slug ON roles(slug);

-- Role lineage: append-only log of every adaptation.
-- Never delete entries. Role learning survives role changes.

CREATE TABLE IF NOT EXISTS role_lineage (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    role_id         UUID NOT NULL REFERENCES roles(id),
    event_id        UUID REFERENCES org_events(id),  -- the event that triggered this
    adaptation_type VARCHAR(50) NOT NULL
                        CHECK (adaptation_type IN (
                            'charter_change', 'capability_added', 'capability_removed',
                            'authority_change', 'hat_assigned', 'hat_removed',
                            'suspended', 'reactivated', 'retired', 'created'
                        )),
    description     TEXT NOT NULL,
    evidence        TEXT,               -- what observation triggered this
    rationale       TEXT,               -- why this change was made
    approved_by     VARCHAR(100),       -- 'captain', role slug, or 'system'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_role_lineage_role ON role_lineage(role_id);
CREATE INDEX IF NOT EXISTS idx_role_lineage_type ON role_lineage(adaptation_type);
CREATE INDEX IF NOT EXISTS idx_role_lineage_created ON role_lineage(created_at DESC);

-- Hats: temporary specializations assigned to roles for specific missions.
-- A hat is a focused responsibility that expires when the mission ends
-- or when explicitly removed. Repeatedly useful hats become capabilities.

CREATE TABLE IF NOT EXISTS role_hats (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    role_id         UUID NOT NULL REFERENCES roles(id),
    mission_id      UUID,               -- optional: tied to a mission
    name            VARCHAR(200) NOT NULL,
    description     TEXT NOT NULL,
    capabilities    TEXT[] NOT NULL DEFAULT '{}',
    expires_at      TIMESTAMPTZ,        -- null = until explicitly removed
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_role_hats_role ON role_hats(role_id);
CREATE INDEX IF NOT EXISTS idx_role_hats_mission ON role_hats(mission_id);

-- Outcomes: Captain-declared goals with ratification.

CREATE TABLE IF NOT EXISTS outcomes (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name                VARCHAR(500) NOT NULL,
    description         TEXT,
    measurable_criteria TEXT[] NOT NULL DEFAULT '{}',
    status              VARCHAR(20) NOT NULL DEFAULT 'draft'
                            CHECK (status IN ('draft', 'active', 'achieved', 'abandoned')),
    captain_ratified    BOOLEAN NOT NULL DEFAULT FALSE,
    ratified_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Missions: compiled from outcomes, contain work graph metadata.

CREATE TABLE IF NOT EXISTS missions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    outcome_id      UUID REFERENCES outcomes(id),
    name            VARCHAR(500) NOT NULL,
    description     TEXT,
    status          VARCHAR(20) NOT NULL DEFAULT 'planning'
                        CHECK (status IN ('planning', 'active', 'verifying', 'complete', 'failed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_missions_outcome ON missions(outcome_id);
CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status);

-- Work graph: DAG of tasks within a mission.

CREATE TABLE IF NOT EXISTS work_graph_nodes (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mission_id              UUID NOT NULL REFERENCES missions(id),
    description             TEXT NOT NULL,
    assigned_role           VARCHAR(50),
    status                  VARCHAR(20) NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending', 'ready', 'active', 'done', 'failed', 'skipped')),
    verification_criteria   TEXT,
    evidence                TEXT,           -- what proves this task is done
    completed_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wgn_mission ON work_graph_nodes(mission_id);
CREATE INDEX IF NOT EXISTS idx_wgn_role ON work_graph_nodes(assigned_role);
CREATE INDEX IF NOT EXISTS idx_wgn_status ON work_graph_nodes(status);

CREATE TABLE IF NOT EXISTS work_graph_edges (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mission_id  UUID NOT NULL REFERENCES missions(id),
    from_node   UUID NOT NULL REFERENCES work_graph_nodes(id),
    to_node     UUID NOT NULL REFERENCES work_graph_nodes(id),
    UNIQUE(from_node, to_node)
);

CREATE INDEX IF NOT EXISTS idx_wge_mission ON work_graph_edges(mission_id);

-- OVI snapshots: weekly composite scores.

CREATE TABLE IF NOT EXISTS ovi_snapshots (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    snapshot_date   DATE NOT NULL UNIQUE,
    composite_score NUMERIC(10, 4) NOT NULL,
    trend_direction VARCHAR(10) CHECK (trend_direction IN ('up', 'down', 'flat')),
    components      JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Policy evaluation audit log.

CREATE TABLE IF NOT EXISTS policy_evaluations (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    officer     VARCHAR(50) NOT NULL,
    tool_name   VARCHAR(100) NOT NULL,
    policy_name VARCHAR(200),
    result      VARCHAR(10) NOT NULL CHECK (result IN ('allow', 'block')),
    reason      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pe_officer ON policy_evaluations(officer);
CREATE INDEX IF NOT EXISTS idx_pe_result ON policy_evaluations(result);
CREATE INDEX IF NOT EXISTS idx_pe_created ON policy_evaluations(created_at DESC);
