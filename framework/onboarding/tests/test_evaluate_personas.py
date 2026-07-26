"""Red-path coverage for the persona acceptance harness.

The green path (every persona passes) is exercised by
test_journey.py::test_persona_evaluation_harness_is_executable. These
tests pin the FAILURE path so a vacuously-green acceptance gate — one that can
never report failure — would be caught.
"""
from __future__ import annotations

from framework.onboarding import evaluate_personas


def _mismatch_software_product(monkeypatch) -> None:
    # Point software-product at a kind its fixture never produces (its real
    # dividend is software_command_drift), leaving the other personas intact so
    # no source_missing raise masks the assertion.
    spec = dict(evaluate_personas.PERSONAS["software-product"])
    spec["expected_kind"] = "attention_marker"
    monkeypatch.setitem(evaluate_personas.PERSONAS, "software-product", spec)


def test_evaluate_flags_a_persona_whose_finding_kind_mismatches(monkeypatch):
    _mismatch_software_product(monkeypatch)
    result = evaluate_personas.evaluate("software-product")
    assert result["passed"] is False
    assert result["finding_kind"] != result["expected_kind"]


def test_main_returns_nonzero_when_a_persona_fails(monkeypatch, capsys):
    _mismatch_software_product(monkeypatch)
    code = evaluate_personas.main()
    capsys.readouterr()  # swallow the machine-readable JSON payload
    assert code == 1
