# Checkpoint review — feat/source-ownership-class (cp1)

Reviewed-Scope-Digest: 8f4978c90e5bc3f7d07997f03dac4ffe0d1d4b8ea59cfe23082374ad17003513

Verdict: PASS

## What landed

A per-source ownership plane (`self | employer | third_party` + an authority
basis), refusal-on-unclassified in both directions, structural read-only for any
non-owned source, six sensitivity classes that refuse by name, a per-source
access record that survives the read it describes, and an egress verdict on the
one card every surface renders. Direction of record: the 2026-07-26 altitude
gate (two blind arms), item 4 of its resulting order plus the ACTIVE hazard it
named in `task_adapters/base.py`.

## What I attacked, and what it cost

**The word "structural."** The claim is only worth making if the write path
cannot be re-opened at runtime. Attacked three ways, each now a pinned arm:
`writes_permitted` takes no override parameter (asserted against the signature);
`ObserveOnlyTaskAdapter` is a different TYPE handed out by the factory, and its
push/delete/link never reach `self.inner` (asserted against the method bodies);
and re-classifying the live object does not help, because re-wrapping an owned
source is itself refused. The first draft of the test was defeated by my own
docstring — it scanned the class source for `read_only` and matched the
sentence explaining what the class is NOT. Fixed by scanning the code with the
docstring removed, which is the version that would catch a real regression.

**The degenerate end, everywhere.** `screen_egress([])` reports `screened: 0`
rather than an empty allow-list a caller could read as approval; an item with no
`ownership` key is REFUSED, not passed, because that is the state every row
written before this plane existed is in; `sensitivity_classes("")` returns `()`
and `sensitivity_refusal("")` returns `None`; a manifest seeds every sensitivity
class at zero so an untouched class reads as "nothing matched" rather than
"never checked"; and a journey state persisted without a class renders as
`per_item_approval`, the strictest case, not the loosest.

**Two Captain-facing promises collided and both are kept.** The direction says
the sweep record must SURVIVE the purge and must carry the source root. The
existing purge contract promises no source path is retained, pinned by
`test_purge_requires_typed_confirmation_and_removes_sensitive_history`. Rather
than weaken either, the purge now REDACTS the root to its sha256 and stamps the
receipt: the audit trail survives, the path does not. The pre-existing test
passes unchanged; two new arms pin both halves.

**Egress is graded, not binary, and that is a calibration I could get wrong.**
`employer` content moves with a record; only `third_party` waits for per-item
approval. Reasoning is in the module and the doc: refusing to show an employee
their own view of their employer's repo would be safety theatre that costs the
whole feature at that altitude, while a client's words leaving on a channel the
client never agreed to is the exposure the adjudication actually names. A
future session that disagrees should argue against that reasoning, not against a
missing rationale.

## Assertions inverted by the ruling, each stated rather than deleted

1. `test_act_bytestream.py` — byte-identity between the pre-migration journey
   and the live one. Now literally impossible: ownership rides inside the
   Charter payload. NARROWED, not deleted — the recording SKELETON (which
   events, in what order, for which act, by which actor, with which status) must
   still match exactly, that being the actual R-8 claim; file sets must match;
   every diverging path must sit in an enumerated set; the divergence must be
   non-empty and be exactly the ownership keys; and the harness now also pins
   the behaviour change itself (pre arm accepts an unclassified source, live arm
   refuses it). Verified non-vacuous: the allowlist is asserted to have actually
   caught movement.
2. `test_charter_binds_exact_scope_...` — the permission block grew three
   ownership-derived keys. Extended to pin all of them plus the class.
3. `telegram.test.ts` — the three one-tap Documents buttons acted. A tap cannot
   carry whose data a folder is, so a button here would be a dead end that reads
   like an offer. Buttons removed; the legacy callback now answers with the
   question; three new arms pin the parse, the no-invention rule (the surface
   must NOT manufacture a class to make the core accept), and the rendering of
   the core's egress verdict.
4. `test_cognitive_architecture_census.py::test_live_registry_carries_no_unregistered_surplus`
   — asserted the expansion registry was EMPTY, which was the honest state until
   the first adjudicated expansion landed. Replaced by the bijection assertion,
   which is strictly stronger: it still fails on an unregistered member AND now
   also fails on a row that outlives its member.
5. `_rewrite_contract` in the same file REPLACED the live expansion rows in its
   synthetic trees, so every live member became an unregistered surplus inside
   fixtures that never meant to test it. Changed to append.

## Budget

+1 framework module and +585 non-comment lines, paid as `temporary_allowances`
rows at the exact measured totals; +1 `durable_store_units` paid as a maximum
bump rather than an allowance, because the access record is a permanent organ
and an allowance would promise a deletion gate that will never fire. The module
is additionally registered in the expansion registry with its adjudication
document, since an allowance cannot buy a net-new member of a named set. The
contract sits in the COG-4 frozen-review scope, so the digest re-bind rides in
this same commit.

## Open, and honestly so

- The sensitivity classes read NAMES, never contents. A payroll table in a file
  called `q3.xlsx` is read. The doc says this in the same words rather than
  implying coverage the detectors do not have.
- Memory rows still carry no ownership column. The provenance that exists today
  is the Charter, the access record and the card's egress verdict; a row-level
  stamp needs a schema migration and a writer change in the bash/SQL plane, and
  is not in this unit.
- The framework cannot verify the attestation. Stated in the module docstring,
  in the Charter payload (`verified_by_framework: false`), on the approval card,
  in the config template and in the doc.
