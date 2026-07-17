# Review artifact — fix/captain-inbound-archive cp1 (2026-07-17)

Batch: durable captain-inbound archive (Wave-1 item b) —
`archive_captain_dm` + call sites in `officer-inbound-poller.py`, conftest
fence line, 10-test suite, runbook §10 durable-state row. ~300 lines →
FW-019 artifact.

## Gap
The only record of inbound Captain DMs was the redis ring
`cabinet:captain:recent-msgs` (LTRIM 0 29, 280-char truncation, silent
best-effort) — ~30-message half-life; 8 of 26 traced Captain messages were
unrecoverable verbatim by 2026-07-16. The captain-message-effect design
(gap #2) needs a durable verbatim archive with stable dm_ids as the Tier-2
case-ledger source and every attention metric's denominator.

## What shipped
`archive_captain_dm`: appends one JSON row per Captain utterance to UTC day
files `inbound-YYYY-MM-DD.jsonl` under `CABINET_CAPTAIN_INBOUND_DIR`
(default `~/Library/Application Support/cabinet/captain-inbound` — the
events/feed/undo family convention), verbatim (`ensure_ascii=False`,
untruncated text + untruncated quoted reply-context), fsync'd. Row schema
v1: v, dm_id (`tg-<chat>-<mid>`, CHAT-scoped id per Telegram semantics),
chat_id, message_id, update_id, officer (multi-writer attribution), kind
(text | file | file-error | onboarding), text, quoted, file_kind,
file_name, tg_date, ts. In-process dedup bounded at 4096 (readers dedup by
dm_id; crash-replay duplicates are verbatim-identical by contract).
Degrade-safe but LOUD: failure logs `ARCHIVE-GAP`, never raises, never
blocks delivery; failed appends aren't marked deduped (crash-replay
retries). Call sites: text / file / file-error relay paths + the
onboarding-ack path (Captain message-updates routed to the dashboard skin
archive as kind="onboarding" — Tier-0 anchor source material). Callback
taps / reactions / poll votes deliberately excluded (decisions, not
utterances — feed-journaled); unsupported media not relayed → not archived
(archive records what the officer saw). `CABINET_CAPTAIN_INBOUND_DIR`
fenced in the repo-root conftest AT BIRTH (this week's leak-class lessons).

## Review
Independent adversarial review (fresh-context Fable subagent):
**SHIP-WITH-FIXES** — all applied in this commit:
- P1-1: the test file used the Captain's REAL Telegram id (and a 9-digit
  epoch) — a privacy token in an egg-shipped test that the publish gate's
  9+-digit pattern would flag → fake ids (4242, tg_date 12345678) + a
  comment pinning the rule; grep confirms zero 9+-digit runs remain.
- P1-2: onboarding-routed Captain DMs bypassed the archive undocumented →
  archived now (kind="onboarding", captain-gated, taps still excluded) +
  exclusions documented in the archive docstring.
- P1-3: the call-site pin was vacuous for kind="text" (the def line's
  `kind="text"` default satisfied `\([^)]*kind=`; mutation-verified) →
  re-anchored on the call shape `archive_captain_dm\(chat_dm,`;
  mutation-delete of the text call site now fails the pin (teeth confirmed
  in-verification).
- P2-4: dm_id was sender-scoped (frm) — message_ids are chat-scoped →
  call sites pass `msg["chat"]["id"]` (falls back to frm); multi-writer
  comment corrected (409-reaping is per bot token, not per host); officer
  field added for attribution.
- P2-5: schema version `v: 1` + `officer` added while the schema has zero
  readers.
- P2-6: poller GUARANTEES header gained the archive bullet; runbook §10
  durable-state table gained the out-of-repo
  `~/Library/Application Support/cabinet/` family row — flagged ⚠ as NOT
  yet in any backup set (pre-existing blind spot the archive inherits;
  backup-manifest addition filed as follow-up).
- P2-7: retry docstring corrected (crash-before-offset-save replay retries;
  a miss with successful delivery is a permanent log-visible gap —
  accepted: delivery outranks the journal).
- P2-8 (filed, not fixed): unsupported media (video/sticker/…) is not
  relayed (pre-existing) and not archived; a kind="unsupported" row is a
  captain-gated cheap close.

Reviewer-verified sound: call-site placement (3/3 parity with the ring,
after the captain gate, before deliver; non-captain messages structurally
excluded), sp-reply-wire answers archived with the ⟦sp:…⟧ marker verbatim
in quoted, edited_message not in ALLOWED_UPDATES (archive matches what the
officer saw), import side-effect-free, fsync negligible at captain-DM
rates, conftest fence correct, CI-ubuntu clean, no layer-sep/A13 impact,
no personal tokens in code, runtime data never written into the repo tree.

## Verification (post-fixes)
- cabinet/scripts/tests: 1133 passed (incl. the 10 new; 71 poller-family).
- framework/: 5240 passed, 24 skipped (conftest fence extended).
- Pin teeth mutation-confirmed; zero 9+-digit runs in the test file;
  fresh-HOME run creates no live cabinet dir.
