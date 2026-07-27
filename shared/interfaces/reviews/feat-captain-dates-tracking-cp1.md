# FW-019 checkpoint review — feat/captain-dates-tracking (cp1)

**Unit:** dated-commitment tracking for the Captain — a date he sets must be
impossible for the org to forget.
**Origin:** `designs/captain-perspective-retro-2026-07-26.md` (cabinet-meta),
§4 addendum, dry-run **finding 1**: the Captain set a release date and it
appeared in **zero** of the next twelve days of briefings, verified at the time
by reading the briefing contents directly.
**Authority:** Captain GO 2026-07-27 on the queued Captain-Seat follow-ups
(captain-decisions officer-note 2026-07-26T23:05:00Z); per 2026-07-07
full-autonomy grant + 2026-07-21 ownership-on-GO.
**Base:** fresh clone of origin, tip `a55dea44` (`Merge pull request #209`);
the availability-dial merge `ac56ce78` (PR #210) is an ancestor.
**Size:** ~2.4k inserted lines across 22 files, of which ~1.0k are tests and
fixtures and ~0.2k are docs. Over the FW-019 300-line threshold, hence this
artifact.

## What the failure was, mechanically

The briefing had two dated legs and neither was his: `commitment_items` renders
dated promises he owes OTHER people (from the personal-source adapter's
`briefing_commitments`), and `followup_items` renders dated follow-ups the ORG
wrote down. A date **he** declared had no store, no resolver and no reader
anywhere in the tree — so nothing could surface it, and the only thing holding
it was him.

## Shape, mirroring the availability dial (PR #210) deliberately

| piece | file | why it is there |
|---|---|---|
| store | `instance/config/captain-dates.yml` (+ `.example` twin) | append-only, LATEST ROW PER id WINS; gitignored (his calendar, not repo content) |
| resolver | `framework/env.py` — `captain_dates_path`, `captain_dates`, `captain_open_dates`, `render_captain_date` | ONE path and ONE line shape, so writer and readers cannot drift |
| writer + grammar + CLI | `cabinet/scripts/lib/captain_dates.py` | anchored both-ends grammar, refuse-don't-repair, YAML-safe label |
| phone verbs | `cabinet/scripts/officer-inbound-poller.py` | mechanical from its own process, captain-id-gated, DM archived (`kind="dates"`), flight-recorder row, fail-open relay |
| **consumer** | `framework/frontdoor/morning_synthesis.py::captain_date_items` → `gather_items` | ONE briefing item, one line per open date, every 07:30 and 19:30 run |
| Captain-seat evidence | `cabinet/scripts/meta-cognition/captain-seat-pack.sh` DATES section | open dates **plus** `tracked_in_latest_briefing=yes|no` |
| doctrine | Part 1c of the retro skill + its byte-parity doctrine-pack twin | an untracked open date is an in-window paid cost |
| deploy/egg/test fences | `runtime-provision.sh` persistence list · egg `delete` + `expect-present` · `conftest.py` env fence · docs-sweep allowlist | a deploy that reset the store would reproduce the failure, silently |
| docs | `docs/runbooks/captain-dates.md` (+ cross-link from the availability runbook) | |

## Design calls worth arguing with

1. **ONE item carrying N lines, not N items.** The composer caps non-`ping-now`
   tiers at five items and rolls the overflow into a count line
   (`framework/frontdoor/run_frontdoor.py`). N date items would therefore let
   the sixth date go quiet — the exact failure class. One item costs one slot
   however many dates are open, and the lines inside it are never capped. The
   leg is appended LAST in `gather_items` so its `ts` puts it at the safe end of
   that cap.
2. **No new interrupt channel.** Open dates ride the existing twice-daily
   briefing at `batch` tier. An overdue date gets a louder LINE (`OVERDUE by N
   days`, sorted to the top), not a `ping-now` real-time DM — `ping-now` would
   also be ACKed by the 5-minute surface pass and so would never reach the
   briefing body the pack checks against. The availability doctrine (the org
   fits the declared budget) is unchanged.
3. **Every refusal errs toward the date STAYING VISIBLE.** A row the reader
   cannot validate reads as absent, which leaves the previous row for that id
   standing. So a garbled `done` row leaves the date open (worst case: he sees
   something he already closed) rather than making a real date disappear (the
   failure being fixed). Pinned by
   `test_an_unknown_status_is_refused_and_leaves_the_date_open`.
4. **`move` writes two rows, never an edit.** "What did he originally say, and
   when did it change?" has to stay answerable; an in-place re-date would erase
   exactly the evidence a Captain-seat review needs.
5. **The label is the one free-text field that becomes a value**, because the
   briefing prints it back to him. It is control-character stripped,
   whitespace-collapsed, capped at the writer, and written as a quoted scalar.
   His whole sentence still rides along as an inert comment, as on the dial.
6. **A selector miss is an answer, not an error.** No match / several matches
   changes nothing and replies naming the real open dates. Closing the wrong
   date is worse than refusing. Genuinely unexpected exceptions still fall open
   to the Chair relay.

## Verification (all run in this session, in the clone at the base tip)

**Class-11: new sensors shown RED against pre-change state.** Pre-change tree =
second clone checked out at `a55dea44`, with only the new test files, the
extended eval harness and the new fixtures copied in; `__pycache__` purged before
every run.

- `cabinet/scripts/tests/test_captain_dates_wiring.py` — **16 of 17 arms red**
  (`16 failed, 1 passed`). The one that passes pre-change is the read-only
  control (`test_pack_does_not_write_into_the_dates_tree_it_reads`): a pack that
  never reads the store trivially never writes it. Stated rather than dressed up
  as falsification.
- `cabinet/evals/captain-seat/harness.py --self-test` — **RED, 5 mismatches**:
  the DATES section absent in both fixture arms, the healthy-arm absence marker
  missing, and both new Part 1c clauses missing. GREEN post-change with 15
  clauses pinned and both fixture trees unmutated.
- The resolver and library suites (`framework/tests/test_env_captain_dates.py`,
  `cabinet/scripts/lib/tests/test_captain_dates.py`) are **new-module** suites:
  pre-change they fail on absence (24 errors / a collection error), which proves
  nothing about what they claim. Their falsification is the sweep below.

**Guard-mutation sweep — 20/20 guards falsifiable.** Each row disables exactly
one guard in the shipped code and asserts a NAMED arm turns red, then green again
on restore (`__pycache__` purged between, `PYTHONDONTWRITEBYTECODE=1`). Guards
covered: the grammar's start anchoring, the calendar check, the year sanity
window, the label control-char strip, the quote escaping, prefix-not-substring
matching, the ambiguity refusal, content-derived ids, the status enum, the
required-field refusal, the latest-row-per-id fold (resolver AND pack), the read
cap, the OVERDUE branch, the date-ascending sort, honest-empty, the open-only
filter, the `gather_items` leg, the pack's tracked-column check, and the pack's
UNCHECKED honesty.

**Four sensors the sweep proved were NOT pinning what they claimed** — all four
fixed, not relabelled:

1. The newline-in-label arm asserted only the RESOLVED value, and a YAML
   double-quoted scalar legally folds an embedded line break to a space, so the
   arm stayed green with the strip disabled. Now asserts the physical FILE shape
   (exactly one `label:` line, no column-0 line).
2. The missing-required-field arm built its fixture by deleting a line from a
   template; dropping the `- id:` line left YAML that no longer parsed as a
   list, so the arm went green on a parse failure and stayed green with the id
   guard disabled. Now rebuilds the row field-by-field and asserts the fixture is
   still one parseable row before asserting the refusal.
3. The overdue-first sort key was a composite `(past_due_flag, date)` that a
   mutation showed to be provably equivalent to plain date-ascending (an overdue
   date is by definition earlier than today). The redundant key was DELETED and
   the simpler sort is what the arm now pins.
4. The grammar's start anchor: neither the leading `^` nor `re.match` alone is
   falsifiable — each is sufficient — so the mutation now removes the pair. The
   module docstring records the measurement rather than the assumption.

**Repo batteries, this session, in the clone:**

- `pytest framework/ -q` → `6597 passed, 25 skipped, 1 failed`. The single
  failure is `framework/fidelity/tests/test_retro_shim.py::test_reexports_constants`,
  **red on the unmodified base clone too** (verified at `a55dea44`): it asserts a
  model-id constant re-exported from a LOCAL screenpipe pipe on this machine,
  which CI does not have (the fidelity conftest collect-ignores that family when
  the retrodiction lib is absent) — master's own CI run for `a55dea44` is 7/7
  green. Not caused by, and not touched by, this unit.
- `pytest cabinet/scripts/lib/tests -q`, `pytest framework/tests/test_env_captain_dates.py`,
  `pytest cabinet/scripts/tests/test_captain_dates_wiring.py`, and
  `pytest cabinet/scripts/tests/test_memory_distill.py` → green.
- `cabinet/scripts/check-layer-separation.sh` → `new=0`. The resolver's
  `instance/config/...` string is the sanctioned crossing seam and does not add a
  violation (the rule matches the bare quoted token, not a path literal); the
  briefing consumer reaches the store only through the resolver.
- `cabinet/scripts/state-persistence-preflight.py` → `0 UNACCOUNTED` (the two
  pre-existing known gaps unchanged) — the new gitignored store is on the
  persistence list.
- `cabinet/scripts/docs-track-code-sweep.sh` → `GREEN (findings=0)`. One finding
  en route: the runbook named a gitignored `shared/interfaces/` path; reworded to
  name the tracked reader script rather than widening an allowlist.
- `bash -n` + `shellcheck --severity=error` on both touched shell scripts, and
  `py_compile` on every touched Python file → clean.
- The whole-tree ratchets (launcher/product-token hardcode, declared residuals,
  egg keep-list, ledger parity) and the HEAD-reading egg suites are re-run
  against the COMMITTED tree, since a working-tree pass on those proves nothing.

## Known limitations, stated

- The pack's tracked check is a substring match of the label against the newest
  briefing body. That is deliberate (the pack imports stdlib only and reads a
  fixture tree in the eval), and it can only ever UNDER-claim tracking when a
  label is reworded — never over-claim, because a label absent from the body
  cannot be found in it. It reports `UNCHECKED`, never `yes`, when there is no
  briefing to check against.
- In briefing-card mode (on by default) the composed body is archived rather
  than sent, so the date lines land in the archive the pack reads. That is the
  pre-existing behaviour of every briefing leg, not something this unit changes;
  the card headline carries counts only, by design.
- Nothing here is scheduled. This is a store, a resolver, one consumer and one
  evidence section — no new service, no new launchd row.
