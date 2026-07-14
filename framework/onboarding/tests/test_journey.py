"""Production contracts for the canonical Onboarding v2 First Window.

Hermetic: every mutable state root is tmp_path; fixture estates are read-only
repo data; no network, subprocess, Redis, Telegram, or LLM is involved.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from framework.onboarding import journey

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "framework" / "onboarding" / "fixtures"


def estate(tmp_path: Path, name: str) -> Path:
    target = tmp_path / "sources" / name
    shutil.copytree(FIXTURES / name, target)
    return target


def propose(root: Path, source: Path, *, surface: str = "dashboard", action_id: str = "propose-1") -> dict:
    return journey.act(
        {
            "action": "propose_window",
            "action_id": action_id,
            "surface": surface,
            "source": str(source),
            "purpose": "Find one release risk before it surprises the team.",
            "relationship_destination": "reversible",
        },
        root,
        now="2026-07-14T10:00:00Z",
    )


def ratify(root: Path, proposed: dict, *, surface: str = "telegram", action_id: str = "ratify-1") -> dict:
    return journey.act(
        {
            "action": "ratify_charter",
            "action_id": action_id,
            "surface": surface,
            "charter_hash": proposed["state"]["charter"]["hash"],
            "expected_revision": proposed["state"]["revision"],
        },
        root,
        now="2026-07-14T10:00:03Z",
    )


def test_welcome_card_is_stable_and_plain_language(tmp_path):
    first = journey.snapshot(tmp_path)
    second = journey.snapshot(tmp_path)
    assert first["card"] == second["card"]
    assert first["card"]["id"].startswith("onboarding:journey-")
    assert first["card"]["title"] == "Let me earn my first responsibility"
    body = first["card"]["body"].lower()
    assert "folder" in body and "nothing is opened" in body
    assert "mcp" not in body and "api" not in body


def test_proposal_reads_no_source_content_before_charter_approval(tmp_path, monkeypatch):
    source = estate(tmp_path, "software-product")
    original = Path.read_bytes

    def refuse_source_reads(path: Path):
        if source in path.parents:
            raise AssertionError(f"source content read before consent: {path}")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", refuse_source_reads)
    out = propose(tmp_path, source)
    assert out["state"]["stage"] == "charter_pending"
    assert out["state"]["access"] == "not_granted"
    assert not (tmp_path / journey.DATA_REL / journey.MANIFEST_NAME).exists()
    assert not (tmp_path / journey.DATA_REL / journey.DIVIDEND_NAME).exists()


def test_charter_binds_exact_scope_limits_purpose_and_destination_without_granting_authority(tmp_path):
    source = estate(tmp_path, "software-product")
    out = propose(tmp_path, source)
    charter = out["state"]["charter"]
    payload = charter["payload"]
    assert payload["source"]["root"] == str(source.resolve())
    assert payload["permission"] == {
        "read_only": True,
        "writes_to_source": False,
        "network": False,
        "connectors": False,
        "follow_symlinks": False,
    }
    assert payload["limits"]["max_files"] == journey.MAX_FILES
    assert payload["relationship_destination"]["id"] == "reversible"
    assert payload["relationship_destination"]["authority_effect"] == "none; this is a destination, not a grant"
    assert charter["hash"] == hashlib.sha256(journey._canonical(payload)).hexdigest()
    disk = json.loads((tmp_path / journey.DATA_REL / journey.CHARTER_NAME).read_text())
    assert disk == charter


@pytest.mark.parametrize("bad_hash", ["", "0" * 64, "stale"])
def test_stale_or_missing_charter_hash_refuses_without_reading(tmp_path, monkeypatch, bad_hash):
    source = estate(tmp_path, "software-product")
    proposed = propose(tmp_path, source)

    def no_scan(*_args, **_kwargs):
        raise AssertionError("scan must remain locked behind the hash gate")

    monkeypatch.setattr(journey, "_scan_source", no_scan)
    with pytest.raises(journey.JourneyError, match="stale|changed") as exc:
        journey.act(
            {"action": "ratify_charter", "action_id": f"bad-{bad_hash}", "surface": "world", "charter_hash": bad_hash},
            tmp_path,
        )
    assert exc.value.code == "charter_hash_mismatch"
    assert journey.snapshot(tmp_path)["state"]["stage"] == "charter_pending"


def test_primary_software_product_persona_returns_missing_release_command_with_citation(tmp_path):
    source = estate(tmp_path, "software-product")
    out = ratify(tmp_path, propose(tmp_path, source))
    finding = out["state"]["first_dividend"]["finding"]
    assert finding["kind"] == "software_command_drift"
    assert finding["quality"] == "strong"
    assert "deploy:prod" in finding["summary"]
    assert finding["citations"][0]["path"] == "README.md"
    assert finding["citations"][0]["line"] == 7
    assert len(finding["citations"][0]["sha256"]) == 64


def test_client_services_persona_returns_delivery_conflict_with_both_sources(tmp_path):
    source = estate(tmp_path, "client-services")
    out = ratify(tmp_path, propose(tmp_path, source))
    finding = out["state"]["first_dividend"]["finding"]
    assert finding["kind"] == "conflicting_commitment"
    assert {c["path"] for c in finding["citations"]} == {"project-plan.md", "proposal.md"}
    assert {c["excerpt"] for c in finding["citations"]} == {
        "Delivery date: 2026-08-21",
        "Delivery date: 2026-08-28",
    }


def test_nontechnical_community_persona_returns_uncovered_welcome_desk_shift(tmp_path):
    source = estate(tmp_path, "community-nonprofit")
    out = ratify(tmp_path, propose(tmp_path, source))
    finding = out["state"]["first_dividend"]["finding"]
    assert finding["kind"] == "attention_marker"
    assert finding["citations"] == [{
        "path": "volunteer-rota.md",
        "line": 3,
        "excerpt": "URGENT: Saturday's welcome desk has no volunteer after 13:00.",
        "sha256": finding["citations"][0]["sha256"],
    }]


def test_manifest_is_content_hashed_and_raw_source_is_not_persisted(tmp_path):
    source = estate(tmp_path, "software-product")
    out = ratify(tmp_path, propose(tmp_path, source))
    manifest = json.loads((tmp_path / journey.DATA_REL / journey.MANIFEST_NAME).read_text())
    assert manifest["charter_hash"] == out["state"]["charter"]["hash"]
    assert manifest["file_count"] == 3
    assert all(set(row) == {"path", "bytes", "sha256"} for row in manifest["files"])
    without_hash = {k: v for k, v in manifest.items() if k != "manifest_hash"}
    assert manifest["manifest_hash"] == journey._hash(without_hash)
    serialized = json.dumps(manifest)
    assert "deploy:prod" not in serialized
    assert out["state"]["first_dividend"]["raw_source_persisted"] is False


def test_sensitive_hidden_binary_and_symlink_entries_are_excluded(tmp_path):
    source = tmp_path / "sources" / "guarded"
    source.mkdir(parents=True)
    (source / "README.md").write_text("URGENT: review the public rota.\n")
    (source / ".env").write_text("API_KEY=must-never-appear\n")
    (source / "client-secrets.md").write_text("password=must-never-appear\n")
    (source / "binary.txt").write_bytes(b"hello\x00world")
    outside = tmp_path / "outside.md"
    outside.write_text("URGENT: symlink bait\n")
    (source / "linked.md").symlink_to(outside)
    out = ratify(tmp_path, propose(tmp_path, source))
    manifest = json.loads((tmp_path / journey.DATA_REL / journey.MANIFEST_NAME).read_text())
    assert [row["path"] for row in manifest["files"]] == ["README.md"]
    all_persisted = "\n".join(
        p.read_text(errors="replace")
        for p in (tmp_path / journey.DATA_REL).parent.rglob("*")
        if p.is_file()
    )
    assert "must-never-appear" not in all_persisted
    assert "symlink bait" not in all_persisted


def test_secret_shaped_cited_line_is_redacted(tmp_path):
    source = tmp_path / "sources" / "redaction"
    source.mkdir(parents=True)
    (source / "notes.md").write_text("URGENT: password=hunter2 rotate this today\n")
    out = ratify(tmp_path, propose(tmp_path, source))
    citation = out["state"]["first_dividend"]["finding"]["citations"][0]
    assert citation["excerpt"] == "[sensitive value redacted]"
    assert "hunter2" not in json.dumps(out)


def test_secret_keyword_without_assignment_is_still_redacted(tmp_path):
    source = tmp_path / "sources" / "redaction-words"
    source.mkdir(parents=True)
    (source / "notes.md").write_text("URGENT: rotate token sk-abcdefghijklmnopqrstuvwxyz today\n")
    out = ratify(tmp_path, propose(tmp_path, source))
    assert out["state"]["first_dividend"]["finding"]["citations"][0]["excerpt"] == "[sensitive value redacted]"
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in json.dumps(out)


def test_empty_or_unremarkable_window_is_honest_not_manufactured(tmp_path):
    source = tmp_path / "sources" / "calm"
    source.mkdir(parents=True)
    (source / "about.md").write_text("# About\n\nWe host a reading circle every Tuesday.\n")
    out = ratify(tmp_path, propose(tmp_path, source))
    finding = out["state"]["first_dividend"]["finding"]
    assert finding["quality"] == "orientation_only"
    assert "did not find a strong" in finding["summary"]


def test_one_action_id_is_idempotent_across_surfaces(tmp_path):
    source = estate(tmp_path, "software-product")
    first = propose(tmp_path, source, surface="dashboard", action_id="same-action")
    second = journey.act(
        {
            "action": "propose_window",
            "action_id": "same-action",
            "surface": "telegram",
            "source": str(source),
            "purpose": "A different replay must not replace state.",
            "relationship_destination": "sovereign",
        },
        tmp_path,
    )
    assert second["duplicate"] is True
    assert second["state"] == first["state"]
    assert len(journey._read_events(tmp_path)) == 1


def test_cross_surface_snapshot_is_the_same_card_and_resolution_continues_everywhere(tmp_path):
    source = estate(tmp_path, "software-product")
    dashboard = propose(tmp_path, source, surface="dashboard")
    telegram = journey.snapshot(tmp_path)
    world = journey.snapshot(tmp_path)
    assert dashboard["card"] == telegram["card"] == world["card"]
    resolved = ratify(tmp_path, telegram, surface="world")
    after = journey.snapshot(tmp_path)
    assert after["card"] == resolved["card"]
    assert after["card"]["stage"] == "dividend_ready"
    assert after["card"]["id"] != dashboard["card"]["id"]


def test_stale_cross_surface_revision_fails_closed(tmp_path):
    source = estate(tmp_path, "software-product")
    proposed = propose(tmp_path, source)
    ratify(tmp_path, proposed)
    with pytest.raises(journey.JourneyError) as exc:
        journey.act(
            {
                "action": "revoke",
                "action_id": "stale-world",
                "surface": "world",
                "expected_revision": proposed["state"]["revision"],
            },
            tmp_path,
        )
    assert exc.value.code == "revision_conflict"


def test_malformed_revision_and_action_id_fail_as_user_refusals(tmp_path):
    for malformed in ({}, True, 1.5, "1.5"):
        with pytest.raises(journey.JourneyError) as revision:
            journey.act(
                {"action": "undo", "action_id": "valid", "surface": "test", "expected_revision": malformed},
                tmp_path,
            )
        assert revision.value.code == "revision_invalid"
    with pytest.raises(journey.JourneyError) as action_id:
        journey.act({"action": "undo", "action_id": "../../escape", "surface": "test"}, tmp_path)
    assert action_id.value.code == "action_id_invalid"


def test_revoke_then_undo_restores_previous_read_only_state(tmp_path):
    source = estate(tmp_path, "software-product")
    dividend = ratify(tmp_path, propose(tmp_path, source))
    revoked = journey.act({"action": "revoke", "action_id": "revoke-1", "surface": "telegram"}, tmp_path)
    assert revoked["state"]["stage"] == "revoked"
    assert revoked["state"]["access"] == "revoked"
    restored = journey.act({"action": "undo", "action_id": "undo-1", "surface": "dashboard"}, tmp_path)
    assert restored["state"]["stage"] == "dividend_ready"
    assert restored["state"]["access"] == "active_read_only"
    assert restored["state"]["first_dividend"] == dividend["state"]["first_dividend"]


def test_replacing_window_then_undo_restores_dividend_and_matching_manifest(tmp_path):
    first_source = estate(tmp_path, "software-product")
    first = ratify(tmp_path, propose(tmp_path, first_source))
    first_manifest = json.loads(
        (tmp_path / journey.DATA_REL / journey.MANIFEST_NAME).read_text()
    )
    next_source = estate(tmp_path, "client-services")
    propose(tmp_path, next_source, action_id="replace-window")
    assert not (tmp_path / journey.DATA_REL / journey.MANIFEST_NAME).exists()

    restored = journey.act(
        {"action": "undo", "action_id": "undo-replace", "surface": "dashboard"},
        tmp_path,
    )

    assert restored["state"]["first_dividend"] == first["state"]["first_dividend"]
    assert json.loads(
        (tmp_path / journey.DATA_REL / journey.MANIFEST_NAME).read_text()
    ) == first_manifest


def test_purge_requires_typed_confirmation_and_removes_sensitive_history(tmp_path):
    source = estate(tmp_path, "software-product")
    ratify(tmp_path, propose(tmp_path, source))
    with pytest.raises(journey.JourneyError) as exc:
        journey.act({"action": "purge", "action_id": "purge-no", "surface": "dashboard"}, tmp_path)
    assert exc.value.code == "purge_confirmation"
    purged = journey.act(
        {"action": "purge", "action_id": "purge-yes", "surface": "dashboard", "confirmation": "PURGE"},
        tmp_path,
        now="2026-07-14T11:00:00Z",
    )
    assert purged["purged"] is True
    assert purged["state"]["stage"] == "purged"
    assert purged["state"]["source"] is None
    persisted = "\n".join(
        p.read_text(errors="replace")
        for p in (tmp_path / journey.DATA_REL).parent.rglob("*")
        if p.is_file()
    )
    assert str(source.resolve()) not in persisted
    assert "deploy:prod" not in persisted
    receipt_files = list((tmp_path / journey.PURGE_RECEIPTS_REL).glob("*.json"))
    assert len(receipt_files) == 1
    receipt = json.loads(receipt_files[0].read_text())
    assert set(receipt) == {
        "schema", "purged_at", "purged_journey_id_hash", "surface",
        "action_id", "status", "note",
    }
    assert receipt["status"] == "completed"
    assert str(source.resolve()) not in json.dumps(receipt)


def test_interrupted_purge_is_completed_on_next_locked_read(tmp_path, monkeypatch):
    source = estate(tmp_path, "software-product")
    ratify(tmp_path, propose(tmp_path, source))
    finish = journey._finish_purge

    def interrupt(*_args, **_kwargs):
        raise RuntimeError("simulated power loss after durable intent")

    monkeypatch.setattr(journey, "_finish_purge", interrupt)
    with pytest.raises(RuntimeError, match="simulated power loss"):
        journey.act(
            {
                "action": "purge",
                "action_id": "purge-crash",
                "surface": "dashboard",
                "confirmation": "PURGE",
            },
            tmp_path,
            now="2026-07-14T11:05:00Z",
        )
    monkeypatch.setattr(journey, "_finish_purge", finish)

    recovered = journey.snapshot(tmp_path)
    assert recovered["state"]["stage"] == "purged"
    receipts = list((tmp_path / journey.PURGE_RECEIPTS_REL).glob("*.json"))
    assert json.loads(receipts[0].read_text())["status"] == "completed"
    assert not any(str(source.resolve()) in p.read_text(errors="replace") for p in receipts)


@pytest.mark.parametrize("raw", ["/", "~", "", "does-not-exist"])
def test_scope_refuses_disk_home_empty_and_missing_paths(tmp_path, raw):
    with pytest.raises(journey.JourneyError):
        journey.act(
            {
                "action": "propose_window",
                "action_id": f"bad-{raw}",
                "surface": "test",
                "source": raw,
                "purpose": "test",
                "relationship_destination": "earn",
            },
            tmp_path,
        )


def test_state_and_artifacts_are_owner_only(tmp_path):
    source = estate(tmp_path, "software-product")
    ratify(tmp_path, propose(tmp_path, source))
    for name in (journey.STATE_NAME, journey.EVENTS_NAME, journey.CHARTER_NAME, journey.MANIFEST_NAME, journey.DIVIDEND_NAME):
        mode = (tmp_path / journey.DATA_REL / name).stat().st_mode & 0o777
        assert mode == 0o600, f"{name} permissions were {oct(mode)}"


def test_append_first_event_recovers_projection_and_artifacts_after_crash(tmp_path):
    source = estate(tmp_path, "software-product")
    proposed = propose(tmp_path, source)
    ratified = ratify(tmp_path, proposed)
    events = journey._read_events(tmp_path)
    assert events[-1]["manifest"]["manifest_hash"] == ratified["state"]["source"]["manifest_hash"]

    # Simulate power loss after the ratify event fsync but before state/artifact
    # replacement: projection is still the preceding proposal and derived files
    # are absent. Snapshot must replay, not re-read the source.
    journey._atomic_json(tmp_path / journey.DATA_REL / journey.STATE_NAME, proposed["state"])
    (tmp_path / journey.DATA_REL / journey.MANIFEST_NAME).unlink()
    (tmp_path / journey.DATA_REL / journey.DIVIDEND_NAME).unlink()
    recovered = journey.snapshot(tmp_path)
    assert recovered["state"] == ratified["state"]
    assert (tmp_path / journey.DATA_REL / journey.MANIFEST_NAME).is_file()
    assert (tmp_path / journey.DATA_REL / journey.DIVIDEND_NAME).is_file()


def test_partial_event_tail_is_trimmed_before_the_next_committed_action(tmp_path):
    source = estate(tmp_path, "software-product")
    dividend = ratify(tmp_path, propose(tmp_path, source))
    event_path = tmp_path / journey.DATA_REL / journey.EVENTS_NAME
    with open(event_path, "ab") as fh:
        fh.write(b'{"schema":"partial-crash"')
        fh.flush()
        os.fsync(fh.fileno())

    paused = journey.act(
        {
            "action": "pause",
            "action_id": "after-partial-tail",
            "surface": "dashboard",
            "expected_revision": dividend["state"]["revision"],
        },
        tmp_path,
    )

    assert paused["state"]["stage"] == "paused"
    raw_lines = event_path.read_text().splitlines()
    assert len(raw_lines) == 3
    assert all(isinstance(json.loads(raw), dict) for raw in raw_lines)


def test_mission_compiler_cannot_read_the_journey_surface(tmp_path):
    from framework.missions import session_bridge

    source = estate(tmp_path, "software-product")
    ratify(tmp_path, propose(tmp_path, source))
    instance_root = tmp_path / Path(journey.DATA_REL).parts[0]
    assert session_bridge._outcomes_path(str(tmp_path)) == instance_root / "config" / "outcomes.yml"
    assert session_bridge.get_next_task("cos", cabinet_root=str(tmp_path)) is None


def test_module_has_no_network_subprocess_or_source_write_primitive():
    source = (REPO / "framework" / "onboarding" / "journey.py").read_text()
    assert not re.search(r"\b(import|from)\s+(socket|urllib|requests|httpx|subprocess)\b", source)
    assert "write_text(" not in source
    assert "write_bytes(" not in source


def test_cli_snapshot_and_action_are_json_only(tmp_path):
    env = {**os.environ, "CABINET_ROOT": str(tmp_path)}
    snap = subprocess.run(
        [sys.executable, "-m", "framework.onboarding.journey", "snapshot"],
        cwd=REPO,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert snap.returncode == 0
    assert json.loads(snap.stdout)["card"]["stage"] == "welcome"
    bad = subprocess.run(
        [sys.executable, "-m", "framework.onboarding.journey", "act"],
        cwd=REPO,
        env=env,
        input='{"action":"unknown","surface":"cli"}',
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert bad.returncode == 3
    assert json.loads(bad.stdout)["code"] == "action_unknown"


def test_three_persona_evaluation_harness_is_executable():
    proc = subprocess.run(
        [sys.executable, "-m", "framework.onboarding.evaluate_personas"],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["passed"] is True
    assert [row["persona"] for row in payload["results"]] == [
        "software-product", "client-services", "community-nonprofit"
    ]
    assert all(row["elapsed_seconds"] < 5 for row in payload["results"])
