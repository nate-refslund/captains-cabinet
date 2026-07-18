"""HP-1 signer-seam tests — the dark-default proof and the fail-closed law.

Pins, in order of load-bearingness:
  * KNOWN-ANSWER VECTORS generated at base commit 345461c0 (pre-seam
    recorder code): the frozen v1 signature formats can never drift — not
    in the recorder's module helpers and not in the LocalKeySigner twin.
  * UNCONFIGURED = BYTE-IDENTICAL: with no signing config the recorder
    resolves a LocalKeySigner and every stored signature equals a direct
    ``hmac.new(store_key, frozen_message)`` recomputation that never
    touches the seam.
  * FAIL-CLOSED: ``mode: broker`` with a dead socket is a typed
    ``EvidenceError`` and ZERO store bytes — and the local key-create
    branch is provably unreachable in broker mode (no ``.signing-key`` is
    ever minted; a locally minted second key would split-brain the store).
"""
from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

import pytest

from framework.evidence import EvidenceError, EvidenceRecorder
from framework.evidence.recorder import _event_signature, _object_signature
from framework.evidence.signing import (
    BrokerSigner,
    LocalKeySigner,
    SigningError,
    config_path_for,
    load_signing_config,
    resolve_signer,
)

# Fixed key + inputs for the known-answer vectors (generated at base commit
# 345461c01803 by running the PRE-SEAM recorder helpers).
VECTOR_KEY = bytes(range(32))
VECTOR_EVENT_HASH = "ab" * 32
VECTOR_ANCHOR_PAYLOAD = {
    "schema": "cabinet.evidence-anchor/v1",
    "trial_id": "DOGFOOD-001",
    "sequence": 7,
    "event_hash": VECTOR_EVENT_HASH,
    "event_signature": "cd" * 32,
    "updated_at": "2026-07-17T00:00:00.000001Z",
}
VECTOR_CONTROL_PAYLOAD = {
    "schema": "cabinet.evidence-control/v1",
    "retention_days": None,
    "diagnostic_mode": False,
    "note": "løft ægget",
}
KNOWN_EVENT_SIG = "9bfada2ea6e81c01e52ec22afec8525afb20006074e86f1bfdf4a2608bd5dfe4"
KNOWN_ANCHOR_SIG = "ee99ac0e2da0418d63ba8c0aec4cd6e8df6d0cfa27a0ed8bd518cff4d9f0ebc4"
KNOWN_CONTROL_SIG = "0da840533fa176d108939011a16bd7ea410a8ade18027f955a878e8904609f2b"
KNOWN_PURGE_SIG = "3e44962d56b60210b1d8f019b3b232c7c4e8bac6bd1c090795dd30cbb168f83e"
KNOWN_WATERMARK_SIG = "984551836b7db0a871b317d1c6269b943f4d50f684c2b24b2dc55d6235d78e19"


def _layout(tmp_path: Path) -> tuple[Path, Path]:
    """A store laid out like production: <root>/evidence/v1 + <root>/config."""
    store = tmp_path / "evidence" / "v1"
    store.mkdir(parents=True)
    return store, tmp_path / "config" / "evidence-signing.yml"


def _tree_digest(store: Path) -> dict[str, str]:
    return {
        str(path.relative_to(store)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(store.rglob("*"))
        if path.is_file()
    }


# ---------------------------------------------------------------------------
# Known-answer vectors: the frozen formats can never drift
# ---------------------------------------------------------------------------

class TestKnownVectors:
    def test_recorder_helpers_match_base_vectors(self):
        assert _event_signature(VECTOR_KEY, "DOGFOOD-001", 7, VECTOR_EVENT_HASH) == KNOWN_EVENT_SIG
        assert _object_signature(VECTOR_KEY, "anchor", VECTOR_ANCHOR_PAYLOAD) == KNOWN_ANCHOR_SIG
        assert _object_signature(VECTOR_KEY, "control", VECTOR_CONTROL_PAYLOAD) == KNOWN_CONTROL_SIG
        assert _object_signature(VECTOR_KEY, "purge", {"trial_id": "DOGFOOD-001"}) == KNOWN_PURGE_SIG
        assert _object_signature(VECTOR_KEY, "watermark", {"trials": {}}) == KNOWN_WATERMARK_SIG

    def test_local_signer_matches_base_vectors(self):
        signer = LocalKeySigner(VECTOR_KEY)
        assert signer.event_signature("DOGFOOD-001", 7, VECTOR_EVENT_HASH) == KNOWN_EVENT_SIG
        assert signer.object_signature("anchor", VECTOR_ANCHOR_PAYLOAD) == KNOWN_ANCHOR_SIG
        assert signer.object_signature("control", VECTOR_CONTROL_PAYLOAD) == KNOWN_CONTROL_SIG
        assert signer.verify_event("DOGFOOD-001", 7, VECTOR_EVENT_HASH, KNOWN_EVENT_SIG)
        assert not signer.verify_event("DOGFOOD-001", 7, VECTOR_EVENT_HASH, "0" * 64)
        assert signer.verify_object("anchor", VECTOR_ANCHOR_PAYLOAD, KNOWN_ANCHOR_SIG)
        assert not signer.verify_object("anchor", VECTOR_ANCHOR_PAYLOAD, "0" * 64)


# ---------------------------------------------------------------------------
# Dark default: unconfigured == local == byte-identical
# ---------------------------------------------------------------------------

class TestUnconfiguredIsLocal:
    def test_absent_config_resolves_local_over_store_key(self, tmp_path: Path):
        store, _config = _layout(tmp_path)
        recorder = EvidenceRecorder(store)
        assert isinstance(recorder._signer, LocalKeySigner)
        assert recorder._signer.mode == "local"
        # The captain-capability token seam keeps its raw-key handle in
        # local mode (broker mode deliberately has none).
        assert recorder._key == (store / ".signing-key").read_bytes()

    def test_recorded_bytes_equal_direct_hmac_recomputation(self, tmp_path: Path):
        import json

        store, _config = _layout(tmp_path)
        recorder = EvidenceRecorder(store)
        context = recorder.trace(
            "SEAM-001", surface="test", trace_id="trace-seam-001",
            action_id="action-seam-001", correlation_id="corr-seam-001",
        )
        event = recorder.append(
            context, phase="intent", status="started",
            actor={"kind": "system", "id": "seam-test"},
            component={"name": "seam-test", "version": "1.0.0", "commit": "abc123"},
            detail={"action": "seam_proof"},
        )
        key = (store / ".signing-key").read_bytes()

        message = f"event\nSEAM-001\n1\n{event['event_hash']}".encode("utf-8")
        assert event["signature"] == hmac.new(key, message, hashlib.sha256).hexdigest()

        trial_dirs = [p for p in (store / "trials").iterdir() if p.is_dir()]
        assert len(trial_dirs) == 1
        stored = json.loads((trial_dirs[0] / "events.jsonl").read_text().splitlines()[0])
        assert stored["signature"] == event["signature"]

        anchor = json.loads((trial_dirs[0] / "anchor.json").read_text())
        anchor_payload = {k: v for k, v in anchor.items() if k != "anchor_signature"}
        canonical = json.dumps(
            anchor_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        expected = hmac.new(key, b"anchor\n" + canonical, hashlib.sha256).hexdigest()
        assert anchor["anchor_signature"] == expected

        control = json.loads((store / "control.json").read_text())
        control_payload = {k: v for k, v in control.items() if k != "control_signature"}
        canonical = json.dumps(
            control_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        expected = hmac.new(key, b"control\n" + canonical, hashlib.sha256).hexdigest()
        assert control["control_signature"] == expected

    def test_present_config_without_broker_mode_stays_local(self, tmp_path: Path):
        store, config = _layout(tmp_path)
        config.parent.mkdir(parents=True)
        config.write_text("# staged\nmode: local\n")
        recorder = EvidenceRecorder(store)
        assert isinstance(recorder._signer, LocalKeySigner)

    def test_config_geometry_is_store_adjacent(self, tmp_path: Path):
        store, config = _layout(tmp_path)
        assert config_path_for(store) == config
        assert load_signing_config(store) is None


# ---------------------------------------------------------------------------
# Broker mode: fail-closed, zero bytes, no local key minting
# ---------------------------------------------------------------------------

class TestBrokerModeFailClosed:
    def test_dead_socket_fresh_store_zero_bytes_no_local_key(self, tmp_path: Path):
        store, config = _layout(tmp_path)
        config.parent.mkdir(parents=True)
        config.write_text(f"mode: broker\nsocket: {tmp_path / 'no-such.sock'}\n")
        with pytest.raises(EvidenceError) as excinfo:
            EvidenceRecorder(store)
        assert excinfo.value.code == "signing_broker_unavailable"
        # Fail-closed left ZERO store bytes: no control, no events — and no
        # locally minted key (the split-brain guard: the create branch is
        # unreachable in broker mode).
        assert _tree_digest(store) == {}
        assert not (store / ".signing-key").exists()

    def test_dead_socket_existing_store_unchanged(self, tmp_path: Path):
        store, config = _layout(tmp_path)
        recorder = EvidenceRecorder(store)  # local birth
        context = recorder.trace(
            "SEAM-002", surface="test", trace_id="trace-seam-002",
            action_id="action-seam-002", correlation_id="corr-seam-002",
        )
        recorder.append(
            context, phase="intent", status="started",
            actor={"kind": "system", "id": "seam-test"},
            component={"name": "seam-test", "version": "1.0.0", "commit": "abc123"},
        )
        before = _tree_digest(store)
        config.parent.mkdir(parents=True)
        config.write_text(f"mode: broker\nsocket: {tmp_path / 'no-such.sock'}\n")
        with pytest.raises(EvidenceError) as excinfo:
            EvidenceRecorder(store)
        assert excinfo.value.code == "signing_broker_unavailable"
        assert _tree_digest(store) == before

    def test_broker_mode_without_socket_is_typed_refusal(self, tmp_path: Path):
        store, config = _layout(tmp_path)
        config.parent.mkdir(parents=True)
        config.write_text("mode: broker\n")
        with pytest.raises(EvidenceError) as excinfo:
            EvidenceRecorder(store)
        assert excinfo.value.code == "signing_config_invalid"
        assert not (store / ".signing-key").exists()

    def test_broker_signer_holds_no_key_and_key_loader_never_runs(self, tmp_path: Path):
        store, config = _layout(tmp_path)
        config.parent.mkdir(parents=True)
        config.write_text(f"mode: broker\nsocket: {tmp_path / 's.sock'}\nidentity: officer-core\n")

        def _forbidden_loader() -> bytes:
            raise AssertionError("key loader must be unreachable in broker mode")

        signer = resolve_signer(store, key_loader=_forbidden_loader, error_cls=SigningError)
        assert isinstance(signer, BrokerSigner)
        assert not hasattr(signer, "key")

    def test_symlinked_config_refused(self, tmp_path: Path):
        store, config = _layout(tmp_path)
        config.parent.mkdir(parents=True)
        real = tmp_path / "elsewhere.yml"
        real.write_text("mode: broker\nsocket: /tmp/x.sock\n")
        config.symlink_to(real)
        with pytest.raises(SigningError) as excinfo:
            load_signing_config(store)
        assert excinfo.value.code == "signing_config_invalid"


# ---------------------------------------------------------------------------
# Leaf-module laws
# ---------------------------------------------------------------------------

class TestLeafLaws:
    def test_no_environment_borne_behavior_and_no_layer_leak(self):
        import framework.evidence.signing as signing_module

        source = Path(signing_module.__file__).read_text(encoding="utf-8")
        # No environment variable may bear behavior (MAX_TRIAL_EVENTS law).
        assert "os.environ" not in source and "getenv" not in source
        # Layer separation: no instance-path literal in framework code.
        # The token is assembled at runtime so this test file itself never
        # carries the quoted literal that check-layer-separation.sh greps
        # for repo-wide (rule class FRAMEWORK_PATH_INSTANCE).
        tok = "in" + "stance"
        assert (chr(34) + tok + chr(34)) not in source  # double-quoted form
        assert (chr(39) + tok + chr(39)) not in source  # single-quoted form

    def test_leaf_module_imports_nothing_from_the_evidence_package(self):
        import framework.evidence.signing as signing_module

        source = Path(signing_module.__file__).read_text(encoding="utf-8")
        for forbidden in ("recorder", "verifier", "identity", "classification"):
            assert f"from .{forbidden}" not in source
            assert f"from framework.evidence.{forbidden}" not in source
