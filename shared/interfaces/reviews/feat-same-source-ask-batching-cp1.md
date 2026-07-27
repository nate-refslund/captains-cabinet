# Checkpoint review — feat/same-source-ask-batching (cp1)

**Unit:** SAME-SOURCE ASK BATCHING. N pending Captain asks cued by ONE source
must arrive as ONE decision.
**Base:** `b614800997a7a81c0f5d4f8f3b219e314124c066` (origin/master).
**Origin of the requirement:** dry-run finding 3 in
`/Users/nate/cabinet-meta/designs/captain-perspective-retro-2026-07-26.md`
(§4 addendum): "11 same-source memory-supersession asks fanned at identical
6.6d dwell". The Captain's own verdict on that shape: *"I never gave ten
answers, I gave zero."*
**Reviewer:** the landing agent, against the staged diff and re-run batteries
(no builder claim taken as evidence — every number below was produced by a
command in this session).

---

## 1. What changed

| file | change |
|---|---|
| `cabinet/scripts/lib/ask_mint.py` (new, 232 lines) | the generic producer-side batcher: `group_by_source`, `group_pending_asks`, `render_batch_body`, `batch_members`, `batch_action_type` / `is_batch_action` / `batch_source_key`. Pure — no file handle of its own; its ONLY effect is the injected `file_need` seam. |
| `cabinet/scripts/memory-supersede-apply.py` | `_ACTION_NS` constant; `cue_source_key`; `file_cue_batch_card`; `load_batch_rulings`; `_mint_cue_cards`; `_close_batch_needs`; `run_apply_pass` mints cue cards AFTER the classify loop (grouping needs the whole pass) and fans a ruling out per member. |
| `cabinet/scripts/lib/tests/test_ask_mint.py` (new) | 22 arms on the helper. |
| `cabinet/scripts/tests/test_memory_supersede_apply.py` | `TestSameSourceAskBatching`, 13 arms. |

## 2. The boundary this had to respect

The attention plane and the needs ledger are germline (schg + the hook's
path regex), verified in THIS clone against `cabinet/scripts/germline-lock.sh`:
`framework/attention/{queue,queue_card,hygiene,situations,situation,feed,acted_overlay}.py`
and `framework/authority/needs.py` are all in the locked `FILES` array.

So the fix is **producer-side only**: it decides how many asks get FILED,
never how a filed ask is rendered, ruled on or recorded. `needs.file_need`
and `needs.mark` are CALLED, never edited. Diff path-set is four files, none
in `FILES`, none under a locked `DIRS` entry — and that property is now a
test arm (`test_batching_lives_entirely_outside_the_germline_set`), shown red
by mutation M6 below.

**No new reply verb.** The scout map proposed a `cv2|nda` group verb across
`decision_card.py` + `tap_wire.py` + `binder_wire.py`. Rejected: the ruling
verbs the Captain already has fit exactly — `grant NEED-<hex8>` on the batched
need is approve-all, `deny NEED-<hex8>` is skip-all, and both already ride the
captain-gated door (`CABINET_NEEDS_WIRED=1` + `captain_verified`), the
`ndg`/`ndd` one-taps, fingerprint dedup, 90d deny-suppression and the
guardian-dark no-op. A new verb would have widened the callback grammar and
three framework files for zero new capability.

## 3. The three properties that make ONE card safe to answer for N asks

1. **Membership is what he SAW.** The card body carries a machine-readable
   `members (N): …` line; `batch_members()` parses that same body back at
   fan-out time. Re-deriving the group from today's pending set would let one
   approval reach pairs that were never on the card. Every failure mode of the
   body — no line, two lines, a count that disagrees with the list, a token
   that is not an engine-minted id, a duplicate — resolves to the EMPTY tuple,
   so a batch whose membership cannot be read reaches nobody.
2. **Membership cannot grow after a ruling.** While a source's batched card is
   ruled, no new card is minted for it: a re-file would rewrite the body the
   ruling was given on. A late ask waits for the next window (recorded,
   uncarded, retried) instead of joining an approval it was never listed in.
3. **The fan-out is mechanical, not new authority.** Approve-all puts each
   member through the SAME per-item path — same liveness/type/order guards,
   same soak/hold/veto/action-seam gates, its own ledger row carrying
   `via: captain-grant` and the batch id. Skip-all writes one
   `cue-card-skipped` row per member. An OPEN batch card resolves nothing:
   silence is still not agreement (constitution D12).

Plus one bug the design had to avoid and now pins: closing the batch need on
the FIRST member's outcome would evict the rest from `load_granted_pids` and
silently un-approve them. `_close_batch_needs` marks once, only after every
listed member reached a terminal state.

## 4. What I did NOT change, deliberately

The same-run touched-id guard (`{old_id_int, new_id_int} & touched`) blocks
siblings of an applied pair, and every member of a same-source group shares
its cueing row — so an 11-member approval applies one pair per run. That is
pre-existing apply-path safety (the reciprocal equal-ts case), and narrowing
it to `old_id` alone would let a reciprocal pair supersede BOTH rows. Out of
scope for this unit; the approval stays live across runs and the receipt waits
for the last member, which the fan-out arm proves end-to-end over three runs.
Worth a follow-up look at whether the guard can be narrowed safely — it is now
the rate limiter on a batched approval.

## 5. Evidence (commands run this session)

**Pre-change red — behavioural.** A probe running the identical 11-ask fixture
against a clean checkout of the base SHA:

```
pre-change : cards filed for 11 same-source asks: 11 (11 distinct action_types, no batch)
post-change: cards filed for 11 same-source asks: 1  (memory-supersede:batch:100)
```

The new arms replayed against that same base tree (with only the two new
symbol names shimmed, so each fails on its BEHAVIOURAL claim rather than an
AttributeError) fail 8/13, with these reasons:

| arm | pre-change failure |
|---|---|
| eleven asks are one card listing eleven | `eleven asks minted 11 cards, not one` |
| three distinct sources are three cards | `assert 6 == 3` |
| guardian-dark batch retries next run | `assert 3 == 1` |
| approve-all fans out to every member | `KeyError: 'via'` (the batch ruling never reached the apply path) |
| a ruled batch is never re-filed | `a ruled source re-filed its card` |
| skip-all records one skip per member | 3 per-pair cards filed where zero were expected |
| single ask stays unbatched | new counter absent (over-application control — see mutation M1) |
| distinct single asks never merge | new counter absent (same) |

**Mutation sweep — for the negative controls, which pre-change state cannot
validate.** Nine mutations of the post-change code, each run against the arms
that claim to catch it; all nine caught:

| mutation | arms | verdict |
|---|---|---|
| M1 every single-ask floor lowered to 1 (helper x2 + organ) | single-ask / distinct-singles / helper degenerate | RED |
| M2 an OPEN batch card counts as a ruling | open-card-resolves-nothing | RED |
| M3 membership parsed without the count check | unreadable-membership-fans-to-nobody | RED |
| M4 a DENIED batch routed into the granted map | denied-never-applies, skip-all | RED |
| M5 `is_batch_action` matches any namespaced action | pair-card-never-read-as-a-batch | RED |
| M6 `ask_mint.py` added to the germline locked set | germline-boundary arm | RED |
| M7 batch need closed on the first member's outcome | approve-all fan-out | RED |
| M8 batching bypassed (per-item minting restored) | eleven-as-one, three-sources | RED |
| M9 skip-all recorded once, not per member | skip-all | RED |

M5 caught a real blind spot on the first pass: the arm was passing because the
membership parse excluded the pair row, not because the action-type gate did.
The arm now gives every non-batch row (pair card, soak-halfway card, another
producer's batch) a well-formed membership line, so only the action type can
separate them.

**Batteries re-run here, not taken from a builder claim:**

```
pytest cabinet/scripts/lib/tests -q       -> 424 passed
pytest cabinet/scripts/tests -q           -> 4781 passed, 28 skipped
pytest framework/tests/test_no_launcher_hardcode.py \
       framework/tests/test_bash32_empty_array_ratchet.py -q -> 35 passed
bash cabinet/scripts/check-layer-separation.sh   -> new=0, OK
python3.12 cabinet/scripts/state-persistence-preflight.py --repo . -> 0 UNACCOUNTED, OK
bash cabinet/scripts/docs-track-code-sweep.sh    -> GREEN (files=64 findings=0)
```

`__pycache__` purged before every red/green comparison; `PYTHONDONTWRITEBYTECODE=1`
on every run.

## 6. Residual risk

- The batch card's body is longer than a pair card's. The cap is 100 members;
  beyond it the tail is DEFERRED (listed nowhere, carded next window) rather
  than truncated into a body that under-states what approve-all covers.
- A denied batch suppresses re-filing for that source for 90 days, inherited
  from `file_need`'s deny-suppression. That matches existing per-pair
  behaviour and is the intended reading of "skip all".
- No store, config or instance file is added, so there is no `.example` twin,
  egg-manifest row or persistence entry to carry.

**Verdict: land.** The claim ("N same-source asks arrive as one decision")
is demonstrated by the behavioural probe in both directions, every new sensor
either fails against pre-change code or is validated by a mutation, and the
germline boundary is untouched and now machine-checked.
