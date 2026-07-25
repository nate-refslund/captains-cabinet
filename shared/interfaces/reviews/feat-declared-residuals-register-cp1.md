# Review — feat/declared-residuals-register cp1 (declared residuals register + pin test)

**Batch:** two NEW files plus this artifact, one unit commit off master
`a1357829`. FW-019 applies (818 added lines, zero modified lines). Purely
ADDITIVE: no existing file is touched — verified with
`git status --porcelain` and `git diff --stat` (three additions, nothing else).

## Files

* `docs/plans/declared-residuals-register.md` — the register. 11 rows, each
  carrying phase · status · what is CLOSED · what stays OPEN · why it is not
  closed now · where it is declared (`file:line`) · an exact-substring anchor ·
  the retirement condition (what must land AND what must be removed in the same
  commit). Plus the marker survey, the home justification, the sweep-surface
  definition, the COG-5 W2 absorption contract, the legacy-exemption note, and
  an explicit "known limits" section.
* `cabinet/scripts/tests/test_declared_residuals_register.py` — 9 tests binding
  the register to the tree in BOTH directions. ~0.9s, no network, no clock, one
  optional `git ls-files`.

## Home — why `docs/plans/`, checked against bytes not convention-guessing

`shared/interfaces/` is fail-closed at export: `t_interfaces_header_only`
(`cabinet/scripts/egg-export.sh:184-195`) `verify_fail`s on any file outside a
four-name allowlist, so the register there would break packaging AND force an
edit to `cabinet/scripts/egg-export-manifest.txt` — which is inside the frozen
COG-4 review digest scope. `docs/plans/` needs no manifest change at all:
`t_plans_archive` (`:198-210`) keeps three named specs and `rm -rf`s the rest,
so a new file archives out of the egg by construction (R145).

## Marker convention — the survey, and why nothing was invented

Case-sensitive counts over the whole tree at `a1357829`:
`DECLARED RESIDUAL` 0 · `HONEST SCOPE` 0 · `known limitation`/`KNOWN LIMITATION`
0 · uppercase `RESIDUAL` word token **8 sites / 6 files** · `RETIREMENT
CONDITION` 56 · `PARKED` markers 4 · lowercase `residual` 208 / 88 files.

The three zero-count candidates were rejected outright. The adopted marker is
the uppercase word token, which already appears in three qualifier variants
(bare / `HONEST` / `KNOWN`) — so the convention is the TOKEN, not a prefix. The
retirement field takes its name from the repo's existing 56-use idiom. The
lookarounds `(?<![A-Za-z0-9_])RESIDUALS?(?![A-Za-z0-9_])` are load-bearing:
without them `_TEMPORARY_RESIDUALS` (`framework/tests/test_no_launcher_hardcode.py`)
and `RESIDUAL_NOTE` (`cabinet/scripts/evidence-tamper-drill.py`) — mechanisms,
not declarations — would be swept as residuals.

Lowercase `residual` was rejected as a marker on evidence, not taste: of 208
uses, the overwhelming majority describe channels already CLOSED
(`framework/evidence_anchor.py:7` "closes that documented residual") or
threat-model facts explicitly "accepted and stated"
(`framework/evidence/signing.py:43`). Keying on it would produce a register that
is 95% noise. The register's "known limits" section names this gap, names the
clearest unregistered instance (`cabinet/mcp-server/server.py:537`), and states
the one-commit remediation.

## What the gate actually enforces

1. `test_register_parses_and_is_not_empty` — strict grammar. Any h3 that is not
   a row heading, any unknown/duplicate/empty field, any missing required
   field, any bad status, zero rows, or all-rows-retired ⇒ RED.
2. `test_every_row_carries_a_retirement_condition` — non-empty and ≥40 chars, so
   "TBD" cannot pass.
3. `test_open_row_cites_still_resolve_to_their_declaration` — ROWS→TREE: the
   cited `file:line` must exist and still contain the row's anchor.
4. `test_code_cites_sit_on_a_house_marker` — a declaration inside the sweep
   surface must carry the token, which is what keeps direction (5) enforceable.
5. `test_every_discovered_marker_is_registered` — TREE→ROWS: every swept marker
   must be a registered cite or a pinned legacy exemption.
6. `test_registered_code_cites_are_discovered_by_the_sweep` — the two directions
   must agree on coordinates; catches a surface-filter hole.
7. `test_retired_rows_have_no_live_declaration` — retiring a row requires the
   declaration to actually leave the tree.
8. `test_legacy_exemptions_are_real_and_shrink_only` — the escape hatch is
   itself pinned (must still be a marker line, must still read its recorded
   text, may not overlap a row, `LEGACY_MAX` never rises).
9. `test_sweep_modes_agree_where_they_can` — the gitless filesystem fallback
   must cover at least what the tracked-file mode does.

## Anti-vacuity — five proofs run, each reverted, green re-confirmed after each

| probe | result |
|---|---|
| delete RES-006's row while `verifier.py:61` still declares it | RED (5) names the orphaned site |
| plant `# RESIDUAL: …` at `framework/hygiene/apoptosis.py:1` | RED (5) names the unregistered declaration |
| gut every row, keep the prose | RED — 8 of 9 tests, "declares ZERO rows" leads |
| insert a line above `verifier.py:61` so the declaration drifts to `:62` | RED (3)(4)(5)(6) — anchor missed, marker missed, orphan found, coordinate disagreement |
| register absent + no `ARCHIVED-NOTE.md` | RED — "lost its register, not an egg export cut" |
| register absent + `ARCHIVED-NOTE.md` present | SKIP LOUD, the intended export-cut arm |

The sweep additionally refuses to be vacuous from the inside: it asserts
`files_read > 0` and `sites > 0`, so a broken roots filter or a broken pattern
is RED rather than silently green.

## Deliberate exclusions, each with a reason

* `shared/interfaces/reviews/` is out of the SWEEP (rows may still cite it):
  frozen append-only review artifacts, and the COG-4 one is digest-bound by
  `cognitive-phase4-review-scope.py` — its bytes may not be reworded to satisfy
  a linter.
* The test self-excludes (`SELF_REL`) — the file defining the marker cannot be
  its own subject. Same idiom `test_no_launcher_hardcode.py` uses for its
  pattern list.
* `docs/` is not swept — narrative prose. Rows cite it; the gate does not
  police it.
* The 56 `RETIREMENT CONDITION` vacuity guards are NOT registered: each already
  trips RED when its target lands, so it cannot rot silently. Registering them
  would add churn and collide with in-flight corpus surgery for zero added
  guarantee.
* The two `RESIDUAL SCRUB` lines in `egg-export-manifest.txt` are exempted, not
  registered — they describe scrub rules already executed, and that file is
  inside the frozen COG-4 digest scope so it cannot be reworded.

## Frozen-review scope — checked, NOT touched

`cabinet/scripts/cognitive-phase4-review-scope.py` `EXPECTED_SCOPE` was read in
full first. It names individual files plus five DIR-wholesale entries
(`framework/projection`, `framework/scheduler`, `framework/organs`,
`cabinet/config/organs`, `cabinet/scripts/tests/fixtures/cog4`). Neither new
path is a named entry nor sits under a bound dir, and `docs/plans` and
`cabinet/scripts/tests` are NOT dir entries. The digest is computed over
`git ls-tree -r HEAD -- <scope>`, so files outside scope cannot move it. No
re-bind ceremony is triggered.

## Gates

`cabinet/scripts/tests` 3399→3408 passed, 12 skipped (delta = exactly the 9 new
tests, zero disturbed) · `cog2-import-gate.py` rc0 · `check-layer-separation.sh`
rc0, unchanged 24/19/43/0/0 · census PASS with all ten budgets byte-identical
(the new file is under `cabinet/`, not `framework/`, so no production-module or
line budget moves) · `ledger-status-parity.sh` (A13) OK · `test_egg_export.py`
green.

## Residual of this unit, stated

The gate binds `RESIDUAL`-token declarations in the sweep surface. It cannot
force a future author to use the token instead of prose — that is judgment, and
the register says so in "known limits" rather than pretending otherwise. What it
does guarantee is that once the token is used, the row is mandatory; and that
every row already here dies loudly rather than rotting.

**Provenance:** authored per the 2026-07-07 full-autonomy grant.
