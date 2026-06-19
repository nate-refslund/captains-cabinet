"""Pytest config for the fidelity test suite.

Registers the ``live`` marker so the T5 real end-to-end smoke
(test_run_e2e_smoke.py) can be selected/deselected explicitly
(``-m live`` / ``-m "not live"``) without a PytestUnknownMarkWarning. The
``live`` test self-skips when its OAuth/Voyage/retrodiction preflight fails, so
a plain ``pytest`` run is safe; the marker just makes the deselection clean.
"""

from __future__ import annotations


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live: real end-to-end run hitting the OAuth `claude -p` judge + "
        "Voyage + retrodiction lib; self-skips when those deps are unavailable.",
    )
