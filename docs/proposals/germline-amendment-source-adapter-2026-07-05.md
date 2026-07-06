# Germline amendment proposal — SOURCE-ADAPTER credential path — 2026-07-05

**Status:** AWAITING CAPTAIN. Both germline files named below are
Captain-applied only. Reply **"apply source-adapter"** and the session executes
the apply ritual (§5) exactly: unlock → apply the three-file reparent → re-lock →
verify. Nothing in this package changes live behavior on THIS instance at all —
it is a credential-PATH reparent whose entire correctness proof is that, on this
deployment, it renders byte-identical to today.

**Branch of record:** `feat/source-adapter-p2` (worktree
`.claude/worktrees/source-adapter-p2`, base `5e79138d`). The branch is the diff;
this document is its Captain-readable contract for the **germline** subset (3
files). The branch also carries the ~non-germline source-adapter PASS-2 work
(the emptied ratchet, the `clean-room-source` CI job, `eval-021`, the plan/spec
update) recorded in `docs/plans/source-adapter-boundary-2026-07-05.md`, not
here.

**Encodes (already-ruled — reference only, do NOT re-paste):**

- **FOUNDATION-FIRST (2026-07-05, Captain-ruled, logged in
  `shared/interfaces/captain-decisions.md`)** — `framework/` is the universal
  base for any captain and either flavor; anything launcher-specific (name,
  vault paths, board ids, **credential paths**) belongs in `instance/` or an
  adapter, never `framework/`. This amendment discharges the source-adapter
  spec's Tier-2 germline flag (`docs/plans/source-adapter-boundary-2026-07-05.md`
  §3, §5 Phase 4) for the two credential-path carriers.

## §0 · What this changes, in one paragraph

`framework/frontdoor/action_exec.py` and `framework/frontdoor/actfirst_canary.py`
each carried a **hardcoded** `~/.screenpipe/pipes/_shared/.env` credential PATH
(a module-level `_SHARED` / `_SHARED_ENV` constant). Both now resolve that path
through the shipped resolver **`framework.env.shared_env_path()`** (base
`5e79138d`; reads `shared_env_path` from `instance/config/platform.yml`, env
`CABINET_SHARED_ENV` overrides, fallback `""`). No credential VALUE is touched —
`MONDAY_API_KEY` and every other secret stay in the `.env` file and are read the
same way; only the *default path to that file* moves from a launcher literal to
instance config. Because `shared_env_path()` resolves to
`~/.screenpipe/pipes/_shared/.env` on this deployment, **every runtime byte is
identical to `5e79138d`** — the correctness proof. The only NEW behavior is a
fail-closed guard for the universal base: when `shared_env_path()` resolves `""`
(a clean-room / Flavor-B box with no shared env configured), `_load_shared_env`
loads nothing (Monday calls then fail closed on the missing key) and
`env_perms_finding` returns `None` (nothing to check) — neither path can fire on
this instance, where the resolver is non-empty. No verdict table, threshold,
authority path, board id, event vocabulary, or control flow is touched.

## §1 · Per-file inventory (the branch is the diff)

Export the exact germline diff set for review:

```bash
git -C /Users/nate/captains-cabinet/.claude/worktrees/source-adapter-p2 \
  diff 5e79138d -- \
  framework/frontdoor/action_exec.py \
  framework/frontdoor/actfirst_canary.py \
  framework/acting/run_action_lane.py
```

| File (absolute) | Reparent | Byte-identical proof (this instance) |
|---|---|---|
| `/Users/nate/captains-cabinet/.claude/worktrees/source-adapter-p2/framework/frontdoor/action_exec.py` | Deleted module const `_SHARED = str(Path.home() / ".screenpipe" / "pipes" / "_shared")`; `_load_shared_env()` now `shared = env.shared_env_path(); … Path(shared).expanduser()`. Doc comment for `MONDAY_API_KEY` source updated. Uses the pre-existing `from framework import env` import. | `shared_env_path()` → `~/.screenpipe/pipes/_shared/.env`; `Path("~/.screenpipe/pipes/_shared/.env").expanduser()` == old `Path(_SHARED) / ".env"` == `/Users/nate/.screenpipe/pipes/_shared/.env`. |
| `/Users/nate/captains-cabinet/.claude/worktrees/source-adapter-p2/framework/frontdoor/actfirst_canary.py` | Deleted module const `_SHARED_ENV = Path.home() / ".screenpipe" / "pipes" / "_shared" / ".env"`; `env_perms_finding()` now resolves the default via `shared = env.shared_env_path(); … Path(shared).expanduser()`. Docstring updated. Uses the pre-existing `from framework import env` import. | Same resolver → same absolute path as the removed `_SHARED_ENV`. The explicit-`path` caller contract is unchanged (an argument still wins). |
| `/Users/nate/captains-cabinet/.claude/worktrees/source-adapter-p2/framework/acting/run_action_lane.py` | **(a) sensing-seam migration (P2-REHOME):** the acting `screenpipe_adapter` import is split — pure loop-plumbing → `framework.acting.lane_dedup` (in framework, zero screenpipe), the screenpipe surface → `get_source()`. **(b) credential/vault-path reparent:** `VAULT = Path.home()/"Obsidian"/"screenpipe-brain"` → `Path(vault_dir() or str(Path.home()/"vault"))`; `_load_env`'s `~/.screenpipe/…/.env` → `Path(shared_env_path()).expanduser()`. No act-first perimeter / verdict / board / authority change. | `vault_dir()` → `/Users/nate/obsidian/screenpipe-brain` (same dir as `~/Obsidian/screenpipe-brain` on macOS case-insensitive FS — behaviorally identical); `shared_env_path()` → same absolute `.env`. `get_source()` returns `ScreenpipeSource` delegating to today's code. **sovereign+earn_up sweeps (1499/542) confirm no verdict change.** |

Diffstat: **3 germline files, byte-identical behavior** — no logic outside the
path-resolution + sensing-seam sites; the act-first authority perimeter in
`run_action_lane.py` is untouched (posture sweeps green).

## §2 · Correctness proof (byte-identical on this instance)

1. `instance/config/platform.yml` sets `shared_env_path:
   ~/.screenpipe/pipes/_shared/.env` — the exact literal both files previously
   hardcoded. `env.shared_env_path()` returns it; `.expanduser()` yields the
   identical absolute path. The credential file, its `0600` perms target, and
   the `MONDAY_API_KEY` read are unchanged.
2. The added `if not shared:` branch is UNREACHABLE on this instance (resolver
   non-empty); it exists only so the universal base fails closed on a generic
   deployment. So there is no behavior delta here — the existing frontdoor tests
   that pin `_load_shared_env` / `env_perms_finding` stay green unchanged.
3. No credential VALUE is read, logged, moved, or re-scoped by this amendment —
   Corridor's guardrail (secrets stay in `.env`; resolve the path, never the
   value) holds exactly.

## §3 · One-revert rollback

**One-revert rollback:** a single `git revert`/`git checkout 5e79138d --` of the
two named germline files restores the pre-amendment bytes; both are
independent path-resolution reparents with no cross-file coupling and no schema
or state migration, so reverting either or both is safe in any order:

```bash
git -C /Users/nate/captains-cabinet/.claude/worktrees/source-adapter-p2 \
  checkout 5e79138d -- \
  framework/frontdoor/action_exec.py \
  framework/frontdoor/actfirst_canary.py \
  framework/acting/run_action_lane.py
```

Every germline file in this amendment: `framework/frontdoor/action_exec.py`,
`framework/frontdoor/actfirst_canary.py`, `framework/acting/run_action_lane.py`.

## §4 · Per-directory pytest evidence

Run the frontdoor package tests (the directory that owns both files) after the
reparent — green:

```bash
cd /Users/nate/captains-cabinet/.claude/worktrees/source-adapter-p2
python3.12 -m pytest framework/frontdoor/tests -q -p no:cacheprovider
# 699 passed, 17 skipped in 2.44s
```

And the two source-boundary gates the reparent feeds (post-reparent, this
instance): `check-layer-separation.sh` green (the removed `~/.screenpipe`
literals drop the two files out of the `FRAMEWORK_PATH_SCREENPIPE` baseline),
and `framework/tests/test_no_screenpipe_in_core.py` no longer flags these two
files (they carry no screenpipe path literal after the reparent).

## §5 · Apply ritual (Captain-only)

On **"apply source-adapter"**:

1. **Unlock** the germline for all three files
   (`cabinet/scripts/germline-lock.sh unlock` per the standing ritual —
   `run_action_lane.py` is germline too, so unlocking only the two frontdoor
   files would fail the merge when it writes the acting file).
2. **Apply** the three-file reparent from `feat/source-adapter-p2` by **merging
   the branch** (do not cherry-pick a subset — `run_action_lane.py`'s
   sensing-seam migration is coupled to the non-germline `lane_dedup.py` +
   `framework/sources` seam that only the full merge carries).
3. **Re-lock** (`cabinet/scripts/germline-lock.sh lock`).
4. **Verify:** `python3.12 -m pytest framework/frontdoor/tests framework/acting/tests -q`
   green; `bash cabinet/scripts/check-layer-separation.sh` green; the reparented
   files import + run byte-identically (Monday credential load, the `0600` perms
   finding, and `run_action_lane`'s `VAULT`/`.env` resolve the same paths as before).

## §6 · Concurrent-germline-agent conflict flag ⚠️

**These two files are germline HOT-SPOTS edited by more than one in-flight
amendment.** `action_exec.py` and `actfirst_canary.py` both appear in the
sovereign-posture amendment's germline edit set
(`docs/proposals/germline-amendment-sovereign-posture-2026-07-05.md` — the
act-first executor + canary tables), and `action_exec.py` also carries a
de-nate name-generalization
(`docs/proposals/germline-amendment-de-nate-2026-07-05.md`). A **concurrent
germline agent** is editing these same files in the live repo.

Consequences the Captain / orchestrator must reconcile BEFORE applying:

- **Do not apply blind.** This amendment's diff base is `5e79138d`. If the
  sovereign-posture or de-nate germline edits have already landed on these files
  (or land concurrently), the two-file reparent must be **re-based onto the
  current germline bytes** and re-verified — a stale `git checkout 5e79138d --`
  would CLOBBER a co-resident amendment's edit.
- **This reparent is orthogonal** to those amendments (it touches only the
  `_SHARED`/`_SHARED_ENV` credential-path sites; sovereign touches act-first
  verdict/tell surfaces; de-nate touches a name string), so a three-way merge is
  clean in principle — but it must be an explicit merge, not a whole-file
  overwrite. Prefer applying the **per-hunk** `shared_env_path` reparent over
  merging the whole file if another amendment is mid-flight.
- **Apply order is free but must be serialized:** unlock → apply ONE amendment's
  hunks → re-verify → re-lock, per amendment. Never hold the germline unlocked
  across two agents' writes.

## §7 · Scope boundary

This amendment covers ONLY the `shared_env_path()` credential-path reparent in
the two named files. The board-id sourcing in `action_exec.py`
(`env.tasks_board()`) and any act-first table / name-string edits in these files
are the property of their own amendments (de-nate, sovereign-posture, mission)
and are NOT re-authorized here. The `retro.py` scoring-seam vendoring (spec §5
Phase 4) is likewise a separate, later package.
