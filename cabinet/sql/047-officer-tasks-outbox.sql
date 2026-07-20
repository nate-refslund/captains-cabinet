-- cabinet/sql/047-officer-tasks-outbox.sql
-- COG-1 (Cognitive Core Phase 1) — officer_tasks transactional outbox.
-- Plan: docs/plans/cognitive-core-phase-1-contract-2026-07-20.md §5 (design),
-- §9 (crash/concurrency matrix), §12.2 item 3 (tests-first battery:
-- cabinet/scripts/tests/test_cog1_outbox_capture.py).
--
-- Spec-038 ADDENDUM NOTE: additive only. officer_tasks columns are UNTOUCHED
-- (gate-3 _HASH_COLS unaffected — no Spec-038/039 amendment ceremony,
-- gate-3-idempotency.py:37-45). This file adds two NEW tables and one NEW
-- AFTER trigger on officer_tasks that clones the proven Spec-038 v1.2
-- history-trigger mechanics (038-officer-tasks.sql:243-269).
--
-- HONEST CAPTURE POSTURE (§5.1): the trigger is LIVE inside every
-- officer_tasks transaction from the moment this file applies — an outbox
-- INSERT failure fails the business transaction BY DESIGN (atomicity:
-- mutation + outbox row commit together or neither). The production apply is
-- gated on the §9 sims + verb suites + the §11.2 p95 bound in the ephemeral
-- harness; the rehearsed one-command emergency inverse is
--   cog1-authority-flip.sh disarm
--     -> ALTER TABLE officer_tasks DISABLE TRIGGER trg_officer_tasks_outbox_capture
-- (reversible via `enable`; no data surgery).
--
-- IDENTITY (§5.2): cabinet_id is sourced DB-side from the database-level GUC
--   ALTER DATABASE <db> SET app.cabinet_id = '<identity>'
-- issued by the load-preset.sh identity step (ordered BEFORE this file in the
-- DDL chain — value read at run time from the CABINET_ID environment,
-- default 'main'; NEVER a tracked literal, so this file and the egg stay
-- identity-clean). DB-level settings apply at backend session start and
-- survive connection pooling. A database that reaches 047 without identity
-- fails its first task write LOUDLY (fail-closed RAISE) rather than minting
-- unattributable rows; a session-level override that diverges from the
-- database-provisioned value RAISEs (anti-spoof, sim 10a).
--
-- Postgres pin: production work store is PostgreSQL 17.10 (S0 ground finding
-- 2026-07-20 — supersedes the plan text's "16" mentions); harness/CI pins are
-- MAJOR 17. pgcrypto 1.3 is already present in production, so the extension
-- line is a no-op there (045-org-runtime-slice.sql:8 precedent — local/CI/
-- Neon identical).
--
-- Trigger firing order note: AFTER triggers on the same event fire
-- alphabetically — trg_log_officer_task_transition (history) fires before
-- trg_officer_tasks_outbox_capture; both run pre-commit inside the same
-- transaction, so the order carries no semantics.
--
-- Idempotent — safe to re-run. Registered in cabinet/scripts/load-preset.sh's
-- work-store chain AFTER the identity-GUC step (fresh hatches must never hit
-- the fail-closed RAISE).
--
-- Provenance: authored per the 2026-07-07 full-autonomy grant (COG-1 plan
-- self-ratification record).

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid(); no-op in prod

-- =============================================================
-- officer_tasks_outbox — the co-committed durable event record
-- =============================================================
-- Immutable-content columns (§9.3 replay-hash projection) come first;
-- dispatch bookkeeping (claimed_at .. last_error) is relay-owned and
-- excluded from the replay hash. event_id stays NULL at capture — the relay
-- backfills a ULID in its own COMMITTED update strictly BEFORE any adapter
-- effect (§6.1), making the id stable across redelivery.
CREATE TABLE IF NOT EXISTS officer_tasks_outbox (
  id               BIGSERIAL PRIMARY KEY,
  idempotency_key  TEXT NOT NULL UNIQUE,      -- the SQL-unique race fix (§6.2)
  event_id         TEXT UNIQUE,               -- ULID; relay-backfilled (§6.1)
  task_id          BIGINT NOT NULL,
  old_status       TEXT,
  new_status       TEXT NOT NULL,
  old_blocked      BOOLEAN,
  new_blocked      BOOLEAN,
  blocked_reason   TEXT,
  actor            TEXT NOT NULL,
  context_slug     TEXT,
  cabinet_id       TEXT NOT NULL,
  correlation_id   TEXT NOT NULL,             -- uuid4-hex via gen_random_uuid() (B2.1)
  causation_id     TEXT,                      -- ULID of the causing event; pilot rows are roots
  occurred_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  payload          JSONB NOT NULL,
  destination      TEXT NOT NULL DEFAULT 'stream',
  claimed_at       TIMESTAMPTZ,
  attempts         INT NOT NULL DEFAULT 0,
  dispatched_at    TIMESTAMPTZ,
  failed_terminal_at TIMESTAMPTZ,
  last_error       TEXT
);

CREATE INDEX IF NOT EXISTS idx_officer_tasks_outbox_pending
  ON officer_tasks_outbox (id) WHERE dispatched_at IS NULL AND failed_terminal_at IS NULL;

-- =============================================================
-- task_sync — canonical-id -> external-id mapping
-- =============================================================
-- Closes base.py:183-184's promised-but-absent mapping table ("Cabinet
-- stores the inverse mapping in the `task_sync` table"). CONSUMED-BY-
-- REHEARSAL-ONLY this phase (§5.3): the dark external-push path and the §9
-- idempotency rehearsal are its only consumers — no live external push
-- (NoOpTaskAdapter stays; services.yml unedited).
CREATE TABLE IF NOT EXISTS task_sync (
  canonical_id  TEXT NOT NULL,
  destination   TEXT NOT NULL,
  external_id   TEXT NOT NULL,
  linked_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (canonical_id, destination)
);

-- =============================================================
-- Capture trigger — clones 038's history-trigger mechanics (038:243-269)
-- =============================================================
-- Both load-bearing guards are FAITHFUL clones (§5.1):
--   (a) the UPDATE arm fires only when status/blocked actually change
--       (IS DISTINCT FROM, 038:252-254) — idempotent no-op writes (the
--       deliberately idempotent unblock-on-unblocked, Spec §3.3 AC#7;
--       re-block reason refreshes) mint NO outbox row, exactly as they mint
--       no history row and no legacy event;
--   (b) actor = COALESCE(current_setting('app.cabinet_officer', TRUE),
--       'unknown') (038:250,:258) — an unset officer GUC degrades to
--       'unknown', never bricks a verb against actor NOT NULL.
-- Suppression (§5.1): SET LOCAL app.cabinet_outbox_suppress = 'true' (the
-- ETL's app.etl.* bypass value convention, etl-common.py:112-116) is honored
-- ONLY when the actor GUC equals the ETL's recognized actor-role literal
-- 'cpo-etl' (etl-common.py:64,:116 — a role literal already hardcoded in
-- repo scripts, not an instance identity); ANY other actor setting it
-- RAISES. Suppressed ETL runs write history rows with no outbox rows; the
-- §8.3 parity predicate excludes actor-'cpo-etl' transitions.
CREATE OR REPLACE FUNCTION capture_officer_task_outbox() RETURNS TRIGGER AS $$
DECLARE
  v_actor       TEXT;
  v_suppress    TEXT;
  v_db_identity TEXT;
  v_effective   TEXT;
  v_old_status  TEXT;
  v_old_blocked BOOLEAN;
BEGIN
  -- Arm dispatch + 038-exact IS DISTINCT FROM guard.
  IF TG_OP = 'INSERT' THEN
    v_old_status  := NULL;
    v_old_blocked := NULL;
  ELSIF TG_OP = 'UPDATE' THEN
    IF NOT (NEW.status IS DISTINCT FROM OLD.status
            OR NEW.blocked IS DISTINCT FROM OLD.blocked) THEN
      RETURN NULL;  -- idempotent no-op: mint nothing (mirrors 038:252-254)
    END IF;
    v_old_status  := OLD.status;
    v_old_blocked := OLD.blocked;
  ELSE
    RETURN NULL;
  END IF;

  -- 038-exact actor fallback.
  v_actor := COALESCE(current_setting('app.cabinet_officer', TRUE), 'unknown');

  -- ETL suppression: recognized actor only; misuse RAISES (enforceable rule).
  v_suppress := COALESCE(current_setting('app.cabinet_outbox_suppress', TRUE), '');
  IF v_suppress NOT IN ('', 'false') THEN
    IF v_actor = 'cpo-etl' THEN
      RETURN NULL;  -- bulk-migration bypass: history still logs, no outbox row
    END IF;
    RAISE EXCEPTION 'COG-1 outbox capture: app.cabinet_outbox_suppress set by actor "%" — only the recognized ETL actor cpo-etl may suppress capture', v_actor;
  END IF;

  -- §5.2 identity: PRIMARY enforcement layer (the relay dispatch check is
  -- the backstop). The database-provisioned value is read from the catalog
  -- (pg_db_role_setting, database-wide entry setrole=0) so a session-level
  -- override can never masquerade as provisioning.
  SELECT substr(cfg, length('app.cabinet_id=') + 1)
    INTO v_db_identity
    FROM pg_db_role_setting s, unnest(s.setconfig) AS cfg
   WHERE s.setdatabase = (SELECT oid FROM pg_database
                           WHERE datname = current_database())
     AND s.setrole = 0
     AND cfg LIKE 'app.cabinet_id=%'
   LIMIT 1;
  IF v_db_identity IS NULL OR v_db_identity = '' THEN
    RAISE EXCEPTION 'COG-1 outbox capture: app.cabinet_id is not provisioned on this database (run the load-preset identity step: ALTER DATABASE ... SET app.cabinet_id) — refusing to mint unattributable outbox rows';
  END IF;
  v_effective := current_setting('app.cabinet_id', TRUE);
  IF v_effective IS NULL OR v_effective = '' THEN
    -- Session predates provisioning (DB-level GUCs bind at backend start).
    RAISE EXCEPTION 'COG-1 outbox capture: app.cabinet_id resolves empty in this session (database is provisioned as "%") — reconnect so the database-level setting binds', v_db_identity;
  END IF;
  IF v_effective <> v_db_identity THEN
    RAISE EXCEPTION 'COG-1 outbox capture: session app.cabinet_id "%" diverges from the database-provisioned identity "%" — refusing (possible spoof)', v_effective, v_db_identity;
  END IF;

  -- Mint. Key = task:<task_id>:<txid_current()>:<to_status>:<to_blocked> —
  -- unique per mutation, deterministic within a transaction; ON CONFLICT
  -- tolerates a same-transaction exact-duplicate transition (a genuine
  -- no-op, §5.2). Explicit ::text casts keep boolean rendering 'true/false'.
  INSERT INTO officer_tasks_outbox
    (idempotency_key, task_id, old_status, new_status, old_blocked,
     new_blocked, blocked_reason, actor, context_slug, cabinet_id,
     correlation_id, occurred_at, payload)
  VALUES
    ('task:' || NEW.id::text || ':' || txid_current()::text || ':'
             || NEW.status || ':' || NEW.blocked::text,
     NEW.id, v_old_status, NEW.status, v_old_blocked,
     NEW.blocked, NEW.blocked_reason, v_actor, NEW.context_slug, v_db_identity,
     replace(gen_random_uuid()::text, '-', ''),  -- uuid4-hex, B2.1 standard
     NOW(),
     jsonb_build_object(
       'task_id',        NEW.id,
       'old_status',     v_old_status,
       'new_status',     NEW.status,
       'old_blocked',    v_old_blocked,
       'new_blocked',    NEW.blocked,
       'blocked_reason', NEW.blocked_reason,
       'actor',          v_actor,
       'context_slug',   NEW.context_slug))
  ON CONFLICT (idempotency_key) DO NOTHING;

  RETURN NULL;  -- AFTER trigger, return value ignored (038:261)
END;
$$ LANGUAGE plpgsql;

-- Name is load-bearing: target of the `disarm` emergency inverse (§12.4) and
-- of the rung-2 trigger-exists probe (§8.2).
DROP TRIGGER IF EXISTS trg_officer_tasks_outbox_capture ON officer_tasks;
CREATE TRIGGER trg_officer_tasks_outbox_capture
  AFTER INSERT OR UPDATE OF status, blocked ON officer_tasks
  FOR EACH ROW EXECUTE FUNCTION capture_officer_task_outbox();
