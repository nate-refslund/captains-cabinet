# Tamper game-day drill — runbook + outcome template

Phase 4 of the whole-cabinet Evidence program (design of record 2026-07-16,
section 2.4 response path; section 3 Phase 4). SHADOW LAW applies: every
output of the drill is a Captain-facing report; nothing downstream consumes
it to gate, block, score, or act.

## What the drill proves

The evidence store is hash-chained, signed, and anti-rollback watermarked —
but all of that lives INSIDE the store. Restoring an earlier byte-copy of
the whole store (events + tip anchors + watermark sidecar together) resets
protection, and the local verifier stays green. The daily external anchor
(`cabinet/scripts/evidence-anchor.py`) exports a content-free snapshot of
the store's tamper-evidence surface OUTSIDE the store; comparing the live
store against the last exported record catches exactly that class.

The drill rehearses the whole loop against a SACRIFICIAL SCRATCH STORE:

1. Build a scratch store with real recorder trials; `verify_store` green.
2. Take a byte-for-byte snapshot of the whole store directory.
3. Append more events and a new trial; verify again; export a REAL anchor
   record to a scratch `evidence-anchors.jsonl`.
4. Replace the store with the earlier snapshot (restore-to-earlier).
5. Blindness proof: `verify_store` on the restored store is GREEN.
6. Catch proof: `evidence-anchor.py --store <scratch> --check
   <scratch-anchors.jsonl>` exits 2 with findings (`trial_rollback`,
   `trial_missing`, `watermark_regression`), and `first_run` is False
   (the vacuous-pass trap is guarded: an anchor exported AFTER the restore,
   or a missing `--check FILE`, would "pass" while proving nothing).
7. Respond: set the judging-frozen marker, page the CHAIR (never the
   Captain directly), render the outcome report.

The live evidence store (`instance/evidence/`) is never read, written, or
verified by the drill. There is deliberately no `--store` option.

## Honest claim (mandatory in every report)

The external-anchor check detects retroactive single-plane tamper and
INCONSISTENT forgery only; consistent same-user forgery of both planes
(the same OS user rewrites ledger and store together, key file readable)
stays open until HP-1 (OS-user/key isolation) lands — necessary, not
sufficient.

Concrete residual: `check_anchor` excuses a missing trial when any
`purge-receipts/` file NAME matches `sha256(trial_id)[:16]`, and a receipt
appearing after the last anchor is not itself a finding — a same-user
forger can mask a deletion by planting a receipt-shaped file.

## Running it

TEST mode (default — safe anytime, leaves only the two report files):

    python3.12 cabinet/scripts/evidence-tamper-drill.py run

- Freeze marker is set under the drill's own scratch pseudo-root and
  removed with it; no real judging is frozen.
- The Chair page is a `WOULD PAGE Chair (<chair>): ...` stdout line plus a
  `"paged": "would-page"` report field; nothing is sent.

LIVE mode (the actual game day — schedule it with the Chair):

    python3.12 cabinet/scripts/evidence-tamper-drill.py run --mode live --confirm-live

- The store under test is STILL scratch; what goes live is the RESPONSE:
  the freeze marker is set at the real repo root and the Chair is really
  paged via the outcome-watchdog trigger mechanism (Redis
  `cabinet:triggers:<chair>`; chair id from `CABINET_CHAIR_OFFICER`,
  default `cos`; the message is clearly labelled a drill). Telegram is
  never used by the drill.
- Shadow evidence services (detectors, calibration, fuel-integrity
  reporter) check the marker at entry and refuse to run while frozen —
  that outage is deliberate and part of the rehearsal.
- The drill refuses to start a live run when a real freeze marker is
  already present (Captain clears first).
- The rehearsal is complete only when the Captain clears the marker (see
  below) and the outcome doc is annotated with the time-to-clear.

Report surfaces (both gitignored runtime files, Captain-facing only —
never projected to officers, never org events):

- `cabinet/logs/tamper-drills.jsonl` — one row per run
  (`cabinet.tamper-drill/v1`: mode, caught, finding_kinds, verifier_blind,
  time_to_catch_s, froze, paged, gaps, honest_claim).
- `shared/interfaces/tamper-drills/tamper-drill-<stamp>.md` — the rendered
  outcome doc (template below).

## The judging-frozen marker (one truth: `framework/evidence_freeze.py`)

- Location: `<repo-root>/instance/state/evidence-judging-freeze.json`
  (runtime, gitignored; NOT inside the evidence store, whose tree must
  stay byte-stable). The framework→instance path is a ratified by-design
  coupling — `.layer-separation-allowlist` row
  `framework/evidence_freeze.py:FRAMEWORK_PATH_INSTANCE` (2026-07-17,
  self-ratified per the 2026-07-07 full-autonomy grant; provenance block
  in that file).
- FAIL-CLOSED: ANY presence — valid JSON, garbage, a symlink, a directory,
  an unreadable entry, even a parent state-dir swapped for a file — reads
  FROZEN. Only a genuinely absent path (ENOENT) reads unfrozen. Corrupting
  the marker or its parents can never unfreeze judging.
- First-freeze-wins: an existing marker is never overwritten. Setting the
  marker is a pure narrowing any process may perform; content is
  content-free (timestamp, reason, finding KIND names, setter, drill flag).
- Shadow services consume it like this (and exit 0 — a freeze is not a
  service fault):

      from framework.evidence_freeze import is_frozen
      if is_frozen(repo_root):
          print("evidence judging is frozen - refusing to run")
          return 0

Status check:

    python3.12 cabinet/scripts/evidence-tamper-drill.py freeze-status

## Captain clear (unfreeze) — Captain-only

Primary path — the token-gated verb. It reuses the evidence CLI's existing
Captain capability mechanism (`HMAC(store-signing-key, purpose)`, minted
once with `python3.12 -m framework.evidence grant-token --output <file>`;
same file-hygiene rules; `CABINET_CAPTAIN_TOKEN_FILE` fallback). No
separate auth scheme exists for unfreeze:

    python3.12 cabinet/scripts/evidence-tamper-drill.py unfreeze \
        --captain-token-file <path-to-token-file>

Exit 0 = cleared; exit 3 = typed refusal (wrong/absent token, marker left
in place). Honest limit (same as the evidence CLI's own gate): in a
same-UID deployment any process that can read the store's signing key can
derive the token — the full boundary arrives with HP-1.

Manual fallback — ONLY when the store itself is too broken to verify a
token (destroyed, corrupted key). The marker carries the user-immutable
flag, so:

    chflags nouchg instance/state/evidence-judging-freeze.json
    rm instance/state/evidence-judging-freeze.json

Any shell probe of the marker's age must be GNU-stat-first:

    stat -c '%Y' instance/state/evidence-judging-freeze.json 2>/dev/null \
      || stat -f '%m' instance/state/evidence-judging-freeze.json 2>/dev/null

## Escalation law

Findings page the CHAIR's trigger stream with a 3h-cooldown-style single
consolidated message; there is deliberately NO direct-to-Captain tier
(P-Alerts-To-Chair). The Chair triages and brings it to the Captain. The
drill message states the response expectations so the Chair rehearses
triage without treating it as real tamper.

## Outcome template (rendered per run by the harness)

Every outcome doc carries these sections — when writing one by hand (e.g.
annotating a live drill after the Captain clear), keep the same shape:

- **What was simulated** — the tamper class, store/event counts at anchor
  time vs after restore, the anchor record digest.
- **What caught it** — the exact production command, exit code, finding
  kinds, the first-run guard result.
- **Local verifier blindness** — `verify_store` ok=True on the restored
  store (why the external anchor exists).
- **Time to catch** — restore completion to check exit, seconds.
- **Response steps taken** — the ordered check list (store built, anchor
  exported, restore simulated, blindness proof, catch, first-run guard,
  in-process agreement, expected kinds, freeze, page), each ok/FAILED.
- **Captain clear** — live mode: pending until cleared; record who cleared
  and time-to-clear when annotating. Test mode: n/a.
- **Gaps found** — every failed check, page failures, cleanup problems;
  "none" only when everything passed.
- **Known residuals (honest claim)** — the claim text above, verbatim.

## Wiring status (Phase 4 batch)

The drill proves the response path against scratch. Wiring the REAL daily
anchor job (`evidence-anchor.py` exit-2 path) to freeze + page
automatically is a pure tighten left to a later, explicitly-reviewed
change — until then the anchor job's FATAL line pages via the watchdog
error-marker floor, and the freeze/page rehearsed here is operated by the
drill (and by hand per this runbook if real findings appear).
