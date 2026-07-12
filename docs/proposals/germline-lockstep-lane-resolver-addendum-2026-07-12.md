# Germline amendment (staged dark) — lane/officer instance-split in the acting organ (PC-E-LOCKSTEP pairs (a) + (e))

**Date:** 2026-07-12 · **Author:** Wave-G framework-sweep build agent (per
the 2026-07-07 full-autonomy grant; Captain "go G" 2026-07-12) · **Ledger
row:** CG-25 · **Targets:** `framework/frontdoor/action_exec.py`
(schg-locked, germline-lock.sh:54) and `framework/acting/action_lane.py`
(schg-locked, germline-lock.sh:60) · **Provenance sha:** diffs authored and
verified against `960d4c4d` (origin/master at wave start; both files
untouched by the wave itself) · **Ceremony:** rides the next germline unlock
window (with CG-23 + CG-24). PREREQUISITE: the Wave-G resolver commit
(`framework.env.officers()` / `lane_default()` + the `instance/config/
platform.yml` `lane_default: polads` key, branch `feat/wave-g-lockstep`)
must be merged to master BEFORE these patches are applied — the patched
code calls those resolvers.

## Why

PC-E-LOCKSTEP (operative-egg-ledger row): lane names are INSTANCE data, and
these two germline files carry the last framework-side officer-name
literals —

- **pair (a)** `action_exec.py:848` — `_DELEGATE_OFFICERS = {"cos",
  "polads-ceo", "stephie-ceo", "comms-officer"}`, the delegate_work +
  investigation_run whitelist;
- **pair (e)** `action_lane.py:158` — the PROPOSER_SYSTEM delegate_work
  officer enum literal — and `action_lane.py:470` —
  `lane_default: str = "polads"`, a Captain PolAds-first ruling encoded as
  a universal-base framework default.

Post-patch, both read the instance roster/config through the established
`framework.env` resolver seam (the captain_name/org_domains/tasks_board
precedent): whitelist + prompt enum from `env.officers()`
(cabinet/officer-capabilities.conf, read-only), proposal default lane from
`env.lane_default()` (instance/config/platform.yml, where the PolAds-first
ruling now lives as data with provenance).

## Verification already performed (shadow tree, not the live files)

- Both diffs apply cleanly with `patch -p1` to pristine copies at the
  provenance sha and reproduce the shadow-verified files BYTE-IDENTICALLY
  (diff -q after apply).
- `python3.12 -m py_compile` clean on both patched files.
- Shadow-tree suites WITH both patches: `python3.12 -m pytest
  framework/frontdoor framework/acting` → **1296 passed, 21 skipped, 0
  failed**.
- Byte-identity on this instance (probed live in the shadow):
  `_delegate_officers()` == the retired literal set exactly;
  `env.lane_default()` == `"polads"` == the retired signature default; the
  composed PROPOSER_SYSTEM carries the conf-order enum with no `%%OFFICERS%%`
  / `%%CAPTAIN%%` slot residue.
- Fail-closed on a generic deployment (CABINET_ROOT → empty dir):
  `_delegate_officers()` == frozenset() and `_exec_delegate` raises
  `delegate_work: unknown officer ...` LOUDLY; `_officer_enum()` renders
  `""`; `lane_default` `""` normalizes to the stable `adhoc` catch-all at
  the runner seam (`_normalize_lane("") == "adhoc"`).
- The lockstep test surface is ALREADY GREEN IN BOTH STATES on the branch
  (see Deviations): `framework/frontdoor/tests/test_action_exec.py` 83
  passed against today's literal, and the same file passes inside the
  patched shadow.

## Deviations from the recon dispositions (named honestly)

1. **The pair-(a) test flip does NOT ride inside this patch.** The recon
   mapped `test_action_exec.py:1111` as a ceremony-coupled flip ("conf
   injected as fixture, never alone"). The file's own `_CLEAN_CALINFO`
   precedent offers the stronger form: test changes that are green in BOTH
   states, pre-staged on the branch. Landed on `feat/wave-g-lockstep`
   instead: the `:1111` payload flips `polads-ceo` → `cos` (in today's
   literal AND in every roster the module now pins), and a new autouse
   `_synthetic_officer_roster` fixture primes `env._officers_cache =
   ("cos", "bakery-ceo")` for the whole module — INERT today, and
   roster-hermetic on ANY instance conf once this patch lands (a fresh
   hatch customizes the roster; the suite must never read it — the
   2026-07-07 blind-hatch lesson). This patch therefore touches germline
   SOURCE only, and the pair law (never a red pair) holds in both states.
2. **Roster injection is cache-priming, not a conf tmp-file.** The recon
   sketched "conf injected as fixture"; the landed fixture primes the
   resolver cache one seam higher (monkeypatch-restored). The full
   conf-read path is covered by `framework/tests/test_env.py::TestOfficers`
   with tmp-file confs; re-testing file IO from the action_exec suite would
   add cross-resolver CABINET_ROOT blast for no coverage gain.
3. **Prompt enum ORDER changes.** Today's hand order
   `"polads-ceo"|"stephie-ceo"|"comms-officer"|"cos"` becomes conf file
   order `"cos"|"polads-ceo"|"stephie-ceo"|"comms-officer"` — same SET
   (byte-equal membership), different rendering order. The recon claimed
   byte-identity only for the pair-(a) accept/reject set, which holds
   exactly; the enum is an LLM spec where order carries no contract.
4. **`propose_actions` purity note.** The module keeps directions/lessons
   as injected PARAMS ("the core never reads disk"); this patch adds
   `env.lane_default()` / `env.officers()` reads — the SAME class as the
   pre-existing `captain_name()` call inside the compose site
   (process-cached stable instance config, replay-stable within a run),
   not mutable ledger state. Documented in the patched comments.

## Known residuals (explicitly NOT covered here)

- `action_lane.py:117` — the `ActionProposal.lane` dataclass comment
  citing the ruling stays as a dated record (recon: leave-with-reason).
- `run_action_lane.py` comment/docstring lane mentions stay (dated
  germline-batch records; recon: leave-with-reason). Its `_context_slugs`
  enumerator is the extract-to-`env.py` candidate for a LATER window —
  `env.lanes()` was built parse-mirrored so that merge is a no-op.
- `cabinet/officer-capabilities.conf` is itself schg: a hatched instance
  customizing its roster needs the egg to ship it unlocked (recon-named,
  egg-side question — not this row).

## The staged diffs (verbatim; apply with `patch -p1` from the repo root)

### Pair (a) — framework/frontdoor/action_exec.py

```diff
diff --git a/framework/frontdoor/action_exec.py b/framework/frontdoor/action_exec.py
index 312a108..4ce03e6 100644
--- a/framework/frontdoor/action_exec.py
+++ b/framework/frontdoor/action_exec.py
@@ -845,7 +845,16 @@ def _exec_calendar_event(payload: dict, osascript: Callable,
     return {"calendar": out_cal, "uid": uid, "title": title[:80]}
 
 
-_DELEGATE_OFFICERS = {"cos", "polads-ceo", "stephie-ceo", "comms-officer"}
+def _delegate_officers() -> frozenset:
+    """The valid delegate/investigation officer targets — the INSTANCE roster
+    (cabinet/officer-capabilities.conf via env.officers(), process-cached),
+    never a baked-in officer set (PC-E-LOCKSTEP pair (a); the conf officer set
+    was verified byte-equal to the retired literal on the launching instance).
+    Call-time resolution so tests inject a synthetic roster and a restart
+    picks up a roster change. Unreadable/empty conf ⇒ empty set ⇒ every
+    officer rejected LOUDLY at the checks below (fail-closed, the tasks_board
+    precedent) — never a foreign roster, never a silent accept."""
+    return frozenset(env.officers())
 
 
 def _exec_delegate(payload: dict) -> dict:
@@ -855,7 +864,7 @@ def _exec_delegate(payload: dict) -> dict:
     is whitelist-validated; the brief travels as an argv value, never shell."""
     officer = (payload.get("officer") or "").strip()
     brief = (payload.get("brief") or "").strip()
-    if officer not in _DELEGATE_OFFICERS:
+    if officer not in _delegate_officers():
         raise RuntimeError(f"delegate_work: unknown officer {officer!r}")
     if not brief:
         raise RuntimeError("delegate_work needs a brief")
@@ -918,7 +927,7 @@ def _exec_investigation(payload: dict) -> dict:
     an argv value, never shell."""
     officer = (payload.get("officer") or "").strip()
     question = (payload.get("question") or "").strip()
-    if officer not in _DELEGATE_OFFICERS:
+    if officer not in _delegate_officers():
         raise RuntimeError(f"investigation_run: unknown officer {officer!r}")
     if not question:
         raise RuntimeError("investigation_run needs a question")
```

### Pair (e) — framework/acting/action_lane.py

```diff
diff --git a/framework/acting/action_lane.py b/framework/acting/action_lane.py
index 3fe9038..10e8158 100644
--- a/framework/acting/action_lane.py
+++ b/framework/acting/action_lane.py
@@ -42,6 +42,7 @@ import re
 from dataclasses import dataclass, field
 from typing import Any, Callable
 
+from framework import env  # instance-config resolvers (officers, lane_default)
 from framework.env import captain_name
 from framework.attention.situation import canonical_refs, path_grade
 
@@ -142,6 +143,20 @@ _CAPTAIN_SLOT = "%%CAPTAIN%%"
 # pure and replay-stable — the runner loads the ledger, the core never reads
 # disk.
 _LESSONS_SLOT = "%%LESSONS%%"
+# PC-E-LOCKSTEP pair (e): %%OFFICERS%% carries the INSTANCE officer roster
+# (env.officers(), conf-derived, process-cached) rendered as the delegate_work
+# officer enum — the spec names no launcher's officers. An empty roster renders
+# an empty enum and the executor's roster check rejects any invented target
+# (fail-closed at the acting seam).
+_OFFICERS_SLOT = "%%OFFICERS%%"
+
+
+def _officer_enum() -> str:
+    """The delegate_work officer enum for the prompt spec — `"a"|"b"` rendered
+    from env.officers() (conf file order; the same roster the executor's
+    whitelist reads, so spec and enforcement can never disagree)."""
+    return "|".join('"%s"' % o for o in env.officers())
+
 
 PROPOSER_SYSTEM = """You are the action-proposal core of %%CAPTAIN%%'s cabinet.
 %%CAPTAIN%% handles ALL communication himself. You propose ACTIONS the captured world
@@ -155,7 +170,7 @@ EXECUTABLE action kinds:
 - monday_task_update: {monday_id, set: {status?|priority?|due?|description?}, why}
 - reminder_create: {title, due_iso, notes?} — lands as a CALENDAR event/block on
   %%CAPTAIN%%'s calendar (never a personal to-do app)
-- delegate_work: {officer: "polads-ceo"|"stephie-ceo"|"comms-officer"|"cos",
+- delegate_work: {officer: %%OFFICERS%%,
   brief: str} — dispatches a precise implementation brief to that officer's
   lane so the work actually gets DONE on approval
 
@@ -467,7 +482,7 @@ def propose_actions(
     decided_subjects: set,
     open_subjects: set,
     budget_left: int,
-    lane_default: str = "polads",
+    lane_default: str = "",
     covered_evidence: frozenset = frozenset(),
     acted_refs: frozenset = frozenset(),
     reversed_refs: frozenset = frozenset(),
@@ -503,6 +518,15 @@ def propose_actions(
       drops, SEC-4 RT-A12). Default None = no-op, so the core stays pure and
       replay-deterministic; the runner passes a real logger.
     """
+    # PC-E-LOCKSTEP pair (e): the proposal default lane is INSTANCE data (a
+    # Captain ruling, `lane_default` in instance config), not a framework
+    # literal. A caller-supplied value wins; unset resolves env.lane_default()
+    # — process-cached instance config, replay-stable within a run, the same
+    # class of read as captain_name() below. "" on a generic deployment: the
+    # runner's _normalize_lane then files cards under the stable adhoc
+    # catch-all, never an invented lane.
+    lane_default = lane_default or env.lane_default()
+
     def _drop(subject: str, reason: str) -> None:
         if suppress_log:
             try:
@@ -516,6 +540,8 @@ def propose_actions(
     valid_ids = _direction_ids(directions)
     enforce_dir = bool(isinstance(directions, dict) and directions.get("directions"))
     system = PROPOSER_SYSTEM.replace(_CAPTAIN_SLOT, captain_name()).replace(
+        _OFFICERS_SLOT, _officer_enum()
+    ).replace(
         _DIRECTIONS_SLOT, render_directions(directions) or "(no directions loaded)"
     ).replace(
         _LESSONS_SLOT,
```

## Ceremony apply steps

1. Confirm `feat/wave-g-lockstep` is merged (resolvers + platform.yml key +
   the pre-staged test fixture present at HEAD).
2. Captain unlock window: `sudo cabinet/scripts/germline-lock.sh unlock`
   (per its own procedure).
3. From the repo root: `patch -p1 < <pair-a diff>` then
   `patch -p1 < <pair-e diff>` (both carried verbatim above).
4. `python3.12 -m py_compile framework/frontdoor/action_exec.py
   framework/acting/action_lane.py`
5. `python3.12 -m pytest framework/frontdoor framework/acting -q` — expect
   green (1296 passed / 21 skipped at staging time).
6. `grep -n "polads\|stephie" framework/frontdoor/action_exec.py
   framework/acting/action_lane.py` — expect the pair-(a)/(e) LOGIC hits
   gone; `action_lane.py:117` comment record remains by design.
7. Commit + `germline-lock.sh lock` the SAME session; relock verified with
   `germline-lock.sh verify`.

## One-revert rollback

Do not apply at the ceremony (or `git revert` the applied commit before
relock): the whitelist returns to the module-literal set and the proposer
returns to the literal enum + "polads" default. The branch-side resolvers,
platform.yml key, and the pre-staged test fixture are inert in that state
(proven green pre-ceremony) — no second revert needed.
