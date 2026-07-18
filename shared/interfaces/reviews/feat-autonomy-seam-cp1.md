# Review artifact — feat/autonomy-seam checkpoint 1 (FW-019)

**Batch:** autonomy-graded action seam landing — 17 files (14 lane + ledger +
plan doc + this artifact), +~1770/-68 lines. Landed 2026-07-18 by the
autonomy-seam integrator from the reviewed lane diff on a clean worktree off
origin/master @c117de12. Provenance: per the 2026-07-07 full-autonomy grant;
Captain doctrine ruling 2026-07-17 (autonomy-graded action), recorded to
`shared/interfaces/captain-decisions.md` as the 2026-07-18T09:50:30Z
officer-note at landing (from the orchestrator-backlog capture made at
ruling time).

## What lands

The Captain's 2026-07-17 ruling — "every autonomous mutation's mode is a
FUNCTION of the posture level: propose-first/earn-trust → ASK;
act-then-tell → ACT with proven undo + receipt; sovereign → GO; Ring-0
ALWAYS Captain regardless" — becomes THE machine law:

1. **The seam** — `framework/authority/action_mode.py` (NEW, unlocked half
   of the authority dir; the nine judged-authority modules around it stay
   schg). `action_decision({ring, reversibility, category[, undo_handle]},
   posture)` → `propose|act_tell|go` + `captain_card`. `RING0_CATEGORIES`
   = {constitution, germline, officer-model-routing, claude-binary,
   spend-caps} pinned by EQUALITY; a Ring-0 category forces ring 0 against
   a claimed ring 2 (tighten claims, never honor them upward). The
   forward-compatible `act_then_tell` rung grants `act_tell` ONLY with
   `reversibility=reversible` AND a registered `undo_handle` — the ladder
   does not define the rung today (test-pinned). Every unknown
   posture/ring/reversibility/category/descriptor fails closed to
   `propose`; never raises. Pure: posture resolves with
   `file_needs=False`; nothing written. `ring_for_repo_path` classifies
   repo paths off the immutable-core enumeration (unknown ⇒ None ⇒
   propose downstream).

2. **Retrofits (tighten-only)** —
   `cabinet/scripts/workaround-retest.py`: the retirement DISPOSITION is
   asked of the seam and stamped (`action_mode`, `captain_card`) on every
   fix_confirmed verdict + proposal row; rows stay `propose_only: true` in
   EVERY mode; `_PRERATIFIED_AUTO_CLASSES` pinned EMPTY until a recorded
   Captain ratification; Ring-0 components map to Ring-0 categories.
   `cabinet/scripts/memory-supersede-apply.py`: the seam is an OUTER gate —
   an ARMED soak additionally requires an act-mode answer (`go`/`act_tell`)
   or the gate reads `held-by-action-seam` (recorded, never executed); a
   `go` answer never bypasses soak/hold/veto. Under today's
   guardian/earn_up postures both organs behave byte-identically to v1
   propose-only.

3. **Golden eval EVAL-026-ACTION-MODE** — deterministic harness
   `cabinet/evals/action-mode/harness.py` + pinned
   `fixtures/matrix.json` (32 arms), wired into
   `cabinet/scripts/run-golden-evals.sh` fail-closed (missing
   harness/fixture = FAIL; only a missing interpreter skips). The eval
   BODY belongs in the schg-locked `memory/golden-evals/` and is STAGED
   for the Captain's next germline unlock window via
   `docs/proposals/germline-amendment-action-mode-eval-2026-07-17.md` —
   the house EVAL-024/EVAL-025 pattern (body germline, harness
   non-germline). Nothing else waits on the body.

4. **Doctrine** — `framework/constitution-base.md` new section "Autonomy —
   GRADED ACTION LAW (Captain ruling 2026-07-17)"; adoption-gates GATE
   0/1/3 rewritten around the seam in the verbatim twins
   `docs/runbooks/platform-adoption-gating.md` +
   `memory/skills/platform-radar-triage.md` (parity test-pinned); the
   triage skill obeys the stamp — tighten-only, never widen.

## Review provenance

Built and reviewed upstream in the autonomy-seam lane (builder → suites →
lane.diff emitted with the full test battery green). Integrator re-ran the
entire battery in this worktree at the tip (below) — no divergence from
the lane's recorded results. Diff base 345461c0 → tip c117de12: none of
the 14 touched files changed in between; `git apply --3way` clean, zero
conflicts, zero dropped hunks.

## SCHG guard (zero locked hunks)

`ls -lO` on every touched live path: all 14 unlocked. New files land in
unlocked dirs (`cabinet/evals/action-mode/`, `framework/authority/` file
level, `framework/authority/tests/`, `docs/proposals/`). The only germline
content in the wave — the eval body — ships exclusively as the staged
amendment doc, never a tree edit.

## Gates at landing (this worktree, python3.12)

- seam suite `framework/authority/tests/test_action_mode.py`: **137 passed**
- retrofit + twin-parity suites (`test_memory_supersede_apply.py`,
  `test_workaround_retest.py`, `test_platform_radar_triage_skill.py`):
  **132 passed**
- framework/authority full: **934 passed / 5 skipped**
- full `cabinet/scripts/tests`: **1605 passed / 5 skipped / 1 failed** —
  `test_evidence_seam_bypass_replay[evidence-access.sh]`, REPRODUCED
  byte-identically on a PRISTINE detached worktree at c117de12: the
  pre-existing local-env condition VAULT-BROWSE-1/LIBRARY-P2-1 already
  recorded, on a surface this lane never touches. CI on the landing push
  is the authority.
- EVAL-026 harness `--self-test`: **32/32 matrix arms hold; ring0
  enumeration + mode vocabulary pinned**
- `bash -n cabinet/scripts/run-golden-evals.sh`: clean
- docs-track-code-sweep: **GREEN (files=54 findings=0)**
- check-layer-separation: **new=0** (baseline=24 allowlist=19 current=43)
- A13 + id-uniqueness + ledger-status-parity: green **pre (332)** and
  **post (333)**

## Ledger

Row `AUTONOMY-SEAM-1` (status=done, last_update 2026-07-18) + plan-doc §48
addendum table row (A13 parity).

## Residuals

- Eval body `memory/golden-evals/eval-026-action-mode-autonomy-seam.md`:
  Captain-only germline-window ceremony (staged verbatim in the amendment
  doc, apply/verify/relock steps included).
- Pre-existing local-env `test_evidence_seam_bypass_replay
  [evidence-access.sh]` failure (not this lane's surface; tracked since
  VAULT-BROWSE-1).
