# CI cost + a local LLM lens — what was measured, what changed, what did not

2026-07-28. Two asks that pull against each other: hosted CI minutes have become
expensive, and LLM analyzers could run locally for free on the Max pool. The
honest resolution is that they are **two different projects**. One saves money
and touches no coverage. The other buys a new kind of coverage and saves no
money. Conflating them is how the second would get justified badly.

Everything below was measured on 2026-07-28 against the live repository. The
commands are named so a later session can re-run them rather than trust this
file.

---

## 1. What the run history actually says

`gh run list --limit 1000 --created ">=2026-06-28"` → **776 workflow runs**,
714 distinct head SHAs.

| event | runs |
|---|---|
| `push` (master) | 306 |
| `push` (`feat/fidelity-harness-design`) | 132 — all before 2026-07-11 |
| `pull_request` | 319 |
| `schedule` | 19 |

**"Most work runs twice" is false.** Exactly **1 SHA** in 30 days fired both a
`push` and a `pull_request` run. `push:` only triggers on `master` and one
now-dead branch, so a push to a PR branch fires once. The duplication in this
repo is not push-vs-PR; it is temporal — a merge commit re-testing the tree its
PR head was just tested on.

**Billable minutes per run** (sum of per-job wall time, each job rounded up to
the minute, `ubuntu-latest` = 1×):

* 32-run stratified sample across the whole window: **23.8 min/run**.
* 14 most recent completed runs: **60.0 min/run**.

The suite roughly tripled in cost inside the window (2–5 min/run in early July,
56–60 today), so the trailing average understates the forward rate badly. Every
saving below is stated at **today's** weight, which is the only one that
predicts next month's bill.

Where the 60 minutes sit — mean billable minutes over those 14 runs:

| job | min | share | required check? |
|---|---|---|---|
| `framework-tests` | 22.9 | 38% | yes |
| `ci` | 18.0 | 30% | yes |
| `cognitive-phase4` | 11.2 | 19% | **no** |
| `null-hatch` | 3.9 | 6% | yes |
| `clean-room-foundation` | 1.0 | 2% | yes |
| `clean-room-source` | 1.0 | 2% | yes |
| `gitleaks` | 1.0 | 2% | yes |
| `zizmor` | 1.0 | 2% | yes |

**There are SEVEN required checks, not eight.** `GET /branches/master/protection`
returns `ci, framework-tests, clean-room-foundation, clean-room-source,
null-hatch, gitleaks, zizmor`, with `strict: true` and `enforce_admins: false`.
`cognitive-phase4` is 19% of the bill and holds no merge button — the workflow's
own comment says to treat its red as blocking by hand until it is required.

---

## 2. The dedup saving — landed by another session, and not duplicated here

`git rev-parse <sha>^{tree}` vs `<sha>^2^{tree}` over every master push run,
joined to that parent's run conclusions:

| trailing window | master push runs | tree already tested | genuinely new tree |
|---|---|---|---|
| 30 days | 306 | **99 (32%)** | 207 |
| last 7 days | 105 | **66 (63%)** | 39 |

Of the 99, **99 had a completed `conclusion=success` run of this workflow on
the exact parent SHA. Zero exceptions.** That join is the thing worth checking:
tree identity alone would not be enough, because if the PR run had been
cancelled the master push would have been the first complete test of that tree
and skipping it would delete real coverage. It never was. At today's 60.0
min/run and the 7-day duplicate rate, that class is worth **~16,970 billable
minutes a month, about 19.2% of the bill**.

**A concurrent session shipped this first.** PR #272 (`perf/ci-cost`, merged as
`6dfd39ac` while this branch was in CI) added a `tree-dedupe` job that solves
the same problem, measured independently: 122 runs / 3,943 billable minutes,
21.1% of the bill. Two independent skip paths on one workflow is strictly worse
than either alone, so this branch **deleted its own mechanism** rather than
landing a second one. Theirs is broader where it counts — it compares the
pushed tree against the last 40 successful `pull_request` runs rather than only
the pushed commit's second parent, and it accepts evidence ONLY from
`pull_request` runs, which closes the chain where a skipped (and therefore
"successful") run becomes the evidence for skipping the next one.

### What this branch contributes instead: the precondition, made executable

`tree-dedupe`'s safety argument rests on two claims in its header, and the
second one is not true by construction:

1. *"A pull_request or schedule run can NEVER be skipped."* This is the claim
   that matters, because GitHub reports a job skipped by an `if:` as
   **successful** to branch protection — a condition that went false on a PR
   would show a green merge button over a tree nothing ran on.
2. *"A run-level `success` … means all eight jobs ran and passed."* GitHub does
   not guarantee that: a run concludes `success` when jobs are merely skipped.
   It is true here **only because of claim 1**.

Both are properties of expression strings in a YAML file — the kind of thing
that decays silently the next time someone adds a condition. So
`cabinet/scripts/tests/test_ci_dedupe_cannot_skip_a_pr.py` evaluates the real
`if:` expressions under a simulated `pull_request` context, for every value the
dedupe output can take, and the workflow comment now states the precondition
instead of asserting the conclusion.

Non-vacuity, both directions:

* the same evaluator must report the gate jobs as **skipped** on a master push
  with `skip=true` — so it measures the mechanism rather than agreeing with it;
* nine mutation arms strip the event guard out of each gate job in turn and
  require the check to fail;
* the evaluator itself has arms in both directions, refuses any expression node
  it does not model rather than guessing, and parses via a restricted AST walk
  rather than `eval`;
* run against the pre-`tree-dedupe` workflow (`a70bcfb5`) three arms **FAIL**,
  so the file is wired to the live artifact rather than to a fixture.

## 3. What did NOT land, and why

### A self-hosted runner on the Captain's machine — refused

Not on principle; on three independent grounds, any one of which is fatal.

1. **The expensive work physically cannot move.** The three jobs holding 87% of
   the bill all declare Docker `services:` — `redis:7` (`ci`),
   `redis:7-alpine` + `postgres:17` (`framework-tests`), `redis:7`
   (`cognitive-phase4`). GitHub Actions does not support service containers on
   macOS runners. Moving the four cheap jobs instead buys ~8% of the bill and
   sells the enforcement plane for it.
2. **Two jobs would damage the live machine.** `clean-room-source` runs
   `rm -rf "$HOME/.screenpipe"` and then `chmod 000` on it — on that box, that
   is the real vault. The redis-touching jobs `SET`/`DEL` `cabinet:killswitch`
   on 6379, which is the live fleet's port.
3. **It converts the last agent-independent record into agent-controlled
   territory.** A runner at the uid where agents already operate can have its
   checkout edited between checkout and test, its PATH shadowed, its pip cache
   poisoned, or its registration credential read and replayed — all invisible
   from the GitHub side, which would show a plausible green log. The hosted
   plane's value here is not unbypassability (`enforce_admins: false`; 207
   direct pushes to master in 30 days prove it binds the PR path only). Its
   value is that the record is **third-party attested**: a red on master cannot
   be quietly made green. That is the substrate the whole program's evidence
   discipline rests on.

So: **nothing moved to the local machine.** All eight jobs stay on
`ubuntu-latest`. That is a complete result, not a gap.

### Removing the dead `feat/fidelity-harness-design` triggers — declined

The branch's last push was 2026-07-11 and it burned 132 runs early in the
window, but it is quiet now, so removing the trigger saves ≈0 going forward
while removing coverage from a branch that still exists. Not worth it.

### Touching the concurrency block — declined

It is already correct: per-SHA groups on master, so a push train can never
cancel the run that would have caught a regression, and ref-scoped
`cancel-in-progress` everywhere else. Extending cancellation to master would
reproduce a failure this repo has already paid for — a `timeout-minutes` hit
reports as `cancelled` and was read as a mystery red.

### Caching apt/pip — declined on measurement

`cache: pip` is already enabled in the four jobs with a `setup-python` step.
Step timings on a recent green master run put "Install system deps" at 10s,
"Install redis-cli + redis-server 8 + psql client" at 19s, "Setup Node" at 10s.
Total install overhead is well under a minute per run, not the several minutes
it was assumed to be. The real time is real work: "Cabinet script tests"
1,134s, "COG-4 exit gate" 633s, "Dashboard vitest" 361s, "Hook regression
harnesses" 355s. Cutting those means changing what is tested, which is exactly
the trade this refuses to make.

### Left for a decision, deliberately not taken here

* **`cognitive-phase4` is 19% of the bill and is not a required check.** Either
  wire it into branch protection (the spend is then justified) or scope it to
  `push` + nightly (~3,000 min/month back off PR iterations). Leaving it as-is
  is the only option that is wrong either way. Changing branch protection is
  not this change's business.
* **`enforce_admins: false`.** 207 of 306 master runs in 30 days were direct
  pushes that never faced the required checks; 60 of them went red on master.
  The repo's own plan already carries this as `CI-STRICT-ENFORCE` and it is
  still `todo`. Flipping it would strengthen the gate *and* remove the
  duplicate class this guard has to work around — but it changes how every
  other session pushes, so it is the Captain's call, not a side effect of a
  cost PR.

---

## 4. The LLM half: an agnosticism advisor, local and advisory

`cabinet/scripts/agnosticism-advisor.py`, on the OAuth/Max pool through
`framework/fidelity/oauth_llm.py` — a `claude -p` headless agent, no
`ANTHROPIC_API_KEY`. Model pinned to `claude-opus-5`.

**The line: an LLM verdict may create WORK. It may never create PERMISSION.**
That is already this repo's ratified division — the world-render judge carries
"the judgment half" beside deterministic gates, and the scoring pins say it
twice ("only verdict\_human promotes"; "machine/judge artifacts never promote a
mission edge"). This extends the pattern; it does not invent one.

### The one question it answers

*Does this change teach the framework about a specific tool, industry, role,
organisation, product, jurisdiction or person?*

A grep provably cannot answer it. The deterministic half already exists and
stays authoritative — `cabinet/scripts/check-layer-separation.sh` catches
`framework`→`instance` imports and path coupling;
`framework/tests/test_no_launcher_hardcode.py` is a shrink-only ratchet over
banned literals. Both answer "does this text contain a token I already know to
ban?" The tracked patterns in that ratchet are **synthetic placeholders** by
design, precisely so the shipped source names nobody real, and its real-token
half lives in an untracked, gitignored file. So a brand-new real-world proper
noun landing in `framework/` today is invisible to every tracked sensor. The
ban-list *is* the answer being sought — which is the shape of question a reader
can answer and a pattern-matcher cannot.

### Where it must never go

Not a required status check. Not a CI job. Not in front of any question a
deterministic check can answer — a digest, a set comparison, a secret scan, a
syntax check, a ratchet, ledger parity, the germline set. If a deterministic
check is merely *hard to write*, that is an argument for writing it. A required
check has to be reproducible from bytes alone; this is not.
`test_the_advisor_is_not_wired_into_any_workflow` keeps that mechanical.

### The three ways an LLM lens rots, and the answer to each

**(a) It becomes a rubber stamp.** `--calibrate` scores a planted corpus with
recorded ground truth (`cabinet/scripts/agnosticism-corpus/manifest.yml`),
**blind** — fixtures are presented under opaque `item-<hash>.txt` names, so the
judge cannot read the answer off a path (pinned by an arm that asserts no
`known_bad` / `known_good` / fixture-name token reaches the model). Missing one
planted violation VOIDs the run. Flagging more than one clean fixture VOIDs it
too. **Both directions**, because a one-sided floor leaves the other free to
rot: a stub answering "agnostic" to everything and a stub answering
"instance-specific" to everything both VOID, and both are pinned as tests. An
oracle stub PASSES, so the floors are provably satisfiable rather than merely
unreachable. A degenerate corpus — no plants, or no clean set — VOIDs rather
than passing vacuously.

**(b) It flakes.** Model id pinned; rubric and corpus hashed into a digest
recorded with every verdict; output schema-constrained JSON; `--votes N` takes
a majority; verdicts cached by (rubric digest, content hash) so a re-read
replays and a re-decision is impossible without changing the rubric or the
bytes. An unparseable or absent answer is `error`, **never** `agnostic` —
"nothing came back" must not read as "nothing found". Residual flake costs a
re-read, because the lane is advisory.

**(c) It judges its own judge.** Any run whose input set touches the advisor,
its rubric or its corpus **ABSTAINS**, without calling the model at all.

### Measured, against the real model

`claude-opus-5`, rubric digest `2a7e29461e6a`, two independent calibration
passes with the cache disabled, then a sweep over twelve ordinary
`framework/**/*.py` modules picked by seeded sample (60–400 lines, no tests).

| | pass 1 | pass 2 |
|---|---|---|
| planted violations caught | **8 / 8** | **8 / 8** |
| clean fixtures wrongly flagged | 1 / 8 | 1 / 8 |
| verdict | CALIBRATED | CALIBRATED |
| wall clock (16 calls) | 114.5s | 109.4s |

**Row-level agreement across the two passes: 16/16.** Every fixture got the
same verdict twice, including the false positive — this judge's residual
non-determinism did not show up at all at this corpus size, which is a
measurement, not a guarantee.

**The false positive is stable and understood**: `known_good/ci_helper.txt`
(a helper that reads the repo's own GitHub Actions workflow) was called
instance-specific in both passes. The rubric carves out "infrastructure the
framework itself runs on", and the model applies that carve-out conservatively.
It is inside the corpus budget of one and it is left as-is rather than tuned
away: tuning a rubric until the corpus goes green is how a calibration set
turns into a fixture that agrees with the judge's defect. It also errs in the
safe direction for an advisory lens — over-flagging infrastructure rather than
under-flagging identity.

**Sweep over ordinary work: 4 of 12 modules flagged, 0 unreadable, 121s.** That
is a discovery rate, not a false-positive rate. Every one of the four was
checked by hand against the source and every one cites a literal that is
actually there:

| module | what it names | present at |
|---|---|---|
| `framework/comms/tools.py` | one messaging vendor's constraints in channel-neutral core | `:20`, `:135` |
| `framework/learning/self_proposal.py` | a specific automation vendor and one operator's mail/chat flow | `:371`, `:372` |
| `framework/acting/lane_dedup.py` | three named correspondents and a deal artifact, as docstring rationale | `:103`, `:138`, `:161` |
| `framework/acting/draft_queue.py` | a named correspondent's incident as docstring rationale | `:6` |

**On that same tree `check-layer-separation.sh` reports no new violations and
`framework/tests/test_no_launcher_hardcode.py` is 21/21 green.** Both are
working correctly — none of these are the couplings they were built to catch.
That gap is the whole argument for this lens, and these four findings are the
first thing it produced. They are findings, not a gate: nothing here blocked,
and the follow-up belongs in the backlog rather than bolted onto a cost PR.

### How to use it

```
python3.12 cabinet/scripts/agnosticism-advisor.py --calibrate
python3.12 cabinet/scripts/agnosticism-advisor.py --diff origin/master
```

Run it locally before opening a PR — by hand, from a Claude Code hook, or from
the orchestrator. Findings go in the PR body or a review artifact and a human
acts on them. It saves zero CI minutes, and saying otherwise would be the
dishonest way to justify it.
