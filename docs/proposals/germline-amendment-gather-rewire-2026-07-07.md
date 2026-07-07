# Germline amendment — run_action_lane gather rewire onto the PersonalSource seam (2026-07-07, egg rows CG-2 / R004a / R003-tests)

**Status:** STAGED on branch `feat/germline-window-2` (germline window 2,
worktree-staged — the live checkout's schg boundary was never opened). The
via-source path lands **DARK**: `CABINET_GATHER_VIA_SOURCE` defaults OFF and
the flag-off behavior is byte-identical (parity-pinned). Canary one tick with
the flag ON, then relock — per the CG-2 row's own discipline. Reply
**"revert gather rewire"** to drop the branch commit (one-revert rollback
below).

**Ratification chain (already-ruled — reference only, do NOT re-paste):**

- **Egg plan rows CG-2 + R004(a)** — `docs/plans/operative-egg-plan-2026-07-07.md`:
  "Unlock-window amendment: replace vault-dir literals
  (run_action_lane.py:739-755, VAULT at :87) with
  PersonalSource.open_commitments/search + channel-contract presentation.
  Live acting-lane organ: land dark behind a flag, canary one tick, then
  relock." R004(b) (run_draft_lane side) rides W1A-T1 and is NOT part of
  this change.
- **Germline-window-2 order (2026-07-07)** — executed under the 2026-07-07
  standing full-autonomy grant; germline edits staged in a worktree, never
  live.

**What (the germline edit set — one germline file):**

- `framework/acting/run_action_lane.py` (germline, files-class):
  - The gather SECTION TABLE (`PROFILES` with the vault-dir literals), the
    file-walk helpers (`_read_frontmatter` / `_ff_match` / `_mtime` /
    `_recent_files` / `_named_files` / `_excerpt` / `_relpath`), the module
    `VAULT` constant (:87), and the D13 inbound-prefix TABLE moved to the
    NEW unlocked module `framework/sources/vault_signals.py` — the personal
    vault LAYOUT is adapter knowledge; the JUDGMENTS (D13 fence, ask
    budget, cid-echo suppression, verdict routing) all stay in the germline
    lane file.
  - `gather_signals` keeps its exact signature and becomes a dispatch:
    - **Flag OFF (default):** `vault_signals.collect_sections(...)` — the
      extracted-but-identical walk. Behavior byte-identical, pinned by the
      pre-existing `test_gather_v2.py` + `test_gather_corpus.py` (untouched,
      green) plus the new flag-off parity test asserting
      `gather_signals(...) == join(collect_sections(...))` and that the
      source seam is NEVER resolved flag-off.
    - **Flag ON (`CABINET_GATHER_VIA_SOURCE=1`, dark):** `_source_parts` —
      `PersonalSource.open_commitments()` (both contract directions, capped
      8 like the legacy commitments section) + per-commitment leak-scoped
      `PersonalSource.search(handle, topic=…)` context, presented in the
      SAME `--- LABEL ref=… ---` fenced-block channel; hits are
      content_ts-fenced `<= as_of` and ts-less hits are DROPPED (absent =
      unfenceable, never assumed-past); org-corpus sections ride along
      unchanged. FAIL-CLOSED: broken/absent source ⇒ EMPTY gather — never a
      silent fallback to the vault walk.
- NEW (unlocked): `framework/sources/vault_signals.py`,
  `framework/acting/tests/test_gather_via_source.py` (R003: extends the
  test_gather_corpus fixture patterns — tmp vault, explicit mtimes, no live
  APIs).

**Why:** the acting lane is a Ring-0 judged organ; carrying the captain's
personal vault layout inside it (a) widened the germline surface with
non-judgment content, and (b) blocked the egg/clean-room story (SRC-5: core
reaches the estate only through `framework.sources.get_source()`). The seam
was widened for exactly this on 2026-07-07 (T1 protocol widen,
`framework/sources/base.py`).

**Non-entries (promises pinned):**

- Flag default is OFF — zero live-behavior change at merge; the CG-2 row
  gate `grep -c '6-Commitments' framework/acting/run_action_lane.py` → 0
  is pinned as a test (`test_cg2_gate_no_vault_dir_literals_in_lane_file`).
- No ask-budget, verdict, posture, or act-first change; `_directions_block`
  (instance config read) unchanged; TI-7 cid-echo suppression unchanged on
  both paths.
- `vault_signals.py` is deliberately NOT lock-listed: it supplies
  OBSERVATION layout, not judgment — the D13 fence and every verdict stays
  in the locked lane. (Same class as the flavor adapters the seam binds.)

**Gates (run in the staging worktree, 2026-07-07):**

- `python3.12 -m pytest framework/acting -q` → 279 passed (both flag
  states exercised; gather_v2 + gather_corpus untouched and green).
- `grep -cE '6-Commitments|2-Meetings|5-Reflections'
  framework/acting/run_action_lane.py` → 0.
- `bash cabinet/scripts/check-layer-separation.sh` → no new violations.
- `python3.12 -m pytest framework/ -q` → green (full suite, branch gate log).

**One-revert rollback:** `git revert` of the CG-2 commit on
`feat/germline-window-2` restores the inline table + walk in
`framework/acting/run_action_lane.py` (germline file back byte-identical to
pre-window) and removes `vault_signals.py` + the via-source tests; flag off
(or absent) is already the shipped state, so no runtime action is needed
beyond `sudo bash cabinet/scripts/germline-lock.sh lock` on the live
checkout after merge/revert.
