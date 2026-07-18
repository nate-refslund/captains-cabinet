# Germline amendment — EVIDENCE HP-1/2/3 (hard preconditions, staged dark) — 2026-07-17

**Status:** PROPOSED on `feat/evidence-hp-preconditions` (off `345461c0`).
The Captain's merge of this branch to master (after CI is green) is the
apply; the post-merge on-Mac unlock ceremony below re-materializes the
schg paths at the landed bytes and relocks the same day. The SEPARATE
OS-user/key/daemon deploy ceremony (`docs/runbooks/evidence-hp-deploy.md`)
is NOT part of this amendment — it is a fresh-cabinet launch step that
stays dark until the Captain runs it.

**Design of record:** whole-cabinet evidence & self-improvement phased
design (2026-07-16), §2.3 hard preconditions HP-1/HP-2/HP-3 under the §2
safety envelope (A3/A5/A6 in §2.8 Table A; B1 in Table B), §8 decision D1
("push to auto-fix" = front-load the HP track). Authored and self-ratified
per the 2026-07-07 full-autonomy grant; the ceremony itself stays
Captain-only.

**Checkpoint review:**
`shared/interfaces/reviews/evidence-hp-preconditions-cp1.md` (FW-019
artifact for this >300-line batch).

## What this batch is (the three Act-layer blockers, staged dark)

Every piece lands STAGED: unconfigured = byte-identical current behavior
(proven at the composed level — a scratch store written under this tree
with nothing configured is byte-identical, file by file, to one written at
`345461c0`); both new services ship `disabled: true`.

1. **HP-1 — signing-key custody seam** (germline — this amendment):
   `framework/evidence/signing.py` (NEW leaf module) owns WHERE evidence
   signatures come from; `framework/evidence/recorder.py` routes its
   existing sign/verify call sites through it. No signing config (the
   default, and the only pre-ceremony state) = `LocalKeySigner` over the
   store's own key — byte-identical pre-seam behavior. A ceremony-armed
   `mode: broker` config routes every signature through
   `framework/evidence_signing_broker.py` (non-germline daemon, runs as a
   separate OS user post-ceremony): event-hash-shaped payloads only,
   kernel peer credentials (LOCAL_PEERCRED/SO_PEERCRED, feature-detected,
   required), per-uid rate limit, divergent re-sign refusal, key never on
   the socket, key path never in output. A dead/refusing broker is a
   typed, fail-closed `EvidenceError` — never a silent local fallback.
2. **HP-2 — independent recompute legs** (non-germline):
   `framework/evidence_recompute.py` re-derives the fuel-bearing machine
   outcomes from RAW artifacts and appends verification events to its own
   `evt-recompute-*` day trials via the public recorder API;
   `framework/evidence_fuel_integrity.py` consumes them as its third-leg
   signal (report-only; disagree wins, fail-closed). Its detail keys stay
   UNREGISTERED in the germline classification registry (fail-closed
   producer-asserted default) — the promotion is a separately-queued
   ceremony (`docs/runbooks/evidence-recompute.md`), NOT this amendment.
3. **HP-3 — authenticated Captain-label channel** (non-germline):
   `cabinet/scripts/governance-review.py` writes `detail.label_channel`
   (hash-covered in the signed event) minted only by fail-closed channel
   resolvers (token+TTY today; telegram reserved behind the
   `instance/config/platform.yml captain_telegram_chat_id` allowlist);
   `framework/evidence_calibration.py` pairs ONLY attested labels
   (legacy/unknown/diverging rows excluded + counted honestly, never
   silently) and re-verifies the claimed channel against store bytes;
   `framework/evidence_anchor.py --recount-labels` proves the label
   journal append-only against the anchored history.

THREAT HONESTY (design §2.2 R2, stated wherever these surfaces speak):
HP-1 raises the evidence-forgery bar from same-OS-user to root — root can
still forge everything, including the broker's own request log; that
residual is accepted and stated, not hidden. HP-2's independence before
the HP-1 ceremony is corroboration-by-re-derivation under the SAME OS
user, never a trust-domain boundary. HP-3 is tamper-evident, not
tamper-proof, until the key is isolated.

## Why this touches germline

The recorder is inside the locked `framework/evidence` `DIRS[]` cover, and
the signer seam decides WHOSE key mints the signatures every verifier
trusts — exactly the code the judged population must not be able to edit.
The seam module and its suite land inside the same recursive cover so they
are locked the moment they land. The broker daemon itself stays OUTSIDE
germline deliberately: pre-ceremony it grants nothing (no key, no socket),
and post-ceremony its integrity comes from the OS boundary (separate user,
root-owned config/plist), not from schg on officer-side bytes.

**No boundary extension.** No path JOINS or LEAVES the locked set:
`cabinet/scripts/germline-lock.sh` `FILES[]`/`DIRS[]`,
`framework/policies/immutable-core.yml`, and the pre-tool-use hook screen
are all byte-identical in this branch (verified: `git diff` empty on all
three). The germline lockstep consistency suite is green (371 tests; run
recorded in the review artifact). The production signing config
`instance/config/evidence-signing.yml` deliberately does NOT exist in this
branch (only the `.example` ships); it is born root-owned at the deploy
ceremony and enters the lock set THEN, via the immutable-core `pending:`
admission mechanism — a future ceremony, not this amendment.

## Exact ceremony file list

The complete set of schg-locked paths whose content this branch changes —
verified mechanically against `germline-lock.sh` `FILES[]` + `DIRS[]` over
the composed diff (3 of 31 changed paths — 27 from the three reviewed
group patches + 4 integrator docs/pins; no other germline path is touched; `journey.py`, `evidence-event.schema.json`, `evidence-read.sh`,
`graduation.py`, `gate.py`, `apply_watch.py`, and every golden eval are
byte-identical):

1. `framework/evidence/recorder.py` (MODIFIED — `DIRS[]` cover
   `framework/evidence`): sign/verify call sites route through
   `resolve_signer()`; local mode is byte-identical (composed golden
   proof + `test_signing_seam.py` vector pins).
2. `framework/evidence/signing.py` (NEW — `DIRS[]` cover
   `framework/evidence`): the leaf signer seam (local + broker modes,
   fail-closed; frozen v1 preimage formats pinned equal to the
   recorder's).
3. `framework/evidence/tests/test_signing_seam.py` (NEW — `DIRS[]` cover
   `framework/evidence`): its adversarial suite (byte-identity goldens,
   dead-socket fail-closed matrix, config-geometry pins, no-env-behavior
   law, leaf-import law).

## Live application (Captain, same day)

On the armed Mac, after the merge lands on master (the dir unlock is
required for the two NEW files — `chflags -R schg` blocks new-file
creation inside the cover):

```bash
cd /Users/nate/captains-cabinet
sudo cabinet/scripts/germline-lock.sh unlock
git -C . fetch origin && git -C . checkout origin/master -- \
  framework/evidence/recorder.py \
  framework/evidence/signing.py \
  framework/evidence/tests/test_signing_seam.py
sudo cabinet/scripts/germline-lock.sh lock
cabinet/scripts/germline-lock.sh verify
python3.12 -m pytest framework/evidence \
  framework/tests/test_germline_lockstep_consistency.py \
  framework/tests/test_signing_broker.py -q
```

Relock the SAME day. `germline-lock.sh verify` and the lockstep suite are
the exit checks; any drift is a stop-and-page, not a workaround.

## Safety envelope conformance (§2, binding)

- **Dark by default, proven composed:** with no signing config, no broker
  user, no enabled service, every stored byte equals the `345461c0`
  recorder's output (file-hash-identical scratch stores, recorded in the
  review artifact); absent recompute events leave every fuel-integrity
  verdict byte-identical; an all-attested label corpus measures and
  renders byte-identically to the pre-HP-3 shape.
- **Fail-closed everywhere:** broker mode with a dead/refusing socket
  refuses evidence operations (typed error, never local fallback — the
  refusal fires at store OPEN already); an unattestable label context is
  refused before any store byte; unattested/legacy labels are excluded
  from pairing and tallied, never silently dropped and never able to
  shadow an attested label.
- **Determinism:** stored bytes == hashed bytes; v1 + v1.1 events verify;
  frozen signing preimages are byte-exact twins pinned by test; the full
  suite is green at BASE counts plus the new tests (0 removed).
- **Never-a-score:** EVAL-025 green; recompute/calibration/fuel surfaces
  emit counts only, never rates, never officer-visible metrics.
- **No new officer surface:** no new CLI verbs, no new tool grants, no
  new doorway arguments; the broker socket pre-ceremony does not exist,
  post-ceremony is group-gated at the OS layer.
- **Shadow law (Phase-4 inheritance):** recompute events and the
  third-leg join are REPORT-ONLY toward minting; nothing gates, blocks,
  scores, or acts on them; the judging-freeze marker halts the recompute
  service exactly like the other shadow services (pinned in the composed
  seams suite).
- **Observe-only soak (D8):** zero runtime behavior change while
  unconfigured; both services `disabled: true`; the only enable path is
  the Captain's deploy ceremony (`docs/runbooks/evidence-hp-deploy.md`).
