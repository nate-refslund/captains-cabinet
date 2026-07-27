# `propose_only` means propose — closing the enforcement-plane collapse (2026-07-27)

**Change:** `fix/propose-means-propose`. Follows the direction-gate adjudication
in `LAUNCH-DIRECTION-TOOLCHAIN-2026-07-27.md` (cabinet-meta), which refused a
new `toolchain` risk class in both arms and located the defect one layer down.

---

## 1. The defect, proved by EXECUTION before anything was changed

`main()` exits 2 on ANY non-None result, so a verdict meaning *"above your bar
— ask, and the chain proceeds without this step"* and a verdict meaning *"hard
ceiling, no auto path exists"* produced the same caller-visible refusal.

Measured on master `f77bcf45`, `CABINET_AUTHORITY_ENFORCING=1`, guardian:

| probe | verdict family | exit | stderr |
|---|---|---:|---|
| `gh secret set FOO --body bar` | propose_only | **2** | `PROPOSE-ONLY (unclassified action 'ambiguous') — …` |
| `curl -X POST …/sendMessage` | always_gated | **2** | `GATED (hard ceiling: network_write) — …` |
| `vercel --prod` | always_gated | **2** | `GATED (hard ceiling: deploy_prod) — …` |
| `stripe charges create` | always_gated | **2** | `GATED (hard ceiling: spend) — …` |
| `ls -la` | act_with_undo | 0 | *(allow)* |

`propose_only exit codes: [2]` · `always_gated exit codes: [2]` ·
**OPERATIONALLY IDENTICAL: True.** The lead was correct.

Arm A's phrase — *"the verdict vocabulary is already richer than enforcement
can express"* — is exactly right.

## 2. What was NOT done, and why it matters more than what was

**A propose verdict still WITHHOLDS the step. Exit codes are unchanged.**

"Let the chain proceed" is about the ORG, not about executing the tool. The
propose set is dominated by the `unclassified` bucket, and both arms of the
direction gate proved that bucket is byte-indistinguishable from its hostile
twins: `bash cabinet/scripts/send-to-group.sh` (whose target is a Telegram
`sendMessage` POST), `gh api -X POST …/comments` (notifies real humans, matches
no ceiling regex), `python3 -c "…smtplib…"`. Anything that let a propose
verdict RUN would ship precisely the widening both arms refused, through a
different door.

There is also no use of the hook protocol's `permissionDecision: "ask"`. Its
meaning depends on the session's permission mode, and officers run with
permissions bypassed — an `ask` there could resolve to auto-allow. A
fail-open on the enforcer is the worst fail-open there is.

At a PreToolUse hook, exit 2 already *is* "the step is withheld and the agent
continues" — it is not a session kill. So the chain already proceeded; what was
missing was any way to tell the two refusals apart, and any trace of the first.

## 3. What changed

1. **A structured verdict kind**, never a substring of prose. `GateDecision` is
   a `str` subclass carrying `.kind` and `.need_id`; ~100 call sites and
   assertions depend on `evaluate_policy` returning `str | None`, and every one
   of them is byte-identical. Nothing was weakened to buy the distinction.
2. **THREE kinds, not two** — `gate`, `propose`, `unclassified`. Two would
   misreport the residual: calling "the classifier cannot see this" a proposal
   dresses an unmeasured hole as a governed decision. Infrastructure
   fail-closed paths (corrupt matrix, classifier unavailable, misplaced
   `standing_grant`) are `gate`, never `propose` — they are not grantable.
3. **A propose verdict files a deduped `capability` need**, reusing the ONE
   ledger the ceiling rows already file to rather than minting a second store.
4. **`needs_enabled()` gains a matrix-enforcement disjunct**
   (`CABINET_AUTHORITY_ENFORCING=1`, and *only* that). It was a no-op in
   guardian, which is *why* a withheld step left no trace. The invariant that
   no-op protects is "the guardian DEFAULT world is bit-identical", and the
   default world is matrix enforcement OFF — where the matrix is skipped
   entirely and there are no refusals to record. The invariant is preserved;
   the blind spot is closed.

   **A near-miss worth recording.** The first version also treated the
   `instance/config/authority-enforcing` FILE as a trigger, on the reasonable-
   looking grounds that `pre-tool-use.sh` honours it. It is a *different*
   switch, already true since the Captain flipped it on 2026-07-03, and its own
   scope line reads *"typed STATELESS policy set enforcing"* — a set that
   EXCLUDES `authority_matrix`. Because every deployment carries that file, the
   seam turned on everywhere and the guardian world stopped being
   bit-identical. Six digest/gate parity tests went red and caught it. Two
   switches one word apart, meaning different things; there is now a test
   asserting the file does NOT wire this seam.
5. **A measured rate limit on filing.** `file_need` costs **~102ms flat** —
   profiled, it is not the ledger read but `_emit` → `evidence_mirror` →
   `recorder.append` → `verify_trial` (54k `contains_secret_shape` calls per
   filing). This gate runs on every tool call. Unbounded filing would add
   ~100ms to ~41k withheld steps and append a ledger row per refusal. A
   stat-based marker holds the hot path to one `os.stat` and the ledger to ~24
   rows per cell per day; true per-call counts already live in the shadow
   record.

## 4. THE RE-MEASURED BLAST RADIUS

Corpus rebuilt from the live shadow record read-only (`--extract`, `mode=ro`,
DB md5 `3ad9664c…` identical before and after): **80,307 records — an exact
round-trip to the baseline of record.**

| | count | share of what runs today |
|---|---:|---:|
| records replayed | 80,307 | |
| blocked today by legacy types | 10,652 | |
| no verdict (timed out) | 52 | |
| **allowed today** | **69,603** | |
| **newly withheld by the flip** | **52,659** | **75.66%** |

**The 75.66% is UNCHANGED — that is the honest headline, and it is deliberate.**
No call that used to run stops running; no call that was refused now executes.
What changed is that the refusals are no longer one undifferentiated number:

| verdict kind | count | share of what runs today | what it means |
|---|---:|---:|---|
| **`gate`** | **11,570** | **16.62%** | hard ceiling — terminal, no auto path exists |
| `propose` | 3,465 | 4.98% | above the bar — withheld, filed, grantable |
| `unclassified` | 37,624 | 54.06% | the classifier cannot see what this is |

Cross-check: `gate` = 6,507 `deploy_prod` + 4,471 `secrets` + 364
`network_write` + 219 `spend` + 6 `credentials_grant` + 3 `external_comms` =
**11,570 — exactly the six hard ceilings and nothing else.** `propose` = 3,459
`deploy_nonprod` + 6 `internal_comms`. Independent confirmation that no ceiling
leaked into a softer kind.

### Does the flip become possible?

**No — and this change does not claim to make it so.** 52,659 calls still do
not execute, so the fleet still cannot run `git commit`, `pytest` or `gh pr
checks` under enforcement. The residual is **54.06% `unclassified`**, and it is
a classifier problem, not an enforcement problem: allowlist widening was
measured to top out at an unusable ~84% only by admitting `gh`, `sudo`,
`python3`, `source` and `tar` — deleting the very property the allowlist
proves.

What this change does establish is that **only 16.62% of what the fleet runs is
a genuine ceiling**. That is the number a per-invocation Bash sub-decider (arm
B's proposal, sequenced second precisely so it could be measured rather than
assumed) has to get down to. Before this, that figure was unknowable.

## 5. Who reads a filed need — answered honestly

There ARE readers, and this change turns two of them on. It does **not** make
the loop closeable, and that gap is stated rather than papered over.

| consumer | what it does | live? |
|---|---|---|
| `tell_digest.py:494` — 🙋 NEEDS leg of the frontdoor briefing | renders open needs | gated on `needs_enabled()` → **now on under enforcement** |
| `attention_drain.py:411` | turns needs into decision cards | same gate → **now on under enforcement** |
| `governance-review.py:847` | prints ledger tail as "pending petitions" | on demand |
| `captain-reminder-arm.py:492` | reads merged needs for the briefing leg | scheduled with the briefing |
| `grant-apply.sh:96` | applies an approved grant | manual, root ceremony |

**The gap, stated plainly:** the Captain's one-tap reply verbs
(`grant NEED-x` / `deny` / `later`) are gated by
`binder_wire.py:720 _needs_wired()`, which reads `CABINET_NEEDS_WIRED == "1"`
**and nothing else** — unlike `attention_drain.py:411`, which delegates to
`needs.needs_enabled()`. This change does not set that variable, so **a filed
need becomes visible but not answerable by reply.** That divergence was left
alone deliberately: `cabinet/services.yml` marks the verb plane dark by design,
and arming a live authority-reply surface is not this unit's call. It is
recorded here as the next question rather than silently fixed.

So: **a filed need is read by the digest and the attention queue, and cannot yet
be actioned from the Captain's phone.** Anyone citing the ledger as a closed
loop is overstating it today.

## 6. A sensor that lied, and the guard now standing on it

The first measurement run reported `legacy_typed: 52659` — every record without
a kind — while printing a clean, plausible 75.66%. Cause:
`_first_block` returned `name, str(result)`, and that `str()` flattened the
subclass. The split was UNMEASURED and the report looked fine.

Fixed, plus a sensor-on-the-sensor: if `authority_matrix` is in the candidate
set and produced blocks, it is impossible for none of them to carry a kind —
the instrument now exits 3 rather than reporting.

Also fixed: `--extract` required a corpus positional it does not use, so the
documented rebuild command failed with a usage error unless given a dummy path.
The measurement was documented as repeatable and was not.

## 7. Adversarial review round — what it broke and what it confirmed

A fresh-context reviewer attacked the change on six axes. Full dispositions in
`shared/interfaces/reviews/fix-propose-means-propose-cp1.md` §Checkpoint 2.

**Confirmed, independently and by execution:** the allow set did not move.
166,656 differential cases through both trees gave `ALLOW pre=20008
post=20008`, **newly allowed = 0**, and zero differing message bytes; an AST
pass found 5 `return None` sites before and 5 after at identical control-flow
positions; a `settrace` run hit every allow line on both trees. The six
ceilings could not be made to allow or to report a softer kind across posture,
quarantine and hostile `classify_action` returns.

**The one finding that mattered, and it is the mirror image of this change's
thesis.** A floor whose `hard_ceiling` is missing, empty or mistyped sent every
ceiling class down to the step-6 collapse — where, *because of this change*,
it was labelled PROPOSE and filed a `capability` need reading *"grant
autonomous external_message for this lane"*. The pre-existing bug was an
undifferentiated block; this change converted it into **grantable headroom on
the Captain's deny surface**. Fixed by fail-closing on the canonical ceiling
set (`classifier.CEILING_CLASS_ACTION_TYPES`) rather than on what the floor
claims. Deliberately narrow: an empty list stays legal for a matrix that
declares no ceiling classes.

**Three deliberately wrong implementations passed the entire 1199-test suite** —
a constant marker path, an unclassified branch that files nothing, and an
infinite refile window. Each destroys something the code comments promise and
none was caught, because every arm used the same probe or the same cell. Three
arms added; each mutant now fails and the control stays green. That is the
difference between a test that describes an implementation and one that
constrains it.

Also fixed: a future-dated marker could mute a need forever (`abs()`); an unset
`CABINET_ROOT` silently disabled the rate limit at 45.65 ms/call vs 3.87;
`copy`/`pickle` raised where a plain `str` round-tripped; an undo-plane outage
filed under the capability wording; and the kind sensor caught only a *total*
coercion, not a partial one.

**Carried forward, not fixed:** `policy-shadow.py:509 authority_decision()`
re-implements the gate and records `propose_only` for both the unclassified
bucket and the quarantine — the same misattribution this change fixes on the
other half of the plane. The measurement above is unaffected (the dry run
recomputes through the real gate), but the recorded field stays collapsed until
that duplicate implementation is removed. And `authority-matrix-dryrun.py` has
no test in any CI step, so the new counter and guards are unpinned.

## 8. Final re-measurement, after master's shell-parser fix merged in

`fix/shell-command-word-parser` landed on master while this branch was in CI
and it changes `_is_provably_local`'s view of the corpus, so the split was
re-measured on the merged tree (same 80,307-record corpus):

| verdict kind | before the parser fix | after | Δ |
|---|---:|---:|---:|
| **`gate`** (terminal ceiling) | 11,570 (16.62%) | **11,570 (16.62%)** | **0** |
| `propose` (above the bar) | 3,465 (4.98%) | **3,465 (4.98%)** | **0** |
| `unclassified` | 37,624 (54.06%) | **37,549 (53.95%)** | −75 |
| **total newly withheld** | 52,659 (75.66%) | **52,584 (75.55%)** | −75 |

**`gate` and `propose` did not move by a single record; the entire delta landed
in `unclassified`.** That is the behaviour the three-kind split was built to
make visible: a classifier improvement should shrink the bucket that means "the
gate cannot see what this is" and leave the two governed buckets untouched. It
is also an independent check on the ceiling classification — a parser change
large enough to reclassify 75 commands moved no ceiling and no below-bar cell.

The conclusion is unchanged: **the flip is still not possible**, the residual is
still ~54% unclassified, and the number a per-invocation sub-decider has to
reach is still **16.62%**.
