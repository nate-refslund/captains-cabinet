# evidence-recompute — HP-2 independent recompute legs (report-only, staged dark)

Module: `framework/evidence_recompute.py` · Runner: `cabinet/scripts/evidence-recompute.py`
Service row: `evidence-recompute` in `cabinet/services.yml` (**shipped `disabled: true`** — the
Captain ceremony below is the only enable path). Design of record:
`whole-cabinet-evidence-self-improvement-2026-07-16.md` §2.3 HP-2, §2.5, §3 Phase 4.

## The honest claim (mandatory — carried on every report line and every event)

This leg is a **DIFFERENT producer identity but the SAME OS user until HP-1**
(OS-user/key isolation) lands. Its independence comes from **re-deriving outcomes
from raw artifacts**, never from a trust-domain boundary. A same-user attacker who
forges the raw artifacts (undo-journal rows, pack files, org-event day files)
**consistently** still passes, and **root forges everything** — the leg is
**necessary, not sufficient**. Do not describe its events as broker-attested:
`attestation_mode: "process"` is same-user-DECLARED (identity.py R2 caveat).

## What it does

Out-of-band, per fuel-bearing machine-claimed outcome, it re-derives the outcome
from **raw artifacts only** — the producer's claimed verdict is read **only to
COMPARE**, never as derivation input — and appends **ONE verification event per
checked outcome** to its OWN day trial `evt-recompute-<yyyymmdd>` with
`agreement: agree | disagree | underivable:<reason>`:

| # | Outcome kind | Raw artifacts | Disagree means |
|---|--------------|---------------|----------------|
| 1 | act-lane `ttl_ok` / `silent_revert` labels | undo-journal row bytes (status/executed_at/reversed_at/ttl_expires_at/canary/demo), joined by the ledger row's `undo-journal:<jid>` ref; optional Monday artifact probe (injected) | the journal bytes (or probed artifact state) contradict the minted label |
| 2 | learning-gate verdicts | pack JSON + archived `variants/<sha16>.patch` bytes (sha recompute), stage→verdict control-flow consistency, `applies_nothing` invariant, pack↔store `gate_ratify` receipt equality; `gh` check-runs **only where a pack names a commit** | pack bytes are internally inconsistent, the archived patch does not hash to the claim, the store receipt diverges, or CI contradicts a pass |
| 3 | `graduation_transition` org events | re-run of the germline `graduation.evaluate` over the consequence ledger at the claimed time + org-mirror receipt sha over the org-event JSONL row | the re-derived state differs from the claimed `to_state`, or the signed mirror receipt disagrees with the org-event bytes on disk |

**Discriminator law:** a contradiction is claimed only with AFFIRMATIVE evidence.
Absence — journal row GC'd (30d retention), archived patch missing, purged trial,
`gh` absent (`underivable:artifact-unavailable`), probe unavailable, ledger window
gone — is `underivable:<reason>` and passes through. Absence alone never renders
tamper, and an honest skip is never a guess.

## Shadow law (Phase 4 binds)

- **Report-only.** Nothing the minter reads: the report JSONL
  (`cabinet/logs/evidence-recompute-report.jsonl`, gitignored) lives OUTSIDE both
  planes and `write_report` refuses paths inside the store or the ledger dir.
  Exit codes carry no verdict signal (0 = measured, 2 = could not measure).
- **Disagree events are INFORMATION** for the Captain's weekly review — the
  weekly line carries COUNTS only, never rates (never-a-score). Nothing may
  gate, block, score, or act on them.
- The fuel-integrity checker consumes the events as its **third-leg signal** —
  itself report-only shadow (`ungrounded:recompute_contradicts_claim` is a report
  verdict, not an action).
- **Read-only** toward both planes except the ONE sanctioned write: appends to
  its OWN `evt-recompute-*` day trials via the public recorder API under a
  process-attested identity. It never writes the ledger, the journal, or org
  events; never opens `.signing-key`; never constructs a recorder over an absent
  store. Idempotent: re-runs dedup by `claim_sha256` across the window's
  recompute day trials (crash-recovery re-checks are normal, never re-minted).
- **Freeze respect:** while `instance/state/evidence-judging-freeze.json` is
  present the run refuses with one plain line and exit 0. A broken freeze probe
  reads FROZEN (fail-closed).

## Classification honesty (the registry pattern)

The event detail keys this producer mints (`target`, `agreement`, `claim`,
`rederived`, `claim_sha256`, `legs`, …) are **UNREGISTERED** in the germline
classification registry (`framework/evidence/classification.py`) and therefore
read back as **producer-asserted** — the fail-closed default; nothing becomes
independently established by omission. That is deliberate for the dark wave.

## Deploy ceremony (Captain; the only enable path)

1. Remove `disabled: true` from the `evidence-recompute` row in
   `cabinet/services.yml`; run `generate-plists`; load the LaunchAgent.
2. Uncomment `evidence-recompute-liveness` in `instance/config/watchdog.yml`
   and land its catalog row in `framework/watchdog/registry.py` in the same step.
3. **Classification registry promotion (germline ceremony):** now that the
   independent checker exists, promote the recompute detail keys to
   `independently_established` via the documented registry pattern — a
   ceremony-gated content change to `framework/evidence/classification.py`
   (schg unlock window, amendment doc under `docs/proposals/`, relock same day).
   The evidence-event schema needs no change (detail keys are not schema-gated).
4. **Trusted-core forward obligation (design §3 Phase-4 item 5):** the moment
   recompute events are allowed to SATISFY the fuel third leg for **actual
   minting** (the enforce flip / Phase 6), either admit
   `framework/evidence_recompute.py` to `framework/policies/immutable-core.yml`
   via the `pending:` procedure (Captain ceremony), or keep its events
   re-derived by the fuel-integrity checker at consume time. Explicit ceremony
   line — never implicit.

## Reading a run

- Weekly line (stdout + report):
  `recompute: N checked (A agree, D disagree, U underivable; R recorded) [shadow — report-only] | claim: …`
- Per-outcome JSONL lines carry `target`, `claim`, `rederived`, `agreement`,
  join keys (`jid` / `pack_id` / `org_event_id`), per-leg statuses, and the
  honest claim. A `disagree` line is the weekly review's cue to look at the
  named raw artifact — remember the ledger is last-write-wins, so rows
  superseded after a graduation claim legitimately shift that recomputation.

## Residual risks (stated, not hidden)

- Same-user forgery of the raw artifacts themselves defeats the leg until HP-1;
  root defeats everything including this module's own events and report.
- `verdict_gate` fuel is structurally ZERO today (`_label_floor_met` hardwired
  False — CG-1 Option B), so gate-verdict recompute is consistency-checking /
  future-proofing; it fabricates no gate-fuel violations.
- External anchoring (`evidence_anchor.py`, D3 both-surfaces) remains the
  after-the-fact cross-check that outlives even root forgery detection windows.
