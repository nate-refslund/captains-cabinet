from __future__ import annotations

import hashlib
from pathlib import Path

from framework.evidence.dogfood import run


def test_dogfood_001_generates_verified_purge_surviving_review_bundle(tmp_path: Path):
    bundle = tmp_path / "DOGFOOD-001-review-bundle"
    result = run(bundle)
    assert result["ok"] is True
    assert result["trial_id"] == "DOGFOOD-001"
    assert result["scenario_count"] >= 14
    assert result["pre_purge_event_count"] > 50
    assert result["post_purge_store_ok"] is True
    assert result["source_unchanged"] is True
    assert result["checksums_ok"] is True
    assert (bundle / "purge-receipt.json").is_file()
    assert (bundle / "post-purge-verification.json").is_file()
    assert "**PASS.**" in (bundle / "audit-report.md").read_text()
    for line in (bundle / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        assert hashlib.sha256((bundle / name).read_bytes()).hexdigest() == expected
