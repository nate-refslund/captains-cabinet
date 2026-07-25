# Attention well spent — the north-star instrument

**One line:** of the Captain's measured minutes, what share went to decisions
only he could make — and did every decision that had to reach him actually
reach him?

Run it:

```
python3.12 cabinet/scripts/attention-well-spent.py --window-days 7
python3.12 cabinet/scripts/attention-well-spent.py --json
python3.12 cabinet/scripts/attention-well-spent.py --out ~/aws-2026-07-25.json
```

It reads. It never writes to the org, never emits an event, and refuses to
write its report anywhere inside the repo tree.

---

## Why the wording changed

The org's stated north star was `verified_outcomes_per_captain_minute`. Two
things were wrong with it.

**It was computed nowhere.** The string appeared only in
`instance/config/directions.yml` and in a dashboard test asserting the string
is present in that YAML. No code ever produced a value.

**What *was* computed pointed the other way.**

| Surface | What it does | Direction |
|---|---|---|
| `framework/ovi/compute.py` + `framework/ovi/components.yml` | counts Captain-input events as `captain_attention_cost`, weighted `direction: inverse` | fewer Captain events ⇒ **higher** score |
| `cabinet/scripts/lib/org_runtime.py` `burden_index()` | takes `--captain-attention-minutes` as a **declared** input, default `0`; `ovi = verified_value / burden` | declare zero minutes ⇒ **higher** score |
| `cabinet/scripts/work-graph-complete.sh` | `--evidence` is optional | verify your own work, no evidence ⇒ **higher** score |
| `framework/attention/queue.py` `demoted_kinds()` | demotes producers whose cards keep expiring | never push a card ⇒ never demoted |
| `framework/constitution-base.md` §5 | "Minimize Captain interrupts." | asking is a cost |

Put together, the winning strategy was: emit `work_item_verified` with no
evidence, declare a high `--verified-value`, pass no burden flags so
`burden = 1.0`, and never push a card. The number rises monotonically while
the founder is cut out of his own company. Nothing anywhere counted the
questions that should have been asked.

So the metric is re-worded as **attention well spent** — the share of Captain
minutes spent on decisions only he could make — and, crucially, **under-asking
now registers as a failure rather than a win.**

---

## What it computes

**Denominator — measured, never declared.** Captain minutes come only from
observed interactions, priced by a published constant table in
`cabinet/config/attention-well-spent.yml`:

- a real verdict at the approval gate (`approved` / `edited` / `rejected`) on a
  consequence-ledger row — the Captain read the card and decided;
- an `expired` card — it reached the queue, cost queue-time and produced
  nothing, so it is attention **spent** and never **well** spent. Pricing it
  above zero is what makes card-spam lower the share instead of being free;
- a Captain-authored org event (`captain_goal_declared`,
  `captain_outcome_ratified`, `captain_boundary_set`, `captain_decision_logged`,
  `captain_gate_bounced`) whose `actor` is in the config's captain-actor list —
  an officer emitting one under its own id contributes nothing.

No flag, payload field, or CLI argument lets a producer set its own
contribution.

**Numerator — decisions only he could make.** A touch is well spent when its
`action_type` is in a hard-ceiling risk class, or when it is an act of the
authority root (declaring a goal, ratifying an outcome, setting a boundary).

**The must-ask floor.** Read at runtime from the `hard_ceiling` risk classes in
`framework/policies/authority-matrix.yml` — the classes the matrix itself marks
"always-gated regardless of confidence": `external_comms`, `deploy_prod`,
`spend`, `secrets`, `network_write`, `credentials_grant`. This instrument keeps
no editable copy: `framework/policies/` is schg-locked germline, so narrowing
the floor means editing a system-immutable file, not flipping a knob here. An
unreadable or empty matrix is a hard error (exit 2), never a green reading.

The floor reads:

| State | Meaning |
|---|---|
| `breached` | a hard-ceiling action **executed** with no Captain verdict, **or** the window had org activity and zero Captain touches (the silent-window rule) → verdict RED |
| `unprovable` | no breach, but an executed row carried no `action_type` — the floor cannot be proven held over rows whose class was never recorded → verdict AMBER |
| `held` | every hard-ceiling action that ran was decided by the Captain |

The silent-window rule is what makes the floor un-optimisable. Without it, an
org that simply stops interacting reports `0/0` and pays nothing.

**Verified outcomes — never an officer's own emit.** A `work_item_verified`
counts only when the attestor is:

- the **Captain** (`actor` in the captain list, or a `captain_outcome_ratified`
  for that task), or
- a **counterparty** (an actor that did not emit the `work_item_completed`), or
- a **probe** — the payload carries a ref shaped like a pointer to an
  independently recorded artifact (literal prefixes: `https://github.com/`,
  `eval:`, `probe:`, `run:`; whitespace-free; at least 12 characters).

Anything else is self-attestation and counts zero.

---

## Reading the output

```
verdict       : RED
well spent    : 100% of 6 measured minutes across 1 touches
must-ask floor: breached
  NOT ASKED  external_comms/external_email  <ts>|officer:cos|did-external_email|unasked-1
```

The floor dominates. A perfect share with one unasked hard-ceiling action is
RED — that is the whole point of the re-wording.

`unmeasured` means no org activity and no Captain touches: honest absence, not
a pass.

---

## Report-only — the standing law

Evidence-derived aggregates are **monitoring metrics and kill criteria only**:
never officer-visible scores, never inputs to generation or selection
(`cabinet/evals/never-a-score/README.md`). This reading is Captain-facing.

Structurally enforced, not just promised:

- the instrument lives in `cabinet/`, not `framework/` — officer-plane code
  cannot import what is not on its import path;
- it emits nothing: no `emit()` call, no event type, no ledger write;
- `--out` refuses any destination inside the repo tree, so the report can never
  quietly become a file some selector reads;
- `cabinet/scripts/tests/test_attention_well_spent.py` fails if any file under
  `framework/`, `presets/`, `cabinet/dashboard/src/` or `.claude/` names it.

---

## Known gaps (stated, not papered over)

- **Ring-0 governance acts are not in the v1 floor.** The consequence schema
  carries no field that classifies a row into a Ring-0 category
  (`framework/authority/action_mode.py` `RING0_CATEGORIES`), so the v1 floor is
  exactly the ratified hard-ceiling set. Closing this needs a row-level
  category, not a wider list here.
- **The floor only sees actions that ran.** A must-ask row whose `outcome` was
  never recorded is neither a breach nor a hold — it is invisible. The
  symmetric "just don't stamp it" evasion on the *class* axis is closed
  (`unclassified_executed` ⇒ `unprovable`); the one on the *outcome* axis is
  not, because treating every undecided must-ask proposal as suspect would fire
  on every card legitimately awaiting the Captain right now, and an instrument
  that cries wolf gets ignored. Closing it needs a staleness clock.
- **A probe ref is a pointer, not a re-execution.** The instrument checks that
  a ref is shaped like an independently recorded artifact, not that the
  artifact says what the officer claimed. It is still strictly stronger than
  optional free-prose `--evidence`: a forged pointer is falsifiable by anyone
  who follows it.
- **`verified_outcomes_per_captain_minute` still appears in
  `instance/config/directions.yml`.** It is superseded and computed nowhere,
  and is retained only because
  `cabinet/dashboard/src/lib/world/directions.test.ts` pins the literal string.
  Retiring the string and that test line belongs in one change.
