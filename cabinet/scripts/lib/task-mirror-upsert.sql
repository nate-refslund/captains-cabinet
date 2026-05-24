-- task-mirror-upsert.sql — shared idempotent upsert for the Claude Code → officer_tasks
-- mirror. Used by BOTH cabinet/scripts/hooks/post-task-mirror.sh (live, per task change)
-- and cabinet/scripts/backfill-cc-tasks.sh (one-time). A fix lands once.
--
-- Invoke with psql -v: officer, title, desc, st, proj, due, prio, founder, ttype, extref.
-- Keyed on (external_source='claude-tasks', external_ref='<officer>:<cc-task-id>').
-- Metadata fields are STICKY (COALESCE(NULLIF(new,''), existing)) so a metadata-less
-- update doesn't wipe a prior tag; status/title/desc always overwrite from the source.
--
-- Suspends the two AUTHORING-discipline triggers (their built-in ETL escape hatches):
-- the mirror reflects the officer's REAL working state and must not be rejected by the
-- WIP=3-per-context limit or the founder_action⇒due_date rule (those govern tasks
-- AUTHORED in /tasks, not this read-only reflection). due → both due_date (the founder
-- rule's column) and due_at (Spec 041 reminder trigger).

-- MUST be SET LOCAL inside an explicit transaction: $NEON_CONNECTION_STRING is the
-- PgBouncer -pooler endpoint, where a plain `SET` persists on the server backend and
-- leaks to the next client that checks it out — silently disabling these triggers
-- cabinet-wide for the dashboard / ETL / other officers' authored writes (review caught
-- this: 5/5 fresh connections read the leaked GUCs). SET LOCAL reverts at COMMIT, so the
-- suspend is scoped to THIS mirror write only, regardless of pooler backend reuse.
BEGIN;
SET LOCAL app.etl.suspend_wip_limit = 'true';
SET LOCAL app.etl.suspend_founder_check = 'true';

WITH upd AS (
  UPDATE officer_tasks
     SET title          = :'title',
         description    = :'desc',
         status         = :'st',
         context_slug   = COALESCE(NULLIF(:'proj',''), context_slug),
         due_at         = COALESCE(NULLIF(:'due','')::timestamptz, due_at),
         due_date       = COALESCE(NULLIF(:'due','')::date, due_date),
         priority       = COALESCE(NULLIF(:'prio',''), priority),
         founder_action = COALESCE(NULLIF(:'founder','')::boolean, founder_action),
         type           = COALESCE(NULLIF(:'ttype',''), type),
         started_at     = CASE WHEN :'st' IN ('wip','done') THEN COALESCE(started_at, now()) ELSE started_at END,
         completed_at   = CASE WHEN :'st' = 'done' THEN COALESCE(completed_at, now()) ELSE NULL END,
         cancelled_at   = CASE WHEN :'st' = 'cancelled' THEN COALESCE(cancelled_at, now()) ELSE NULL END,
         updated_at     = now()
   WHERE external_source = 'claude-tasks' AND external_ref = :'extref'
  RETURNING id
)
INSERT INTO officer_tasks
  (officer_slug, title, description, status, context_slug, due_at, due_date, priority,
   founder_action, type, external_source, external_ref, started_at, completed_at, cancelled_at)
SELECT :'officer', :'title', :'desc', :'st', NULLIF(:'proj',''), NULLIF(:'due','')::timestamptz,
       NULLIF(:'due','')::date, NULLIF(:'prio',''), COALESCE(NULLIF(:'founder','')::boolean, false),
       COALESCE(NULLIF(:'ttype',''), 'task'), 'claude-tasks', :'extref',
       CASE WHEN :'st' IN ('wip','done') THEN now() END,
       CASE WHEN :'st' = 'done' THEN now() END,
       CASE WHEN :'st' = 'cancelled' THEN now() END
WHERE NOT EXISTS (SELECT 1 FROM upd);
