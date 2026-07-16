"""Phase-1 per-class retention: the default is a byte-for-byte no-op.

Pins the whole-cabinet evidence design (2026-07-16) Phase-1 item 4 contract:
`retention_classes` is an additive, Captain-gated control key. Unset, the
retention pass behaves exactly as before; old control files written before
the key existed keep verifying (the control signature covers only present
keys); per-class ages apply ONLY to day-bounded taxonomy trials
(``evt-<class>-<yyyymmdd>``) and fall back to the scalar dial everywhere
else. Lives in unlocked framework/tests/ (freestanding additions stay out of
the germline package).
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from framework.evidence import recorder as recorder_module
from framework.evidence.__main__ import main as evidence_cli
from framework.evidence.recorder import (
    CONTROL_SCHEMA,
    EvidenceError,
    EvidenceRecorder,
    _utc_now,
)
from framework.evidence.verifier import verify_store


def _aged_stamp(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )


def _append_aged(recorder: EvidenceRecorder, trial_id: str, days_ago: int) -> None:
    """Append one event whose recorder-owned ``ts`` is ``days_ago`` old.

    Swaps the module clock only for the append (the house pattern —
    test_recorder.py monkeypatches the same seam) and always restores it.
    """
    original = recorder_module._utc_now
    recorder_module._utc_now = lambda: _aged_stamp(days_ago)
    try:
        context = recorder.trace(trial_id, surface="system")
        recorder.append(
            context,
            phase="system",
            status="succeeded",
            actor={"kind": "system", "id": "retention-test"},
            component={"name": "retention-test", "version": "1"},
            detail={"action": "seed"},
        )
    finally:
        recorder_module._utc_now = original


def _trial_dirs(store: Path) -> set[str]:
    trials = store / "trials"
    return {p.name for p in trials.iterdir() if p.is_dir()} if trials.is_dir() else set()


def test_fresh_store_defaults_to_no_classes_and_noop(tmp_path: Path):
    store = tmp_path / "store"
    recorder = EvidenceRecorder(store)
    _append_aged(recorder, "evt-noise-20200101", days_ago=400)

    assert recorder.control()["retention_classes"] is None
    result = recorder.enforce_retention(actor="captain")
    assert result == {
        "ok": True,
        "schema": "cabinet.evidence-retention/v1",
        "retention_days": None,
        "retention_classes": None,
        "purged": [],
    }
    assert "evt-noise-20200101" in _trial_dirs(store)


def test_old_control_file_without_the_key_still_verifies_and_noops(tmp_path: Path):
    """A pre-Phase-1 control.json (no retention_classes key) is untouched v1
    data: it must keep verifying and behave exactly as before."""
    store = tmp_path / "store"
    recorder = EvidenceRecorder(store)
    _append_aged(recorder, "evt-noise-20200101", days_ago=400)
    # Rewrite control in the exact pre-change shape (signature covers only
    # the keys present).
    recorder._write_control({
        "schema": CONTROL_SCHEMA,
        "retention_days": None,
        "diagnostic_mode": False,
        "diagnostic_until": None,
        "updated_at": _utc_now(),
        "updated_by": "captain-default",
    })
    control = recorder.control()
    assert "retention_classes" not in control
    assert verify_store(store)["ok"] is True

    result = recorder.enforce_retention(actor="captain")
    assert result["purged"] == [] and result["retention_classes"] is None
    assert "evt-noise-20200101" in _trial_dirs(store)

    # Appends still work against the old-shape control file.
    _append_aged(recorder, "evt-noise-20200101", days_ago=399)


def test_scalar_only_behavior_is_unchanged(tmp_path: Path):
    store = tmp_path / "store"
    recorder = EvidenceRecorder(store)
    _append_aged(recorder, "evt-old-20200101", days_ago=40)
    _append_aged(recorder, "trial-fresh", days_ago=0)

    recorder.configure(actor="captain", retention_days=30, diagnostic_mode=False)
    result = recorder.enforce_retention(actor="captain")
    assert result["retention_days"] == 30
    assert result["retention_classes"] is None
    assert len(result["purged"]) == 1
    remaining = _trial_dirs(store)
    assert "evt-old-20200101" not in remaining and "trial-fresh" in remaining


def test_class_override_purges_only_that_class(tmp_path: Path):
    store = tmp_path / "store"
    recorder = EvidenceRecorder(store)
    _append_aged(recorder, "evt-noise-20200101", days_ago=40)
    _append_aged(recorder, "evt-keep-20200101", days_ago=40)
    _append_aged(recorder, "trial-plain", days_ago=40)

    recorder.configure(
        actor="captain",
        retention_days=None,
        diagnostic_mode=False,
        retention_classes={"noise": 30},
    )
    assert recorder.control()["retention_classes"] == {"noise": 30}
    result = recorder.enforce_retention(actor="captain")
    assert result["retention_days"] is None
    assert result["retention_classes"] == {"noise": 30}
    assert len(result["purged"]) == 1
    remaining = _trial_dirs(store)
    assert "evt-noise-20200101" not in remaining
    assert {"evt-keep-20200101", "trial-plain"} <= remaining
    receipts = list((store / "purge-receipts").glob("purge-*.json"))
    assert receipts, "a per-class purge must leave the usual signed receipt"


def test_class_overrides_mix_with_the_scalar_dial(tmp_path: Path):
    store = tmp_path / "store"
    recorder = EvidenceRecorder(store)
    _append_aged(recorder, "evt-noise-20200101", days_ago=40)   # class says keep
    _append_aged(recorder, "evt-other-20200101", days_ago=40)   # falls to scalar
    _append_aged(recorder, "trial-plain", days_ago=40)          # scalar

    recorder.configure(
        actor="captain",
        retention_days=30,
        diagnostic_mode=False,
        retention_classes={"noise": 3650},
    )
    result = recorder.enforce_retention(actor="captain")
    assert len(result["purged"]) == 2
    remaining = _trial_dirs(store)
    assert "evt-noise-20200101" in remaining
    assert "evt-other-20200101" not in remaining
    assert "trial-plain" not in remaining


def test_exclude_still_shields_live_trials_from_class_purge(tmp_path: Path):
    store = tmp_path / "store"
    recorder = EvidenceRecorder(store)
    _append_aged(recorder, "evt-noise-20200101", days_ago=40)
    recorder.configure(
        actor="captain",
        retention_days=None,
        diagnostic_mode=False,
        retention_classes={"noise": 1},
    )
    result = recorder.enforce_retention(actor="captain", exclude={"evt-noise-20200101"})
    assert result["purged"] == []
    assert "evt-noise-20200101" in _trial_dirs(store)


def test_retention_class_validation_is_fail_closed(tmp_path: Path):
    recorder = EvidenceRecorder(tmp_path / "store")
    bad_maps = [
        {"Bad Name": 30},          # spaces / uppercase
        {"UPPER": 30},
        {"": 30},
        {"x" * 65: 30},
        {"noise": 0},
        {"noise": 3651},
        {"noise": True},
        {"noise": "soon"},
    ]
    for bad in bad_maps:
        with pytest.raises(EvidenceError) as excinfo:
            recorder.configure(
                actor="captain",
                retention_days=None,
                diagnostic_mode=False,
                retention_classes=bad,
            )
        assert excinfo.value.code == "retention_class_invalid"
    # Captain-only, exactly like every other control mutation.
    with pytest.raises(EvidenceError) as excinfo:
        recorder.configure(
            actor="officer",
            retention_days=None,
            diagnostic_mode=False,
            retention_classes={"noise": 30},
        )
    assert excinfo.value.code == "captain_required"
    # An empty map normalizes to None (back to the scalar dial).
    control = recorder.configure(
        actor="captain", retention_days=None, diagnostic_mode=False, retention_classes={}
    )
    assert control["retention_classes"] is None


# --- CLI exposure (Captain capability token, same gate as every mutation) ---

def _run_cli(capsys: pytest.CaptureFixture, argv: list[str]) -> tuple[int, dict]:
    code = evidence_cli(argv)
    return code, json.loads(capsys.readouterr().out.strip())


def _mint_token(store: Path, target: Path) -> Path:
    key = (store / ".signing-key").read_bytes()
    token = hmac.new(
        key, b"cabinet.evidence-captain-capability/v1", hashlib.sha256
    ).hexdigest()
    target.write_text(token + "\n", encoding="utf-8")
    target.chmod(0o600)
    return target


@pytest.fixture(autouse=True)
def _no_ambient_captain_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CABINET_CAPTAIN_TOKEN_FILE", raising=False)


def test_cli_retention_class_flags(tmp_path: Path, capsys: pytest.CaptureFixture):
    store = tmp_path / "store"
    EvidenceRecorder(store)
    token = _mint_token(store, tmp_path / "captain.token")

    # The new flags are mutations: without the capability token they refuse.
    code, out = _run_cli(
        capsys, ["--store", str(store), "control", "--retention-class", "noise=30"]
    )
    assert code == 3 and out["ok"] is False

    # With the token: set, preserve-through-unrelated-change, then clear.
    base = ["--store", str(store), "--captain-token-file", str(token), "control"]
    code, out = _run_cli(
        capsys, base + ["--retention-class", "noise=30", "--retention-class", "ui=45"]
    )
    assert code == 0 and out["retention_classes"] == {"noise": 30, "ui": 45}

    code, out = _run_cli(capsys, base + ["--retention-days", "30"])
    assert code == 0 and out["retention_days"] == 30
    assert out["retention_classes"] == {"noise": 30, "ui": 45}, (
        "an unrelated control change must preserve the stored class map"
    )

    code, out = _run_cli(capsys, base + ["--clear-retention-classes"])
    assert code == 0 and out["retention_classes"] is None
    assert out["retention_days"] == 30

    # Malformed flag values are the typed exit-3 refusal, not a crash.
    for bad in ["noise", "noise=", "=30", "noise=lots"]:
        code, out = _run_cli(capsys, base + ["--retention-class", bad])
        assert code == 3 and out["code"] == "retention_class_invalid"

    # Read-only control still needs no token and reports the stored map.
    code, out = _run_cli(capsys, ["--store", str(store), "control"])
    assert code == 0 and out["retention_classes"] is None
