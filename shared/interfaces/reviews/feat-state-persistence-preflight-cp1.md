# Checkpoint review — feat/state-persistence-preflight (cp1)

**Unit:** a state-persistence preflight that blocks a deploy which would
discard the cabinet's learned state, plus the live list fixes it exposed, plus
a non-vacuity fix to the restore drill's Postgres arm.

## The defect, reproduced before fixing

`cabinet-deploy.sh` provisions each release as a fresh `git worktree`, so a
release contains tracked files and nothing else. Gitignored runtime state
survives only if `runtime-provision.sh`'s three hand-maintained lists symlink it
into `<runtime_root>/shared/`. Those lists had drifted from `.gitignore`.

Reproduced end-to-end with the repo's own scripts (two real releases, real
`git worktree`, `provision` between them). Written into release A, then
release B provisioned:

| path | result in the new release |
|---|---|
| `memory/skills/evolved/RULE-042.md` | **LOST** |
| `memory/tier3/decision-log.jsonl` | **LOST** |
| `memory/logs/tools.jsonl` | **LOST** |
| `shared/interfaces/foundry/trajectory-0001.jsonl` | **LOST** |
| `instance/config/trusted-mcps.json` | **LOST** |
| `instance/config/war-room-seed.yml` | **LOST** |
| `instance/config/posture.yml` (control, on a list) | CARRIED, updated value |

No error was emitted and the health gate was unaffected. The state was stranded
in the old release directory, which `prune --keep 5` later `rm -rf`s — so the
loss is permanent, not recoverable.

## What was built

`cabinet/scripts/state-persistence-preflight.py` **derives** the durable set
from `.gitignore` rather than adding a fourth hand-maintained list, then asserts
every derived path is carried, wildcard-linked, or explicitly exempted with a
written reason. Two modes: static (CI, catches drift at review time) and
`--slot` (deploy time, asserts against the real provisioned release rather than
trusting the lists to describe what happened).

Wired into `do_deploy` **after provision, before the health gate and promote**,
so a release that would discard state never becomes `current`.

### Fail-closed decisions (each one deliberate)

- A derived path on no list and no policy entry → fail.
- A policy entry without a non-empty `reason` → fail.
- A persistence list that cannot be parsed out of `runtime-provision.sh` → exit
  2. An unparseable list must never read as an empty list.
- A `wildcard_covered` claim whose linking block no longer exists → exit 2.
- The checker missing from the release → deploy aborts. The gate must not be
  disableable by deleting it.
- `known_gap` requires an `expires:` date and fails once it passes, so a
  deferral cannot rot into a permanent hole.

## Live gaps fixed

Beyond the six above, the preflight surfaced seven more genuinely durable paths
on its first run. Homes were confirmed against tracked content before carrying
(a whole-dir symlink over tracked content would shadow it):

- `SEEDED_DIRS` (ship a tracked `.gitkeep` skeleton): `memory/skills/evolved`,
  `memory/tier3`, `memory/logs`, `cabinet/cache`, `cabinet/logs`.
  `cabinet/cache` is the most severe — it holds `org-runtime.sqlite3` (with an
  append-only DB trigger), the chained-hash predictions store, COG-2 beliefs and
  the purge undo archive, seeded once at setup and never re-seeded.
  `cabinet/logs` holds the append-only verdict series `cabinet-doctor` reads
  *across* runs, so losing it made the rolling-window health checks
  unmeasurable.
- `DIRS` (zero tracked content): `shared/interfaces/foundry`,
  `shared/interfaces/world`, and `world-aesthetic/corpus/{positive,negative}` —
  linked at subdir level because the corpus root holds a tracked
  `manifest.json`.
- `FILES`: `instance/config/trusted-mcps.json`, `instance/config/war-room-seed.yml`,
  `.claude/project-config.json` (every sibling local-config file was already
  listed; these were the lone omissions), and `bin/cabinet-calread` — carried
  because the macOS Calendar TCC grant is keyed to the binary's CDHASH, so a
  rebuild costs a Captain re-grant.

Two durable paths are recorded as time-boxed `known_gap`s rather than guessed
at: `world-aesthetic/goldens` (PNGs sit beside a tracked manifest, no subdir to
carry) and `bin/Cabinet Companion.app` (absolute-path login item plus
two-dirs-up self-location).

## Restore-drill vacuity

`restore-drill.sh`'s Postgres arm was a `SELECT count(*)` with no floor: `0` is
numeric, so it hit the catch-all `*)` arm and reported success. A backup that
restored to an **empty database** — exactly what a disaster-recovery drill
exists to catch — passed. Proven against a real empty Postgres 17.10 cluster:

- before: `✓ postgres.dump restores into disposable PostgreSQL (0 user relations…)`
- after: `✗ FAIL: the restored database contains ZERO user relations`

Fixed with a floor plus a **shape** comparison against the dump's own table of
contents — self-calibrating per snapshot, so no magic expected-count, and it
catches a partial restore a count alone would wave through. A populated dump
still passes (`all 2 declared tables present`), so the fix is not always-fail.

## Reviewer notes / residual risk

- The `known_gap` expiry is a deliberate calendar trigger. It will go red on
  2026-10-31 if untouched; that is the intent, not a time-bomb.
- The missing-checker branch blocks `deploy --ref <old-sha>` to a pre-checker
  commit. `rollback` is untouched and remains the emergency path.
- Reported, not fixed here: nothing seeds `<runtime_root>/shared/shared/interfaces/`,
  so the `*.md` wildcard block and ~20 `shared/interfaces/*` file rows may link
  nothing on a runtime root built by the documented flow; no script
  re-materializes `cabinet/loop-prompts/<role>.txt` or
  `cabinet/officer-skills/<officer>.txt` after a deploy; `vault/` has no
  persistence entry at all; and `runtime-provision.sh`'s prune orders candidates
  with BSD-first `stat -f`, which on a GNU box silently sorts on garbage and can
  delete the wrong release slots.
