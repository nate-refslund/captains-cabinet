# Checkpoint review — feat/onboarding-entry-modes cp1

Reviewed-Scope-Digest: abf710e5e27aa3519a49fad20e2be0b278142b574fb0aa34a18a36871e69f2a4

Verdict: PASS

Unit: three entry modes, and never a dead end (Captain ruling 2026-07-26,
adjudicated in the ALTITUDE direction gate — two blind arms, Fable 5 + Opus 5).
Reviewed by a fresh read of the staged diff against the pre-change module, with
every claim below re-run this session on this branch.

## What changed, and the defect each change closes

**1. The welcome card was a single locked door.** `_card()` at `welcome`
offered exactly one option — `propose_window`, "Choose a folder" — and named no
alternative. An operator with nothing to grant, or nothing they were *allowed*
to grant, had no path at all. `orientation_offered` was worse: pause, revoke and
purge, three ways to stop and none to go on, under a body that says the work "is
disabled and has not started".

`entry_plan()` now classifies what has actually been granted into
`connected` / `seeded` / `ungranted` and returns the opening move for that
class. `next_actions` is non-empty in all eight grant combinations —
`propose_window` is the floor, because a folder is the one grant an operator can
always make — and both cards now carry the plan plus a plain statement of what
this cabinet cannot know. `orientation_offered` gained `propose_window`, which
is what stops it being terminal.

**2. The residual questionnaire asks nothing the data answers.** Four
questions: rights, salience, limits, purpose. None is org-shaped, and a
forbidden-prompt list is asserted, not merely commented — a later author adding
"what does your company do" flips
`test_the_residual_questionnaire_never_asks_what_your_company_is`.
`grant_rights` is declared `NEVER_DERIVABLE` and appears in the cannot-know list
of *every* mode including the fully connected one, because connecting more
sources never answers who is entitled to grant them.

**3. The seed question is a seed, not an interview answer.** `seed_probes()`
turns a few words into typed discovery probes, deterministically and with no
model. A probe is emitted only for a grant that exists: no web grant, no web
probe. The module still makes zero network calls, so what comes back is the
plan, and the docstring says so rather than implying a search ran.

**4. The sweep told the operator a negative it never earned.** Measured
2026-07-26 (`docs/persona-employee-slice-2026-07-26.md` §5): 200 of 2103
eligible files, allocated ALPHABETICALLY, all from one top-level directory, two
of three systems with zero coverage — and then the card said it "did not find a
strong contradiction, broken documented command, or explicit urgent marker"
while exactly such a command sat unopened. The statistic that should have shown
the loss concealed it: the scan stopped counting candidates once the cap
tripped, so `scan_statistics` read `candidate_files == included_files` with zero
exclusions, indistinguishable from complete coverage.

Three fixes, all in `_scan_source` / `_first_dividend`: the scan is two passes
so it counts the whole tree; the bounded read is spent in relevance order
(`_relevance_key`, path and name only — nothing is read to decide what to read,
so file *content* cannot steer the window); and the negative is earned or
scoped, gated on a new `coverage` block carried on both the manifest and the
dividend.

## Attacks run against the change

- **Does each arm fail against pre-change code?** Yes, both directions, cache
  purged. The five coverage/ranking arms were extracted into a probe file and
  run against a worktree at `91faed1b`: 5 failed / 65 passed. The entry-mode
  arms fail at collection there (`module 'journey' has no attribute
  'ENTRY_MODE_UNGRANTED'`). The vitest arm was run against the pre-change
  component: 1 failed / 2342 passed.
- **The degenerate end.** `coverage.complete` is asserted true on an untruncated
  window and false on a capped one; a seed of `None` / `""` / whitespace / pure
  stopwords / a non-string yields no terms and no probes, and the plan still
  returns a next step; a truthy-but-not-`True` grant (`"yes"`, `1`) is NOT a
  grant.
- **Can the sensor be steered?** Ranking is content-blind by construction and
  the manifest is asserted byte-identical across two runs over one tree.
- **Is the fix partial in a way that relabels the rest as covered?** Ranking
  narrows the loss; it cannot abolish it. That is why the disclosure half is
  pinned separately at `MAX_FILES = 1`, where no ordering can hold both halves
  of a join.

## The one structural change, stated plainly

`test_act_bytestream.py` compared the pre-migration snapshot against the LIVE
module. That made a claim about a historical commit ("4467476f changed no
behaviour") depend on every future commit, and so froze the onboarding product
surface permanently — the first deliberate behaviour change reds it, and the
only exits are to weaken the gate or abandon the change. Measured here: the
divergence reaches `events.jsonl`, the anchor and the watermarks, because the
manifest hash chains into the evidence hash chain, so no narrowing or declared
field-delta can preserve byte identity.

Both sides are now frozen: the post-migration snapshot at `4467476f` is
vendored beside the pre-migration one, so the R-8 claim is byte-exact and true
forever. Nothing was removed. Two arms were ADDED: a negative arm proving the
comparison still rejects a diverged stream (one changed constant in a throwaway
copy), and a live arm asserting today's journey still produces a complete,
hash-chained, signed, verifiable evidence stream across the same twelve-step
scenario. A comparison never seen to fail is a green tick, not a gate; it had no
such arm before.

## Budget

`framework_production_noncomment_lines` +386, measured with
`cognitive-architecture-census.py` against master `91faed1b` (69654, itself at
the pinned maximum) → 70040. Paid as a `temporary_allowances` row with the
closed key set. ZERO new modules (244 unchanged): the entry classifier lives in
the module that owns the entry surface rather than in a new file wired back to
it. Docstrings are counted as written. The contract file sits inside the COG-4
frozen-review digest scope, so the re-bind rides this same commit.

## Verification run this session

- `framework/` suite: 7119 passed, 1 failed — `test_retro_shim.py::
  test_reexports_constants`, the known pre-existing red, unrelated to this diff.
- `cabinet/scripts/tests` 4890 passed; `task_adapters` 38; `world-aesthetic` 87;
  `cabinet/scripts/lib/tests` 469.
- Dashboard `tsc --noEmit` clean; vitest 2343 passed.
- Golden evals 32/32. Layer separation: 0 new. cog2 import gate OK.
  `verify-cognitive-architecture.sh` PASS. A13 parity OK (353 ids).
  Docs sweep GREEN. Ledger status-parity GREEN.
