# Captain-seat eval (EVAL-027) — harness + fixtures

Runnable half of golden eval **eval-027-captain-seat-review** (CAPTAIN-SEAT
REVIEW, Captain ruling 2026-07-26): the retro gains **Part 1c**, a pass run
from the Captain's seat — the reviewer TAKES HIS PLACE and reports what the
window COST him, evidence-cited or silent.

The eval BODY belongs in `memory/golden-evals/` (schg-locked on the live
checkout); it is staged for the Captain's next germline window via
`docs/proposals/germline-amendment-captain-seat-eval-2026-07-26.md`. The
runnable half lives here, non-germline, wired into
`cabinet/scripts/run-golden-evals.sh` (section EVAL-027-CAPTAIN-SEAT) — the
house pattern of EVAL-024/025/026.

What it pins, and why those two things:

- the **evidence half** (`cabinet/scripts/meta-cognition/captain-seat-pack.sh`)
  must COUNT the repetition it is shown and must print an absent store as a
  measured ABSENCE — a pass that miscounts, or that quietly omits what it
  could not find, gives the reviewer a false window;
- the **judgment half's contract** (Part 1c of
  `memory/skills/cross-officer-retro.md`) must keep its load-bearing clauses.
  That text is the only thing between this pass and a friction-invention
  machine, so silent dilution is a FAIL.

Layout:

- `harness.py` — deterministic `--self-test` CLI. Three arms:
  1. **repetition** — the pack over `fixtures/repetition/` (same subject twice)
     reports that subject with count 2 plus the pinned taxonomy counts;
  2. **healthy** — the pack over `fixtures/healthy/` (every subject distinct,
     the other stores absent) reports repetition `(none)` AND prints each
     absent store as an `ABSENT:` line. This is the **degenerate end**: a quiet
     window must stay quiet and honest. The store is present-but-boring rather
     than absent on purpose — an absent store would make "reports none"
     vacuous;
  3. **contract-pin** — every pinned Part 1c clause is still present verbatim
     in the skill (the in-window-paid-cost rule, the NO FINDINGS healthy-window
     rule, the kill condition, the candor precedence, never-a-score).
  Plus a fourth check: both fixture trees are byte-identical after the runs —
  the pack claims read-only, and a control nobody tried to defeat is an
  assumption.
- `fixtures/pins.json` — the pinned expectations (every clause carries its
  `why`).
- `fixtures/{repetition,healthy}/shared/interfaces/action-lessons.yml` —
  synthetic stores naming no real person, product, lane or deployment.

Safety — this eval can never touch Redis, the network, or any live store:
every run points `CAPTAIN_SEAT_ROOT` at a committed fixture tree, the
subprocess environment is rebuilt from scratch (no inherited `REDIS_*`), and a
scratch PATH dir shadows `redis-cli` with a stub that connects to nothing, so
the pack's channel-health probe resolves to its own "unavailable" branch. No
assertion depends on that line — redis genuinely absent is equally fine. The
paid lesson behind this: the golden suite once defaulted to the live
127.0.0.1:6379 and an eval armed the real emergency stop.

Run it directly:

    python3.12 cabinet/evals/captain-seat/harness.py --self-test

Class-11 discipline (each arm was shown RED against pre-change state before
landing): the contract-pin arm fails against master's pre-Part-1c skill text;
the repetition arm fails when the fixture's duplicate row is removed; the
healthy arm fails when pointed at the repetition fixture; and a missing pack
script fails closed rather than skipping.
