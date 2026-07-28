# FW-019 checkpoint review — feat/onboarding-ordering-inversion cp1

Reviewed-Scope-Digest: 3a2c3d9c3efb7296c3585b7fd5853e508fc903b9a9b3c17b08ea8e583f5a3df2

Unit: the onboarding ORDERING INVERSION — make the cabinet READ the operator's
world instead of interviewing them about it. Design of record:
`docs/plans/onboarding-ordering-inversion-2026-07-26.md` (direction gate,
Fable 5 + Opus 5 run independently and blind, adjudicated in writing).

## 1. What changed, and what each change is load-bearing for

| Surface | Change | Why it is not decoration |
|---|---|---|
| `framework/onboarding/estate.py` (new) | the derived-estate contract | one shared schema with one producer (formation) and two consumers (genesis, generate-instance) |
| `framework/onboarding/formation.py` | `DISCOVERY_DONE` derives instead of writing an IOU; undo supersedes its outputs | the estate has to be PRODUCED by something scheduled, or it is another dead substrate |
| `framework/onboarding/genesis.py` | estate is a first-class card input; altitude reshapes the proof; leftover-question card | the 1/3 briefing was a COMPOSITION failure — cards were derived from a placeholder lane |
| `cabinet/scripts/generate-instance.py` | `lanes: []` accepted on a usable estate; `mission.altitude` validated; `resolve_preset` + `--print-preset`; `--defaults --altitude` | the absolute lane refusal was the hard stop that made the Captain's order impossible |
| `cabinet/scripts/hatch.sh` | `--altitude`; preset selection asks the generator | altitude must reach the file that is actually written, not a printed suggestion |
| `cabinet/scripts/formation.sh` | prose + per-stage status now honest | a blanket "every stage is a stub" line became false |
| `framework/frontdoor/run_briefing.py` | docstring only | "a genesis instance has no estate to gather" became literally false |
| `cabinet/config/cognitive-architecture-contract.yml` | 2 temporary_allowances rows + 1 expansions row | zero-headroom budgets; the module is registered with its adjudication, consumer and merge refutation |

## 2. Attacks run against this change, and what they found

* **Does the derivation secretly read the operator's folder?** Deleted the
  granted source and re-derived: byte-identical document
  (`test_derivation_performs_no_new_read_of_the_source`). No new read.
* **Can a file body leak into the estate?** Planted a distinctive token in a
  scanned file and asserted its absence from the serialized document.
* **Is the `lanes: []` gate a rubber stamp?** Four refusal arms — absent,
  wrong schema, no `derived_at`, wrong deployment — plus the positive arm that
  an EMPTY-but-real estate passes, because "I looked and found nothing" is a
  legitimate lane-less state and a fabricated lane is the failure being
  removed.
* **Degenerate end of the lane-less path?** No `active-project.txt` is written
  (a placeholder slug would be a value pretending to be an answer), the roster
  is Chair-only, and no context/project/agent file is invented.
* **Can a ratified proposal point a write-capable adapter at someone else's
  estate?** No: only a source classified `ownership: self` yields a
  write-capable proposal; everything else proposes `task_system: none` and no
  repos (parametrized over all four ownership classes).
* **Does undo actually undo?** The derived estate and the lanes proposal live
  outside the run dir, so they are supersede-archived with the run — and a
  later run's estate is never dragged away by an older run's undo.
* **Is altitude carried or consumed?** Two arms: `resolve_preset` differs by
  rung (and the CLI prints two different slugs for the same answers), and the
  card proof line differs by rung. The forward-compat pin that read "mission
  changes NOTHING" is SPLIT so nobody can take the inert half for the whole.
* **Does the propose-only surface stay inert?** The compiler filename gate is
  unchanged, the generator still takes lanes ONLY from the answers file, and
  the formation script test now pins the EXACT set of files a run may write
  under `instance/config/` rather than asserting the directory does not exist.

## 3. Tests inverted rather than weakened (each stated in the commit message)

| Test | Was | Is | Why the old assertion is literally wrong |
|---|---|---|---|
| `test_genesis.py::test_card_count_band_is_two_to_four` | 0 lanes → 2 cards | 0 lanes → 3 | the two were pure org ceremony; a cabinet told nothing now asks the leftover questions |
| `test_formation.py::test_stage_stub_writes_honest_iou_and_journals` | subject `DISCOVERY_DONE` | subject `INGEST_DONE` | the IOU contract is unchanged; discovery is no longer a stub |
| `test_formation.py::test_full_run_stamps_all_stages_in_order` | 5 IOU artifacts | 4 IOU + `discovery.yml` | same |
| `test_formation_script.py::test_full_run_...propose_only` | `instance/config` must not exist | exact set == `{lanes-proposed.yml}` + `outcomes.yml` absent | the invariant is compiler-readability, and it is now asserted by name |
| `test_cognitive_architecture_census.py::test_live_registry_carries_no_unregistered_surplus` | surplus is EMPTY | surplus == the registered members | "empty" and "complete" were indistinguishable only while `expansions: []` |
| `test_cognitive_architecture_census.py::_rewrite_contract` | replaced `expansions` wholesale | preserves live rows, appends synthetic | dropping a real row leaves its real member unregistered in the fixture tree |

Nothing was skipped, xfailed, or relaxed. Every new arm was executed against
pre-change code in a separate pristine clone: 18 genesis/formation arms and 33
generator arms FAIL there, and the arms that pass there are the ones whose
subject is deliberately unchanged behaviour (absent altitude, high altitude,
declared lanes).

## 4. Known limits, stated rather than implied

* No egress gate keys on the ownership class yet; the class is recorded and
  the question is forced. The framework cannot verify an attestation's truth.
* No ingest engine and no new connector: gated on the employee-slice
  experiment per the direction gate's sequencing law.
* No shipped preset is shaped for a low-altitude operator; `developer` is the
  closest fit and the generator says so.
