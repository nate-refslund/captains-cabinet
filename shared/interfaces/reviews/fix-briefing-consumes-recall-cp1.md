# fix/briefing-consumes-recall — checkpoint 1

**Unit:** the first briefing reads what recall already holds; the recall scope
is declared rather than defaulted; altitude reaches the WHAT line.
**Trigger:** a MEASURED hatch scored 1 of 3 ("read it, no value") while recall
on the same box was live and unread. Adjudication of record:
`docs/plans/briefing-consumes-recall-2026-07-28.md`.

Reviewed-Scope-Digest: 4c60ef48f5327099f3ceb5700bb3a9fe96220678c2770abe4c550f31c96ffaf3

## What changed and why

| File | Change | Why it is the right place |
|---|---|---|
| `framework/onboarding/genesis.py` | `recall_probes` / `probe_recall` / `recall_state` / `_subject_what` / `_quote_of` / `_join_terms`; `recall=` threaded through the card path; `genesis-recall` intake item | genesis is where the first briefing's cards are derived; the probe runs in `run_genesis_proposal` (the orchestration layer that already does I/O for the estate) so `propose_outcome_cards` stays PURE |
| `framework/sources/local.py` | `resolve_root()` → `Optional[Path]` (no `<root>/vault` default); `binding_status()` | the default WAS the false positive: `vault/README.md` and `vault/architecture.md` are tracked, so an undeclared personal box answered out of the framework's own docs with `available() True` |
| `cabinet/scripts/generate-instance.py` | `sources.notes_root` answers key + validation; `render_sources_personal(None)` emits the key commented out | the answers file had NO way to declare the operator's folder; `local_root` was pinned to `ORG_VAULT_DEFAULT` |
| `cabinet/config/cognitive-architecture-contract.yml` | `temporary_allowances` row, `+456` on `framework_production_noncomment_lines` | measured growth, paid visibly; `framework_production_modules` unchanged at 247 (zero new modules) |

## Falsification — every new arm fails against pre-change code

Ran the new tests against `git checkout HEAD -- <the three production files>`
(tests kept, production reverted):

```
18 failed, 70 passed     framework/onboarding/tests/test_genesis.py
                         framework/sources/tests/test_local_source.py
 8 failed, 15 passed     cabinet/scripts/tests/test_generate_instance.py
                         cabinet/scripts/tests/test_cleanroom_org_instance.py  (-k personal/notes_root/sources)
```

The defect itself was reproduced on master's bytes, not argued:

```
MASTER resolve_root -> <root>/vault
MASTER available    -> True
MASTER search hits  -> ['README.md#Where a document lives (the placement one-pager)', …,
                        'architecture.md#Architecture — <product>']
```

Two arms are regression GUARDS rather than falsifiers and are labelled as such
in their docstrings (`test_read_note_refuses_when_no_root_was_granted`,
`test_recall_item_absent_on_a_bare_root`) — both passed pre-change, and both
pin behaviour a future edit could break.

## Degenerate ends, checked

- `recall=None`, a seam that raises, a seam reporting `available() False`, and a
  seam with an empty corpus all derive **byte-identical** cards to the
  pre-recall derivation (`test_no_recall_derives_byte_identical_cards`), and
  carry **no** `recall_refs` key at all — an empty citation list is still a
  citation key.
- Zero declarations ⇒ zero probes (`test_probes_are_derived_never_invented`).
- Bare root ⇒ zero intake items, including no recall claim.
- `_FakeSource` is deliberately NOT a "return nothing" stub: a stub that
  answered nothing would make every arm pass while asserting the defect.

## What the REAL clean-room hatch found that this suite did not (+7 lines)

`hatch.sh --defaults --clean-room` (org flavor, from a scratch export) rendered:

> 🧠 Recall: live — framework.sources.org:OrgSource answered 0 hit(s) across 0
> of 1 subject(s) (First Lane). — *recall answered, but NO card above derives
> from it: the proposals on file were written before this run.*

That blamed an **ordering** problem for an **empty** one, and sent the operator
to re-run genesis for a result that cannot change. Nothing was cited because
there was nothing to cite. Three live sub-states are now three sentences, and
`test_a_live_but_empty_recall_is_not_reported_as_a_stale_ordering` is the arm
that would have caught it — verified failing against the pre-fix bytes. This is
the same unearned-claim class the estate provenance item was already corrected
for, reappearing in the surface built to prevent it.

## What the hostile pass found in its own new code (fixed here, +3 lines)

- The provenance card's `why` attributed the **undeclared-folder** cause to
  every non-live state, including "not consulted" and "could not be reached".
  It is now state-neutral about the cause and specific about why silence is the
  thing that must not happen.
- A probe that failed **mid-sweep** left `available` True, so the live line
  reported a partial answer as a complete one. The failure is now named on the
  card.
- `import re` was landing mid-file in the test module; hoisted.

## Known cost, stated rather than discovered later

`genesis_intake_items` re-probes rather than receiving the
`run_genesis_proposal` result (its caller, `run_briefing._run_local_render`,
passes no recall). On a local folder this is free — `get_source()` caches the
adapter and the adapter caches its corpus. On a CONFIGURED org box it is up to
four extra `memory.sh` spawns at hatch time. Bounded by `_MAX_RECALL_PROBES`,
and `CABINET_GENESIS_RECALL=0` turns it off.

## Blast radius considered

- **Hermeticity:** `probe_recall` is ROOT-GUARDED. `get_source()` resolves from
  `CABINET_ROOT`, so a scratch/test root does not consult the live checkout's
  binding (`test_recall_is_not_probed_for_a_foreign_root`).
- **Hatch latency:** a CONFIGURED org box's `search()` shells to `memory.sh`.
  `OrgSource.available()` is an env-name check only, so an unconfigured box
  never spawns anything; `CABINET_GENESIS_RECALL=0` is the kill switch.
- **Untrusted content:** quotes are the operator's own notes, flattened,
  non-printables stripped, capped at 200 chars, and they ride only the LOCAL
  first-briefing file — no card surface, no send path (`--local-render` never
  touches Redis or channel.py).
- **Digest scope:** `cabinet/config/cognitive-architecture-contract.yml` is
  inside the frozen COG-4 §15 scope; the `Reviewed-Scope-Digest` re-bind rides
  the same commit. The three edited framework/cabinet source files are NOT in
  `EXPECTED_SCOPE`.

## Batteries (this session, re-measured against master)

| Battery | Master baseline | This branch |
|---|---|---|
| `pytest framework/ -q` | 1 failed*, 7341 passed | 1 failed*, 7360 passed |
| `pytest cabinet/scripts/tests -q` | 4992 passed, 34 skipped | 4998 passed, 34 skipped |
| `check-layer-separation.sh` | OK | OK (new=0) |
| `cog2-import-gate.py` | OK | OK |
| `cognitive-architecture-census.py` | PASS | PASS (72261 <= 72261, zero headroom kept) |

\* `framework/fidelity/tests/test_retro_shim.py::test_reexports_constants` — a
LOCAL-only red on this machine (a third-party lib drifted its model id past a
hardcoded pin); CI lacks the lib and is green. Identical in both columns.

## Proven by hatching, not asserted

`generate-instance.py --force` → `--print-preset` (the hatch's own resolution)
→ `load-preset.sh` → `first-briefing.sh --local`, twice: once with
`sources.notes_root` pointed at a three-note fixture (card cites three distinct
files, newest first, with derived dates and shared terms), once with the key
absent (`🧠 Recall: bound to NOTHING …` plus the exact fix). Scored **2 of 3**,
honestly — rung 3 is "changed what I did next", which only the operator can
report, and claiming it would be the unfounded claim that produced the 1.
