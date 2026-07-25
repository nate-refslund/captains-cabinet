# Checkpoint review — feat/outbound-identity cp1 (2026-07-25)

Reviewer: build session, self-review of the staged diff before the first commit.
Base: master `05871f128da8e2be9e94e50ff531f35f6f9bd719`. Churn ≈ 1.6k lines.

## Scope

Give the cabinet an outbound identity separable from the Captain's, and extend
the machine-provenance disclosure from Monday board artifacts to every channel
that reaches a non-Captain human. Configurable, fail-closed to the safe side, no
hardcoded address.

Files: `framework/outbound_identity.py` (new) · `instance/config/outbound-identity.yml.example`
(new) · `framework/frontdoor/chair_drafts.py` · `framework/frontdoor/action_exec.py` ·
`framework/channels/contract.py` · `instance/flavor-a/flavor_a/screenpipe_dispatch.py` ·
`cabinet/config/cognitive-architecture-contract.yml` · two new test modules · one proposal doc.

## Premise check (mandatory, done first)

All four reported premises re-confirmed at `05871f12`, same file:line. Details in
`docs/proposals/outbound-identity-separation-2026-07-25.md` §1. No scope
adjustment was needed.

## What I checked, and what I changed as a result

**Two defects found in my own first draft and fixed before commit:**

1. `deliver_draft` stamped unconditionally, so a record whose draft was empty
   would have been delivered as a message whose entire content was the
   disclosure line — manufacturing an outbound message out of nothing rather
   than making one safer. Now blank stays blank: no content, nothing to
   disclose.
2. `contract.disclosure_state` resolved the policy through two unbound lookups,
   each re-reading the config file, and journaling happens twice per send
   (dispatched/failed). Now resolved once and passed down.

**Deliberate design calls, with the reasoning:**

* **Idempotency keys on the rendered line, not on the robot glyph.** A glyph
  scan is the obvious implementation and it is attackable: an inbound message
  that quotes the glyph (accidentally or deliberately) would make the cabinet
  skip its own disclosure. Exact-line matching means a "already stamped" verdict
  is only ever returned when the property actually holds. Arm:
  `test_a_quoted_machine_glyph_cannot_suppress_it`.
* **No partial parse.** One malformed field returns the WHOLE file to the safe
  default. A half-applied identity block is worse than no config, because it
  looks configured. Every malformed-config arm plants a valid `mode: captain`
  beside the malformation, so "refused the file" and "ignored the field" are
  distinguishable — without that pairing every one of those arms would pass
  under either implementation.
* **A blank `disclosure.text` is refused, not honoured.** It is a silent kill
  switch wearing a typo's clothes. Turning disclosure off requires
  `enabled: false`, which is legible in a diff.
* **A configured `from_address` the transport cannot honour is a refusal, not a
  fallback.** The Flavor-A dispatch sends through the Captain's own mailbox.
  Silently delivering under his name after being told to use another address is
  exactly the confusion this work exists to remove.
* **The disclosure applies in `mode: captain` too.** Signing as the Captain does
  not buy silence.
* **No try/except around the egress stamp.** `stamp()` is contracted not to
  raise; if it somehow did, the send must stop rather than leak an undisclosed
  message past a swallowed error. Fail-closed polarity, deliberately.

## Residual risks — accepted, and why

* **Config changed between present and deliver.** If the Captain edits the
  disclosure text after a draft is presented, the egress stamp appends the NEW
  line beside the old one. Over-disclosure, which is the safe direction. Not
  worth a version-pin in the record.
* **The channel-adapter body is not stamped.** Reported, not worked around — see
  §4 of the proposal doc. Four existing assertions pin verbatim body passthrough
  to the transport; none were edited. Mitigation shipped is audit
  (`disclosure_required` / `disclosed` on every outbox row), and the exposure is
  bounded: Teams/Outlook adapters cannot reach a human at all (their default
  transport raises) and Slack's live path is gated on `allow_sends()`.
* **The Monday estate still acts under the Captain's personal token.** Ratified
  policy, untouched, surfaced as an open Captain question rather than resolved
  unilaterally.
* **Default behaviour changes on this deployment.** Outbound mail stops carrying
  the Captain's signature and starts carrying a disclosure line. That is the
  point, it is visible in the draft he approves, and one config line
  (`mode: captain`) restores the old behaviour exactly.

## Test quality

The suite would be worthless if it only proved the module correct in isolation,
so both weaknesses were addressed explicitly:

* The module is new, so absence-failure proves nothing about it. Its guards are
  proven by mutation instead: `TestGuardsAreLoadBearing` disables one guard at a
  time (closed key sets, version pin, mode vocabulary, realpath containment, the
  fallback posture constant) and asserts the protected property flips.
* The wiring was proven the other way: both test files were run against a clean
  `05871f12` checkout **with `framework/outbound_identity.py` copied in**, so the
  only missing piece was the wiring. 14/16 arms red there. The 2 that stayed
  green are explicitly no-regression arms.
* One order-dependence found and fixed during the sweep: the egress arms passed
  alone and failed in the full suite, because `framework.sources` caches whatever
  binding an earlier module resolved and a live source reporting
  "no longer awaiting" self-cancels the draft before the egress. The fixture now
  pins the fire gate open, as the Casey suite does. Left unfixed, those arms
  would have silently stopped exercising the disclosure.

## Gates

Serial, `__pycache__` purged + `PYTHONDONTWRITEBYTECODE=1` before every run, vs a
re-measured baseline. framework 6552 passed / 1 known-red (out-of-repo retro
shim, unchanged) / 25 skipped · cabinet/scripts/tests 4543 passed / 28 skipped ·
layer-sep unchanged at current=43 new=0 with neither ledger grown · docs sweep
GREEN · architecture census PASS with zero headroom (239<=239, 67372<=67372).

One flake observed and re-run rather than adjusted:
`test_cog1_outbox_capture.py::TestB1B2Baselines::test_baselines_hold_the_bound`
is a 100-iteration wall-clock p95 bound against an ephemeral Postgres cluster; it
reddened once under load, passed alone (36.5s), and the full suite re-ran clean
and bit-identical to baseline. No threshold was touched.

## Verdict

Ship to a branch. Not merged: landing is sequenced separately so master does not
go transiently red for other writers. The Captain question (PM-estate identity)
and the channels-seam contradiction both need adjudication that is not this
session's to make.
