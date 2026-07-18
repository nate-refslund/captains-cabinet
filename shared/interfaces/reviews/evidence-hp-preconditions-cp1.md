# Checkpoint review — feat/evidence-hp-preconditions cp1 (integration)

**Date:** 2026-07-18 · **Reviewer:** evidence HP integrator (Fable 5) ·
**Scope:** the composed three-group batch off `345461c0` (31 files: 27
unique paths from the three patches + 4 integrator docs/pins) — groups
`hp1-signing`, `hp2-recompute`, `hp3-label-channel`, each adversarially
reviewed per-group before integration; this checkpoint reviews the
COMPOSITION and the integrator's seam work.

## What this checkpoint lands

Design-of-record §2.3 hard preconditions (D1: front-loaded HP track), all
STAGED DARK: HP-1 signing-key custody seam (germline — 3 paths inside the
`framework/evidence` DIRS[] cover, ceremony via
`docs/proposals/germline-amendment-evidence-hp-2026-07-17.md`; no boundary
extension, lock-set definition files byte-identical) + the out-of-process
broker daemon (non-germline, `disabled: true`); HP-2 independent recompute
legs + the fuel-integrity third-leg join (non-germline, report-only,
`disabled: true`); HP-3 channel-attested Captain labels with fail-closed
calibration pairing + the anchor `--recount-labels` verb (non-germline,
rides the existing governance ritual). Deploy ceremony hand-off:
`docs/runbooks/evidence-hp-deploy.md` (fresh-cabinet launch, Captain sudo
— never executed by this branch).

## Integration decisions (beyond the three reviewed patches)

1. **Two append-append conflicts, resolved keep-both:**
   `cabinet/services.yml` (both groups add a service row at the same
   anchor — broker row then recompute row kept, zero content changes) and
   `cabinet/scripts/evidence-coverage.py` (both add a SURFACES census
   entry at the same anchor — `signing-broker` then `evidence-recompute`
   kept verbatim). `docs-sweep-allowlist.txt` and
   `framework/tests/test_evidence_phase4_seams.py` merged clean (disjoint
   hunks: HP-2 adds the fourth freeze-respect leg, HP-3 stamps the label
   helper's channel args).
2. **One coherent classification registry:** NEITHER group extended
   `framework/evidence/classification.py` (germline) — verified untouched.
   HP-2's recompute detail keys and HP-3's `label_channel` both read back
   producer-asserted via the registry's fail-closed default; both
   promotions are separately-queued ceremonies in their runbooks. No
   duplicate keys, no registry drift.
3. **Composed cross-seam proof (the joins no group could test alone), all
   18 checks green on ONE scratch store family:** store born local →
   flipped to broker mode against a live same-user-simulation daemon →
   broker-signed work trial + recompute verification event + channel-
   attested Captain label written through the SAME broker-mode recorder;
   then (a) public verifier green over every broker-signed trial, (b)
   fuel-integrity `_recompute_index` consumes the recompute event by jid
   (third-leg join), (c) calibration counts the attested pair while a
   legacy journal row buckets `legacy_unauthenticated=1` (excluded +
   counted, never silent) and a journal row LYING about its channel is
   defeated by the store's hash-covered copy (`channel_unverified=1`), (d)
   the label writer refuses an unattested channel value and the TTY
   attestor refuses without the token gate, (e) the broker request log has
   one row per request and zero key material/key-path leakage, (f) a dead
   broker refuses evidence operations with a typed fail-closed error — at
   store OPEN already, never a silent local fallback.
4. **Composed dark-default proof (byte-level):** deterministic harness
   (pre-seeded key, frozen `_utc_now`, deterministic uuid4 +
   monotonic_ns) writes the same scratch store under the BASE tree
   (`345461c0`) and the composed tree with NOTHING configured — all 8
   store files sha256-IDENTICAL (`.signing-key`, control.json,
   events.jsonl, anchor.json, watermarks, locks). The unconfigured seam is
   byte-identical, not just test-equivalent.

## Gate battery (composed tree; BASE = `345461c0` in the same environment)

| Gate | Result |
|---|---|
| `python3.12 -m pytest framework -q` | **GREEN** 5812 passed, 29 skipped (BASE: 5691/29 → +121 new, 0 removed) |
| `python3.12 -m pytest cabinet/scripts/tests -q` | 1561 passed, 5 skipped, **1 pre-existing environmental failure** (below; BASE: 1544/5 + the SAME failure → +17 new, 0 removed) |
| lockstep consistency (`test_germline_lockstep_consistency.py`) | **GREEN** 371 passed |
| `cabinet/scripts/check-layer-separation.sh` | **GREEN** new=0 fixed=0 |
| `cabinet/scripts/run-golden-evals.sh` | **GREEN** 27/27 incl. EVAL-025-NEVER-A-SCORE |
| `cabinet/scripts/docs-track-code-sweep.sh` | **GREEN** files=55 findings=0 (re-run after integrator docs) |
| dashboard tsc+vitest | **SKIPPED — dashboard untouched** (zero `cabinet/dashboard` paths in the diff; skipped, not faked) |
| composed seams script | **GREEN** 18/18 |
| composed dark-default byte-identity | **GREEN** 8/8 files identical |

**The one red, named honestly:**
`cabinet/scripts/tests/test_evidence_seam_bypass_replay.py::test_shipped_catalog_harness_still_green[evidence-access.sh]`
fails in ANY scratch clone of this environment — the shipped bypass-replay
harness rows "Bounded projection" and "Ordinary onboarding read" exit 2
without the real deployment context. Reproduced IDENTICALLY at bare BASE
`345461c0` (1 failed / 1 passed on that node id) before any HP byte:
pre-existing and environmental, not an HP regression. CI on the PR is the
authority for the deployment-shaped run.

## Reviewer verdict

- Germline diff is minimal and exactly enumerated (3 paths, all DIRS[]
  cover; `FILES[]`/`DIRS[]` arrays, `immutable-core.yml`, hook screen
  byte-identical). Amendment doc + egg-export pin land in this commit.
- Broker discipline verified in code + composed run: 0700/0600 staged
  socket posture, peer-credential requirement (feature-detected,
  refuses-to-serve without), event-hash-shaped payloads only, governance
  purposes never minted, rate limit, divergence refusal, no key material
  on the wire or in logs/errors.
- HP-2 stays read-only toward both planes except its own evt-recompute
  day trials (public recorder API); report-only toward minting; freeze
  marker respected (fourth shadow leg pinned in the seams suite).
- HP-3 is fail-closed at writer AND consumer; legacy labels excluded from
  NEW pairing runs with an honest count line, never silently.
- Threat honesty present at every surface (module docstrings, services.yml
  rows, runbooks, amendment): HP-1 raises the bar same-user → root; root
  forges everything; stated, not hidden.
- SHIP (as a staged-dark PR; the deploy ceremony stays with the Captain).
