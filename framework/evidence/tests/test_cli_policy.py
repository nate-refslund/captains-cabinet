"""Regression tests for the CLI Captain-capability gate and fail-closed policy.

Pinned defects (PR #140 review):
- #4: mutating CLI commands handed ``actor="captain"`` to any invoker; a
  Captain mutation must instead present a capability derived from the
  store's private signing key. Round 2: a non-ASCII (valid UTF-8) token
  file crashed the gate with an uncaught TypeError from
  ``hmac.compare_digest`` instead of the typed exit-3 refusal.
- #22: an unrelated retention change was refused because the CLI replayed a
  stored, already-lapsed ``diagnostic_until`` into configure().
- #23: ``RepairRequest`` danger dimensions defaulted ``False`` (fail-open),
  so omitting a danger fact resolved to ``auto_repair``.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from framework.evidence import EvidenceRecorder, RepairRequest, repair_verdict
from framework.evidence.__main__ import main as evidence_cli
from framework.evidence.recorder import CONTROL_SCHEMA, _utc_now

NO_DANGER = {
    "external_effect": False,
    "irreversible": False,
    "security_sensitive": False,
    "authority_changing": False,
    "audit_changing": False,
    "governance_changing": False,
}


@pytest.fixture(autouse=True)
def _no_ambient_captain_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CABINET_CAPTAIN_TOKEN_FILE", raising=False)


def run_cli(capsys: pytest.CaptureFixture, argv: list[str]) -> tuple[int, dict]:
    code = evidence_cli(argv)
    return code, json.loads(capsys.readouterr().out.strip())


def seed_trial(store: Path, trial: str = "trial-cap-1") -> EvidenceRecorder:
    recorder = EvidenceRecorder(store)
    context = recorder.trace(trial, surface="test")
    recorder.append(
        context,
        phase="intent",
        status="started",
        actor={"kind": "system", "id": "cli-policy-test"},
        component={"name": "cli-policy-test", "version": "1"},
    )
    return recorder


def mint_token(store: Path, target: Path) -> Path:
    """Independent re-derivation of the documented capability contract."""
    key = (store / ".signing-key").read_bytes()
    token = hmac.new(
        key, b"cabinet.evidence-captain-capability/v1", hashlib.sha256
    ).hexdigest()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(token + "\n", encoding="utf-8")
    target.chmod(0o600)
    return target


def write_lapsed_diagnostic_control(recorder: EvidenceRecorder) -> str:
    lapsed = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    recorder._write_control({
        "schema": CONTROL_SCHEMA,
        "retention_days": None,
        "diagnostic_mode": True,
        "diagnostic_until": lapsed,
        "updated_at": _utc_now(),
        "updated_by": "captain",
    })
    return lapsed


# --- Finding #4: capability required for every Captain mutation ---------------


def test_captain_mutations_are_refused_without_capability(tmp_path: Path, capsys):
    store = tmp_path / "store"
    recorder = seed_trial(store)

    code, out = run_cli(capsys, ["--store", str(store), "retain"])
    assert (code, out["code"]) == (3, "captain_capability_required")

    code, out = run_cli(capsys, ["--store", str(store), "control", "--retention-days", "30"])
    assert (code, out["code"]) == (3, "captain_capability_required")
    assert recorder.control()["retention_days"] is None  # mutation never ran

    code, out = run_cli(capsys, ["--store", str(store), "export", "trial-cap-1"])
    assert (code, out["code"]) == (3, "captain_capability_required")
    assert list((store / "exports").iterdir()) == []

    code, out = run_cli(
        capsys,
        ["--store", str(store), "purge", "trial-cap-1", "--confirmation", "PURGE trial-cap-1"],
    )
    assert (code, out["code"]) == (3, "captain_capability_required")
    assert (store / "trials" / "trial-cap-1").is_dir()


def test_grant_token_mints_capability_and_gated_commands_accept_it(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch,
):
    store = tmp_path / "store"
    seed_trial(store)
    token_path = tmp_path / "captain" / "capability.token"

    code, out = run_cli(
        capsys, ["--store", str(store), "grant-token", "--output", str(token_path)]
    )
    assert code == 0 and out["ok"] is True and out["path"] == str(token_path)
    assert stat.S_IMODE(token_path.stat().st_mode) == 0o600
    # The minted token matches the documented derivation exactly.
    expected = mint_token(store, tmp_path / "captain" / "rederived.token")
    assert token_path.read_text().strip() == expected.read_text().strip()

    # Minting never overwrites an existing token file.
    code, out = run_cli(
        capsys, ["--store", str(store), "grant-token", "--output", str(token_path)]
    )
    assert (code, out["code"]) == (3, "grant_output_exists")

    # Explicit flag path.
    code, out = run_cli(
        capsys,
        [
            "--store", str(store), "--captain-token-file", str(token_path),
            "control", "--retention-days", "30",
        ],
    )
    assert code == 0 and out["retention_days"] == 30

    # Environment path covers the remaining Captain mutations.
    monkeypatch.setenv("CABINET_CAPTAIN_TOKEN_FILE", str(token_path))
    code, out = run_cli(capsys, ["--store", str(store), "retain"])
    assert code == 0 and out["ok"] is True

    code, out = run_cli(capsys, ["--store", str(store), "export", "trial-cap-1"])
    assert code == 0 and out["ok"] is True and Path(out["path"]).is_dir()

    code, out = run_cli(
        capsys,
        ["--store", str(store), "purge", "trial-cap-1", "--confirmation", "PURGE trial-cap-1"],
    )
    assert code == 0 and out["status"] == "completed"
    assert not (store / "trials" / "trial-cap-1").exists()


def test_forged_foreign_lax_or_symlinked_tokens_are_refused(tmp_path: Path, capsys):
    store = tmp_path / "store"
    recorder = seed_trial(store)
    other_store = tmp_path / "other-store"
    EvidenceRecorder(other_store)

    def mutate_with(token_file: Path) -> tuple[int, dict]:
        return run_cli(
            capsys,
            [
                "--store", str(store), "--captain-token-file", str(token_file),
                "control", "--retention-days", "30",
            ],
        )

    forged = tmp_path / "forged.token"
    forged.write_text("a" * 64 + "\n", encoding="utf-8")
    forged.chmod(0o600)
    code, out = mutate_with(forged)
    assert (code, out["code"]) == (3, "captain_capability_invalid")

    # Valid UTF-8 but non-ASCII content is definitionally not a token and
    # must get the same typed refusal — never an uncaught TypeError from
    # hmac.compare_digest (fail-closed contract: exit 3, no traceback).
    non_ascii = tmp_path / "non-ascii.token"
    non_ascii.write_text("naïve-not-a-token\n", encoding="utf-8")
    non_ascii.chmod(0o600)
    code, out = mutate_with(non_ascii)
    assert (code, out["code"]) == (3, "captain_capability_invalid")

    foreign = mint_token(other_store, tmp_path / "foreign.token")
    code, out = mutate_with(foreign)
    assert (code, out["code"]) == (3, "captain_capability_invalid")

    lax = mint_token(store, tmp_path / "lax.token")
    lax.chmod(0o644)
    code, out = mutate_with(lax)
    assert (code, out["code"]) == (3, "captain_capability_invalid")

    real = mint_token(store, tmp_path / "real.token")
    link = tmp_path / "link.token"
    os.symlink(real, link)
    code, out = mutate_with(link)
    assert (code, out["code"]) == (3, "captain_capability_invalid")

    code, out = mutate_with(tmp_path / "missing.token")
    assert (code, out["code"]) == (3, "captain_capability_required")

    assert recorder.control()["retention_days"] is None  # nothing mutated


def test_read_only_commands_require_no_capability(tmp_path: Path, capsys):
    store = tmp_path / "store"
    seed_trial(store)

    code, out = run_cli(capsys, ["--store", str(store), "verify"])
    assert code == 0 and out["ok"] is True

    code, out = run_cli(capsys, ["--store", str(store), "project", "trial-cap-1"])
    assert code == 0 and out["mode"] == "read_only_redacted"

    code, out = run_cli(capsys, ["--store", str(store), "control"])
    assert code == 0 and out["schema"] == CONTROL_SCHEMA


# --- Finding #22: never replay a lapsed diagnostic expiry ---------------------


def test_retention_change_succeeds_when_stored_diagnostic_window_lapsed(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch,
):
    store = tmp_path / "store"
    recorder = EvidenceRecorder(store)
    write_lapsed_diagnostic_control(recorder)
    monkeypatch.setenv(
        "CABINET_CAPTAIN_TOKEN_FILE", str(mint_token(store, tmp_path / "captain.token"))
    )

    code, out = run_cli(capsys, ["--store", str(store), "control", "--retention-days", "30"])
    assert code == 0, f"retention change blocked by lapsed diagnostic window: {out}"
    assert out["retention_days"] == 30
    # The lapsed window was already off in effect; preserving it stores that
    # effective state instead of replaying the stale expiry.
    assert out["diagnostic_mode"] is False
    assert out["diagnostic_until"] is None


def test_live_diagnostic_window_is_preserved_across_retention_change(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch,
):
    store = tmp_path / "store"
    recorder = EvidenceRecorder(store)
    live_until = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    recorder.configure(
        actor="captain", retention_days=None,
        diagnostic_mode=True, diagnostic_until=live_until,
    )
    monkeypatch.setenv(
        "CABINET_CAPTAIN_TOKEN_FILE", str(mint_token(store, tmp_path / "captain.token"))
    )

    code, out = run_cli(capsys, ["--store", str(store), "control", "--retention-days", "45"])
    assert code == 0 and out["retention_days"] == 45
    assert out["diagnostic_mode"] is True
    assert out["diagnostic_until"] == live_until


def test_diagnostic_on_with_lapsed_stored_window_mints_a_fresh_window(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch,
):
    store = tmp_path / "store"
    recorder = EvidenceRecorder(store)
    lapsed = write_lapsed_diagnostic_control(recorder)
    monkeypatch.setenv(
        "CABINET_CAPTAIN_TOKEN_FILE", str(mint_token(store, tmp_path / "captain.token"))
    )

    code, out = run_cli(capsys, ["--store", str(store), "control", "--diagnostic", "on"])
    assert code == 0 and out["diagnostic_mode"] is True
    refreshed = datetime.fromisoformat(out["diagnostic_until"].replace("Z", "+00:00"))
    assert refreshed > datetime.now(timezone.utc)
    assert out["diagnostic_until"] != lapsed


# --- Finding #23: an unstated danger fact never resolves to auto_repair -------


def test_repair_request_omitting_danger_facts_never_auto_repairs():
    verdict = repair_verdict(RepairRequest(True, True, True, True, True, True))
    assert verdict["verdict"] == "captain_gated", (
        "omitting every danger dimension must gate to the Captain"
    )
    assert verdict["reason"] == "hard_ceiling"
    assert verdict["gates"] == sorted(NO_DANGER)

    for omitted in NO_DANGER:
        attested = {name: value for name, value in NO_DANGER.items() if name != omitted}
        verdict = repair_verdict(RepairRequest(True, True, True, True, True, True, **attested))
        assert verdict == {
            "verdict": "captain_gated", "reason": "hard_ceiling", "gates": [omitted]
        }

    # Positive control: a fully attested request still auto-repairs.
    full = repair_verdict(RepairRequest(True, True, True, True, True, True, **NO_DANGER))
    assert full["verdict"] == "auto_repair"
