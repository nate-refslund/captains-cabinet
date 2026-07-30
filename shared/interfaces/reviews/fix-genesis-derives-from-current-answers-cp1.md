# FW-019 checkpoint review — `fix/genesis-derives-from-current-answers` cp1

**Branch:** `fix/genesis-derives-from-current-answers` off `origin/master` @ `4fd9b2b4`
**Scope:** 4 staged paths, 863 changed lines (905 added / 43 removed).
**Method:** every claim below is bound to bytes or to a command executed against this tree with
`python3.12` and `PYTHONDONTWRITEBYTECODE=1` after purging every `__pycache__`. The pre-change arm
counts come from a SEPARATE pristine clone checked out at `4fd9b2b4` with only the new test file
copied in — not from reverting in place.

Reviewed-Scope-Digest: 6794e8366e682c1f5b5f9a8b0ddc462dd92f9004ba866d76898940ad58977c79

---

## 1. What the diff claims to fix

Two defects, both measured on a live agnostic-proof hatch through the answers file's OWN sanctioned
refinement path (`--defaults` hatch → edit `instance/config/cabinet-init.answers.yml` → re-run
`generate-instance.py` → re-run `first-briefing.sh --local`).

| # | Defect | Fix |
|---|---|---|
| M7 | Neither genesis derivation could notice its INPUT had moved. The proposals file is write-once (the Captain may have edited the drafts); a delivered brief is never re-fetched (a re-run must not burn a CLI call). Both contracts are about the artifact. So after the operator replaced the placeholder lane with her real one and wrote a real mission, her first briefing still said "You staked First Lane as a lane at genesis" over a Library baseline researching the placeholder label. | Each derived artifact records the digest of the answers it was derived from; a mismatch re-derives genesis's own untouched drafts and supersedes the brief into the tree's dated `_pre-adopt` archive. |
| M8 | A lane at COMPANY altitude declaring `task_system: none` and `repos: []` was handed "traced end-to-end: task → change → verified deploy/close" and "A closed task in the lane's task system linked to the shipped change". The card's own inputs say there is neither. | `_has_execution_surface` conditions the WHAT, the PROOF and the card headline on what the lane declared; the fallback is this tree's existing completion vocabulary (the action's receipt in the org journal), not a new noun. |

---

## 2. The four questions (class 11 — the sensor tests something other than the control)

### Q1 — does the arm FAIL against pre-change code, both directions, cache purged?

Yes, and the split is the point.

```
pristine clone @ 4fd9b2b4 + only the new test file:
  18 failed, 88 passed        (framework/onboarding/tests/test_genesis.py)
this tree:
  106 passed
baseline before the new arms: 82 passed
```

24 new test ids. **18 fail against pre-change bytes.** The other 6 are deliberate regression pins
that MUST pass in both directions, and each one exists because the corresponding behaviour had to
survive this change unharmed:

| Arm | Passes pre-change because |
|---|---|
| `test_unchanged_answers_rederive_nothing` | write-once already did nothing — this pins that the seam did not break idempotence |
| `test_an_unchanged_answers_file_never_re_runs_the_brief` | the delivered-idempotence contract, unchanged |
| `test_an_unparseable_answers_file_never_wipes_the_drafts` | `no-answers` short-circuit, unchanged |
| `test_an_absent_brief_writes_normally_even_with_a_digest_on_file` | ordinary write path, unchanged |
| `test_an_unreadable_proposals_file_is_refused_not_rewritten` | never-clobber, and the new code must not weaken it |
| `test_a_declared_task_system_keeps_todays_wording_byte_identical` | **the byte-identity pin for M8** — it asserts the three exact strings, so any drift in the software-shaped branch is a hard red |

A test that passes both ways is not evidence of a fix. Every arm that IS evidence is in the 18.

### Q2 — what does the check do at the DEGENERATE end?

Every "unknown" resolves to *today's behaviour*, never to a rewrite. Nine degenerate ends, each with
its own arm:

| Degenerate input | Behaviour | Arm |
|---|---|---|
| answers file absent | `answers_digest()` → `""`; nothing treats `""` as staleness | `test_an_absent_answers_file_yields_no_digest_and_no_rewrite` |
| answers file unparseable | bytes still hash, so the digest MOVES — but there are no answers to derive from and `run_genesis_proposal` returns `no-answers` before any write | `test_an_unparseable_answers_file_never_wipes_the_drafts` |
| proposals doc records no digest (predates the seam) | `kept-existing`, byte-identical | `test_a_file_predating_the_seam_keeps_the_write_once_behaviour` |
| a row records no digest | preserved verbatim | `test_a_row_with_no_recorded_digest_is_never_rewritten` |
| proposals `outcomes` is not a list / file unparseable | refused, exactly as `merge_proposals` refuses | `test_an_unreadable_proposals_file_is_refused_not_rewritten` |
| delivered brief records no digest | left intact, never archived | `test_a_delivered_brief_with_no_recorded_digest_is_left_intact` |
| brief absent but a digest is on file | ordinary write, no supersede key | `test_an_absent_brief_writes_normally_even_with_a_digest_on_file` |
| lanes list emptied | stale lane card dropped, leftover-question card proposed, 2–4 band holds | `test_refining_the_lanes_away_leaves_no_lane_card_behind` |
| `task_system` key absent entirely | read as `none`, matching `generate-instance.py`'s own `task_system or "none"` normalisation | `test_each_declared_surface_maps_to_exactly_one_proof_shape[lane1]` |

**The `outcomes`-not-a-list guard was found BY this review, not before it.** The first draft of
`_stale_proposals` checked only the two digests. `_rederive_proposals` iterates `doc["outcomes"]`,
so a doc carrying a live digest and a mangled `outcomes` key would have had its own keys written
back as rows — a clobber dressed as a re-derivation, on the exact file this seam exists to protect.
Guarded and pinned in the same commit; the census note carries the +11 it cost.

### Q3 — what does the test environment guarantee that production does not?

Three real gaps, named rather than papered over.

1. **`tmp_path` roots skip the recall probe.** `probe_recall`'s root guard refuses to answer for a
   root that is not `CABINET_ROOT`, so no arm exercises re-derivation *with live recall data*. This
   is not a hole in the seam: the digest is computed over the answers file alone and recall reaches
   card composition as data, exactly as it did before. It IS a gap in coverage of the composed
   output, and it is the same gap every genesis test already has.
2. **Tests inject `run_fn`; production runs a real subprocess.** The supersede happens BEFORE the
   CLI attempt, so in production a superseded brief on a box with no CLI leaves an IOU where a
   delivered brief was. That is a genuine trade-off, not an oversight — the alternative is keeping a
   brief about a deployment that no longer exists — and it is stated in `research_brief`'s docstring
   and pinned by `test_a_superseded_brief_falls_back_to_the_honest_iou`, which asserts the old text
   is gone from the live file and still present in the archive.
3. **`st_mtime_ns` could pass vacuously** on a coarse-resolution filesystem if a rewrite landed in
   the same tick. It is never the only signal: both no-churn arms assert the returned `status`
   (`kept-existing` / `already-delivered`, returned only on the non-write path) AND byte equality
   AND mtime. A re-derivation always changes `rederived_at` and `proposed_at`, so byte equality
   cannot pass through one.

### Q4 — is the sensor wired to the LIVE artifact?

Yes, checked by reading the call chain rather than assuming it:

- `cabinet/scripts/first-briefing.sh` step 1 runs `python3.12 -m framework.onboarding.genesis`;
  `main()` calls `run_genesis_proposal()` then `research_brief()` — the two functions the arms call.
- `test_the_rendered_briefing_card_carries_the_neutral_language` goes through
  `genesis_intake_items`, which is what `run_briefing --local-render` composes from (step 2 of the
  same script). It greps the RENDERED item text, not the derivation dict.
- No new entry point, no new daemon, no new schedule. The staleness check lives inside
  `write_proposals` and `research_brief`, i.e. where derivation already ran.

---

## 3. Attacks that found nothing (recorded so the next reader does not redo them)

| Attack | Result |
|---|---|
| Does the row digest survive the YAML round-trip? | Yes — and it is load-bearing, because dropping the stale `first-lane` row in `test_refined_answers_rederive_the_cards_from_the_current_lane` REQUIRES `_regeneration_safe` to return True after a write-then-parse cycle. `json.dumps(sort_keys=True)` makes it order-independent. |
| Does it survive a non-Latin lane name? | Yes — `ensure_ascii=False` in the digest, `allow_unicode=True` in the dump. Pinned by `test_the_row_digest_round_trips_through_a_non_latin_lane`, because the alternative failure is silent: every non-Latin deployment's own drafts treated as hand-edited and never re-derived. |
| Does the generator stamp a clock into the answers file, so the digest moves every run? | No. `render_default_answers` is deterministic and carries no timestamp (`grep` for `generated_at`/`datetime` in the answers writer returns nothing), so a repeated `--defaults` run does not re-derive. |
| Can a card another organ merged in be destroyed? | No. `_regeneration_safe` requires `proposed_by: onboarding-genesis` at ROW level, and `_proposals_doc` only writes that key when the card itself carries it. Rows built by hand — the shape `docs/runbooks/hero-demo-2026-07-10.md` §A1(b) tells an operator to append — carry neither the key nor a digest and are doubly protected. |
| Does the extra row key break the mission compiler? | No new class of risk: `framework/schemas/outcome.schema.json` is `additionalProperties: false` and the proposed rows ALREADY carry six keys it forbids (`lane`, `derived_from`, `what`, `why`, `proof_expected`, `recall_refs`). Ratification has always meant trimming. And the compiler's filename gate reads only `outcomes.yml`, which this file is not. |
| Is `advisor.detect_aging_drafts` disturbed? | No — it reads `status`, `captain_ratified` and `proposed_at` and ignores unknown keys. Its age computation now correctly restarts for rows that were genuinely re-proposed. |
| Empty-string repo entries reaching `repos[0]`? | Pre-filtered by the existing `if str(r).strip()` comprehension in the lane loop; the same filtered list is what reaches `_subject_what`. |
| Cross-filesystem `shutil.move`? | Source and destination are both under `base`. |

---

## 4. Judgement calls, with the counter-argument stated

**Whole-file digest, not a scoped one.** A digest of only the keys genesis reads today is the better
sensor exactly until someone adds a read of a key it does not cover, at which point it silently
stops covering the thing it exists to watch — the sensor-not-wired-to-the-control class this program
keeps paying for. The cost of the whole file is over-triggering: a comment-only edit re-derives
drafts and re-runs one CLI call. The cost of under-triggering is the defect itself. Stated in
`answers_digest`'s docstring so the next reader can reverse it with the argument in hand.

**The focus letter is NOT in the digest.** `load_focus_text` is also a derivation input, so an
operator who writes `instance/config/onboarding-focus.md` after the hatch gets the same staleness
class. It is out of scope here deliberately — the key is named `answers_digest`, it means what it
says, and widening it silently would make the name a lie. This is a known, narrower instance of the
same defect and it is not claimed as covered.

**Estate cards get the neutral proof too.** The helper is shared, and an estate entity declares no
task system and no repository — so the software-shaped proof was unearned there BEFORE this change
as well. Leaving it would be a partial fix relabelled as covered. Counter-argument: a discovered
entity may in fact be a code checkout, and the neutral proof is less specific for that operator.
Answer: `_estate_subject_cards` passes no repo because nothing declared one, and a folder path is
not a shipping surface. Pinned by `test_an_estate_card_gets_the_neutral_proof_too`.

**A superseded brief is MOVED, not copied or annotated in place.** The `_pre-adopt-<UTC-stamp>/`
idiom is this tree's own (`generate-instance.py` adopt, `formation.undo_run`), it never clobbers an
earlier archive, and the replacement names the archive in its own `supersedes:` frontmatter so the
pointer rides the live artifact. `_BRIEF_HEAD_CHARS` was raised 400 → 1200 in the same change
because the frontmatter block already ran ~330 characters and the two new lines could have pushed
the digest field past the read window — a sensor that silently stops seeing what it was pointed at.

---

## 5. Gates run against this tree

| Gate | Command | Result |
|---|---|---|
| Onboarding + framework unit batteries | `python3.12 -m pytest framework/onboarding/tests framework/tests -q` | green |
| Whole framework suite | `python3.12 -m pytest framework/ -q` | 7867 passed, 1 pre-existing local failure (`framework/fidelity/tests/test_retro_shim.py::test_reexports_constants`) that **reproduces identically on the pristine `4fd9b2b4` clone** and whose CI run on that SHA was green — an environment-resolved model id, not this diff |
| Layer separation | `bash cabinet/scripts/check-layer-separation.sh` | `baseline=24 allowlist=19 current=43 new=0` |
| Architecture census | `python3.12 cabinet/scripts/cognitive-architecture-census.py --check` | PASS, `76505 <= 76505`, zero headroom; modules unchanged at 248 |
| Docs track code | `bash cabinet/scripts/docs-track-code-sweep.sh` | `GREEN (files=64 findings=0)` |
| Ledger parity | `bash cabinet/scripts/ledger-status-parity.sh` | `GREEN (ids=353 md_rows=353)` |
| Never-a-score | `python3.12 cabinet/evals/never-a-score/harness.py --self-test --repo-root .` | 12/12 green |
| Launcher / specifics / person ratchets | `python3.12 -m pytest framework/tests/test_no_launcher_hardcode.py -q` | 67 passed |
| Register + control-plane fences | `python3.12 -m pytest cabinet/scripts/tests/test_declared_residuals_register.py cabinet/scripts/tests/test_safety_switch_test_fence.py cabinet/scripts/tests/test_killswitch_test_fence.py -q` | 25 passed |
| Null hatch | `bash cabinet/scripts/null-hatch.sh` | run post-commit (reads `git archive HEAD`) |

The census bump is paid VISIBLY (`maximum:` raised with a dated in-file note breaking the +242 down
by half), never by a temporary allowance: an allowance promises a deletion gate, and neither a
derivation that follows its own inputs nor a proof line reachable outside one trade has one that
could ever fire. Roughly two thirds of the mass is docstring, per the house rule, and none of it is
reformatted into `#` comments to duck the counter.

Touching `cabinet/config/cognitive-architecture-contract.yml` moves the COG-4 frozen scope digest;
it is re-bound in `shared/interfaces/reviews/cognitive-core-phase-4-review.md` in the following
commit, with a dated note naming the one in-scope path that moved and confirming no COG-4
implementation byte did.

---

## 6. Addendum — cp1a, second attack pass (same branch, commit 3)

The Q2 sweep above was run against the *caller*. Re-run against the **writer**, one more degenerate
end fell out and is fixed in commit 3:

`write_proposals(cards=[], …)` on a root whose answers had changed took the stale branch, KEPT every
row it could not rewrite and REPLACED the rest with nothing — a wipe wearing a re-derivation's name.
`run_genesis_proposal` returns `no-cards` before it can happen, and "no production caller reaches
it" is exactly the argument this program does not accept: the rule now lives on the writer, so a
caller that does not know it cannot break it.

- Guard: `stale = _stale_proposals(base, digest) if cards else None` — a modified line, **zero**
  net non-comment lines, so the census bump above is unchanged (`76505 <= 76505`) and the COG-4
  binding does not move (`framework/onboarding/genesis.py` is not an in-scope path).
- Arm: `test_an_empty_card_list_never_deletes_the_drafts`, which also asserts the SAME root still
  re-derives with real cards, so the guard cannot pass by disabling the seam it protects.
- Totals move to 25 new arms / 107 passed.

The scope digest above binds commit 1. Commit 3 is sub-threshold (~40 changed lines) and carries no
artifact of its own by design; this section is the record of what it changed and why.
