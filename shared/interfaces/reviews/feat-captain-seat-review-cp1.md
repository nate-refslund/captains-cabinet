# FW-019 checkpoint review — feat/captain-seat-review cp1

**Branch:** `feat/captain-seat-review`
**Base:** `origin/master` @ `835b3e2287b30e12a2f16285502e43de68265ede`
  (`Merge pull request #206 from nate-refslund/fix/egg-egress-default`)
**Size:** 11 files, 1017 insertions, 0 deletions (over the FW-019 300-line bar)
**Model:** Claude Opus 5 (1M) — landing agent
**Provenance:** Captain GO 2026-07-26 (captain-decisions officer-note
  2026-07-26T19:14:08Z); per 2026-07-07 full-autonomy grant + 2026-07-21
  ownership-on-GO.

## What the unit is

The MVP of the **Captain-Seat Review** — a retrospective pass run from the
Captain's seat rather than from ours. Three landed pieces:

1. `cabinet/scripts/meta-cognition/captain-seat-pack.sh` — the deterministic,
   read-only evidence half. Prints what he was sent, what he wrote back,
   mechanical repetition counts, open-item dwell and channel health for a
   window. It judges nothing, reaches no network, and prints an absent source
   as a **measured absence** (an absent scoring/consumption loop is itself
   Captain-seat evidence).
2. **Part 1c** in `memory/skills/cross-officer-retro.md` (+ the byte-parity
   doctrine-pack copy) — the judgment half's contract: the reviewer TAKES THE
   CAPTAIN'S PLACE, the emission bar (own artifact + a cost paid IN-WINDOW +
   falsifiable claim + exactly one mechanical fix + what a proposed rule would
   BAN), the evidence boundary, the NO-FINDINGS-on-a-healthy-window rule, the
   ≤3 cap over the existing Part 1b floor, routing into the existing
   per-item-gated proposal sink, the candor precedence, and the kill
   condition.
3. `cabinet/evals/captain-seat/` + section `EVAL-027-CAPTAIN-SEAT` in
   `cabinet/scripts/run-golden-evals.sh` — the deterministic three-arm eval.
   The eval BODY is staged (germline) via
   `docs/proposals/germline-amendment-captain-seat-eval-2026-07-26.md`.

## Prior review of record (the direction gate)

This unit implements the adjudicated direction from the two-model gate of
2026-07-26 — Opus 5 and Fable 5 run independently and blind on the Captain's
question, then adjudicated in writing. Both arms independently reached
worth_adding=yes, MVP-only, propose-only, evidence-or-silent, and named the
same biggest risk (acting on an inferred frustration he does not have). The
six diverged points were adjudicated there and are reflected here:

- **hand-run before wiring** (Opus) composed with **orchestrator altitude
  first** (Fable, whose live measurement showed the runtime retro has never
  stamped a completion) → the MVP was dry-run-validated at orchestrator
  altitude BEFORE this landing, and Part 1c is deliberately NOT wired to a
  cadence here;
- **over-correction guard** (Opus) → emission-bar clause (e);
- **≤3 hard cap with the floor as the real control** → "Cap and floor";
- **preference-pairs read needs a one-word ratify** (Fable) → ratified in the
  same officer-note, cited in Part 1c's closing note;
- **kill condition verbatim** (Opus) → "Kill condition", delete-don't-tune.

The gate record (both positions verbatim + adjudication) lives outside this
repo in the orchestration workspace:
`designs/captain-perspective-retro-2026-07-26.md`.

## Validation evidence (this session, on this branch)

**Premise validation before landing (orchestrator altitude, 14-day window):**
- live-window run → 3 evidence-cited findings, each citing an artifact of the
  Captain's own;
- control (healthy-window) run → **NO FINDINGS**. The bar shipped in Part 1c
  is the v2 bar: a v1 wording FAILED the control arm (it produced findings
  from a quiet window), and the in-window-paid-cost clause plus the explicit
  "a design improvement with no in-window paid cost is a FORBIDDEN output" are
  exactly the repair. That failure is why clause (b) is worded as a cost
  *already paid* rather than a friction *observed*.

**Class-11 discipline — every arm shown RED against pre-change state**
(`__pycache__` purged between runs):

| Arm | Pre-change mutation | Result |
|---|---|---|
| contract-pin | `--repo-root` at a tree holding master's pre-Part-1c skill | RED, 11 clause mismatches, exit 1 |
| repetition | duplicate row deleted from the fixture store | RED: taxonomy counts + "want {'briefing length': 2} got '(none)'", exit 1 |
| healthy | `healthy/` fixture replaced by `repetition/` | RED: "fabricated repetition", exit 1 |
| fail-closed | pack script absent from the repo root | RED: "Captain-seat pack missing", exit 1 (never a skip) |

Unmutated harness re-run afterwards: GREEN.

**Gates run on this branch:**

| Gate | Result |
|---|---|
| `run-golden-evals.sh` (ephemeral sandbox redis, `CABINET_EVALS_REDIS_DISPOSABLE` NOT set) | 30 pass / 0 fail / 0 skip, incl. EVAL-027 |
| `pytest cabinet/scripts/tests` | 4670 passed, 28 skipped (incl. doctrine-pack ⇄ canonical byte parity + retro-step lint) |
| `pytest framework/tests/test_apoptosis.py test_no_launcher_hardcode.py` | 34 passed |
| `docs-track-code-sweep.sh` | DOCS_SWEEP GREEN (files=61 findings=0) |
| `check-layer-separation.sh` | OK — new=0 |
| `state-persistence-preflight.py` | OK — 0 UNACCOUNTED |
| `bash -n` (both CI globs incl. the shebang-selected subdir walk) | clean |
| `shellcheck --severity=error` on `run-golden-evals.sh` + the new pack | clean |

## Safety review

- **No live-store reach from the eval.** Every pack run inside the harness
  points `CAPTAIN_SEAT_ROOT` at a committed fixture tree, rebuilds its
  environment from scratch (no inherited `REDIS_*`/`CABINET_*`), and prepends
  a scratch PATH dir shadowing `redis-cli` with a stub that connects to
  nothing — so the pack's channel-health probe resolves to its own
  "unavailable" branch. No assertion depends on that line; redis genuinely
  absent is equally fine. This is deliberate defence against the paid lesson
  where the suite defaulted to the live 127.0.0.1:6379 and an eval armed the
  real emergency stop.
- **Read-only proved, not claimed.** The harness digests both fixture trees
  before and after the runs and fails if either byte changes — the pack's
  read-only claim is a tested control, not an assumption.
- **Degenerate end is honest.** The healthy fixture keeps a
  present-but-boring correction store on purpose: an absent store would make
  "reports none" vacuous (the sensor-tests-nothing class), so the arm also
  pins that the repetition line was actually printed.
- **Propose-only, per-item gated.** Part 1c terminates in the existing
  `mc_emit_proposal` → briefing decision-queue path. Nothing self-applies.
- **Candor precedence explicit.** A fix that would soften, delay or drop
  dissent is INVALID by contract; such a tension is surfaced AS a tension.
  Preference-guessing is unrepresentable (no "he would like X" output).
- **Never-a-score respected.** Repeat counts are retro inputs, never
  officer-visible scores; no new file references the report-only suite-scalar
  series (by either of the two tokens EVAL-025 C1 scans for), so its consumer
  allowlist is untouched. This paragraph originally quoted one of those
  tokens verbatim and CI caught it — writing a guarded literal into a doc
  trips the guard that polices it, and the fix is to reword rather than to
  widen the allowlist for an incidental mention.
- **Layer separation.** The pack, the harness and both fixtures name no
  person, product, lane, employer or deployment; fixture subjects are generic
  ("briefing length", "overnight pings").

## Known limitations (stated, not hidden)

- The contract-pin arm is a substring pin: it proves the clauses are present,
  not that a reviewer obeys them. Obedience is what the per-item Captain gate
  on every emitted finding is for.
- The harness shims `python3.12` to the interpreter it is running under,
  because the pack pins the house interpreter by name while the runner
  section resolves `python3.12 || python3`. The eval therefore tests the
  pack's logic, not the interpreter-name layout of the box.
- Part 1c is deliberately NOT wired to the runtime retro cadence. Per the
  adjudicated order, that waits until a fresh instance demonstrably completes
  retro runs; until then the pass runs at orchestrator altitude.

## Handback

The eval BODY (`memory/golden-evals/eval-027-captain-seat-review.md`) cannot
land from a build lane — that directory is schg-locked. It is staged verbatim
in `docs/proposals/germline-amendment-captain-seat-eval-2026-07-26.md` for the
Captain's next unlock window. The EVAL-027 runner section keys off the
non-germline harness and is green with or without the body file.
