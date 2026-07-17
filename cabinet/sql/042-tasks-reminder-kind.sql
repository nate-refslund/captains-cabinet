-- cabinet/sql/042-tasks-reminder-kind.sql
-- Captain-arm — widen officer_tasks.type to admit the 'reminder' kind.
--
-- Spec 041 gave officer_tasks a due_at + a cron worker
-- (cabinet/scripts/due-at-reminder-tick.sh) that fires a task_reminder to the
-- OWNING OFFICER's Redis stream. A Captain reminder has no officer stream, so
-- the arm routes it to the needs-ledger one-tap card surface instead. The two
-- signals that mark a due row as a Captain reminder are:
--   * officer_slug = the Captain owner slug (framework.env.captain_slug(),
--     default 'captain' — the SAME slug the /tasks ETL stamps on founder rows),
--   * type = 'reminder'  ← THIS migration makes that value insertable.
--
-- 039 introduced `type TEXT NOT NULL DEFAULT 'task'` with
-- CHECK (type IN ('task','epic')). This migration is a PURE enum widening:
-- ('task','epic') → ('task','epic','reminder'). No column rename, no type
-- narrowing, no destructive DDL. The epic-hierarchy CHECKs are unaffected
-- (a reminder is never an epic). Reversible: no row is created by this file;
-- to revert, DROP the constraint and re-ADD the two-value form after
-- reclassifying any 'reminder' rows.
--
-- Idempotent — safe to re-run. Registered in cabinet/scripts/load-preset.sh's
-- Neon migration loop AFTER 039 (this depends on 039's type column + CHECK).
--
-- Target: Cabinet Postgres (same DB as officer_tasks). Apply to BOTH Work +
-- Personal cabinet postgres (per Personal-Work parity, like 041).

-- Replace officer_tasks_type_check ONLY when it does not already admit
-- 'reminder'. Guarding on the constraint definition keeps a re-run a no-op and
-- avoids a needless DROP/ADD churn on an already-widened DB.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conrelid = 'officer_tasks'::regclass
       AND conname = 'officer_tasks_type_check'
       AND pg_get_constraintdef(oid) NOT LIKE '%reminder%'
  ) THEN
    ALTER TABLE officer_tasks DROP CONSTRAINT officer_tasks_type_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conrelid = 'officer_tasks'::regclass
       AND conname = 'officer_tasks_type_check'
  ) THEN
    ALTER TABLE officer_tasks
      ADD CONSTRAINT officer_tasks_type_check
      CHECK (type IN ('task','epic','reminder'));
  END IF;
END $$;
