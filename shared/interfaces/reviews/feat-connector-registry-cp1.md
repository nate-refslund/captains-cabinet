# feat/connector-registry — checkpoint 1

**Verdict: PASS** (self-review at the landing boundary; the adversarial pass is
the PR reviewer's, and every number below is a command run this session.)

## What was actually broken, verified before anything was written

`framework/onboarding/journey.py::_entry_grants` read `state["entry_grants"]`.
`git grep -n "entry_grants"` over the whole tree at `6ec81460` returns the
definition, its own docstring, two call sites and three test lines — **no
writer**. So `connectors` was permanently `[]`, `entry_mode()` could never
return `connected`, and the mode the Captain's north-star ruling is *about*
(**connectors present ⇒ sweep, derive, assert with citations**) was
structurally unreachable in production. Two of three advertised modes worked.

Same surface, same shape, two more: `SEED_QUESTION` was rendered into the card
body with no action able to carry an answer (`next_actions` was
`[propose_window]` and the dashboard rendered `entry.questions` as a read-only
`<ul>`), and `seed_probes()` returned typed probes that **no code anywhere in
the tree executed** — `entry_plan(..., seed=)` was never passed a seed by any
caller.

**One part of the brief was STALE and is corrected here.** The alphabetical
walk and the unearned "did not find a broken documented command" were closed by
the three-entry-modes unit that landed as PR #240. Re-verified by EXECUTION,
not by reading: on a 32-file slice at `MAX_FILES=3`, master reads
`zrepo/package.json, zdocs/README.md, aaa-notes/note-000.md` — relevance order,
recovering the cross-directory join an alphabetical walk drops — and reports
`{eligible_files: 32, examined_files: 3, complete: False, ordering: relevance}`.

**The half that was still open, and is closed here:** `detectors` was a
hardcoded `["software_command_drift", "conflicting_commitment",
"attention_marker"]`. `_command_drift` returns nothing at all without a
`package.json` in the window, so every dividend from a window without one
advertised a **structurally disabled sensor as a live one**. Measured on the
same two-source slice: master claims `software_command_drift` ran and returns
the operator's own handwriting with one citation; this branch reports
`detectors_skipped: [{software_command_drift, no_package_json_in_window}]` and
returns a two-source finding with two citations.

## The unit

| Piece | Where | Why there |
|---|---|---|
| Connector registry (`probe_connectors`, `_probe_repo`, `_probe_web`, `_probe_exports`) | `framework/onboarding/research.py` | the altitude gate named this module as the connector inventory that "exists, **wrong subject**" — it reads the *cabinet's* declared MCP servers, never the operator's estate. Repointing it is a fix; a new module beside it would be an expansion. **Zero new modules** — no bijection class moved. |
| The writer (`_entry_registry`, `_with_registry`), wired into `_commit` and `snapshot` | `journey.py` | the state and the lock live here |
| `answer_seed` action, `input: "seed"` on the option, `_execute_probes` | `journey.py` | reading under a ratified Charter is this module's whole job |
| `untracked_commitment` join + `_tracker_rows` + `_detector_roster` | `journey.py` | every dividend detector lives beside its siblings |
| Seed textarea, probe-result block, `answer_seed` in the action allowlist, typed `seed` Telegram command | `cabinet/dashboard/**` | a field the core asks for and no surface renders is still a dead end |

**Probed, never declared** is the load-bearing property. A repo counts only when
`.git/HEAD` **resolves** to an object id (loose ref or `packed-refs`); a tracker
export counts only when its rows parsed **and the file is still there at probe
time**; `web` is the egress ceiling and fails closed on an absent or unparseable
`egress.yml`. Every probe that did not answer carries its reason onto the card,
so "nothing is connected" is never indistinguishable from "I never looked".

**Bounded by the refuted experiment.** Of its four findings, ONE needed more
than one FILE and ZERO needed more than one SYSTEM; two of three existing
detectors are reproduced exactly by one `git grep`. So what lands is **one**
join — two parsers and a comparison, no index, no vault, no ingest engine — and
its named consumer is the connected mode's own card. It cites **both** sides:
without the export citation, "no open row accounts for this" is a negative
nobody can check.

## Two defects my own arms found in my own code, before review

1. `tracker_exports` was persisted at ratification and never re-checked, so a
   **deleted** export kept granting `connected` forever — a declaration wearing
   a probe's clothes, the exact failure the design is against. `_probe_exports`
   now re-stats the file every probe (`export_missing`).
2. `_discovery_note` took the entry plan, and `dividend_ready` carries no plan —
   so an operator who answered the seed question at that stage was shown a card
   that said nothing about it. It now takes the executed block, so every stage
   renders it.

## One test INVERTED, deliberately, not weakened

`test_the_welcome_card_is_no_longer_a_single_locked_door` pinned the option list
at exactly `["propose_window"]`. The ruling makes that literally wrong — the
card prints the seed question, and a printed question with no way to answer it
is the dead end the surface exists to abolish. It now pins
`["propose_window", "answer_seed"]` **and** that the answering option declares
`input: "seed"`, and still fails on any unrelated option appearing there.

## Verification — every command run this session

- **28 new Python arms**; against a worktree at master `6ec81460`, **27 fail**
  and 1 passes. The one that passes is the inverse arm (the connected mode
  offers no seed field), which is a guard against over-adding, not a
  new-behaviour sensor.
- **The UI arm is bound to the live artifact**: deleting *only* the seed-form
  JSX from the component (leaving its `useState` so the harness's hook-order
  assertion stays quiet) turns `renders an input for the seed question` red
  while every other card test stays green.
- `framework` serial: **7369 passed**, 26 skipped, 1 failed — only
  `test_retro_shim.py::test_reexports_constants`, proven pre-existing by
  running it at `6ec81460` (a third-party model-id pin drifted on this machine;
  CI lacks the lib).
- `cabinet/scripts/tests` serial: **4992 passed**, 34 skipped.
- dashboard `tsc --noEmit` clean; `vitest run` **2351 passed**, 1 skipped.
- `check-layer-separation.sh`: `new=0` (a first draft of the test spelled the
  instance path and correctly tripped it; the fixture now locates the file via
  the module's own constant, adding no debt).
- `cognitive-architecture-census.py`: **PASS**. `framework_production_modules`
  unchanged at 247. `framework_production_noncomment_lines` 71805 → **72371**
  (+566), paid as a `temporary_allowances` row with the closed key set. No
  bijection class touched, so nothing needed a visible `maximum` raise.
- Contract edit is inside the COG-4 §15 frozen digest scope, so the
  `Reviewed-Scope-Digest` re-bind rides in this same commit.

## What this unit does NOT claim

The join matches by shared wording, so a tracker row phrased differently is a
miss — stated in the finding's own summary rather than left for the operator to
discover. The web half of discovery is never executed here (this module holds no
egress) and is reported as `deferred` with its reason; `complete` is `false`
whenever anything deferred. And `test_act_bytestream.py`'s live arm allows
divergence anywhere under `instance/onboarding/v2/`, which is where the new
state keys land — so that arm absorbs this diff rather than gating it; the
gating for this unit is the 28 arms above.
