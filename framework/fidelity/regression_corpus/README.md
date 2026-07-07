# Regression corpus — mechanism slot (store relocated, egg plan R009)

The frozen-correction corpus MECHANISM lives in framework; the corpus DATA
does not. Since egg plan R009 (2026-07-07) the store — `cases/*.json` +
`manifest.json` — is instance-layer data at
**`instance/fidelity/regression_corpus/`** (harvested Captain corrections are
deployment-specific, so the framework egg ships no corpus). See the README
there for the store layout and the FROZEN contract.

- **Harvester:** `cabinet/scripts/build-regression-corpus.py` (thin CLI over
  `framework/fidelity/regression_corpus_lib.py`) — its `--corpus-dir` defaults
  to the instance store. The cabinet layer owns that instance default;
  framework code must not path-couple to `instance/`
  (`cabinet/scripts/check-layer-separation.sh`).
- **Gate:** `framework/fidelity/regression_gate.py` — PASS iff **no frozen
  case regresses AND ≥ 1 improves**; empty/missing corpus → `no_verdict`,
  never a spurious pass.
- **This dir** is the lib's `DEFAULT_CORPUS_DIR`, kept as a fail-safe EMPTY
  slot: a caller that never passes `corpus_dir` reads an honest empty corpus
  and the gate yields `no_verdict`. On a fresh deployment the instance store
  is created by the first harvest.
