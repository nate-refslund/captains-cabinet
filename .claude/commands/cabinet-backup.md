---
description: Run the daily Cabinet state backup on demand. Snapshots filesystem artifacts, verified Redis recovery state, and configured Postgres.
argument-hint: "[--dest <path>|--pg|--no-pg|--retention-days N]"
allowed-tools: Bash
# Act-on-invoke runbook (filesystem/Redis/Postgres snapshots) — explicit
# /cabinet-backup only, never model-autonomous inside
# --dangerously-skip-permissions sessions (audit #22).
disable-model-invocation: true
---

Trigger the Cabinet state backup. Normally runs daily via LaunchAgent.

```bash
bash cabinet/scripts/backup.sh $ARGUMENTS
```

What's snapshotted:

1. **Filesystem** — `shared/interfaces/`, `instance/`, `memory/` (rsync; excludes pyc/pycache/session-state).
2. **Redis** — bounded fresh `redis-cli --rdb`; if that cannot complete but
   AOF is healthy, briefly pause writes and wait for a bounded global AOF drain
   (`aof_buffer_length=0`, `aof_pending_bio_fsync=0`, last write OK, no rewrite)
   before copying the complete multipart set. The fallback is replayed in a
   disposable Redis, known Streams operational omissions are repaired from an
   identifier-only manifest, and exact v3 logical state is re-proved. It is
   then converted to RDB, re-proved in a second disposable Redis, and published
   as an RDB with `aof-converted` provenance. The v3 proof hashes canonical
   logical values and absolute expiry deadlines; unsupported Redis value types
   fail closed. That exact v3 logical-state proof—not the drain—is the
   authoritative completeness gate. The blocking source fingerprint aborts at an internal
   55-second deadline within the 60-second write pause.
3. **Postgres** — automatic when `DATABASE_URL` or `NEON_CONNECTION_STRING`
   is configured (or required explicitly with `--pg`; disable only with
   `--no-pg`). Writes a custom-format `postgres.dump` and validates it with
   `pg_restore --list`.

Daily destination: `$BACKUP_DEST/<YYYY-MM-DD>/` (default `~/Cabinet-Backups`).
Pruning: deletes daily snapshots older than `--retention-days` (default 14).

Use this command before a risky cutover, after a Captain decision that
touches many roles/missions, or anytime you want a fresh restore point.
