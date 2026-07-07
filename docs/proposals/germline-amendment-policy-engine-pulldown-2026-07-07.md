# Germline amendment — policy_engine.py pull-down into framework/authority/ (2026-07-07, egg row CG-14)

**Status:** STAGED on branch `feat/germline-window-2` (germline window 2,
worktree-staged — the live checkout's schg boundary was never opened).
Applies on merge + relock: `sudo bash cabinet/scripts/germline-lock.sh lock`
re-arms the boundary at the NEW path (the FILES array in this same change
already names it). Reply **"revert policy-engine pulldown"** to drop the
branch commit (one-revert rollback below).

**Ratification chain (already-ruled — reference only, do NOT re-paste):**

- **Egg plan row CG-14** — `docs/plans/operative-egg-plan-2026-07-07.md`
  (captain-gated lane): "pull cabinet/scripts/lib/policy_engine.py
  (schg-locked, 1,930 LOC, 250-test corpus) down into framework/ so the
  germ layer is import-closed (gate.py:282 imports upward today). Move
  preserves bytes; hook path references update; relock at new path."
- **Germline-window-2 order (2026-07-07)** — the Captain-side orchestrator
  ordered CG-14 executed as part of this window, on this branch, under the
  2026-07-07 standing full-autonomy grant (build/change anything
  cabinet-improving; germline edits staged in a worktree, never live).

**What (the germline edit set):**

- `git mv cabinet/scripts/lib/policy_engine.py
  framework/authority/policy_engine.py` — bytes preserved except two
  minimal edits: the repo-root walk in `_authority_root()` drops one
  `.parent` (authority → framework → root), and the bootstrap comment
  records the move. No logic, table, or verdict change.
- `git mv cabinet/scripts/lib/tests/test_policy_engine.py
  framework/authority/tests/test_policy_engine.py` — the 250-test corpus
  moves beside the engine; import lines flip from the lib path-insert to
  `from framework.authority.policy_engine import …`; two `_REPO_ROOT`
  parents-depth constants adjust to the new location. 250/250 green.
- **Import direction closed:** `framework/learning/gate.py` now imports
  `framework.authority.policy_engine` (was the upward
  `cabinet.scripts.lib.policy_engine`); `framework/authority/matrix.py`,
  `framework/acting/run_action_lane.py`, and every framework test drop the
  `cabinet/scripts/lib` sys.path-insert for the package import — ONE module
  object, no dual-identity import seam. `cabinet/scripts/policy-shadow.py`
  and `setup-mac.sh` (cabinet layer) import downward into framework —
  that direction is allowed.
- **Lockstep set (all four lists + the single source, same commit):**
  - `framework/policies/immutable-core.yml` — files entry
    `cabinet/scripts/lib/policy_engine.py` → `framework/authority/policy_engine.py`.
  - `cabinet/scripts/germline-lock.sh` — FILES array entry swapped to the
    new path (relock covers it at the new location).
  - `cabinet/scripts/hooks/pre-tool-use.sh` — §5 germline case arm entry
    swapped; §5b `GERM_PATH_RE` folds `policy_engine` into the
    `framework/authority/(…)\.py` group.
  - `framework/policies/base-safety.yml` — germline-readonly
    `path_patterns` entry `*cabinet/scripts/lib/policy_engine.py` →
    `*framework/authority/policy_engine.py`.
  - `framework/policies/axes-allowlist.yml` — same path swap.
  - Hook-regression probes (`cabinet/tests/hook-regression/
    germline-readonly.sh` G3/G14, `germline-bash-write.sh` W6) probe the
    NEW path; `memory/golden-evals/eval-019-immutable-core-gate-refusal.md`
    names the new path; `instance/config/outcomes.yml` mission text updated.
- **Layer-separation:** `.layer-separation-allowlist` gains
  `framework/authority/policy_engine.py:FRAMEWORK_PATH_INSTANCE`
  (by-design Captain-config read: `load_policies()` layering over
  `instance/config/policies/` + `active-preset`); the class-barred
  `FRAMEWORK_PATH_PRESETS` hit and the moved test file ride
  `.layer-separation-baseline`. `check-layer-separation.sh` → no new
  violations.

**Why:** the germ layer must be import-closed — `gate.py` (Ring-0 judge)
imported upward into `cabinet/scripts/lib/`, so the egg could not carry the
framework without dragging the cabinet lib path along, and every framework
consumer needed fragile sys.path surgery. With the engine inside
`framework/authority/` the judged authority plane is one package, the
germline boundary relocks at the new path unchanged in strength, and the
hook/typed-engine coverage is byte-equivalent (path strings only).

**Non-entries (promises pinned):**

- No verdict table, policy, ceiling, or floor semantics changed — the move
  is path-mechanical; `resolve_verdict` / `evaluate_policy` bytes are
  untouched.
- `cabinet/scripts/lib/tests/` keeps its remaining suite (shadow / join /
  ETL / work-graph); `test_authority_join.py` still proves the F+A join on
  the moved engine.
- The §5 constitution arm, MCP scope, and every other germline entry are
  untouched by this row.

**Gates (run in the staging worktree, 2026-07-07):**

- `python3.12 -m pytest framework/authority/tests/test_policy_engine.py
  cabinet/scripts/lib/tests -q` → 360 passed (250-corpus intact).
- `python3.12 -m pytest framework/ -q` → green (full suite, see branch
  gate log).
- `bash cabinet/scripts/run-hook-regression.sh` → green (probes at new path).
- `bash cabinet/scripts/check-layer-separation.sh` → no new violations.
- Import-direction crosscut: `grep -rn 'cabinet/scripts/lib.*policy_engine'
  framework/` → 0 code references (docs/history only).

**One-revert rollback:** `git revert` of the CG-14 commit on
`feat/germline-window-2` restores `cabinet/scripts/lib/policy_engine.py`,
its lib-tests corpus, and the prior path in `immutable-core.yml`,
`germline-lock.sh`, `pre-tool-use.sh` (§5 + §5b), `base-safety.yml`,
`axes-allowlist.yml`, the hook-regression probes, and both
layer-separation files; then `sudo bash cabinet/scripts/germline-lock.sh
lock` re-arms at the old path.
