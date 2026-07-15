# Germline 4-file prep — mcp-scope.yml + officer-capabilities.conf (staged, not landed)

**Date:** 2026-07-15 · **Author:** germline-4file-prep worktree-prep agent
(product/captain-agnostic fix request) · **Ledger row:** not yet assigned —
this doc is worktree-staged output for the orchestrator/Captain to file
against the operative-egg-ledger, filed alongside the CG-25 pair (a)/(e) work
this addendum continues · **Targets:** `cabinet/mcp-scope.yml` (schg-locked,
germline-lock.sh:73) and `cabinet/officer-capabilities.conf` (schg-locked,
germline-lock.sh:74) · **Companion:** completes the 4-file request that
started with `docs/proposals/germline-lockstep-lane-resolver-addendum-2026-07-12.md`
(pairs (a) `framework/frontdoor/action_exec.py` and (e)
`framework/acting/action_lane.py`, applied verbatim in this same worktree,
commits `b71fe796` / `3abe4876`) · **Worktree:**
`/Users/nate/cabinet-worktrees/germline-4file-prep`, branch
`feat/germline-4file-prep`, off `origin/master` at `eb6b25ea` · **Provenance:**
all research and diffs below were produced and verified in that worktree —
the live tree was never read for anything but the one read-only roster.yml
inspection cited in Finding 1 (never written, never touched with chflags/sudo).

## Why this doc exists (read this before the diffs)

The 2026-07-12 addendum named `cabinet/officer-capabilities.conf` an
unresolved residual: *"is itself schg: a hatched instance customizing its
roster needs the egg to ship it unlocked (recon-named, egg-side question —
not this row)."* The follow-up request that produced this doc asked for "the
same treatment" pairs (a)/(e) got — moving hardcoded officer literals out of
framework code into a resolver read — applied fresh to `mcp-scope.yml` +
`officer-capabilities.conf`.

**That request, taken literally, does not apply to these two files, and
this doc says so rather than forcing a fit.** Pairs (a)/(e) fixed a real bug:
`framework/frontdoor/action_exec.py` and `framework/acting/action_lane.py`
are **universal-base framework source** — every hatch runs the same copy of
that code — and it had this Captain's specific officer names
(`polads-ceo`/`stephie-ceo`) baked into a Python literal, so a differently-named
hatch running the *same framework file* would get the *wrong* whitelist.
`mcp-scope.yml` and `officer-capabilities.conf` are not that. They are
**already** the instance data layer:

- `framework.env.officers()` (`framework/env.py:273`) reads
  `cabinet/officer-capabilities.conf` directly and generically — no
  officer-name literal anywhere in that resolver. This is the exact function
  pairs (a)/(e) now call.
- `cabinet/scripts/world-compose-portraits.py`'s `default_roster()` reads the
  same conf the same way, for the "product-CEO portraits" the task brief
  mentioned — also generic, no hardcoded slugs.
- `cabinet/scripts/load-preset.sh` treats `mcp-scope.yml`'s `agents:` keys as
  *the* hired-officer list other generation steps key off — it is a source,
  not a derived target.
- `cabinet/scripts/generate-instance.py`'s own hatch-time instructions
  explicitly tell an operator to hand-author rows in **both** files per lane
  CEO they hire (lines ~633, ~682, ~1342-1343) — hand-editing them per
  deployment is the documented, intended mechanism, not a bug.

So the "hardcoding" here is instance data doing its job, not a framework
literal masquerading as one. Rewriting these two files' officer rows to be
mechanically *generated* from `instance/config/roster.yml` was considered and
**rejected** for this pass — see "Rejected approach" below. What actually
*was* missing, and what this doc's diffs deliver, is narrower and real.

## What this patch does

1. **Comment-only provenance headers** in both files (verified zero
   behavior change — see Verification) naming them as instance data, cross-
   referencing `instance/config/roster.yml` as the parallel roster record,
   and pointing at the new test below. No officer/capability/mcp row
   touched.
2. **New test** `framework/tests/test_roster_conf_lockstep.py`: whenever
   `instance/config/roster.yml` exists, asserts every roster officer slug has
   a row in `officer-capabilities.conf` AND an entry in `mcp-scope.yml`'s
   `agents:` map (officer-SET coverage — a hire with a row in neither is a
   silent capability/MCP lockout). Skips cleanly when roster.yml is absent
   (fresh checkout, CI, this worktree, a not-yet-hatched repo).
3. **This doc**, naming a real drift the new test deliberately does not
   assert on (Finding 1) and the residual architecture question pairs
   (a)/(e) already punted (Finding 2, still punted, now with a concrete
   next step named).

## Verification performed (this worktree)

- `python3.12 -c "import yaml; ... yaml.safe_load(...) == yaml.safe_load(...)"` —
  `mcp-scope.yml` parses to a **structurally identical** mapping before/after
  the comment addition.
- `git diff cabinet/officer-capabilities.conf cabinet/mcp-scope.yml | grep -E
  '^[+-][^+-]' | grep -v '^[+-]#'` — **empty output**: every added/removed
  line in both files starts with `#`. No data row changed.
- `framework.env.officers()` and `framework.env.deploys_code_officer()`
  resolve to the exact same values before and after the comment addition:
  `('cos', 'polads-ceo', 'stephie-ceo', 'comms-officer')` /
  `'polads-ceo'`.
- Test suites re-run clean after the comment addition (all run individually;
  a multi-file `pytest a.py b.py c.py` invocation across sibling `tests/`
  packages hit a pre-existing rootdir/import collision unrelated to this
  patch, worked around by invoking per-file):
  `framework/tests/test_env.py` (72 passed),
  `framework/attention/tests/test_advisor.py` (15 passed),
  `framework/learning/tests/test_self_proposal.py` (15 passed),
  `framework/measurement/tests/test_role_evals.py` (23 passed),
  `cabinet/scripts/tests/test_gen_officer_mcp_config.py` (25 passed),
  `cabinet/scripts/lib/tests/test_lanes_sh.py` (14 passed),
  `framework/tests/test_germline_lockstep_consistency.py` (258 passed),
  `framework/tests/test_roster_conf_lockstep.py` (new; 6 passed, 1 skipped —
  the skip is `test_live_roster_officer_set_covered_by_conf_and_scope`,
  correctly, since this worktree has no `instance/config/roster.yml`).

## Finding 1 — a real, pre-existing roster.yml ↔ officer-capabilities.conf drift

Read-only, offline simulation (the live `instance/config/roster.yml` copied
into a scratch tmp dir, never written, live tree untouched) against this
worktree's `officer-capabilities.conf`:

```
officer-SET coverage missing: {}   <- the new test's actual assertion: PASSES
DRIFT cos:           roster.yml=[logs_captain_decisions, reviews_implementations,
                                  reviews_specs, validates_deployments]
                     conf       =[captain_rules_retrieval, drives_computer,
                                  logs_captain_decisions, telegram_bot,
                                  validates_deployments]
DRIFT polads-ceo:    roster.yml=[deploys_code, logs_captain_decisions]
                     conf       =[captain_rules_retrieval, deploys_code,
                                  logs_captain_decisions]
DRIFT stephie-ceo:   roster.yml=[deploys_code, logs_captain_decisions]
                     conf       =[captain_rules_retrieval, deploys_code,
                                  logs_captain_decisions]
DRIFT comms-officer: roster.yml=[logs_captain_decisions]
                     conf       =[captain_rules_retrieval, logs_captain_decisions]
```

`officer-capabilities.conf` is the file that is actually READ by
`framework.env.officers()`/`deploys_code_officer()` and by the pre-tool-use
hook's capability routing — it is authoritative for live enforcement.
`instance/config/roster.yml`'s own header claims officer-capabilities.conf's
"capability rows below mirror it," which is false today for every officer:
the conf grants `captain_rules_retrieval` (and, for `cos`, also
`drives_computer` + `telegram_bot`) that roster.yml's `capabilities:` list
does not carry. **This patch does NOT touch roster.yml or
officer-capabilities.conf's data to reconcile this** — I cannot tell, without
a Captain ruling, whether roster.yml's `capabilities:` list is simply stale
documentation (most likely, given it is described as a "mirror") or whether
officer-capabilities.conf is over-granted — asserting either direction as a
"fix" would be a guess dressed as a correction. Flagging it here is the
honest deliverable; `test_roster_conf_lockstep.py` deliberately checks
officer-SET coverage only, not capability-list equality, so it does not
paper over this by picking a side, and does not spuriously redden the suite
over a data question outside this task's authority.
**Recommended next step (not taken here):** a CoS/Captain pass that either
(a) updates roster.yml's `capabilities:` rows to match
officer-capabilities.conf (if the conf is correct and roster.yml's
"mirror" comment is just stale), or (b) the reverse, then promotes the
lockstep test's assertion from officer-SET coverage to exact capability-list
equality once the two agree, closing the loop this doc opens.

## Finding 2 — the schg-lock-vs-hand-customization tension (still open)

The 2026-07-12 addendum called this "an egg-side question, not this row" and
this pass agrees it should not be resolved unilaterally here, for two
concrete reasons found during this investigation:

1. **A real fix requires touching files outside this task's 4-file scope.**
   Making these two files' officer rows *mechanically generated* from
   `instance/config/roster.yml` (rather than hand-authored parallel data)
   would require changing `framework/env.py`'s `officers()` resolver (not
   schg-locked itself, but changing its read target is a behavior change to
   a function 3+ call sites depend on), `cabinet/scripts/hooks/pre-tool-use.sh`'s
   capability/scope parsing, and `cabinet/scripts/load-preset.sh`'s
   hired-list check — none of which were named in the 4-file request, and
   none of which I can fully regression-test for the LIVE fleet's exact
   enforcement behavior from a worktree alone (`pre-tool-use.sh` is the live
   security hook; a wrong change there is a live-fleet risk class, not a
   worktree-provable one).
2. **It is a Ring-0/Ring-1 classification call, not an engineering call.**
   `germline-lock.sh` classifies both files as "judged config (NOT
   runtime-written)" — Ring-0, ceremony-gated. `officer-capabilities.conf`'s
   own header says "Founders: customize for your officer set," and
   `generate-instance.py`'s hatch flow tells a brand-new operator to hand-edit
   both files directly. Reconciling that (unlock these two from schg
   entirely, add a `.example` twin the egg ships instead — mirroring
   `instance/config/roster.yml.example` — and let hatch/load-preset write the
   real ones fresh, `.gitignore`'d like roster.yml; or leave them Ring-0 and
   accept every hatch needs one unlock ceremony to seat its own roster) is a
   product decision about how much friction a fresh hatch should tolerate. I
   am not making it here; per the standing cardinal fleet-safety instruction
   for this task ("if you cannot prove identical resolution, do not land —
   stage + flag"), this is exactly that flag.

**Staged, not landed:** no diff for either of these two findings is proposed
in this doc. Both are recommendations for a follow-up ledger row with
explicit Captain/CoS input, not code.

## Ceremony apply steps (this doc's actual diffs only — Findings 1/2 are not diffs)

1. Confirm the pair (a)/(e) commits from
   `germline-lockstep-lane-resolver-addendum-2026-07-12.md` are already
   applied (this worktree's commits `b71fe796`, `3abe4876` — do these FIRST,
   `env.officers()`/`env.lane_default()` must exist and be in use before this
   doc's commits add a test that imports them transitively via
   `cabinet/scripts/lib_roster.py`).
2. Captain unlock window: `sudo cabinet/scripts/germline-lock.sh unlock`
   (same window as pairs (a)/(e) — batch it, one unlock/relock cycle).
3. From the repo root: apply this worktree's `officer-capabilities.conf` and
   `mcp-scope.yml` commits (comment-only; `git cherry-pick` or `patch -p1`
   from an exported diff — either reproduces the same byte-for-byte file,
   verified above).
4. Copy `framework/tests/test_roster_conf_lockstep.py` in (new file, no
   patch needed, plain add).
5. `python3.12 -m pytest framework/tests/test_roster_conf_lockstep.py
   framework/tests/test_env.py -q` — expect all green (6 passed + 1 skipped
   in the lockstep module on a checkout without roster.yml load issues; on
   the LIVE tree with the real roster.yml present, expect 7 passed — the
   live officer-SET coverage check passes today per Finding 1's simulation).
6. `grep -n "polads\|stephie" cabinet/mcp-scope.yml
   cabinet/officer-capabilities.conf` — expect the SAME hits as before this
   patch (this patch adds zero new data-row hits; it is comment-only).
7. Commit + `germline-lock.sh lock` the SAME session; relock verified with
   `germline-lock.sh verify`.

## One-revert rollback

`git revert` the comment-only commits (or drop the new test file) at any
time — zero runtime behavior depends on either change (proven in
Verification above), so reverting is a pure no-op for the running fleet.
