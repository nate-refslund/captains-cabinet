# feat/expansions-schema — cp1

Branch: `feat/expansions-schema`
Date: 2026-07-27
Verdict: PASS

## What landed

The expansion registry, as ordered by the 2026-07-27 two-model direction gate
(Fable 5 arm A + Opus 5 arm B, blind, own clones). **Widened the detector that
already exists; built no new plane.** Zero new modules, zero new services, zero
new schedules, zero new deciders, and zero growth against any counted budget —
every file touched sits outside the framework module/line budgets, so no
`temporary_allowances` row was needed or added.

| Surface | Change |
|---|---|
| `cabinet/config/cognitive-architecture-contract.yml` | new closed-key `expansions:` list beside `temporary_allowances:` (empty at landing) |
| `cabinet/config/architecture-baseline-sets.yml` | NEW — the per-class member sets surplus is measured against |
| `cabinet/scripts/cognitive-architecture-census.py` | bijection enforcement + row schema + baseline loader |
| `cabinet/scripts/tests/test_cognitive_architecture_census.py` | permanent both-ways calibration arms (ships in the egg) |
| `cabinet/scripts/tests/test_expansion_adjudication_binding.py` | NEW — source-side adjudication binding (egg-excluded) |
| `cabinet/scripts/egg-export-manifest.txt` + `tests/test_egg_export.py` | ship the baseline sets, exclude the source-side binder |
| `docs/cognitive-core-foundry.md` | the `reuse\|extend\|compose\|retire\|new` disposition is now machine-forced |

## The law

Per class in `BIJECTION_CLASSES`:

    observed - baseline  ==  {row.member for row in expansions}

exactly and disjointly. Three distinct lies, three distinct reds: an
unregistered net-new member; a row naming a member that is not observed (the
stale copy-paste); a row naming a baseline member (the laundering edit). Two
rows for one member are refused at load, as is any row that is under- or
over-specified.

**Why an allowance is not enough** — the crux, verified rather than asserted. An
allowance's schema asks only `phase/budget/additional/reason/owner/sunset/
deletion_gate`: declaration, never adjudication. Measured on pre-change master
`3a710183`: plant a net-new event type, lift the two count ceilings it consumes,
add nothing else — `inspect_repository` returned `ok = True`, `failures = []`.
The same tree post-change returns `ok = False` with
`unregistered set member [census_fixture_unadjudicated_event]`. An allowance
cannot buy a net-new set member; only an expansion row can.

**Nothing here checks that a file exists**, because `touch` passes that — the
counterexample both gate arms named independently was FW-019, whose check
matches any filename containing the branch slug and never reads a byte. A
bijection cannot be faked at all. The two fields that do reach the tree reach it
for content, not presence: `merge_refuted` must OPEN with a `path::symbol`
anchor whose file exists and whose symbol occurs in it (both near-misses this
program caught were answerable by grep against a named symbol), and `consumer`
must resolve to an existing path or a declared `cabinet/services.yml` name and
may be neither the member itself nor the file that declares it.

## Attack surface, and what remains open

- **Laundering by editing the baseline instead of writing a row.** Closed in
  combination, not alone: adding a member to the baseline changes no count, and
  every class is pinned at `observed == max` with zero headroom, so the census
  still REDs until the maximum is raised too. That is two deliberate, visible
  hand edits in the contract, neither forgeable by a script. The baseline ships
  with **no regenerator** for exactly this reason.
- **Line-mass inside an existing module** is a mass, not a set, and stays
  invisible to bijection. Stated in the census docstring and in the baseline
  file header rather than left for a reader to discover.
- **The baseline members were never adjudicated by this gate.** They are the
  tree as it stood at landing. The header says so; the registry claims nothing
  about anything that predates it.
- **`adjudication` is shape-checked in the census, content-bound in a
  source-side test.** The census ships and runs in a gitless hatch, but
  `docs/plans` and `docs/proposals` archive out of the egg — a shipped content
  check would red a hatched cabinet over a document the export removed, whose
  only repair is to disable the check. The binder is therefore egg-excluded by
  the same delete + expect-absent idiom the phase rollback tests use, and it is
  never vacuous: it exercises a passing document, an absent one, a `touch`ed
  empty one and a stale one on every run, whatever the live registry holds.

## Both-ways evidence

- Pre-change master `3a710183`, unadjudicated member, ceilings lifted:
  `ok = True` (the hole). Post-change: `ok = False`, naming the member.
- The new arms run against pre-change code: **50 failed, 29 passed** — the 29
  being the pre-existing arms, unchanged.
- Positive control: the same planted tree WITH one well-formed row is GREEN, so
  the registry is satisfiable and not a blanket refusal. The in-tree model is the
  adapter-conformance calibration anchor (reference passes everything, template
  fails everything).
- `BIJECTION_CLASSES` is pinned by its own arm: a silent narrowing would disable
  the registry for a whole class while every other arm stayed green.
- Both count ceilings the planted member consumes are lifted in every arm, so
  the only thing that can red those trees is the registry — never a
  zero-headroom ratchet standing in for a check that is not running.

## Sibling landing

`cabinet/config/cognitive-architecture-contract.yml`,
`cabinet/scripts/egg-export-manifest.txt` and
`cabinet/scripts/tests/test_egg_export.py` sit inside the frozen COG-4 §15
review scope. The `Reviewed-Scope-Digest` re-bind rides in the SAME commit —
PR #210 skipped that step and left the phase-4 exit gate red on master.
