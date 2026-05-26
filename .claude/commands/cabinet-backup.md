---
description: Run the daily Cabinet state backup on demand. Snapshots filesystem (cabinet runtime artifacts) + Redis BGSAVE + optional Postgres pg_dump.
argument-hint: "[--dest <path>|--pg|--retention-days N]"
allowed-tools: Bash
---

Trigger the Cabinet state backup. Normally runs daily via LaunchAgent.

```bash
bash cabinet/scripts/backup.sh $ARGUMENTS
```

What's snapshotted:

1. **Filesystem** — `shared/interfaces/`, `instance/`, `memory/` (rsync; excludes pyc/pycache/session-state).
2. **Redis** — `BGSAVE` then copy `dump.rdb` from the Homebrew or Linux default path.
3. **Postgres** — only if `--pg` AND `DATABASE_URL` is set. `pg_dump | gzip → postgres.sql.gz`.

Daily destination: `$BACKUP_DEST/<YYYY-MM-DD>/` (default `~/Cabinet-Backups`).
Pruning: deletes daily snapshots older than `--retention-days` (default 14).

Use this command before a risky cutover, after a Captain decision that
touches many roles/missions, or anytime you want a fresh restore point.
