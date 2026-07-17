# Checkpoint review — feat/evidence-phase3-review-surface cp1 (integration)

**Date:** 2026-07-17 · **Reviewer:** evidence Phase-3 integrator (Fable 5) ·
**Scope:** the composed three-group batch off `91dcdc75` (32 files: 24
unique paths from the three patches + 8 integrator seam/docs files) —
groups `read-plane` (G1), `dashboard` (G2), `digest-ritual` (G3), each
adversarially reviewed per-group before integration; this checkpoint
reviews the COMPOSITION and the integrator's seam work.

## What this checkpoint lands

Design-of-record §3 Phase 3 (humans judge first): the cross-trial query
plane on the existing `project` verb (germline — 3 paths, ceremony via
`docs/proposals/germline-amendment-evidence-phase3-2026-07-17.md`; no
boundary extension, lock-set definition files byte-identical, doorway
byte-identical); the auth-gated read-only `/evidence` dashboard page with
evidence-basis tagging (B6); the weekly governance-review ritual — the
phase's ONE designed write, Captain-token-gated through the recorder's
EXISTING capability mechanism, TTY-only, hard 8-label cap; digest evidence
citations; coverage + anchor registration for the labels journal.

## Integration decisions (beyond the three reviewed patches)

1. **Zero patch conflicts:** the three groups touched disjoint files; all
   applied clean on `91dcdc75`.
2. **One validation truth (G1↔G2 seam):** the page's TS filter validation
   MIRRORS the Python query plane; drift is now pinned two ways —
   (a) `cabinet/scripts/tests/test_evidence_read_lockstep.py` parses the
   TS literals (statuses / actor kinds / TRIAL_ID_RE / TIME_RE) and pins
   them to `verifier.py`/`query.py` truths; (b) a SHARED case vector
   (`cabinet/scripts/tests/fixtures/evidence-filter-cases.json`) is run
   through the REAL `query.parse_selector` (pytest) AND the REAL
   `validateFilters` (vitest `filter-lockstep.test.ts`). Divergence law
   pinned: dashboard may differ only via the documented single-day time
   alias (`<d>` ≡ `<d>-<d>`) or the doorway's one-token transport budget,
   and only ever by widening the Captain page, never the officer CLI.
   Integration FIX in `read.ts`: `validDayDigits` was lenient (accepted
   Feb 31); now real-calendar semantics lockstep with Python `strptime`.
3. **Label join wired + proven end-to-end (G3→G1, G3→G2 seam):**
   `cabinet/scripts/tests/test_evidence_label_join.py` — CLI label
   (token gate + scripted TTY) → `by-actor:captain` /
   `by-actor:captain:captain` / `by-component:governance-review` /
   `by-status:verified` all serve the labeled trial; single-trial
   projection serves the same records; redaction pinned (of the label
   detail keys exactly `action`+`result_code` are served — they ARE in
   `PROJECTION_ALLOWED_DETAIL` — while `source`/`basis`/`jid`/`session`/
   `note` stay officer-opaque). `label-join.e2e.test.ts` — the SAME CLI
   path spawned from vitest, then `readEvidence()` through the REAL
   Python verifier renders the trial `basis: human-verified` (bystander
   trial stays `persistence-only`).
4. **Docstring corrections (G3):** governance-review.py + both runbooks
   claimed NO label detail key is projection-allow-listed; factually wrong
   (`action`, `result_code` are). Corrected in all three places and pinned
   by the join test.
5. **Layer-separation root-cause fix (G1):** `test_query_plane.py` pinned
   the doorway argv with a re-typed `instance/evidence/v1` literal —
   a NEW `FRAMEWORK_PATH_INSTANCE` violation. Fixed by parsing the
   expected store path from `evidence-read.sh`'s own bytes (stronger pin,
   no literal, baseline NOT grown — shrink-only doctrine held).
6. **Egg-export pin:** the new amendment doc filename added to
   `test_egg_export.py`'s pinned list in the same commit (the lesson that
   bit Phase 1 and Batch A).

## Read-only proof (the batch's core invariant)

The one mutation in the whole batch is the Captain-token label append.
Proven on scratch stores at three layers, all green:
- **Query/CLI layer:** `test_evidence_label_join.py` — after the label,
  the FULL read surface (4 selector forms, single-trial projection, the
  CLI `project` verb) leaves ledger bytes untouched always, and the whole
  tree byte-identical at rest (the verifier's anti-rollback watermark
  advance on a trial's FIRST verify is the same sanctioned side effect
  `verify` has always had; byte-stable thereafter). G1's own
  `test_query_paths_leave_store_bytes_identical` + unverified-stub
  write-nothing tests corroborate.
- **Page layer:** `label-join.e2e.test.ts` — repeated `readEvidence()`
  passes leave the store tree byte-identical after settling.
- **Refused paths:** G3's suite — no-token / forged-token / non-TTY /
  dry-run leave the store BYTE-identical and write no journal/transcript.
- **Digest layer:** `digest_with_evidence` renders from journal rows in
  memory; it touches no store and returns text unchanged on any error
  (`test_digest_evidence_citation.py`).

## Gate battery (this checkout, 2026-07-17)

| Gate | Result |
|---|---|
| `python3.12 -m pytest framework -q` | 5601 passed, 28 skipped — base 5570 names, 0 removed, +59 (query-plane + digest-citation suites) |
| `python3.12 -m pytest cabinet/scripts/tests -q` | 1458 passed, 5 skipped; +59 new (governance-review 15, lockstep 42, label-join 2); 0 base tests removed; 3 environment/commit-timing fails triaged below |
| Lockstep consistency (`test_germline_lockstep_consistency.py`) | 371 passed |
| `check-layer-separation.sh` | OK — new=0 (after the root-cause fix; baseline unchanged at 24) |
| `run-golden-evals.sh` | 27/27 PASS incl. EVAL-025 (12/12 checks) |
| `docs-track-code-sweep.sh` | exit 0 post-commit (pre-commit findings were references to this batch's own untracked files; re-verified green after the commit) |
| dashboard `npm ci` + `tsc --noEmit` | clean |
| dashboard `vitest run` | 1878 passed / 106 files — base 1779 names, 0 removed (+99; the nav-shape pin test RENAMED 18→19 items for the Evidence entry, by design) |

**Triage of the 3 pre-commit pytest fails:** (1) `test_docs_sweep`
real-tree calibration and (2) `test_egg_export` amendments pin — both read
git-tracked content, so the batch's own not-yet-committed files read as
missing; both re-run GREEN after the commit. (3)
`test_evidence_seam_bypass_replay[evidence-access.sh]` — PRE-EXISTING at
clean BASE `91dcdc75` (reproduced in an untouched base clone): the two
ALLOW probes exit 2 because the org kill switch reads ACTIVE fail-closed
in this sandboxed environment (no reachable redis — the hook's designed
unreachable⇒ACTIVE contract). Not introduced, not maskable here; CI's
per-job run is the authority for it.

## Invariants verified against the composed tree

- Fail-closed display everywhere (CLI projection stubs, page UNVERIFIED
  rows, ritual verify-before-present) — tests named in the amendment doc.
- `cabinet/scripts/evidence-read.sh` BYTE-IDENTICAL; still the only
  officer read path; PR#140/#149 bypass catalog replayed against the
  selector token (G1 suite), the dashboard filters (G2 suite + shared
  vector), and the doorway subprocess (argv-canary tests).
- Never-a-score: query output = records + honest counts; page is
  Captain-facing auth-gated; EVAL-025 green.
- Label writes only via the EXISTING captain-token mechanism; TTY-only;
  never officer-invokable; no services row; per-session cap is a code
  constant with the flag vocabulary pinned.
- Germline: 3 changed paths, all under the existing `framework/evidence`
  DIRS cover; `FILES[]`/`DIRS[]`, `immutable-core.yml`, and the
  pre-tool-use screen byte-identical (no boundary extension).
- Portability: the batch adds NO shell `stat` probes at all (verified by
  grep over the composed diff + the new files), so the GNU-stat-first rule
  has no new call sites; no bare `python3` invocations added —
  `python3.12` pinned throughout.
