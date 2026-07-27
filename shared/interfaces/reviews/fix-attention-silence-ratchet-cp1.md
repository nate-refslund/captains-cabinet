# Review — fix/attention-silence-ratchet cp1

**Scope:** the cabinet is structurally biased toward going quiet, and its own
score rewarded that. Seven findings, each verified by execution against the
real ledger/feed before being fixed. Captain ruling 2026-07-25: the metric is
**attention WELL SPENT** — the share of his minutes spent on decisions only he
could make — which makes **under-asking a failure exactly as much as
over-asking**. Silence is not safe.

## The measurement that drove this

`framework/ovi/compute.py` against the real event ledger
(`~/Library/Application Support/cabinet/events`, read-only, `emit_event=False`):

| window | attention BEFORE | attention AFTER | composite BEFORE | composite AFTER |
|---|---|---|---|---|
| 7d | **1.00** | **0.00** | 0.2043 | 0.0043 |
| 30d | **1.00** | **0.00** | 0.5775 | 0.3775 |
| 365d | **1.00** | **0.00** | 0.5022 | 0.3022 |

The 7d window has 0.0 throughput and 0.0 verification: a week of delivering
nothing scored full marks on the attention term. The root cause is sharper than
"wrong weight" — **zero `captain_*` events have ever been emitted, 0 of 43,894
in the whole ledger**, so 1.00 was not a lucky reading, it was the only reading
the inverse term could ever produce.

## What changed, per finding

1. **Attention polarity + degenerate ends.** `captain_attention_cost`
   (weight 0.20, `direction: inverse`, range [0,20]) →
   `captain_attention_well_spent` (weight 0.20, `direction: normal`, [0,1]),
   computed as `decisions / (decisions + captain_gate_bounced)`, and **0.0 when
   there was no contact at all**. Degenerate ends, each a test: no contact →
   0.0 (was 1.00); no data → 0.0; contact all decision-bearing → 1.0; contact
   none decision-bearing → 0.0; mixed → the honest share. Both failure modes
   read 0.0, so the term cannot be maximised by silence — silence is its
   minimum. Over-ask protection is preserved via the bounce denominator; its
   honest limit (the escalation gate is dark by default) is stated in code.

2. **OVI→promotion wire CUT.** `hat_graduation._ovi_regression_during` read
   `ovi_snapshot_computed.composite_score` as a promotion criterion, feeding
   `self_improvement_loop._apply_hat_graduations` → `role_capability_added`.
   The standing rider is absolute: OVI is Captain-facing and never a selection
   input. Removed, plus `framework/tests/test_ovi_never_a_selection_input.py` —
   an AST scan over twelve selection/ranking/gating trees, with the named-tree
   existence check, a non-empty-file-set check, unparseable-is-a-failure, and a
   planted-reconnection arm proving the scanner is not vacuous. **Extra finding:
   the test that supposedly pinned the old gate was itself VACUOUS** — with both
   `ovi_snapshot_computed` emits deleted it still passed, because the mission
   bar alone produced the empty list. It never exercised the wire in its life.

3. **Ignored ≠ rejected.** Live feed: 58 of 58 demote rows carry
   `card-expiry` — every producer the org ever quieted was quieted by SILENCE,
   and an explicit `rejected` RESET the streak, so the one unambiguous over-ask
   signal actively protected a producer. Added `rejection_streaks()` (reset only
   by a card the Captain actually USED) and `demotions()` returning
   `{kind: reason}`; `demoted_kinds()` kept as the back-compatible set. Expiry
   demotion is preserved exactly, not disabled. The gate now journals which
   evidence fired.

4. **Under-asking has a name.** `missed` verdict + `not-asked` taxonomy in
   `action_lessons.py`, reachable as an anchored `/missed <what>` answered
   mechanically by the inbound poller (the proven `/score` shape — the Captain's
   controls never wait on an officer). It cannot be a reply: every other verb
   quotes a card, and an under-ask has no card. **Honest answer on learning:
   almost nothing in this cabinet learns from any verdict** — the regression
   corpus is read only by the test suite (`evaluate_gate` has zero production
   callers), the authority-matrix path computes a verdict and discards it, and
   the attention demotion is driven by non-response. The ONE real loop is
   `action-lessons.yml → run_action_lane.load_lessons → render_lessons → the
   proposer's system prompt`, which is why the row lands there and not in one of
   the three sinks. That consumer is a disabled lane on this box: the loop is
   architecturally real and operationally dark, and this branch does not
   pretend otherwise.

5. **Doctrine.** `t2-rubric.md` said verbatim *"So silence is safe — it never
   spams and never goes dark"* — rewritten (rubric version 1 → 2), and the
   Chair's job restated as spending attention well rather than protecting it.
   Both shipped `executive-assistant.md` role objectives likewise.

6. **Dead-man: cannot be armed without the Captain, and a shipped default is
   the WRONG answer.** Arming needs an off-machine watcher account, a
   registered check and a per-instance slug — an external act. A default
   endpoint silently phones a stranger's host, and a shared default slug makes a
   DEAD instance indistinguishable from a QUIET one, the exact confusion the
   detector exists to remove. Fixed instead: its docstring called
   time-since-contact "the denominator of value per unit of Captain attention",
   the very framing the ruling overturned; and added `status()` so the unarmed
   state is askable offline — an absence detector that is silently absent
   produces the same observable as a dead cabinet.

7. **`situation_key` stamped on taps.** Measured: 21 Captain taps, 0 carrying a
   situation key; the message-id join recovered only 6. Resolved at journal time
   via `feed.situation_key_for_message`, which is total on failure and returns
   None rather than a wrong attribution at every degenerate end.

## Verification

Every new arm proven to FAIL against pre-change code with caches purged, in
both directions: the OVI selection ratchet (RED naming the exact file and
tokens, GREEN after the cut), the twelve item-3 arms (12 failed / 12 passed),
and the attention arms carry a reconstruction of the old formula showing it
produced the opposite reading on the same input.

`python3.12` throughout; `__pycache__` purged and `PYTHONDONTWRITEBYTECODE=1`
before every run. Full CI batteries and per-job green recorded on the PR.

Only known pre-existing red: `test_retro_shim.py::test_reexports_constants`.
