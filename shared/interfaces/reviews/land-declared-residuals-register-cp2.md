# cp2 — landing integration of the declared-residuals register

Branch `land/declared-residuals-register` (rebase of the parked
`feat/declared-residuals-register` @ `b60c29d7` onto `origin/master`
@ `db180092`). cp1 covered the original two commits; this artifact covers the
THIRD commit only — the integrator changes made at landing.

**Provenance:** per 2026-07-07 full-autonomy grant.

## Why a third commit exists at all

The register was authored against `a1357829`. Master moved to `db180092`
(37 commits) while the branch was parked. The pin test is a two-way binding to
the tree, so it went RED on rebase — which is the gate working, not a defect:

```
FAILED test_open_row_cites_still_resolve_to_their_declaration
FAILED test_every_discovered_marker_is_registered
```

Nothing was landed to make those green by relaxation. The test file is
**byte-identical** to the parked branch — zero assertions, thresholds,
exemptions or docstrings were touched. All 138 added lines are in the register,
which is the DATA the test pins.

## What the two failures actually were

**1. `RES-007`'s cite drifted 233 → 320.** The cited declaration is
byte-identical; two re-bind ceremonies (`fcad8e47`, `598868ed`) inserted an
88-line block at `:70` of `cognitive-core-phase-4-review.md`, ABOVE the findings
table. Verified with `git diff -U0 … | grep '^@@'` → `@@ -70 +70,88 @@`. The
artifact is frozen and digest-bound, so the cite is the only thing that CAN
move. Recorded in the row's Note so the next re-bind is expected, not alarming.

**2. Seven new sweep-surface sites, no rows.** COG-5 W2 landed FIRST — this
register was the last branch of the group — so absorption fell to this landing
rather than to the W2 integrator, exactly inverting the order the register's
own "Absorption" section predicted. That section is rewritten as executed
precedent, not a standing to-do.

## The four new rows (7 sites → 4 residuals)

Two pairs are one residual declared twice (mechanism + test-side restatement),
which is why 7 sites produce 4 rows, not 7:

| row | sites | residual |
|---|---|---|
| `RES-012` | `lib_cog5_boundary_fixtures.py:192`, `test_cog5_arena_escape.py:202` | HOME override confines `expanduser` only; a `pwd.getpwuid()` call still learns the real home |
| `RES-013` | `lib_cog5_scoring_fixtures.py:508`, `test_cog5_sim_scoring.py:339` | a self-consistent fabricated replay map still reads as machine custody |
| `RES-014` | `lib_cog5_scoring_fixtures.py:516` | the machine-value law is fixture-tier; a §9.1 pack carries no evidence, so it cannot re-run at W6 |
| `RES-015` | `test_boundary_dynamic_forms.py:71`, `:705` | the import gate's named undetectable set, including DECIDABLE forms not wired (`fromlist`/`level`) |

`RES-012` and `RES-013` are the two the register PREDICTED. `RES-014` and
`RES-015` were not — `RES-015` comes from a different wave entirely (the
widened boundary engine). That is the sweep finding what the prediction missed,
and it is the strongest evidence the TREE→ROWS direction is worth having.

Every Closed/Open/Why-open field was written from the declaring bytes read in
this session, never from the commit messages. Where a declaration states a
number (`RES-015`: 823 arms, 148 failing, all added, at `766a98c3`) it is
attributed to the declaration as its own measurement rather than re-asserted.
No row claims more than its declaration does — `RES-013` in particular keeps
the narrow VALUE/LABEL-channel split and does not absorb the wider claim the
declaration itself records as FALSE-as-written.

## Two arithmetic errors found in the register's own survey

Both pre-existing on the parked branch, both corrected in place with the
correction recorded rather than silently overwritten:

1. **sweep-surface file count 6 → 7** (`a1357829`). The site count (8) was
   right. `egg-export-manifest.txt` carries two of the eight sites and was
   counted once in the sites tally, dropped in the files tally. It now
   reconciles: 11 files total = 7 sweep + 2 operative + 2 frozen. The test
   docstring carries the same "6"; it was NOT edited (prose only, no assertion
   depends on it) — flagged here instead.
2. **`RETIREMENT CONDITION` count 56 → 42.** This was the pre-correction
   `grep -I` undercount. The branch's own second commit fixed it in the survey
   table and MISSED this second home in the known-limits section — the same
   undercount surviving in two places, which is precisely the failure mode the
   register exists to catch.

A `RE-MEASURED AT LANDING` block now carries `db180092` numbers beside the
anchored `a1357829` ones, including two survey verdicts that were correct when
written and are now false about the live tree (`DECLARED RESIDUAL` 0/0 →
6/5, now the most common qualifier; `HONEST SCOPE` 0/0 → 12/4). Rejecting them
as fixed PREFIXES was still right — the word-token regex catches them
unchanged, which is the argument for the token.

## Verification (all re-measured this session, serial, caches purged)

Baseline re-measured on a worktree at `origin/master` `db180092`; never taken
on trust from the brief.

| gate | master baseline | branch |
|---|---|---|
| `pytest cabinet/scripts/tests -q` (CI cmd) | 4534 passed, 28 skipped | **4543 passed, 28 skipped** (Δ +9 = the pin tests) |
| `pytest framework/ -q` | 1 failed, 6489 passed, 25 skipped | 1 failed, 6488 passed, 25–26 skipped |
| `pytest framework/ --collect-only` | 6515 | 6515 |
| `run-golden-evals.sh` | — | **29/29 PASS**, exit 0 |
| `check-layer-separation.sh` | — | baseline=24 allowlist=19 current=43 **new=0** |
| `docs-track-code-sweep.sh` | — | **GREEN** (files=60 findings=0) |
| `ledger-status-parity.sh` | — | **GREEN** (ids=352 md_rows=352 findings=0) |
| A13 parity `gate_cmd` | — | **OK**, 352 ids |
| `cog2-import-gate.py` | — | **OK**, shadow boundary intact |
| `test_no_launcher_hardcode` + `test_clean_room` | — | 24 passed |
| the pin test itself | n/a (absent) | **9 passed** |

The single `framework/` failure is the documented pre-existing red
(`test_retro_shim.py::test_reexports_constants`, out-of-repo screenpipe library
moved to `claude-sonnet-5`); it is identical on the baseline and CI never
collects it.

The 25↔26 skip jitter was chased rather than waved off: `framework/` is
byte-identical between the trees (`git diff --stat origin/master HEAD --
framework/` is empty; the branch adds three files, none under `framework/`),
collection is constant at 6515 both sides, and every captured skip list across
five runs is byte-identical — all 25 are environment probes (redis-cli
unreachable, EventKit helper absent, undecodable dirnames, gitignored
roster.yml). One of those probes flips run to run. Pre-existing, not this
change.

## Coverage proof — not vacuous

Machine-checked after the edits: 15 sweep sites = 13 covered by an open row + 2
legacy exemptions, **0 uncovered**; 0 rows whose anchor fails to appear in its
cited line. `LEGACY_EXEMPT` untouched at 2 (`LEGACY_MAX` unchanged) — no site
was resolved by exempting it.

## Scope declared

Additive only: three files, no existing file modified outside the register the
branch itself introduces. No ledger row added (this is not an execution-state
item), so A13 parity is unchanged and was verified unchanged rather than
assumed. `shared/interfaces/reviews/*.md` is stripped from the egg by the
export manifest (`delete shared/interfaces/reviews/*.md`), so both artifacts
archive out by construction.
