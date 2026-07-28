# FW-019 checkpoint review — feat/onboarding-ordering-inversion cp2

Reviewed-Scope-Digest: d4de7949e195fbcb72d08e072f4d24aaa93633dccb9246a6d0ce829d0a89087c

Reconciliation with the SIBLING source-ownership landing that reached master
while this branch was in flight (`framework/authority/ownership.py`,
`docs/source-ownership-and-authority.md`, ownership bound into the Charter hash
in `framework/onboarding/journey.py`).

## Why this is a correction, not a tidy-up

Both units were adjudicated out of the same direction gate, and both needed a
per-source ownership class. Landing them side by side would have left the tree
with **two vocabularies, two per-source record shapes and two answers to one
question** — "whose data is this?" — which is the concurrent-writer failure
where another session fixes the same thing differently and your version becomes
*wrong* rather than redundant.

## What changed in `framework/onboarding/estate.py`

| Was (this branch, pre-merge) | Is |
|---|---|
| local `OWNERSHIP_CLASSES` tuple incl. `unclassified` | imports the closed set from `framework.authority.ownership`; `unclassified` demoted to `LEGACY_UNCLASSIFIED`, the marker for a journey persisted before the ingest ceiling existed |
| `derive_estate(..., ownership=...)` parameter — a second place to answer | parameter DELETED; the class is read off `charter.payload.source.ownership`, i.e. the value already inside the hash the Captain approved |
| hand-rolled source record (`root`, `entries`, `egress: none`, `refusals` as a list) | rides `access_record(...)` — `source_root`, `entry_count`, `refusals` + `refusals_total`, `retention`, `attestation_limit` — with only estate-specific fields added |
| `owned = ownership == "self"` | `writes_permitted(class)`, the same function the task adapters route through |

`egress: none` was dropped deliberately: it was **recorded intent with no
enforcement behind it**, and the merged plane has a real `egress_disposition`.
Carrying a field that looks like a control but is not is worse than not
carrying it.

## Evidence

* `pytest framework/onboarding cabinet/scripts/tests/test_generate_instance.py
  cabinet/scripts/tests/test_formation_script.py` — 438 passed, 1 skipped.
* New arm `test_an_employer_source_is_carried_and_proposes_read_only` drives
  the REAL journey with `ownership: employer` end to end and asserts every
  derived lane is proposed read-only. The previous parametrized arms kept their
  discrimination (all four classes still asserted).
* The fixtures now declare a class and a basis because the ingest ceiling
  **refuses** an unclassified source — the tests changed because the product
  changed, not to make a red go away.
* census PASS at `246 <= 246` modules / `71080 <= 71080` lines (the allowance
  re-measured from 617 to 646 and says why in its own reason field);
  layer-separation OK; import gate OK; docs-track-code sweep GREEN.
