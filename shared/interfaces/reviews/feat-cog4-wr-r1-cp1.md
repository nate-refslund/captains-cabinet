# feat/cog4-wr-r1 — cp1: R1 THE VERDICT INBOX (WR rider)

FW-019 review artifact for the >300-line batch on `feat/cog4-wr-r1`.
Unit: masterplan rider R1 (BACKLOG :1559; phase-4 contract §18 WR lane) —
"the graph ranks pending human verdicts by how much downstream certainty each
unlocks; top-3 surfaced on the ONE captain surface". Scope here is the
ARTIFACT-producing instrument only; delivery machinery (needs ledger /
briefing digest / World) is deliberately out of scope.

## Batch

| path | change |
|---|---|
| `cabinet/scripts/cog3-verdict-inbox.py` | NEW read-only CLI: serve-surface-only graph read, chained-hash-verified predictions read, declared VOI ranking, Captain-register markdown brief |
| `cabinet/scripts/tests/test_cog3_verdict_inbox.py` | NEW additive battery (11 tests): real-rebuild fixture graphs, ranking/cap, hashseed determinism, REFUSE-on-tamper x3, prediction pressure, Captain register, surface pins |
| `cabinet/scripts/cog2-import-gate.py` | `ALLOWLIST_EXACT_OBJECTIVES` += the new CLI (curated serve-surface reader) |
| `cabinet/scripts/tests/test_cog3_import_gate.py` | the exact-set pin grown in the SAME commit (the lockstep the pin exists to force) |
| `cabinet/scripts/egg-export-manifest.txt` | `expect-present` line for the new CLI (the cog3-CLI packaging idiom) |
| `shared/interfaces/reviews/feat-cog4-wr-r1-cp1.md` | this artifact |

## Design decisions (with evidence)

1. **Read discipline.** The graph is read ONLY through
   `framework.objectives.query.serve_graph` (the ONE bound loader, F1), so all
   three C-F15 REFUSE limbs (tampered rows / counterfactual manifest /
   mixed-epoch store) guard the inbox for free; the CLI source never names the
   raw row-store file (pinned by test). The predictions store is read only
   after re-deriving its own chained-hash manifest (the exact
   `counterfactual._write_predictions_manifest` chain, `model.digest`);
   mismatch or a half-present store REFUSES. Every refusal: stderr + exit 2 +
   NO artifact — stale advice is never emitted.
2. **VOI bands are exact state-machine facts, not vibes.** Band 1 =
   `observationally_supported`: by §5.2 P5 construction the edge holds
   supporting machine evidence AND declared assumptions AND no human verdict
   (else P2/P3 fire first) — promotion is blocked ONLY by the missing human
   verdict. Band 2 = `hypothesized`+`direction_contested` (P4): machines can
   demote but never refute (P2 is human-only) — a verdict settles a live
   disagreement. Band 3 = bare `hypothesized` (P6). Excluded honestly:
   P3/P2 (verdict exists), P1 contested (a verdict cannot clear a bound
   conflict_set). Tie-breaks: open (unscored) predictions desc, target-node
   degree desc (the recommendation-impact proxy this serve surface actually
   supports), edge_id lexicographic — a deterministic total order. The SAME
   ranking is declared in the artifact in plain words ("How these were
   chosen").
3. **Artifact surface = the existing captain brief surface** (not a new
   channel): officers write briefs to `shared/interfaces/research-briefs/`
   (cabinet/cron/research-sweep.sh:21), backlog-refine consumes the dir
   (cabinet/cron/backlog-refine.sh:20), the FW-033/EV16 significant-artifact
   write class pins exactly this dir (run-golden-evals.sh, positive example
   `research-briefs/2026-04-21.md`), and runtime .md there is gitignored
   (.gitignore:173). Default out: `research-briefs/<date>-verdict-inbox.md`,
   date from the DECLARED `--now` (the cog3-staleness A-m8 no-clock idiom).
4. **Captain register.** Wording uses ONLY the bijective Captain vocabulary
   (`query.to_captain_word` — the words are IMPORTED from the bijection, so
   drift is impossible); a test bans the plumbing vocabulary (state enums, id
   field names, store filenames, section signs) from the artifact.
5. **Ranking is ordinal, never a scalar value-surface.** Band ranks are sort
   keys only; no aggregate/composite/score accessor exists (P12 spirit; the
   mechanical ratchet sweeps framework/objectives only and is untouched).

## Known/accepted

* The phase-3 full-clone footprint ratchet
  (`test_cognitive_phase3_rollback.py::test_manifest_covers_committed_cog3_footprint`)
  already FAILS on full clones at the base master tip (the phase-4 contract
  doc trips it — the recorded systemic BASELINE..HEAD defect, BACKLOG
  :1551-1555; CI shallow-checkouts skip it). This unit's new files join that
  ALREADY-RED-on-full-clones range; per the BACKLOG record the fix is the C1
  closed-range engine, deliberately not attempted here. Phase-3's frozen
  review-scope digest is untouched.
* `test_egg_export.py` full-export fixtures fail while the batch is
  UNCOMMITTED (the exporter cuts from git HEAD; the working-tree manifest
  already expects the new CLI) — self-resolves at commit; re-verified green
  after commit.
* Delivery (needs-ledger card / briefing digest fold / one-tap flow-back of
  verdicts as evidence) is follow-on work on the existing machinery — this
  unit produces the ranked artifact only, per the WR brief.

## Self-review findings applied before commit

* The CLI docstring originally named the raw row-store filename, which would
  have tripped the suite's own no-raw-read tripwire — reworded; the tripwire
  stays armed.
* The footer's open-forecast count is computed over claims awaiting a call
  (not the whole store) — wording tightened to say exactly that, so the
  number and the sentence can never disagree.
* `assumption_set` in tests aligned to the dict shape sim3 established
  (checked against `test_cog3_sim3_counterfactual.py:257` before running).
