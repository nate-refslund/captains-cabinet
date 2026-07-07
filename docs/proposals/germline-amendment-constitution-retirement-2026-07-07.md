# Germline amendment — constitution/ retirement + write-protect entry removal (2026-07-07, egg rows CG-15 / R104)

**Status:** STAGED on branch `feat/germline-window-2` (germline window 2,
worktree-staged — the live checkout's schg boundary was never opened). Reply
**"revert constitution retirement"** to drop the branch commit (one-revert
rollback below).

**Ratification chain (already-ruled — reference only, do NOT re-paste):**

- **Egg plan row R104** — `docs/plans/operative-egg-plan-2026-07-07.md`:
  "Compress constitution/ to the load-preset assembly base
  (framework/constitution-base.md + preset addendum is already the runtime
  source). Retirement TAIL is gated: pre-tool-use.sh:995 write-protect entry
  (germline-locked) → CG-15; re-point create-officer.sh:62,139-140 +
  dashboard governance editor first."
- **Egg plan row CG-15** — "Tail of R104 constitution/ retirement: the :995
  write-protect entry lives in schg-locked pre-tool-use.sh."
- **Germline-window-2 order (2026-07-07)** — executed under the 2026-07-07
  standing full-autonomy grant; germline edits staged in a worktree, never
  live.

**Supersession — VERIFIED before removal (per the row's own demand):**

- `cabinet/scripts/load-preset.sh` (called by `start-officer.sh`) assembles
  the runtime constitution at `/tmp/cabinet-runtime/constitution.md` from
  `framework/constitution-base.md` (v2.0) + the active preset's
  `constitution-addendum.md` — it NEVER reads `constitution/`. Same for
  safety boundaries (`framework/safety-boundaries-base.md` +
  `safety-addendum.md`).
- `constitution/CONSTITUTION.md` was the frozen v1.0 predecessor of the v2.0
  framework base; `constitution/SAFETY_BOUNDARIES.md` likewise (base is a
  superset with the addendum contract).
- `constitution/KILLSWITCH.md` documented the extinct Docker/Hetzner
  deployment (`docker compose -f /opt/founders-cabinet/...`); the live
  mechanism is the `cabinet:killswitch` Redis key enforced by
  `pre-tool-use.sh` + `kill-switch.sh` (eval-001 pins it).
- `constitution/ROLE_REGISTRY.md` was live mutable roster DATA (not
  constitutional text) — relocated, not deleted.

**What (the germline edit set):**

- DELETED: `constitution/CONSTITUTION.md`, `constitution/SAFETY_BOUNDARIES.md`,
  `constitution/KILLSWITCH.md` (dir gone).
- MOVED: `constitution/ROLE_REGISTRY.md` → `instance/config/role-registry.md`
  (deployment data lives in instance/; content byte-preserved).
- `cabinet/scripts/hooks/pre-tool-use.sh` (germline): the §5
  `*"constitution/"*` write-protect case arm REMOVED (the paths it guarded no
  longer exist); section header comment records the retirement. Every other
  §5/§5b germline entry untouched.
- `framework/policies/base-safety.yml` (germline dir-cover): the
  `constitution-readonly` typed policy REMOVED (hook↔typed-engine parity
  preserved — both sides drop the rule in the same commit).
- `cabinet/scripts/policy-shadow.py` (germline): the `constitution_read_only`
  reason branch REMOVED (shadow parity with the hook);
  `test-policy-shadow.sh` drops its constitution parity case.
- `memory/golden-evals/eval-002-constitution-readonly.md` (germline dir)
  DELETED + `run-golden-evals.sh` EVAL-002 section removed (the eval's
  target no longer exists; eval numbering is never reused).
- Hook-regression: `germline-readonly.sh` G19 constitution pin + comment
  references removed (suite renumbering avoided; 15/15 harnesses green).
- Re-pointed consumers (the row's "first" clause): `create-officer.sh`
  REGISTRY_FILE + boot-doc reads → the assembled runtime files + the new
  registry path; dashboard governance editor
  (`governance-editor.tsx` / `governance.ts`) → `framework/constitution-base.md`,
  `framework/safety-boundaries-base.md`, `instance/config/role-registry.md`;
  `framework/constitution-base.md` registry pointer; preset agent docs +
  `_template`, `cabinet-intro` skill, `shared/backlog.md`, `CLAUDE.md`,
  `framework/safety-boundaries-base.md` §read-only line; memory plumbing
  (`backfill-memory.sh`, `memory-reconcile.sh`,
  `post-file-write-memory.sh` watched-path case → the two framework base
  files; `post-tool-use.sh` staged-warn regex drops the dead token).

**Class change (deliberate, documented):** the role registry moves from the
hook-protected `constitution/` dir to officer-editable instance data. It is
DESCRIPTIVE roster metadata — authority is minted only by the authority
matrix / capabilities / mcp-scope plane (all still germline). The Captain
dashboard editor keeps working (it runs outside officer hooks either way).
`framework/constitution-base.md` remains, as before, protected by review
discipline rather than the germline lock — this amendment does not change
its class.

**Non-entries (promises pinned):**

- The generic `*/constitution/*` PATTERN support in
  `framework/authority/policy_engine.py:_path_matches_pattern` (and its
  fixture-based tests) is KEPT — it is matcher capability, not a live rule.
- No other §5 case-arm, §5b regex atom, lockstep list, or immutable-core
  entry changes in this commit (constitution/ was never an immutable-core
  entry — the lockstep suite is unaffected by design).

**Gates (run in the staging worktree, 2026-07-07):**

- `bash cabinet/scripts/run-hook-regression.sh` → 15/15 harnesses, ALL GREEN
  (germline-readonly 59 probes after G19 removal; bash-write 89).
- `python3.12 -m pytest framework/authority framework/tests -q` → 1267
  passed (lockstep + amendment lint included).
- `bash cabinet/scripts/check-layer-separation.sh` → no new violations.
- Shell syntax: `bash -n` clean on every edited script.

**One-revert rollback:** `git revert` of the CG-15/R104 commit on
`feat/germline-window-2` restores the `constitution/` directory (all four
files incl. the registry at its old path), the `pre-tool-use.sh` §5
constitution arm, the `base-safety.yml` constitution-readonly policy, the
`policy-shadow.py` reason + `test-policy-shadow.sh` case, eval-002 +
its `run-golden-evals.sh` section, the G19 probe, and every re-pointed
consumer (create-officer.sh, governance editor, docs, memory plumbing);
then `sudo bash cabinet/scripts/germline-lock.sh lock` on the live checkout.
