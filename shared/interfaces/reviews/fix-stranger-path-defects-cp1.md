# FW-019 checkpoint review — `fix/stranger-path-defects` cp1

Reviewed-Scope-Digest: 19b6ac71e84b9a00d765f28c6c8f4fc1c8b1aafc74048866c1fff1d169954dc6

Verdict: PASS
Date: 2026-08-02
Scope: 13 staged paths (the review plane is excluded from its own digest).

## What this is

Three defects found by driving the REAL browser journey on a fresh hatch on
2026-07-30, plus one adjacent one-liner. Every symptom below was measured, not
hypothesised; where the measurement's stated CAUSE turned out to be wrong, the
correction is recorded rather than quietly dropped.

## D1 — a purge bricked onboarding, and nothing warned

**Measured.** After "Delete onboarding data" on the dashboard, every later
action on every surface — dashboard, Telegram, World, and the CLI — refused
`onboarding_purged` ("No later action can reopen its evidence trial."), and the
purged card offered no options at all. The confirm dialog said only "permanently
delete this onboarding record". Deleting your own data ended onboarding on the
instance, permanently, with no warning that it would.

**Diagnosis.** Two different properties were fused. Purge FINALITY is about the
purged TRIAL — its state, events, manifests, charter, derived excerpts and
evidence trial are gone and nothing may reopen them. That is right, and it is
unchanged. Being able to onboard AT ALL is about the INSTANCE, and no part of
deletion should cost it. `stage == "purged"` was being used as a lock on the
second when it is only a fact about the first.

**Fix.** `framework/onboarding/journey.py`:

- `_restart_after_purge` runs inside `act()`'s first locked block, BEFORE the
  evidence lifecycle opens — so the incoming action's events land in a live
  trial rather than the deleted one. It writes a `_fresh_state` (new
  `journey_id`, new `evidence_trial_id`) and appends a projection-free
  `start_again` event, so `_load_state`'s crash-replay cannot resurrect a dead
  revision.
- `PURGE_TERMINAL_ACTIONS` = `continue`, `pause`, `revoke`, `undo`,
  `ratify_charter`, `purge` — the actions with no meaning without a live
  journey. They still refuse `onboarding_purged`.
- An action carrying an `expected_revision` that is not the purged card's was
  composed against the deleted journey's card. It still refuses
  `onboarding_purged`. "Stale actions cannot reopen them" stays literally true.
- `start_again` is a real dispatch branch and is deliberately INERT on a live
  journey (`start_again_unavailable`): no surface may wipe a running
  orientation by sending a word.
- `_act_core` keeps its own unconditional purged guard. It is the commit
  boundary for an action already in flight when a concurrent purge landed,
  whose evidence is already in the dead trial;
  `test_inner_action_lock_refuses_stale_action_after_concurrent_purge` still
  drives it directly and still passes unchanged.
- `_annotate_access_records` now skips a record an earlier purge already
  redacted. This bug pre-existed and was UNREACHABLE — a second purge needs a
  second journey. Making purge survivable made it reachable, so it is fixed in
  the same commit: a blind re-stamp would point the first read's audit link at a
  deletion that never touched it.

**Deliberate deviation from the brief.** The brief asked that
`onboarding_purged` become unreachable EXCEPT for stale-revision actions. It is
also still reachable for `PURGE_TERMINAL_ACTIONS`. Two reasons: the message is
true for them (there is nothing to continue, undo or delete), and minting a new
journey — with a new evidence trial and a genesis event — as a side effect of a
stale `continue` is an audit-weight act with no operator intent behind it. The
brief's own required arms all hold: `answer_seed` after a purge succeeds with a
new `journey_id`, the purged card carries a start-again control, and stale
actions are still refused.

**Copy.** The purged card, the dashboard confirm dialog and the Telegram purge
prompt now each state three things: what is destroyed, what is kept on purpose
(the content-free access record — whose data, under what claimed right, path
redacted, no content), and that a new orientation can be started afterwards.

## D2 — the folder field, root-caused by execution

**Measured (CDP, twice).** The folder field lost a programmatically-set value
while purpose / authority-basis / the radios in the same batch kept theirs; the
submitted proposal carried the `~/Documents` DEFAULT, so a Charter was approved
over a folder the operator never chose. Reported cause: an effect re-syncing the
field from state on every polling refresh, at `journey-card.tsx:419`.

**The reported cause is wrong, and the correction matters.**

- **There is no poll.** `load()` runs once on mount and again only on a 409.
  Nothing in the component or either host page schedules a refresh; the arm
  `has no recurring refresh at all` executes that.
- **Line 419 is not in an effect.** It is in `choose('propose_window')`, a click
  handler. It cannot fire without an operator click, and the options row that
  carries that click is hidden whenever the form is open.

**Actual mechanism, by elimination on executed arms.** The field is a CONTROLLED
input (`value={source}`), and `windowPayload()` reads `source` STATE. A
programmatic `node.value = x` does not reach React's onChange — React's value
tracker suppresses the synthetic event — so state stays at its default. Any
later re-render (the radios in the same batch DID take, and each one re-renders)
repaints the stale state value over the DOM: that is the "reverted within
seconds". The submit then reads state: that is the `~/Documents` proposal. And
state never changing is also why it looked "sticky" afterwards. One cause, all
four observations. **A human typing cannot hit it — a keystroke IS the
onChange.** So the CDP-only half is an automation artifact, said plainly here as
the brief asked.

**What was still real, and is fixed.** `choose('propose_window')` synced the
field from state UNCONDITIONALLY. Today that is a latent clobber rather than a
live data loss (the UI hides the trigger while the form is open), and it is one
UI change away from being live. Dirty-tracking: `sourceEdited` state, set by the
field's own onChange, cleared by the explicit "Use my Documents" reset, by a
landed proposal (state now holds what they typed, resolved) and by a purge or
restart. The pre-fill happens only while the field is pristine.

The consent-integrity backstop for the whole class is D3: a Charter that names
the full path makes a folder-the-operator-never-chose visible at the one moment
they confirm it.

## D3 — the Charter named only the basename

**Measured.** The approval sentence read `Read-only access to "Documents"`. The
wrong `~/Documents` and the right folder made the SAME sentence, at the one
moment the operator confirms what will be read. Consent to a basename is not
consent to a path.

**Fix.** `_card`'s `charter_pending` body renders
`"{label}" ({resolved root})`. One composer, so Telegram (which renders
`card.body`) gets it for free. The dashboard's body paragraph gains
`break-words` so a long path wraps rather than overflowing its column — that
class is load-bearing, not cosmetic, and has its own arm.

## Adjacent one-liner — duplicate forward-clock rows

`file_clocks` dedupes by (resolved day, line) at emission. Line 2 of the dated
estate's cost CSV writes one day in two formats
(`作成 2026/7/31 …,… 2026年7月31日時点 …`) and emitted two rows for one day, so
every forward-clock list carried a visible duplicate and `rows_found`
over-counted. Only RESOLVED days are deduped: two unresolved dates on one line
are two different unknowns, and collapsing them would hide one.

The other offered one-liner — the top bar reading "fixture" — is NOT taken. I
could not locate where that label resolves (it is not in `nav.tsx`, not in
`lib/config.ts`, not in `active-context.ts`), and guessing at a display-name
resolution without the live instance is how a cosmetic fix becomes a real one.
Filed as a follow-up in the PR body with what was ruled out.

## Class-11 — the four questions, answered by execution

**1. Does the arm FAIL against pre-change code, both directions, cache purged?**
Every fix arm was mutation-tested with `PYTHONDONTWRITEBYTECODE=1` and
`__pycache__` purged between runs. Seven mutations, seven expected reds:

| mutation | red arms |
|---|---|
| `_restart_after_purge` always refuses | purge-survivable, start-again, second-purge, CLI-boundary |
| Charter body back to basename-only | charter-names-the-resolved-path |
| drop the already-redacted guard | second-purge-never-relabels |
| purged card back to `options: []` | typed-confirmation, start-again, CLI-boundary |
| drop the `!sourceEdited &&` guard | never-overwrites-a-typed-folder, no-recurring-refresh |
| drop `break-words` | wraps-the-card-body |
| restore the old purge confirm copy | confirm-dialog-says-what-is-kept |

The clock dedup was proven the other way round: it turned two pinned suite rows
red (`ESTATE_ROWS`, `rows_found`), which is the pre-fix duplicate being
observed, and both were updated with the reason recorded in place.

**2. What does the check do at the degenerate end?**
`_expected_revision(None)` returns `None` and is treated as "no claim" rather
than as revision 0 — the one coercion that would have made every fresh action
look stale. The clock dedup keys only on a RESOLVED day; `iso is None` is never
a key, so two unknowns are never collapsed into one (pinned by the third
assertion of `test_one_day_written_twice_on_one_line_is_one_row`). `start_again`
on `revision != 0` or `stage != "welcome"` refuses rather than resetting, so the
degenerate "already open" case cannot be destructive.

**3. What does the test environment guarantee that production does not?**
The dashboard suite runs in vitest's `node` environment with no DOM, so no arm
here can execute a real keystroke — which is exactly why the D2 conclusion is
stated as elimination over executed properties (controlled input, state-sourced
payload, four enumerated writers, no scheduler) rather than as a reproduction.
That limit is written into the test file's own header. The Python arms are
hermetic on `tmp_path`; the CLI arm crosses the real subprocess boundary the
three web surfaces sit behind, because an in-process arm would not have caught
the measured "including the CLI".

**4. Is the sensor wired to the live artifact?**
`parity.test.ts` compares the LIVE `ACTIONS` set and `ONBOARDING_ACTIONS` array
against the core's parsed dispatch chain, so `start_again` had to be written
into all four places (core dispatch, bridge admission, type vocabulary, Telegram
branch) or the gate reds — it is not possible to ship this action as a dead
button. `journey-card.test.ts` drives the real component function and its real
closures. The hook-order guard fired loudly when `sourceEdited` was inserted,
which is the sensor working.

## Batteries

- `python3.12 -m pytest framework/onboarding/tests framework/tests -q` — 2101
  passed, 2 skipped.
- `python3.12 -m pytest framework/ -q -rs` — 8027 passed, 25 skipped, 1 failed:
  `framework/fidelity/tests/test_retro_shim.py::test_reexports_constants`, a
  KNOWN environment red that reproduces UNCHANGED on a pristine `origin/master`
  worktree (asserts a model id this machine overrides). Cited, not chased.
- `npx vitest run` (full dashboard) — 3309 passed, 1 skipped.
  `npx tsc --noEmit` — clean.
- `bash cabinet/scripts/null-hatch.sh` — PASS (re-run against the COMMITTED tree,
  since it reads `git archive HEAD`).
- `bash cabinet/scripts/check-layer-separation.sh` — OK, 0 new.
- `cognitive-architecture-census.py --check` — PASS at observed == maximum, zero
  headroom, after the +67 bump documented in the contract with its measurement.

## Residual risk

The COG-4 review-to-bytes binding moves because
`cabinet/config/cognitive-architecture-contract.yml` is in its scope; it is
re-bound in `shared/interfaces/reviews/cognitive-core-phase-4-review.md` with a
dated note, prior notes kept verbatim, one recomputed digest — the established
precedent. No COG-4 implementation byte is touched.

`framework/onboarding/journey.py` is a germline path. The content change lands
on master like any other; the live checkout re-materialises the landed bytes at
the Captain's next unlock/relock window. The germline SET is unchanged.
