"""Executable acceptance harness for the three Onboarding v2 personas.

Run from the repository root:

    python3.12 -m framework.onboarding.evaluate_personas

It grants only the synthetic fixture folder, runs the real canonical journey,
and prints machine-readable timing/finding/citation evidence.  Five minutes is
the product target; the deterministic fixture pass should finish in seconds.
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from framework.onboarding import journey

FIXTURE_ROOT = Path(__file__).with_name("fixtures")
TARGET_SECONDS = 5 * 60
PERSONAS = {
    "software-product": {
        "purpose": "Find one release risk before it surprises the product team.",
        "expected_kind": "software_command_drift",
    },
    "client-services": {
        "purpose": "Find one delivery risk before the next client check-in.",
        "expected_kind": "conflicting_commitment",
    },
    "community-nonprofit": {
        "purpose": "Find one practical gap in the next volunteer rota.",
        "expected_kind": "attention_marker",
    },
}


def evaluate(name: str) -> dict:
    spec = PERSONAS[name]
    source = FIXTURE_ROOT / name
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=f"cabinet-onboarding-{name}-") as tmp:
        root = Path(tmp)
        proposal = journey.act(
            {
                "action": "propose_window",
                "action_id": f"eval-{name}-propose",
                "surface": "test",
                "source": str(source),
                "purpose": spec["purpose"],
                "relationship_destination": "reversible",
            },
            root,
            now="2026-07-14T12:00:00Z",
        )
        result = journey.act(
            {
                "action": "ratify_charter",
                "action_id": f"eval-{name}-ratify",
                "surface": "test",
                "expected_revision": proposal["state"]["revision"],
                "charter_hash": proposal["state"]["charter"]["hash"],
            },
            root,
            now="2026-07-14T12:00:01Z",
        )
        finding = result["state"]["first_dividend"]["finding"]
        elapsed = time.perf_counter() - started
        passed = (
            finding["kind"] == spec["expected_kind"]
            and finding["quality"] == "strong"
            and bool(finding["citations"])
            and elapsed <= TARGET_SECONDS
        )
        return {
            "persona": name,
            "passed": passed,
            "elapsed_seconds": round(elapsed, 4),
            "target_seconds": TARGET_SECONDS,
            "finding_kind": finding["kind"],
            "expected_kind": spec["expected_kind"],
            "summary": finding["summary"],
            "citations": finding["citations"],
            "charter_hash": result["state"]["charter"]["hash"],
            "manifest_hash": result["state"]["source"]["manifest_hash"],
            "card_id": result["card"]["id"],
        }


def main() -> int:
    results = [evaluate(name) for name in PERSONAS]
    payload = {"schema": "cabinet.onboarding-persona-eval/v1", "passed": all(r["passed"] for r in results), "results": results}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
