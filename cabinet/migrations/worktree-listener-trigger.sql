-- worktree-listener-trigger.sql — Postgres trigger fires NOTIFY when officer_tasks
-- transitions to a terminal state (done | cancelled). Consumed by worktree-listener.sh
-- which invokes cabinet/scripts/worktree-remove.sh for the task-id.
--
-- Per Spec 063 v1.1 Checkpoint 6.3 (Postgres NOTIFY surface choice).
--
-- Apply on Mac side after Phase 0 Neon round-trip restore + Phase 6.3 execution:
--   psql "$NEON_CONNECTION_STRING" -f cabinet/migrations/worktree-listener-trigger.sql

CREATE OR REPLACE FUNCTION notify_task_terminal() RETURNS TRIGGER AS $$
BEGIN
  -- Only fire on transition TO a terminal state (done | cancelled), not other status changes
  IF (TG_OP = 'UPDATE' AND OLD.status IS DISTINCT FROM NEW.status
      AND NEW.status IN ('done', 'cancelled')) THEN
    -- Payload = task ID (no PII; worktree-listener.sh looks up the rest)
    PERFORM pg_notify('cabinet_task_terminal', NEW.id::text);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS officer_tasks_terminal_notify ON officer_tasks;
CREATE TRIGGER officer_tasks_terminal_notify
  AFTER UPDATE ON officer_tasks
  FOR EACH ROW
  EXECUTE FUNCTION notify_task_terminal();

-- Sanity verification (idempotent):
-- SELECT 1 FROM pg_trigger WHERE tgname = 'officer_tasks_terminal_notify';
