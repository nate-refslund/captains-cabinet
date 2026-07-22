"""Pytest config for the fidelity test suite.

Registers the ``live`` marker so the T5 real end-to-end smoke
(test_run_e2e_smoke.py) can be selected/deselected explicitly
(``-m live`` / ``-m "not live"``) without a PytestUnknownMarkWarning. The
``live`` test self-skips when its OAuth/Voyage/retrodiction preflight fails, so
a plain ``pytest`` run is safe; the marker just makes the deselection clean.
"""

from __future__ import annotations

import os
from pathlib import Path

from framework import env  # instance-config path resolver (retro_pipe_dir); a
                           # sibling of framework.fidelity and import-light — NOT
                           # the fidelity package whose test siblings from-import
                           # scoring names, so this stays collection-safe.


def _retro_available() -> bool:
    """Availability check WITHOUT importing framework.fidelity (whose test
    siblings from-import scoring names and would raise on a lib-less install
    before this guard could act). Resolves the retrodiction pipe dir through the
    EXACT seam framework/fidelity/retro.py uses — CABINET_RETRO_PIPE_DIR override,
    else framework.env.retro_pipe_dir() (instance/config/platform.yml), else the
    ``_retrodiction-absent`` sentinel beside retro.py — so this collect-guard and
    retro.py's runtime shim can never disagree. A hardcoded ~/.screenpipe default
    made them diverge on a scrubbed/export tree sitting on a machine that HAS
    ~/.screenpipe: guard True while retro.py's retro_available() was False ->
    modules un-ignored, then crashing at import (17 collection errors + 16
    runtime failures)."""
    retro_dir = os.environ.get("CABINET_RETRO_PIPE_DIR") or env.retro_pipe_dir()
    pipe_dir = (
        Path(retro_dir).expanduser() if retro_dir
        # Sentinel retro.py falls back to when nothing is configured:
        # framework/fidelity/_retrodiction-absent. This conftest lives one dir
        # deeper (tests/), so parent.parent lands on framework/fidelity/ — the
        # byte-identical path retro.py resolves from its own __file__.
        else Path(__file__).resolve().parent.parent / "_retrodiction-absent"
    )
    try:
        return (pipe_dir / "lib.py").exists()
    except OSError:  # unreadable (mode-000 null-hatch stand-in) ≡ absent — mirror
        return False  # retro.py's _exists_unprivileged; never crash collection

# Flavor-A coupling guard (2026-07-02, CI run 28618-484-301): the scoring engine
# is imported from the screenpipe retrodiction pipe (framework/fidelity/retro.py)
# — deliberate reuse, but on any machine WITHOUT ~/.screenpipe (CI runners,
# flavor-B Mini) 18 test modules error at COLLECTION and drown the other
# ~1,300 tests. Until plan A2.1 vendors the lib into framework/fidelity/
# (then this list DELETES), skip exactly the coupled modules, loudly —
# visibly skipped, never silently green. graduation/consequence/authority
# tests (the trust path) are NOT on this list and always run.
collect_ignore = []
if not _retro_available():
    collect_ignore = [
        "test_aggregate.py",
        "test_benchmark.py",
        "test_decision_cell.py",
        "test_e2e_flow.py",
        "test_f4_consequence_intent.py",
        "test_f4_golden_evals.py",
        "test_f4_judge.py",
        "test_f4_leakguard.py",
        "test_f4_run_case_clone_identity.py",
        "test_f4_run_case_gather.py",
        "test_oauth_llm.py",
        "test_officer_runner.py",
        "test_retro_shim.py",
        "test_run_e2e_smoke.py",
        "test_run_f1.py",
        "test_scorer.py",
        # SOV-7 modules import the retro lib at module level too — added
        # after this list was written and never registered, so they ERRORED
        # at collection on every retro-less box (CI red since 2026-07-08).
        "test_sov7_identity.py",
        "test_sov7_outcome_judge.py",
        # SIE-9 sim runner (agi-wires 2026-07-09, registered 2026-07-10):
        # imports run_f1 -> oauth_llm -> retro.parse_json_block at module
        # level, so it collection-errors on retro-less boxes exactly like
        # test_run_f1.py (already listed). Also unblocks the World binding
        # gate downstream: the collection error killed the framework suite,
        # so cabinet/cache/org-runtime.sqlite3 (side-effect of the events
        # emitter tests) never materialized and two codex mechanism_path
        # checks failed on the runner.
        "test_sim_runner.py",
    ]
    print(
        "[fidelity conftest] screenpipe retrodiction lib ABSENT -> skipping "
        f"{len(collect_ignore)} flavor-A-coupled test modules (vendoring: plan A2.1)"
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live: real end-to-end run hitting the OAuth `claude -p` judge + "
        "Voyage + retrodiction lib; self-skips when those deps are unavailable.",
    )
