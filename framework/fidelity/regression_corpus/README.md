# Regression corpus — frozen human corrections (flywheel §6.2)

Every Captain correction (edit / skip / veto / undo / human-wrong verdict) on
the consequence ledger is frozen here as a replayable regression case, so the
F1/eval cadence can gate behavior changes on task-level non-regression:
**no frozen case regresses AND ≥ 1 improves**
(`framework/fidelity/regression_gate.py`).

- **Harvester:** `cabinet/scripts/build-regression-corpus.py` (thin CLI over
  `framework/fidelity/regression_corpus_lib.py`). Reads the ledger read-only
  via `consequence.read_ledger()` (dedup, sim-quarantine, `CABINET_EVENT_LOG_DIR`).
  Idempotent + deterministic: re-runs append new cases only.
- **Layout:** `cases/case-<16hex>.json` (one frozen case each) + `manifest.json`
  (deterministic index: sorted ids, kind counts, fingerprint — no timestamps).
- **Case shape:** `{case_format, case_id, cell, situation, human_verdict}` —
  the situation is a leak-safe **replay reference** (ts/actor/lane/action/
  subject/refs); the ledger stores no message content, so neither does this
  corpus. The `cell` keys exactly like `consequence.compute_ratios`
  (`__unstamped__` sentinel included), joining each case to the trust cell it
  disciplines.

## FROZEN contract

Case files are **immutable once written**. The harvester never rewrites one;
a regenerated case that disagrees with its frozen file is an integrity alarm
(ledger append-only violation or serialization drift) — the frozen file wins
and the harvest exits 3. Do not hand-edit case files: `regression_gate.load_corpus`
refuses id/filename drift and malformed cases (fail-safe → `no_verdict`,
never a spurious pass).

This dir is deliberately **not** `memory/golden-evals/` — that dir is germline
schg-locked (`cabinet/scripts/germline-lock.sh`), while a growing corpus needs
appends. If this dir is ever added to the germline lock set, the harvester's
append contract must be revisited in the same change.
