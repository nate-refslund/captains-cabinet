# feat/operator-identity — checkpoint 1

**Unit.** The cabinet could not say who the operator is. `operator_identity`
landed one unit earlier with a READER and no writer: nothing anywhere asked who
the operator is in each connected system, so on a real estate the onboarding
record resolved nothing, all four connectors reported `basis: unresolved`, and
every attribution was withheld — correctly, and permanently. Honest, and it
means nothing the cabinet read was known to belong to the person onboarding,
which is the strongest relevance evidence there is. This unit builds the ask,
the writer, the per-connector resolution and the share that travels with every
claim.

**Model.** Opus 5 (1M), single session, execution tier. Direction was already
adjudicated: the who-and-when landing (2026-07-29) fixed that the operator comes
from the onboarding record and never from the credential. This checkpoint makes
that branch reachable; it does not re-open the ruling.

Reviewed-Scope-Digest: 13e8cded15283c4a9bf6891e83b3bd3705d0169542ff2082927c780125928bd5

---

## 1. The defect, measured before the change

Executed against the live estate at `31e3d6b2` with the four declared
connectors, read-only, 14 HTTPS requests, zero writes:

```
declared 4  calls 14  rows 665  not_reached []
  tracker  connected  531 items  0 distinct actors
  code     connected   56 items  3 distinct actors
  hosting  connected   58 items  0 distinct actors
  databases connected  20 items  1 distinct actor
operator: {"names": [], "handles": {}, "basis": "onboarding_record"}
attribution: code/databases/hosting/tracker  ALL basis=unresolved
```

Two independent causes, and both had to be closed or the result is unchanged:

1. **No writer.** `instance/config/cabinet-init.answers.yml` does not exist on
   this estate and no action in the tree writes an `operator:` block, so the
   resolved branch of `attribution_basis` was unreachable by any sequence of
   operator actions. This is the same structural defect `entry_grants` carried
   before `_entry_registry` became its writer, named in that function's own
   docstring.
2. **No actor to resolve.** Two of the four connectors declared no
   `actor_field`, so their 589 rows named nobody. Even a perfectly recorded
   identity would attribute nothing there, and the disclosure would have said
   "I cannot tell" forever without saying why.

## 2. What landed

**The ask** — `research.identity_question(rows, operator)` names every connector
that cannot recognise the operator and offers, per connector, the account
identifiers **that connector's own rows carried**, with counts. It returns
`None` once every connector resolves, so a settled question is never printed. A
connector whose rows carry no actor at all is still listed, flagged
`reports_no_actor`, with a note saying a recorded handle would attribute nothing
there — "you have not told me" and "I cannot use what you tell me here" are
different facts and used to print identically.

**The writer** — journey action `record_operator_identity`. Refuses: a connector
no sweep read (`identity_connector_unknown` — a silent no-op reads to the
operator as "I told it who I am" while every claim stays withheld), an empty or
shapeless answer (`identity_handles_required`, `identity_handle_empty`), and any
recording before anything has been read (`identity_not_offered`). The answer
merges with the interview's answers file — both are the operator's own words,
the journey wins a collision because it is the later statement and the only one
that can name a connector the interview had not read yet — and the who-and-when
block is re-derived in the same action, so the answer visibly goes somewhere.

**Never the credential.** Each connector's `identity:` call asks the TOKEN who it
is; on this estate one of them answers with an integration account. Those strings
stay what they were good for — estate identity, for demotion — and are not
consulted here, not even as a default to confirm.

**Never a look-alike.** `_fold` casefolds and collapses whitespace and does
nothing else: no substring, no prefix, no edit distance. `aperson-bot`,
`aperson.deploy` and `not-aperson` are three other accounts. A near-match works
on one estate and attributes a colleague on the next, and a wrong attribution
reads exactly like a right one.

**The share travels with the basis** — `attribution_share` counts mine / another
actor / **no actor at all** per connector, and the statement carries the numbers.
`no_actor` is its own figure rather than folded into `others` because "somebody
else did this" and "this reports nobody" are opposite facts that would otherwise
print identically; and all three are printed so the reader never has to subtract.
"Your top project" is not a sentence this lane can now produce.

**Two actor paths declared** (instance config, read-only, one extra field on
calls already being made): the tracker's row creator and the hosting account's
deployment creator. Verified by execution that the underlying call returns the
same item count with and without the added field (532 in both), so nothing is
lost to declare it.

## 3. Verification

- **Direction check.** 21 of 22 new Python arms RED against `31e3d6b2` with
  `__pycache__` purged. The twenty-second
  (`test_one_connector_resolving_never_resolves_its_neighbour`) is the
  degenerate-end guard that must stay green in both directions — it pins
  behaviour this unit must not break. Of the two new dashboard arms, the picker
  arm goes RED when the render block alone is removed (checked by removing it
  and re-running); the "asks nothing once resolved" arm is the other
  both-directions guard.
- **Suites.** `pytest framework/` 7732 passed, 1 failed —
  `fidelity/tests/test_retro_shim.py::test_reexports_constants`, the known
  local-only red, unrelated and untouched. `pytest framework/onboarding` 633
  passed. Dashboard `tsc --noEmit` clean; `vitest run` 2884 passed, 1 skipped.
- **Gates.** Census PASS at observed == maximum with zero headroom preserved
  (`framework_production_noncomment_lines` 75502 <= 75502; modules unchanged at
  248; no bijection class moves). Layer separation: no new violations.
  Docs-track-code sweep GREEN. Ledger status parity GREEN.
- **Live re-execution, read-only, after the change** — 4 connectors, 665 rows,
  14 requests, `not_reached` empty, zero writes:

```
  code       onboarding_record  {rows: 56,  mine: 3,  others: 53, no_actor: 0}
  hosting    onboarding_record  {rows: 58,  mine: 28, others: 13, no_actor: 17}
  tracker    onboarding_record  {rows: 531, mine: 1,  others: 530, no_actor: 0}
  databases  unresolved         {rows: 20,  mine: 0,  others: 20, no_actor: 0}
```

  The tracker figure is the whole point of the unit: **1 of 531**. The estate's
  busiest connector is almost entirely other people's work, and before this the
  cabinet had no way to say so — or to say the opposite.

## 4. What this unit deliberately did NOT do

- **No taxonomy and no vendor name enters `framework/`.** A connector remains a
  credential, an inventory call, a timestamp field and an account identifier.
  The two actor paths are instance configuration, which the egg export drops.
- **The dashboard's hidden `card.options` at the welcome stage is untouched.**
  `gather_connectors` and `answer_salience` are unreachable there today because
  the options block renders only when the scope form is closed. That is a real
  defect and it belongs to the unit working on the answer path; this unit
  therefore renders its ask as its own form (like the seed field), which is
  additive and collides with nothing.
- **A recorded handle that matches nothing is not repaired.** It is reported as
  matching nothing. Repairing it would mean guessing, which is the failure this
  lane cannot detect afterwards.
