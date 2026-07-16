# Never-a-score eval (EVAL-025) — harness + fixtures

Runnable half of golden eval **eval-025-never-a-score** (NEVER-A-SCORE LAW,
whole-cabinet evidence design §2.5, 2026-07-16): evidence-derived aggregates
are **monitoring metrics and kill criteria ONLY** — never officer-visible
scores, never inputs to generation or selection. A future consumer that
surfaces an evidence metric to officers fails the suite.

Layout:
- `harness.py` — deterministic static scanner + `--self-test` CLI.
  Wired into `cabinet/scripts/run-golden-evals.sh` (section
  EVAL-025-NEVER-A-SCORE). Checks, all static and read-only:
  1. every tracked file referencing the report-only
     `golden-eval-scalar` series (or its emit lib) sits in the pinned
     allowlist — a new reader is an unsanctioned aggregate consumer;
  2. the officer evidence projection (`cabinet_projection` in
     `framework/evidence/recorder.py`) allow-lists no
     score/aggregate/cost/fuel-shaped detail key (AST, token deny-list,
     exemptions pinned with written justification);
  3. the projection's top-level and per-record shape equals the pinned
     sets and its `trust` literal stays `untrusted_observation` — no
     scores/stats section can appear without deliberately editing this
     eval's fixture inside the same governance-reviewed change;
  4. doctrine strings hold: the UNTRUSTED OBSERVATIONS banner, the trust
     const in schema + verifier, `evidence-raw-read-deny` in
     base-safety.yml, the writers' REPORT-ONLY doctrine, the series'
     gitignore line;
  5. `cabinet/scripts/evidence-read.sh` still invokes only the `project`
     subcommand (the sole officer evidence doorway names no raw verb);
  6. the deny tokenizer itself is pinned by labeled vectors.
- `fixtures/law-pins.json` — the pinned allowlist, exemptions, projection
  shape, doctrine strings, and classifier vectors (fail-closed: a
  missing/malformed fixture is a FAIL, never a skip). The fixture also
  carries the purge/retention **promotion-revocation** doctrine (design
  §2.4) verbatim until its executable home lands with the Phase-4
  fuel-integrity check.
- Tests: `cabinet/scripts/tests/test_never_a_score_eval.py`
  (CI-collected; includes the body↔harness↔runner-section pairing
  validator) and the behavioral half of the doctrine laws in
  `framework/tests/test_evidence_doctrine_laws.py`.

WHY the eval body is not beside this directory: `memory/golden-evals/` is
germline (schg-locked on the live checkout — see
`cabinet/scripts/germline-lock.sh` DIRS). The eval BODY
(`memory/golden-evals/eval-025-never-a-score.md`) lands through the Phase-1
evidence ceremony's unlock window (dir-cover: no lock-list change); this
directory is deliberately non-germline so the harness, fixtures, and runner
wiring are ordinary reviewable code.

Honest limitation: check 1 is a token scan over tracked file contents — a
consumer that constructs the series path dynamically evades the grammar.
Treat such evasion as the violation itself; label the consumer into the
allowlist review the moment it is found. Checks 2–3 pin the single officer
evidence read surface; aggregates computed elsewhere are covered insofar as
they reach that surface or the scalar series.
