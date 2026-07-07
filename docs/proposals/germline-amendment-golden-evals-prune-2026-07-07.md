# Germline amendment — golden-evals prune: phase-0/1/2 + library harnesses (2026-07-07, egg row R137)

**Status:** APPLIED at commit `0557344e` (2026-07-07) under the Captain's
temporary germline unlock for the 2026-07-07 compression wave, executed as
operative egg plan row R137. This document is the RETROACTIVE companion
record for that germline deletion: R137 landed plan-ratified but without
the mandatory amendment record, and authoring this record is the fix for
that discipline gap — the deletion itself needs no re-ratification. No
further apply token is needed. Reply **"revert golden-evals prune"** to
have a session restore all four harnesses via the one-revert rollback
below.

**Ratification chain (already-ruled — reference only, do NOT re-paste):**

- **Egg plan row R137** — `docs/plans/operative-egg-plan-2026-07-07.md`
  (beta-compression lane, wave B1, class remove): "Delete phase-0/1/2 +
  library eval scripts (all cd /opt/founders-cabinet — container-dead,
  zero callers verified)." The execution ledger
  (`docs/plans/operative-egg-ledger-2026-07-07.yml`, row R137) records
  `status: done` @ `0557344e` with the row gate green.
- **CG-12 — operative plan RATIFIED, beta-compression lane OPEN** —
  `shared/interfaces/captain-decisions.md`, 2026-07-07 RULINGS BATCH: the
  Captain ratified the operative egg plan in-session, unblocking the
  beta-compression lane (B1..B5) that R137 executes under.
- **2026-07-07 full-autonomy grant** — the standing grant the RULINGS
  BATCH is recorded under (build/change anything cabinet-improving in this
  window); the wave ran under it and this retroactive record is authored
  under it.

**Why:** the four scripts were pre-Captain gate harnesses for the extinct
Docker/Hetzner `/opt/founders-cabinet` deployment (declared extinct —
CLAUDE.md, re-grounded 2026-07-04). Every one of them hardcodes that path,
so none could run on the live native-Mac deployment; their Mac-native
successors live on in `memory/golden-evals/framework/` (`fw-*.sh`). Dead
weight inside a germline-locked directory is worse than ordinary dead code
— it inflates the locked surface the Captain must reason about at every
unlock window.

**Verified facts (2026-07-07, `git show 0557344e^:<file>` + live
checkout):**

- `memory/golden-evals/phase-0/pre-captain-test.sh` hardcodes
  `cd /opt/founders-cabinet` (line 5).
- `memory/golden-evals/phase-1/pre-captain-test.sh` hardcodes
  `cd /opt/founders-cabinet` (line 9) and
  `HOOK="/opt/founders-cabinet/cabinet/scripts/hooks/pre-tool-use.sh"`
  (line 141).
- `memory/golden-evals/phase-2/pre-captain-test.sh` hardcodes
  `cd /opt/founders-cabinet` (line 9) and
  `MCP="/opt/founders-cabinet/cabinet/mcp-server/server.py"` (line 66).
- `memory/golden-evals/library/sprint-a.sh` sources
  `/opt/founders-cabinet/cabinet/.env` (line 8) and
  `/opt/founders-cabinet/cabinet/scripts/lib/library.sh` (line 10).
- Zero callers: swept across `cabinet/services.yml`, the
  `com.cabinet.*.plist` LaunchAgents, `.claude` hooks,
  `cabinet/scripts/run-golden-evals.sh`, and a repo-wide code grep before
  deletion (sweep recorded in the 0557344e commit message).
- Row gate re-verified while authoring this record:
  `ls memory/golden-evals/phase-* memory/golden-evals/library 2>/dev/null
  | wc -l` → `0`.

## Deleted set (`git show --stat 0557344e`)

All four files are germline: `memory/golden-evals` is schg-listed in
`cabinet/scripts/germline-lock.sh` ("the behavioral judges") and
dir-covered by `framework/policies/immutable-core.yml`.

| File | Lines removed |
|---|---|
| `memory/golden-evals/library/sprint-a.sh` | 188 |
| `memory/golden-evals/phase-0/pre-captain-test.sh` | 99 |
| `memory/golden-evals/phase-1/pre-captain-test.sh` | 216 |
| `memory/golden-evals/phase-2/pre-captain-test.sh` | 189 |

4 files changed, 692 deletions(-). Each of the four directories
(`phase-0/`, `phase-1/`, `phase-2/`, `library/`) held exactly its one
script, so the prune removes those directories entirely.

## What it does NOT do

- Does not touch the behavioral judge docs
  (`memory/golden-evals/eval-0NN-*.md`, `README.md`) or the live
  Mac-native golden shells (`memory/golden-evals/framework/fw-*.sh`) — the
  evals that gate promoted changes remain intact.
- Does not change `cabinet/scripts/run-golden-evals.sh` — it never invoked
  the four harnesses (part of the zero-caller sweep above).
- Does not narrow the germline boundary: `memory/golden-evals` stays
  schg-listed in `germline-lock.sh` and dir-covered in
  `immutable-core.yml`; the lock protects the surviving judges exactly as
  before.
- Does not alter any verdict table, authority path, hook, eval id, or
  test.

**One-revert rollback:** `git revert 0557344e` restores all four harness
scripts (and thereby the `phase-0/`, `phase-1/`, `phase-2/`, and
`library/` directories) byte-for-byte; no other file participates in that
commit.
