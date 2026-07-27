# Governance review — the Captain's weekly ritual (RAMP-2, evidence Phase 3)

One TTY command, ~10 minutes, five stations. This is the Phase-3 deliverable
that starts accruing the Captain-verdict ground truth every later machine
judgment is calibrated against (whole-cabinet evidence design of record
2026-07-16 §3 Phase 3 item 3; onboarding plan 2026-07-14 RAMP-2).

```bash
python3.12 cabinet/scripts/governance-review.py --dry-run   # inspect the plan
python3.12 cabinet/scripts/governance-review.py             # run the ritual
python3.12 cabinet/scripts/governance-review.py --skip-stations   # labeling only
```

## Prerequisite: the Captain capability token

Every mode (dry-run included) requires the evidence store's EXISTING Captain
capability token — the same token that gates `purge`/`retain`/`export`/
`control` on the evidence CLI. Never a new auth scheme. Mint once, keep it
outside the officer tool surface:

```bash
python3.12 -m framework.evidence --store instance/evidence/v1 \
  grant-token --output ~/captain-evidence.token
export CABINET_CAPTAIN_TOKEN_FILE=~/captain-evidence.token
```

Without a valid token the CLI refuses (exit 3) **before touching the store**:
the refused path provably mutates nothing
(cabinet/scripts/tests/test_governance_review.py pins store byte-identity).

## The five stations (printed time budgets)

1. **Posture tile** (~1 min) — `posture-status.py` read-only JSON.
2. **Cost vs this cabinet's own history** (~2 min) — `cost-report.sh` glance.
   Not "vs caps": spend has been uncapped since 2026-07-26 and the meter is a
   watch, not a gate. The question at this station is whether the shape looks
   like the weeks before it, and whether the meter is writing at all — a
   ledger that has gone quiet reads exactly like a cheap week. Background:
   `docs/cost-metering.md`.
3. **Graduation digest + pending petitions** (~2 min) — graduation
   transitions from the org-event day files; needs-ledger tail.
4. **Receipts sample** (~2 min) — falsifier series tail, envelope
   violations, would-apply pointer (`REPORT_ONLY_SUMMARY` in the
   self-improvement loop log).
5. **Labeling** (~3 min) — the core: verified trials, blind, hard-capped.

Stations 1–4 are read-only glances over existing surfaces; each degrades to
an honest "unavailable" line on a deployment where the surface is not wired.

## The labeling station — what actually happens

- **Sampling** leans toward the weakest evidence basis (`self_asserted` >
  `persistence_only` > `machine_labeled`; already-Captain-labeled trials are
  excluded unless `--relabel`) and pulls the high-risk tail first within each
  stratum, then shuffles. Never "suspected disagreements only".
- **Fail-closed display**: every trial passes `verify_trial` immediately
  before presentation. An unverifiable trial renders as an explicit
  `UNVERIFIED` line (trial id + error codes, zero content) and cannot be
  labeled — ground truth is never minted off unverifiable bytes.
- **Blind labeling**: the presentation is the redacted officer projection
  (the same view a Phase-4 judge would read) minus every machine-verdict
  event. The evidence-basis tag names the STRENGTH class honestly; verdict
  directions stay hidden.
- **Hard cap**: `MAX_LABELS_PER_SESSION = 8` is a code constant, not a flag
  (a bar someone can lower from argv is not a bar). Skip/quit write nothing.
- **Verdicts** land on THE SAME trial via the germline recorder API:
  - `right` → `verification/verified` + `outcome/succeeded`
  - `wrong` → `verification/unverified` + `outcome/failed`
  - `unclear` → `verification/skipped` only (recorded, never scoreable)

  Every label event carries `actor {kind: captain, id: captain}`,
  `detail.action=governance_review_label`, `detail.source=verdict_human`,
  `detail.result_code` (`confirmed|wrong|unclear`), the **basis at label
  time**, `detail.jid` + `links=["undo-journal:<jid>"]` when the act-lane
  join exists, the session id, and (HP-3) the **channel attestation**
  `detail.label_channel` — `"captain-token+tty"` on this ritual: the two
  gates the CLI itself enforces (token match + live TTY), recorded
  hash-covered inside the signed event. An unattestable context is refused
  with a typed error before any store byte; `"telegram-captain-dm"` is
  RESERVED (no Captain-DM label writer exists — any future one must attest
  through `attest_telegram_channel()`, whose allowlist config-of-record is
  `instance/config/platform.yml captain_telegram_chat_id`; unconfigured =
  refuse, and the chat id itself never enters evidence, journal, or error
  text). Of those detail keys exactly two are in
  the officer projection allow-list — `action` and `result_code` (a landed
  label is an ordinary record, not a secret) — while `source`, `basis`,
  `jid`, `session`, `label_channel` and the free-text `note` are NOT
  allow-listed and stay redacted from every officer view (pinned by
  `cabinet/scripts/tests/test_evidence_label_join.py`).

## Phase-4 join contract

The undo-sweep reconciler already lands machine labels on the trial named by
the journal row's `evidence_trial_id` with `detail.source=verdict_judge`.
Captain labels land on that same trial with `detail.source=verdict_human`.
Phase-4 calibration pairs per trial id using judge-calibration polarity
(scoreable = `confirmed|wrong`, latest per side wins), per risk stratum.

## Exports (Captain-owned, outside the store)

- **Labels journal** `shared/interfaces/governance-labels.jsonl` — one
  CONTENT-FREE digest line per label (`ts`, session, trial id, verdict,
  basis, `channel` attestation mirror, event ids + hashes — never note
  text) plus one
  `session_complete` marker per run (the marker RAMP-5 later automates the
  REPORT_ONLY flip condition against). Gitignored runtime data.
- **External anchor + re-count** (HP-3, design §2.3): the journal is in
  `evidence-anchor.py`'s `DEFAULT_LABEL_FILES`, so its sha256 rides the
  daily anchor record (`record.captain_labels`) to the meta repo +
  Telegram; `python3.12 cabinet/scripts/evidence-anchor.py
  --recount-labels` then proves the journal APPEND-ONLY against the full
  anchor history and cross-joins it with the store — forged/altered/
  removed journal rows (`label_journal_rewritten`,
  `label_journal_row_unbacked`), in-store labels missing from the journal
  (`store_label_unjournaled` — also the trace of a loudly-degraded
  export; match against that day's transcript), and journal-vs-store
  channel divergence (`label_channel_mismatch`) are named findings, exit
  2. Run `python3.12 cabinet/scripts/evidence-anchor.py --json` after a
  session for write-time anchoring, or let the daily job cover it.
- **Session transcript** `shared/interfaces/governance-reviews/<session>.md`
  — the weekly review record (stations, verdicts, notes). Not in the store.

## Anti-forgery stance (inherited from label-fidelity-cases.py)

- Interactive labeling **refuses a non-TTY stdin** (exit 2) — no cron,
  agent, or pipe can mint `verdict_human` events through it.
- There is deliberately **no services.yml row** for this script.
- `--dry-run` is inert: no verification (no watermark writes), no recorder
  construction, no files written.
- Officer context additionally cannot use it: the Captain token is
  unmintable from officer Bash (grant-token and the signing key sit behind
  the hook screens that block `framework.evidence` interpreter access and
  raw store paths), and the only officer evidence read remains
  `cabinet/scripts/evidence-read.sh`.

## Honest limits (design §2.2 R2 / HP-3)

HP-3 is in: every label carries a channel attestation, calibration pairs
ONLY attested labels (legacy pre-HP-3 labels are excluded from new pairing
runs and counted honestly, never silently), and the anchor re-count verb
proves the journal append-only after the fact. What it is NOT: tamper-proof.
Until HP-1 isolates the signing key, a same-UID process that can read the
key can derive the token and forge the events, the channel field, and the
not-yet-anchored journal tail together; root can forge everything
everywhere. The attestation + re-count make forgery DETECTABLE against the
off-box anchor history — they do not prevent it. Remaining ceremony items:
the HP-1 key-isolation ceremony (the real boundary), an optional
classification-registry promotion of `label_channel` (it is deliberately
unregistered today — `classify_detail_key()` fail-closed-defaults it to
producer-asserted, which is the honest class for a writer-asserted field),
and any future telegram label writer (Captain-gated; must attest through
the reserved resolver).

## Exit codes

`0` ok (labels landed / dry-run / nothing to review) · `1` labels landed but
a Captain-owned export degraded (loud) · `2` refused (non-TTY / bad
invocation) · `3` Captain-token or evidence-plane typed refusal.
