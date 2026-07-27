# Is the value the ingest, or the aggregation? — employee-slice measurement

**Date:** 2026-07-26
**Question under test:** the First Window sweep reads an operator's folder and
produces one cited finding. Does a cross-system sweep surface anything a
developer inside a large organisation could not already get by pointing a
coding agent at their own repo and tracker? Is the value the **ingest**, or
merely the **aggregation** across systems?

**Why this ran before any engine was built.** The programme already carries a
disabled research-sweep service whose stated reason is that it produced briefs
nobody consumed, an unconsumed belief engine, and a five-stage formation
pipeline in which every stage writes "not yet built". A vault-building sweep
that lands without a consumer would be the fourth dead substrate. The cheapest
way to find out is to build one more fixture and run the detectors that
already exist.

---

## Verdict

**The value measured here is neither the ingest nor the aggregation — it is a
small cross-source join, and the current sweep does not perform one.** Of the
four findings the real detectors produced on a realistic employee slice, one
required more than one file and none required more than one system in any
sense a `git grep` across two folders would not also satisfy; every fact in
the estate that genuinely only exists in the join between the repo, the
tracker and the docs space was invisible to all three detectors. The
hypothesis that ingest is the value is **refuted at this altitude**. The
correct first build is a small cross-source join with a named consumer, not a
vault.

A second result, not asked for and more serious than the first, is recorded in
§5: at realistic employee scale the sweep's file cap can make it report that
it did **not** find a broken documented command while exactly such a command
sits unopened in the folder.

---

## 1. What was built

`framework/onboarding/fixtures/enterprise-employee/` — a fourth estate for the
existing persona harness, deliberately shaped as an employee's slice of a large
organisation rather than an owner's view of a whole business.

```
enterprise-employee/
  README.md                                  the operator's own note on the slice
  repo/                                      a service they contribute to, do not own
    README.md  CODEOWNERS  package.json
    config/features.yaml
    src/ledger/reconcile.ts
    docs/adr/0007-dual-write-retirement.md
  tracker/                                   a weekly CSV export of their rows
    my-open-tickets.csv  sprint-42-export.csv
  docs/                                      partial sync of a shared docs space
    design/ledger-migration-plan.md
    incidents/2026-06-18-ledger-lag.md
    notes/2026-07-14-ledger-sync.md
    runbooks/deploy-ledger-api.md
    runbooks/ledger-api-oncall.md
    team/roster.md
```

15 files on disk, 14 scanned, 5,979 bytes. Entirely synthetic: an invented
service, invented team handles, no real organisation, person or material.

**Authoring-bias disclosure.** The detectors were read before the fixture was
authored, so no claim of detector-blindness is available. Two content elements
were placed knowing a detector exists: the stale `npm run migrate:ledger` in a
runbook, and the `BLOCKED:` / `Action required:` lines in the incident and
meeting notes. Both are the commonest forms of real doc rot, but the
declaration matters more than the justification. Everything else was written
to the shape of the artefact type. In particular the dates were written the
way each artefact really writes them, **without** arranging a same-label
duplicate, and that was predicted to produce a miss.

**The fixture was not tuned.** Eight predictions were registered in writing
before the first run; all eight landed on the first execution. No content was
changed to produce a hit, and none should be. The fixture README says so, and
`test_employee_estate_planted_cross_system_facts_are_all_present_but_unfound`
asserts each planted join is still present in the bytes and still absent from
the findings, so a later tuning edit trips a test.

### Why the estate is not registered as a fourth acceptance persona

It was, and the registration was reverted. This is worth recording, because the
obstacle is structural rather than editorial and it will block the next person
too.

`framework/onboarding/evaluate_personas.py` is a framework **production**
module: the census counts every `framework/**/*.py` outside a `tests` path.
`framework_production_noncomment_lines` is pinned at **observed == max with
zero headroom by design** — the structural-compaction mutant gate requires it,
so that any growth is caught. Registering one persona costs one non-comment
line, which reds the census.

The contract provides `temporary_allowances` for exactly this, and an entry of
`additional: 1` was written and verified green. But
`cabinet/config/cognitive-architecture-contract.yml` is inside
`EXPECTED_SCOPE` in `cabinet/scripts/cognitive-phase4-review-scope.py`, so
editing it invalidates the `Reviewed-Scope-Digest` recorded in the frozen COG-4
review artifact, and `verify-cognitive-phase4.sh` blocks with *"reviewed bytes
!= tested bytes"*. Re-stamping that digest would record a review of bytes no
reviewer saw, which is not a thing to do to make a test pass.

So while the COG-4 review is frozen, **the framework production line count
cannot change in either direction** — growth needs an allowance and shrink
needs a tightened maximum, and both live in the frozen file. The estate is
therefore exercised by `framework/onboarding/tests/test_journey.py`, which
costs nothing (a tests path is excluded) and drives the same `journey.act`
propose→ratify path the harness drives. Register it when the budget can move.
The fixture directory itself was always free: 15 files of
`.md`/`.json`/`.csv`/`.ts`/`.yaml`, and the census counts only `*.py`.

---

## 2. The raw finding list

Produced by the real detectors (`journey._command_drift`,
`journey._contradictions`, `journey._risk_markers`) over the real scanner's
entries (`journey._scan_source`). `_first_dividend` returns only the
top-scored finding; all four are listed here.

| # | Kind | Score | Cited at | Would the operator already know? | Needed >1 file? | Needed >1 system? |
|---|---|---|---|---|---|---|
| 1 | `software_command_drift` | 100 | `docs/runbooks/deploy-ledger-api.md:8` — "Run `npm run migrate:ledger` against staging" | **Probably not.** A contributor who never cuts releases has no reason to have run the release runbook. Genuine. | **Yes** — the doc plus every `package.json` in the window | **Nominally** — the doc tree and the repo tree. But this is one `git grep` over two folders, and a coding agent pointed at the repo with the wiki checked out finds it. |
| 2 | `attention_marker` | 80 | `docs/incidents/2026-06-18-ledger-lag.md:20` — "BLOCKED: the alerting work needs a metrics pipeline change…" | **Yes.** They wrote the incident note. | No | No |
| 3 | `attention_marker` | 80 | `docs/notes/2026-07-14-ledger-sync.md:7` — "Action required: someone has to own the on-call rota review…" | **Yes.** They were in the meeting. | No | No |
| 4 | `open_work_marker` | 50 | `repo/src/ledger/reconcile.ts:2` — "TODO: emit a lag metric here…" | **Yes.** They wrote the TODO, and it is one `git grep TODO` away. | No | No |

**Decisive column: findings requiring more than one system = 0**, on the
strict reading (a fact that exists in neither source alone and cannot be
recovered by grepping one directory tree). **= 1** on the generous reading
that counts the docs tree and the repo tree as two systems. Either way the
answer is not the one that would justify building a vault.

**Three of four findings are things the operator wrote themselves.** The
marker detectors do not find knowledge; they find the operator's own
handwriting. That is a real property of the estate, not an artefact of this
fixture: an employee's docs slice is mostly text they or their immediate team
authored.

---

## 3. What the detectors missed

Five facts were planted that a human at this altitude would obviously want.
**All five are invisible to all three detectors.** Each names a detector that
does not exist.

| Missed fact | Where it lives | Why no detector sees it | The detector that does not exist |
|---|---|---|---|
| The on-call runbook step 2 tells you to set `ledger_dual_write=false`. The repo deleted that flag; `config/features.yaml` does not contain it, ADR-0007 retired it, and the June incident records that the step did nothing and cost twenty minutes. | `docs/runbooks/ledger-api-oncall.md` × `repo/config/features.yaml` × `repo/docs/adr/0007-…` | No detector relates an identifier named in prose to the code or config that defines it. | **Referenced-identifier liveness**: a symbol a document instructs you to use, that the code no longer defines. This is `software_command_drift` generalised beyond `package.json` scripts, and it is the single highest-value missing detector. |
| The incident's action item "write down the manual replay procedure, owner @eng-kestrel" has no ticket in either tracker export. | `docs/incidents/…` × `tracker/*.csv` | Nothing compares commitments in prose to rows in a structured export. | **Untracked-commitment join**: an owned action item in one system with no counterpart in another. |
| `LEDG-4501` is assigned to `@eng-briar`, whom the roster says moved teams on 2026-07-01 and is on no payments rotation. | `tracker/sprint-42-export.csv` × `docs/team/roster.md` | No detector reads a CSV as records, and none knows a roster is an authority on people. | **Orphaned-assignment join**: work assigned to someone a roster says has left. |
| The design doc says `Deadline: 2026-09-30`; the tracker says `LEDG-4462` is due `2026-10-14`. A real, current, cross-system date conflict. | `docs/design/ledger-migration-plan.md` × `tracker/my-open-tickets.csv` | `_contradictions` matches only `^label: value` prose lines and compares within one normalised label. A CSV cell is not that shape, and one prose `Deadline:` line alone is not a conflict. | **Structured-export awareness**: parse CSV/TSV headers and compare typed columns against prose claims. |
| The runbook pages `@payments-platform`; the repo README and the roster both say the owning team is `@platform-core`. Whom do you page at 03:00? | `docs/runbooks/…` × `repo/README.md` × `docs/team/roster.md` | No detector models ownership or escalation. `CODEOWNERS`, the densest ownership file in any repo, is not even readable (see §4). | **Ownership/escalation coherence**: one service, more than one claimed owner. |

Two further blind spots the fixture exposes without being planted:

- **`Blocked` as a status value is invisible.** `LEDG-4488` is `Blocked` in both
  exports and has not moved since 2026-07-09. The urgent regex is anchored at
  line start, and a CSV row starts with a ticket key. The detector finds the
  word "BLOCKED" when a human typed it in a sentence and misses it when a
  system recorded it as state.
- **The vocabulary is three detectors wide**, and two of the three
  (`attention_marker`, `open_work_marker`) are keyword markers that a `git
  grep -E 'TODO|FIXME|URGENT|BLOCKED'` reproduces exactly. Only
  `software_command_drift` does work grep cannot.

---

## 4. What the sweep cannot read at all

`repo/CODEOWNERS` is the one excluded file in this fixture
(`unsupported_type: 1`): it has no suffix and is not in `ALLOWED_BASENAMES`
(`readme`, `license`, `dockerfile`, `makefile`, `procfile`). The most
ownership-dense file in a large-org repository is unreadable to the First
Window. `.github/` — CODEOWNERS' other conventional home, along with workflow
and template metadata — is excluded wholesale by the hidden-path rule.

---

## 5. What the caps lose — and a claim the sweep is not entitled to

The sweep caps at 200 files, 2 MB total, 128 KB per file. An employee's slice
is much larger than a founder's whole world, so the caps were measured rather
than reasoned about: a synthetic slice was generated and run through the real
`_scan_source`.

**The slice** (conservative — a real monorepo checkout is an order of magnitude
larger): 900 wiki pages at 6 KB, 1,200 service source files at 4 KB, a 5,000-file
`node_modules` (correctly skipped), one `package.json`, and two tracker
exports, the larger a 6 MB sprint history.

| Measure | Value |
|---|---|
| Files on disk | 7,103 |
| Files eligible after type and skip-dir rules | 2,103 |
| **Files actually scanned** | **200** |
| Eligible bytes on disk | 12.6 MB |
| **Bytes actually scanned** | **963 KB** |
| **Share of eligible files seen** | **9.51 %** |
| **Share of eligible bytes seen** | **7.48 %** |
| Top-level directories with zero coverage | `repo/`, `tracker/` |
| 6 MB tracker export scanned? | No — over the 128 KB per-file cap regardless of slots |

**The cap is resolved by alphabetical walk order, not by relevance.** Both
`dirnames` and `filenames` are sorted, so the first directory encountered
consumes all 200 slots. `docs/` starved `repo/` and `tracker/` completely.
Renaming `docs/` to `wiki/` inverts it: `repo/` takes all 200 slots and the
wiki and tracker get nothing. Which finding an operator receives depends on
what their folders are *named*.

**The claim the sweep is not entitled to.** In both orderings, a stale
documented command and the `package.json` that refutes it were **both present
on disk** — and `_command_drift` fired **zero** times in both, because the cap
never admits the pair together. The card the operator sees then says:

> "I mapped 200 supported files but did not find a strong contradiction,
> broken documented command, or explicit urgent marker. That is an honest
> orientation result, not a manufactured warning."

At this scale that sentence is false, and the word "honest" is doing work it
has not earned. The sweep did not fail to find a broken documented command; it
never opened the file that would have proved one.

**The loss is not disclosed to the operator.** `truncated_by_limits` is set
correctly on the manifest, but the `dividend_ready` card carries only title,
body and citations — no coverage figure, no truncation flag. Worse, the
statistic that should reveal the loss conceals it: once the cap trips, the scan
stops counting candidates, so `scan_statistics` reports
`candidate_files == included_files == 200` with **zero** exclusions. Read on
its own it looks like complete coverage of a 200-file folder.

This behaviour is now pinned by two tests in
`framework/onboarding/tests/test_journey.py` — a control arm proving the
detector *does* fire when both halves are in the window, and a capped arm
proving it does not and that the card says so cleanly. A coverage, ranking or
disclosure fix will flip the second.

> **FIXED 2026-07-27** (three-entry-modes unit). The second arm flipped, as
> designed, and was inverted in place to
> `test_capped_window_reads_by_relevance_and_keeps_the_cross_directory_join`.
> Three changes in `journey._scan_source` / `journey._first_dividend`:
> **(a)** the scan is two passes, so it counts the whole tree instead of
> stopping at the cap — `candidate_files == included_files` with zero
> exclusions is no longer reachable while files are being dropped;
> **(b)** the bounded read is spent in **relevance order** (`_relevance_key`,
> path-and-name only, never file content), and the manifest files that the
> join detectors need are read first — `_command_drift` returns nothing at all
> without a `package.json`, so a manifest file that never fit was a silently
> disabled detector, not a weaker result;
> **(c)** the negative is **earned or scoped** — the manifest and dividend
> carry a `coverage` block, the sentence quoted above is only produced when
> `coverage.complete` is true, and otherwise the card states how many eligible
> files were left unopened. Ranking narrows the loss but cannot abolish it, so
> the disclosure is the part that has to hold; that half is pinned separately
> by `test_a_truncated_window_never_states_a_negative_it_did_not_earn`.

---

## 6. Answers to the four questions

1. **Does it surface anything the operator did not already know?** One of four
   findings, and only for an operator who has never followed the release
   runbook. The other three are their own handwriting.
2. **Which findings required more than one source?** One of four required more
   than one file. Zero required more than one system in any sense that a grep
   across two directory trees does not also satisfy.
3. **What did the detectors miss?** Five planted cross-system facts, all of
   them; plus structured-export status and, structurally, `CODEOWNERS`. The
   named missing detectors are in §3, the most valuable being
   referenced-identifier liveness and the untracked-commitment join.
4. **What do the caps lose?** 90.5 % of eligible files and 92.5 % of eligible
   bytes on a conservative employee slice, allocated alphabetically, with two
   of three systems receiving zero coverage, no disclosure on the card, and a
   scan statistic that reads as full coverage.

---

## 7. What this implies for the build

- **Do not build the vault first.** Ingest at this altitude buys 9.51 % coverage
  of an estate and a finding list dominated by the operator's own markers.
- **Build the join, small, with a named consumer.** The three highest-value
  missing detectors — referenced-identifier liveness, untracked-commitment
  join, orphaned-assignment join — are all *relations between two named
  sources*. None needs a vault, an embedding index or a belief engine. Each
  needs two parsers and a comparison.
- **Relevance ranking is a prerequisite, not a later optimisation.** A cap
  resolved alphabetically is not a budget, it is a coin flip. Any join
  detector inherits this defect: it will silently never see one of its two
  sides.
- **The acceptance harness cannot express an honest null.** `evaluate()`
  requires `finding["quality"] == "strong"` to pass, so a persona whose honest
  outcome is orientation-only cannot be added without failing the gate. Every
  persona in the suite is therefore, by construction, one that produces a
  strong finding. That is a mild version of the bias this experiment was sent
  to look for, and it is worth fixing before more personas are added.
- **The persona set cannot currently grow at all**, for the reason in §1: one
  line against a zero-headroom budget whose contract is frozen under a review
  digest. Whoever unfreezes COG-4 should register `enterprise-employee` in the
  same window.

---

## 8. What could not be settled

- **Whether a join detector's findings would be worth the operator's
  attention.** This measured what the *current* detectors find. The claim that
  referenced-identifier liveness would be valuable is an inference from the
  fixture, not a measurement; it needs its own experiment against a real
  estate.
- **Generality.** One synthetic slice, authored by someone who had read the
  detectors. It is evidence about the detector vocabulary, not a survey of
  employee estates.
- **Whether the caps are wrong or merely small.** Raising them trades against
  the read-only promise and the five-minute target. This report measures the
  loss; it does not price the alternative.
- **A latent robustness issue, not chased down.** `_scan_source` requires an
  already-resolved source path. Given an unresolved one — anything reached via
  a symlinked parent, which on macOS includes `/tmp` and `/var` — every file is
  counted `unreadable_or_raced` and the caller receives an empty manifest with
  `truncated_by_limits: false`, indistinguishable from an empty folder. The
  production path resolves in `_validate_source`, so this is currently guarded
  by its only caller. It is recorded here because the failure is silent and the
  guard is one refactor away from being removed.

---

## 9. Reproducing this

```sh
find . -name __pycache__ -type d -prune -exec rm -rf {} +
PYTHONDONTWRITEBYTECODE=1 python3.12 -m pytest framework/onboarding/tests/test_journey.py -q
```

The employee estate is driven through the real `journey.act` propose→ratify
path by `test_employee_estate_yields_a_strong_cited_finding_through_the_real_journey`;
the finding counts in §2 are pinned by
`test_employee_estate_findings_are_dominated_by_single_source_markers`, the
anti-tuning guard by
`test_employee_estate_planted_cross_system_facts_are_all_present_but_unfound`,
and the cap behaviour in §5 by
`test_uncapped_window_finds_the_cross_directory_command_drift` plus
`test_capped_window_reads_by_relevance_and_keeps_the_cross_directory_join`
(named `test_capped_window_reports_a_clean_negative_it_did_not_earn` until the
2026-07-27 fix inverted it — see the FIXED note in §5).

The harness output that produced §2's table, captured while the estate was
briefly registered as a fourth persona (reverted for the reason in §1):

```json
{"persona": "enterprise-employee", "passed": true, "elapsed_seconds": 0.0454,
 "finding_kind": "software_command_drift", "expected_kind": "software_command_drift",
 "summary": "The documentation tells someone to run \u201cmigrate:ledger\u201d, but no package.json in the approved folder declares that script. ...",
 "citations": [{"path": "docs/runbooks/deploy-ledger-api.md", "line": 8,
   "excerpt": "- Run `npm run migrate:ledger` against staging and check the row counts.",
   "sha256": "d39313480f46e8d315896247aab0cfb4bba4dfd14e1049bd611f554c51832a21"}],
 "charter_hash": "73c167090be8cd38fad7c60f9b7be553b6222d04a544129081dd3726068c9cdf",
 "manifest_hash": "198946d743114e71e06bf00b4055a7ee344ec0045bc3fb56c5cfbcbe7ab1d570"}
```

The other three personas were byte-identical across that registration —
verified by running the pristine tree and the modified tree at the same
filesystem path and diffing every field except wall-clock and the run-volatile
`card_id` segment.
