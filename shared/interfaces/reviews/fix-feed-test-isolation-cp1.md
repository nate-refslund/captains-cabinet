# Review artifact — fix/feed-test-isolation cp1 (2026-07-16)

Batch: repo-root conftest fence extension (CABINET_FEED_DIR +
CABINET_ATTENTION_DIR + CABINET_DRAFT_QUEUE_DIR + CABINET_EVIDENCE_DIR),
new Captain-gated `cabinet/scripts/feed-purge-testrows.sh` + 15-test
subprocess suite, runbook purge-tool enumeration. ~640 lines → FW-019
artifact required at commit time.

## Incident
`framework/acting/tests/test_actfirst_gate.py` seeds an expired card
(subject "stale ask"); the PRODUCTION card-expiry sweep
(`run_action_lane.py`) journals the demotion via
`framework/attention/feed.py::append_event`; with CABINET_FEED_DIR unset,
`_feed_dir()` falls back to the LIVE feed
(`~/Library/Application Support/cabinet/feed`). 124/545 live rows were the
phantom triple `{kind: demote, situation_key: slug:stale-ask,
demote_reason: card-expiry}` (accrued 07-09..07-16; 128 by review time —
still growing until the fence lands). Proof of harm: on 2026-07-11 the live
orchestrator-triage CLOSED the phantom situation (kind=closure row — kept
by the purge, it is genuine system output).

## Review
Independent adversarial review (fresh-context Fable subagent, no authorship
bias), full attack-surface brief: fence collisions with per-suite
env handling, purge data-loss vectors, criterion over/under-match, flock
semantics, today-file UTC rollover, bash 3.2 / set -euo pipefail, gate-2
test validity, CI coverage, egg manifest, docs-track-code.

Verdict: **SHIP-WITH-FIXES** — all fixes applied in this commit:
- P1-1 runbook enumeration: feed purge + `feed-backups/` added to
  `cabinet/docs/mac-mini-deploy-runbook.md` §10.
- P1-2 conftest docstring purge paragraph now names both purge one-shots.
- P1-3 fence class-completed: CABINET_ATTENTION_DIR (overwritten state —
  worse failure mode than append-only rows), CABINET_DRAFT_QUEUE_DIR,
  CABINET_EVIDENCE_DIR fenced in the same unconditional block; docstring
  enumerates them. Both prior incidents (events 2026-07-04, feed
  2026-07-16) began as a production write path added later behind an
  existing fixture-less test — this closes the class, not the instance.
- P2-1 three missing test pins added (empty-dir refusal, second-run
  idempotency, valid-JSON-non-dict kept+counted) → suite now 15 tests.
- P2-2 non-dict JSON lines now increment the `unparseable` diagnostic
  counter (operator visibility parity with the events purge).
- P2-3 criterion residual (ref-less card slugifying to "stale-ask")
  documented in the script header with the live-sweep evidence (zero such
  rows; backup-recoverable).

Attacks that did NOT land (reviewer-verified): no test depends on default
feed-dir resolution (every CABINET_FEED_DIR-touching suite monkeypatches;
subprocess tests build env explicitly or inherit the fence); flock design
strictly stronger than the events pattern (purge holds the SAME seq.txt
flock appends serialize on — closes even the accepted UTC-midnight sliver);
gate-2 refusal test genuinely exercises gate 2; shellcheck
--severity=error + bash -n PASS; CI collects cabinet/scripts/tests
(cabinet-ci.yml ~:469); egg manifest delete-based → new files ship like
their ledger sibling, no manifest change; no product/person tokens; no
egg-ledger row moved (A13 not triggered).

## Verification (post-fixes)
- framework/ full suite, real HOME: **5176 passed, 24 skipped** (identical
  to pre-change baseline).
- cabinet/scripts/tests: **1046 passed, 4 skipped** (incl. the 15 new).
- Class-wide leak proof: full framework run against a FRESH $HOME creates
  **no** `Library/Application Support/cabinet` dir at all (pre-fix:
  1 phantom feed row per run of the acting suite).
- Purge proven on a disposable COPY of the live feed: dry-run then real run
  — 545→428 rows, 117 dropped, 7 deferred (today-file race guard), backup
  verified 545/545, seq.txt + cursors byte-untouched, phantom closure kept,
  `feed.py::_read_all_rows()` reads the purged copy cleanly (428).

## Live-purge status
PREP ONLY in this commit. The live run stays gated
(CABINET_PURGE_CONFIRM=1) and requires the fence merged in the running
checkout (gate 2). Note: the LIVE tree (5 behind master) keeps leaking
until it advances past this commit — re-runs of the purge are cheap,
idempotent (pinned by test), and each day-file's stragglers are caught the
following day.
