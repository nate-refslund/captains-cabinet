"""HP-1 signing-broker tests — protocol, refusal matrix, custody, dark law.

Same-user SIMULATION by design: these tests prove the protocol, the
peer-credential plumbing, and the refusal matrix without a second OS user
(the real user split is the documented Captain deploy ceremony —
docs/runbooks/evidence-signing-broker.md). The unmapped-peer branch is
exercised by configuring an allowlist that excludes the test's own uid; a
foreign uid cannot be faked unprivileged, which is the point of kernel peer
credentials.

File enumeration in the dark-law tests uses os.walk, never git — the
exported null-hatch tree has no .git.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import select
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from framework.evidence_signing_broker import (  # noqa: E402
    BrokerCore,
    Refusal,
    _parse_xucred,
    load_broker_config,
    peer_cred_supported,
    peer_uid,
)
from framework.evidence.signing import BrokerSigner, SigningError  # noqa: E402

KEY = bytes(range(32))
LABEL = "com.cabinet.evidence-signing-broker"
GOOD_HASH = "ab" * 32
MY_UID = os.getuid()


def _event_mac(trial_id: str, sequence: int, event_hash: str) -> str:
    message = f"event\n{trial_id}\n{sequence}\n{event_hash}".encode("utf-8")
    return hmac.new(KEY, message, hashlib.sha256).hexdigest()


def _anchor_payload(sequence: int = 1) -> dict:
    return {
        "schema": "cabinet.evidence-anchor/v1",
        "trial_id": "BROKER-001",
        "sequence": sequence,
        "event_hash": GOOD_HASH,
        "event_signature": "cd" * 32,
        "updated_at": "2026-07-17T00:00:00.000001Z",
    }


# ---------------------------------------------------------------------------
# BrokerCore — transport-free refusal matrix
# ---------------------------------------------------------------------------

@pytest.fixture()
def core() -> BrokerCore:
    return BrokerCore(KEY, {MY_UID: "test-officer"})


def _refusal(core: BrokerCore, request: object, uid: int | None = MY_UID) -> str:
    with pytest.raises(Refusal) as excinfo:
        core.handle(uid, request)
    return str(excinfo.value)


class TestCoreSignEvent:
    def test_sign_event_returns_the_exact_hmac(self, core):
        response = core.handle(MY_UID, {
            "verb": "sign-event", "trial_id": "BROKER-001",
            "sequence": 3, "event_hash": GOOD_HASH,
        })
        assert response == {"ok": True, "signature": _event_mac("BROKER-001", 3, GOOD_HASH)}

    def test_identical_triple_is_idempotent_divergent_hash_refused(self, core):
        request = {"verb": "sign-event", "trial_id": "BROKER-001",
                   "sequence": 1, "event_hash": GOOD_HASH}
        first = core.handle(MY_UID, request)
        second = core.handle(MY_UID, dict(request))
        assert first == second  # crash recovery re-requests stay idempotent
        divergent = dict(request, event_hash="ef" * 32)
        assert _refusal(core, divergent) == "sign_divergence"

    @pytest.mark.parametrize("trial_id", ["", "-bad", "x" * 200, 7, None])
    def test_bad_trial_id(self, core, trial_id):
        assert _refusal(core, {
            "verb": "sign-event", "trial_id": trial_id,
            "sequence": 1, "event_hash": GOOD_HASH,
        }) == "bad_trial_id"

    @pytest.mark.parametrize("sequence", [0, -1, True, "7", 10**7, None])
    def test_bad_sequence(self, core, sequence):
        assert _refusal(core, {
            "verb": "sign-event", "trial_id": "BROKER-001",
            "sequence": sequence, "event_hash": GOOD_HASH,
        }) == "bad_sequence"

    @pytest.mark.parametrize("event_hash", ["", "ab" * 31, "AB" * 32, "zz" * 32, 7])
    def test_bad_event_hash_never_macd(self, core, event_hash):
        assert _refusal(core, {
            "verb": "sign-event", "trial_id": "BROKER-001",
            "sequence": 1, "event_hash": event_hash,
        }) == "bad_event_hash"

    def test_extra_keys_are_a_shape_refusal(self, core):
        assert _refusal(core, {
            "verb": "sign-event", "trial_id": "BROKER-001", "sequence": 1,
            "event_hash": GOOD_HASH, "payload": "arbitrary bytes",
        }) == "request_shape"


class TestCoreSignObject:
    def test_anchor_signature_matches_direct_hmac(self, core):
        payload = _anchor_payload()
        response = core.handle(MY_UID, {
            "verb": "sign-object", "purpose": "anchor", "payload": payload,
        })
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        expected = hmac.new(KEY, b"anchor\n" + canonical, hashlib.sha256).hexdigest()
        assert response == {"ok": True, "signature": expected}

    @pytest.mark.parametrize("purpose", ["control", "purge", "watermark"])
    def test_governance_purposes_are_never_minted(self, core, purpose):
        # Strict tightening: officer context loses control/purge/watermark
        # minting entirely — rollback laundering and store-governance
        # forgery are exactly the powers HP-1 removes.
        assert _refusal(core, {
            "verb": "sign-object", "purpose": purpose,
            "payload": _anchor_payload(),
        }) == "purpose_not_served"

    def test_unknown_purpose(self, core):
        assert _refusal(core, {
            "verb": "sign-object", "purpose": "exfil", "payload": {},
        }) == "purpose_unknown"

    @pytest.mark.parametrize("mutation", [
        lambda p: {k: v for k, v in p.items() if k != "updated_at"},  # missing
        lambda p: dict(p, extra="x"),                                  # extra
        lambda p: dict(p, schema="cabinet.evidence-purge-receipt/v1"),
        lambda p: dict(p, event_hash="zz" * 32),
        lambda p: dict(p, updated_at="x" * 99),
    ])
    def test_anchor_schema_is_exact(self, core, mutation):
        assert _refusal(core, {
            "verb": "sign-object", "purpose": "anchor",
            "payload": mutation(_anchor_payload()),
        }) == "anchor_schema"

    def test_non_dict_payload(self, core):
        assert _refusal(core, {
            "verb": "sign-object", "purpose": "anchor", "payload": "raw",
        }) == "bad_payload"

    def test_oversize_payload(self, core):
        payload = dict(_anchor_payload(), updated_at="x" * 40_000)
        assert _refusal(core, {
            "verb": "sign-object", "purpose": "anchor", "payload": payload,
        }) == "payload_oversize"


class TestCoreVerify:
    def test_verify_event_booleans_only(self, core):
        good = _event_mac("BROKER-001", 2, GOOD_HASH)
        yes = core.handle(MY_UID, {
            "verb": "verify-event", "trial_id": "BROKER-001", "sequence": 2,
            "event_hash": GOOD_HASH, "signature": good,
        })
        no = core.handle(MY_UID, {
            "verb": "verify-event", "trial_id": "BROKER-001", "sequence": 2,
            "event_hash": GOOD_HASH, "signature": "0" * 64,
        })
        assert yes == {"ok": True, "valid": True}
        assert no == {"ok": True, "valid": False}
        assert "signature" not in yes and "signature" not in no

    def test_verify_object_serves_governance_purposes_readonly(self, core):
        # Verification of control/purge/watermark stays available (the
        # recorder re-checks them on every load) — only MINTING is refused.
        payload = {"schema": "cabinet.evidence-control/v1", "diagnostic_mode": False}
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        good = hmac.new(KEY, b"control\n" + canonical, hashlib.sha256).hexdigest()
        yes = core.handle(MY_UID, {
            "verb": "verify-object", "purpose": "control",
            "payload": payload, "signature": good,
        })
        no = core.handle(MY_UID, {
            "verb": "verify-object", "purpose": "control",
            "payload": payload, "signature": "0" * 64,
        })
        assert yes == {"ok": True, "valid": True}
        assert no == {"ok": True, "valid": False}


class TestCoreAuthAndShape:
    def test_unknown_verb(self, core):
        assert _refusal(core, {"verb": "export-key"}) == "unknown_verb"

    @pytest.mark.parametrize("request_obj", [[1, 2], "sign", 7, None])
    def test_non_object_request(self, core, request_obj):
        assert _refusal(core, request_obj) == "request_shape"

    def test_unmapped_peer_uid_refused(self, core):
        assert _refusal(core, {"verb": "unknown"}, uid=MY_UID + 1) == "peer_unmapped"

    def test_absent_peer_cred_refused(self, core):
        assert _refusal(core, {"verb": "unknown"}, uid=None) == "peer_cred_unavailable"

    def test_identity_claim_must_match_the_kernel_map(self, core):
        assert _refusal(core, {
            "verb": "sign-event", "trial_id": "BROKER-001", "sequence": 1,
            "event_hash": GOOD_HASH, "identity": "captain",
        }) == "identity_mismatch"
        response = core.handle(MY_UID, {
            "verb": "sign-event", "trial_id": "BROKER-001", "sequence": 1,
            "event_hash": GOOD_HASH, "identity": "test-officer",
        })
        assert response["ok"] is True

    def test_rate_limit_refuses_the_burst(self):
        throttled = BrokerCore(
            KEY, {MY_UID: "test-officer"}, rate_capacity=2, rate_refill_per_s=0.0,
        )
        request = {"verb": "verify-event", "trial_id": "BROKER-001",
                   "sequence": 1, "event_hash": GOOD_HASH, "signature": "0" * 64}
        throttled.handle(MY_UID, dict(request))
        throttled.handle(MY_UID, dict(request))
        assert _refusal(throttled, dict(request)) == "rate_limited"


# ---------------------------------------------------------------------------
# Peer credentials — same-user simulation
# ---------------------------------------------------------------------------

class TestPeerCredentials:
    def test_platform_supports_peer_credentials(self):
        # On any platform the cabinet targets (macOS/Linux) this must be
        # true; the broker refuses to serve where it is not.
        if not (hasattr(socket, "SO_PEERCRED") or sys.platform == "darwin"):
            pytest.skip("platform without peer credentials — broker refuses to serve there")
        assert peer_cred_supported() is True

    def test_peer_uid_of_a_socketpair_is_this_uid(self):
        if not peer_cred_supported():
            pytest.skip("no peer credentials on this platform")
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            assert peer_uid(left) == MY_UID
            assert peer_uid(right) == MY_UID
        finally:
            left.close()
            right.close()

    def test_xucred_parse_checks_version(self):
        data = struct.pack("II", 0, 501) + b"\0" * 68
        assert _parse_xucred(data) == 501
        wrong_version = struct.pack("II", 9, 501) + b"\0" * 68
        assert _parse_xucred(wrong_version) is None
        assert _parse_xucred(b"\0\0") is None


# ---------------------------------------------------------------------------
# Broker config
# ---------------------------------------------------------------------------

class TestBrokerConfig:
    def _write(self, tmp_path: Path, text: str) -> Path:
        path = tmp_path / "broker.yml"
        path.write_text(text)
        return path

    def test_parses_scalars_and_identities(self, tmp_path):
        config = load_broker_config(self._write(tmp_path, (
            "socket: /tmp/s.sock\nkey: /tmp/k\nlog: /tmp/l.jsonl\n"
            "identities:\n  501: officer-core\n  502: broker-admin\n"
        )))
        assert config["identities"] == {501: "officer-core", 502: "broker-admin"}

    @pytest.mark.parametrize("text", [
        "key: /tmp/k\nlog: /tmp/l\nidentities:\n  501: a\n",       # no socket
        "socket: /tmp/s\nkey: /tmp/k\nlog: /tmp/l\n",              # no identities
        "socket: /tmp/s\nkey: /tmp/k\nlog: /tmp/l\nidentities:\n  bad: a\n",
    ])
    def test_bad_configs_refused(self, tmp_path, text):
        with pytest.raises(ValueError):
            load_broker_config(self._write(tmp_path, text))


# ---------------------------------------------------------------------------
# End-to-end over the socket (subprocess daemon, scratch key)
# ---------------------------------------------------------------------------

def _short_dir() -> Path:
    # AF_UNIX sun_path is ~104 bytes on macOS; pytest tmp dirs are too deep.
    path = Path(tempfile.mkdtemp(prefix="evb-"))
    if len(str(path)) > 80:  # pragma: no cover — degenerate TMPDIR
        path = Path(tempfile.mkdtemp(prefix="evb-", dir="/tmp"))
    return path


def _spawn(config_path: Path, *extra: str) -> subprocess.Popen:
    read_fd, write_fd = os.pipe()
    proc = subprocess.Popen(
        [sys.executable, "-m", "framework.evidence_signing_broker", "serve",
         "--config", str(config_path), "--ready-fd", str(write_fd), *extra],
        cwd=_REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        pass_fds=(write_fd,), text=True,
    )
    os.close(write_fd)
    try:
        ready, _, _ = select.select([read_fd], [], [], 15)
        if not ready or not os.read(read_fd, 16):
            proc.terminate()
            _, stderr = proc.communicate(timeout=10)
            raise AssertionError(f"broker never became ready: {stderr}")
    finally:
        os.close(read_fd)
    return proc


def _stop(proc: subprocess.Popen) -> tuple[str, str]:
    proc.send_signal(signal.SIGTERM)
    try:
        return proc.communicate(timeout=15)
    except subprocess.TimeoutExpired:  # pragma: no cover
        proc.kill()
        return proc.communicate()


class _Broker:
    def __init__(self, identities: dict[int, str], *extra: str, key: bytes = KEY):
        self.dir = _short_dir()
        self.socket_path = self.dir / "sign.sock"
        self.key_path = self.dir / "signing-key"
        self.log_path = self.dir / "requests.jsonl"
        self.key_path.write_bytes(key)
        self.key_path.chmod(0o600)
        config = self.dir / "broker.yml"
        lines = [f"socket: {self.socket_path}", f"key: {self.key_path}",
                 f"log: {self.log_path}", "identities:"]
        lines += [f"  {uid}: {name}" for uid, name in identities.items()]
        config.write_text("\n".join(lines) + "\n")
        self.config = config
        self.proc = _spawn(config, *extra)

    def request(self, payload: object) -> dict:
        raw = payload if isinstance(payload, (bytes, bytearray)) else (
            json.dumps(payload).encode("utf-8"))
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(10)
        try:
            conn.connect(str(self.socket_path))
            conn.sendall(raw + b"\n")
            chunks = []
            while True:
                chunk = conn.recv(8192)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\n" in chunk:
                    break
        finally:
            conn.close()
        return json.loads(b"".join(chunks).split(b"\n", 1)[0])

    def stop(self) -> tuple[str, str]:
        return _stop(self.proc)


@pytest.fixture(scope="module")
def broker():
    instance = _Broker({MY_UID: "test-officer"})
    yield instance
    instance.stop()


class TestBrokerEndToEnd:
    def test_sign_event_roundtrip_matches_direct_hmac(self, broker):
        response = broker.request({
            "verb": "sign-event", "trial_id": "BROKER-E2E-001",
            "sequence": 1, "event_hash": GOOD_HASH,
        })
        assert response == {
            "ok": True, "signature": _event_mac("BROKER-E2E-001", 1, GOOD_HASH),
        }

    def test_verify_event_booleans(self, broker):
        good = _event_mac("BROKER-E2E-001", 2, GOOD_HASH)
        assert broker.request({
            "verb": "verify-event", "trial_id": "BROKER-E2E-001", "sequence": 2,
            "event_hash": GOOD_HASH, "signature": good,
        }) == {"ok": True, "valid": True}
        assert broker.request({
            "verb": "verify-event", "trial_id": "BROKER-E2E-001", "sequence": 2,
            "event_hash": GOOD_HASH, "signature": "0" * 64,
        }) == {"ok": True, "valid": False}

    def test_malformed_and_oversize_and_unknown(self, broker):
        assert broker.request(b"this is not json") == {
            "ok": False, "refusal": "malformed_request"}
        assert broker.request(b"x" * (64 * 1024 + 10)) == {
            "ok": False, "refusal": "oversize"}
        assert broker.request({"verb": "export-key"}) == {
            "ok": False, "refusal": "unknown_verb"}
        assert broker.request([1, 2]) == {"ok": False, "refusal": "request_shape"}

    def test_governance_minting_refused_on_the_wire(self, broker):
        assert broker.request({
            "verb": "sign-object", "purpose": "purge",
            "payload": {"trial_id": "BROKER-E2E-001"},
        }) == {"ok": False, "refusal": "purpose_not_served"}

    def test_socket_permissions_staged_posture(self, broker):
        mode = stat.S_IMODE(os.stat(broker.socket_path).st_mode)
        assert mode == 0o600
        dir_mode = stat.S_IMODE(os.stat(broker.dir).st_mode)
        assert dir_mode & 0o077 == 0

    def test_request_log_rows_and_no_key_material_anywhere(self, broker):
        broker.request({
            "verb": "sign-event", "trial_id": "BROKER-E2E-LOG",
            "sequence": 1, "event_hash": GOOD_HASH,
        })
        rows = [json.loads(line) for line in
                broker.log_path.read_text().splitlines()]
        assert rows, "the broker must append its independent request log"
        target = [r for r in rows if r.get("trial_id") == "BROKER-E2E-LOG"]
        assert target and target[-1]["uid"] == MY_UID
        assert target[-1]["identity"] == "test-officer"
        assert target[-1]["verb"] == "sign-event"
        assert target[-1]["outcome"] == "ok"
        log_text = broker.log_path.read_text()
        assert KEY.hex() not in log_text
        assert str(broker.key_path) not in log_text

    def test_divergence_refused_and_logged(self, broker):
        broker.request({"verb": "sign-event", "trial_id": "BROKER-E2E-DIV",
                        "sequence": 1, "event_hash": GOOD_HASH})
        response = broker.request({
            "verb": "sign-event", "trial_id": "BROKER-E2E-DIV",
            "sequence": 1, "event_hash": "ef" * 32,
        })
        assert response == {"ok": False, "refusal": "sign_divergence"}
        rows = [json.loads(line) for line in
                broker.log_path.read_text().splitlines()]
        assert any(r.get("outcome") == "sign_divergence" for r in rows)


class TestBrokerEndToEndIsolated:
    def test_unmapped_peer_uid_refused_end_to_end(self):
        foreign = _Broker({MY_UID + 1: "someone-else"})
        try:
            assert foreign.request({
                "verb": "sign-event", "trial_id": "BROKER-001",
                "sequence": 1, "event_hash": GOOD_HASH,
            }) == {"ok": False, "refusal": "peer_unmapped"}
        finally:
            foreign.stop()

    def test_rate_limit_end_to_end(self):
        throttled = _Broker({MY_UID: "test-officer"},
                            "--rate-capacity", "3", "--rate-refill", "0.0001")
        try:
            request = {"verb": "verify-event", "trial_id": "BROKER-001",
                       "sequence": 1, "event_hash": GOOD_HASH,
                       "signature": "0" * 64}
            for _ in range(3):
                assert throttled.request(dict(request))["ok"] is True
            assert throttled.request(dict(request)) == {
                "ok": False, "refusal": "rate_limited"}
        finally:
            throttled.stop()

    def test_unloggable_request_is_not_served(self):
        instance = _Broker({MY_UID: "test-officer"})
        try:
            os.unlink(instance.log_path) if instance.log_path.exists() else None
            instance.log_path.mkdir()  # a directory cannot be appended to
            assert instance.request({
                "verb": "sign-event", "trial_id": "BROKER-001",
                "sequence": 1, "event_hash": GOOD_HASH,
            }) == {"ok": False, "refusal": "log_unavailable"}
        finally:
            instance.stop()

    def test_dead_socket_is_a_typed_client_failure(self):
        instance = _Broker({MY_UID: "test-officer"})
        instance.stop()
        signer = BrokerSigner(str(instance.socket_path), SigningError)
        with pytest.raises(SigningError) as excinfo:
            signer.event_signature("BROKER-001", 1, GOOD_HASH)
        assert excinfo.value.code == "signing_broker_unavailable"

    def test_refused_request_is_a_typed_client_failure(self):
        instance = _Broker({MY_UID: "test-officer"})
        try:
            signer = BrokerSigner(
                str(instance.socket_path), SigningError, identity="impostor")
            with pytest.raises(SigningError) as excinfo:
                signer.event_signature("BROKER-001", 1, GOOD_HASH)
            assert excinfo.value.code == "signing_broker_refused"
            assert "identity_mismatch" in str(excinfo.value)
        finally:
            instance.stop()


# ---------------------------------------------------------------------------
# Recorder in broker mode — the full same-user simulation
# ---------------------------------------------------------------------------

class TestRecorderBrokerMode:
    def test_recorder_rides_the_broker_and_fails_closed_when_it_dies(self, tmp_path):
        from framework.evidence import EvidenceError, EvidenceRecorder
        from framework.evidence.verifier import verify_trial

        store = tmp_path / "evidence" / "v1"
        store.mkdir(parents=True)
        # Store is BORN local (no signing config): key + control minted.
        EvidenceRecorder(store)
        store_key = (store / ".signing-key").read_bytes()

        # Same-user simulation: the broker holds the SAME key bytes (the
        # daemon loads its key ONCE at start — never per request).
        instance = _Broker({MY_UID: "evidence-recorder"}, key=store_key)
        try:
            config_dir = tmp_path / "config"
            config_dir.mkdir()
            (config_dir / "evidence-signing.yml").write_text(
                f"mode: broker\nsocket: {instance.socket_path}\n"
                "identity: evidence-recorder\n"
            )
            recorder = EvidenceRecorder(store)
            assert recorder._signer.mode == "broker"
            assert recorder._key is None  # no key handle in officer context

            context = recorder.trace(
                "BROKER-SIM-001", surface="test", trace_id="trace-sim-001",
                action_id="action-sim-001", correlation_id="corr-sim-001",
            )
            event = recorder.append(
                context, phase="intent", status="started",
                actor={"kind": "system", "id": "sim-test"},
                component={"name": "sim-test", "version": "1.0.0", "commit": "abc123"},
                detail={"action": "broker_sim"},
            )
            message = f"event\nBROKER-SIM-001\n1\n{event['event_hash']}".encode()
            assert event["signature"] == hmac.new(
                store_key, message, hashlib.sha256).hexdigest()
            assert verify_trial(store, "BROKER-SIM-001")["ok"] is True
            # The store key was NOT re-minted by broker-mode construction.
            assert (store / ".signing-key").read_bytes() == store_key
            # The independent second record saw the mint.
            log_rows = [json.loads(line) for line in
                        instance.log_path.read_text().splitlines()]
            assert any(r.get("verb") == "sign-event" and
                       r.get("trial_id") == "BROKER-SIM-001" for r in log_rows)
            assert any(r.get("verb") == "sign-object" and
                       r.get("purpose") == "anchor" for r in log_rows)

            # Governance minting is refused end-to-end (strict tightening).
            with pytest.raises(EvidenceError) as excinfo:
                recorder.purge_trial(
                    "BROKER-SIM-001", confirmation="PURGE BROKER-SIM-001",
                    actor="captain")
            assert excinfo.value.code == "signing_broker_refused"
            assert verify_trial(store, "BROKER-SIM-001")["ok"] is True
            with pytest.raises(EvidenceError) as excinfo:
                recorder.configure(
                    actor="captain", retention_days=30, diagnostic_mode=False)
            assert excinfo.value.code == "signing_broker_refused"

            trial_dir = next(p for p in (store / "trials").iterdir() if p.is_dir())
            rows_before = (trial_dir / "events.jsonl").read_text().splitlines()

            instance.stop()
            # Evidence-before-action: a dead broker REFUSES the append with
            # a typed error and zero new bytes — never a local fallback.
            with pytest.raises(EvidenceError) as excinfo:
                recorder.append(
                    context, phase="outcome", status="succeeded",
                    actor={"kind": "system", "id": "sim-test"},
                    component={"name": "sim-test", "version": "1.0.0", "commit": "abc123"},
                )
            assert excinfo.value.code == "signing_broker_unavailable"
            rows_after = (trial_dir / "events.jsonl").read_text().splitlines()
            assert rows_after == rows_before
        finally:
            if instance.proc.poll() is None:
                instance.stop()


# ---------------------------------------------------------------------------
# Dark law — staged disabled row; no setup surface arms the daemon
# ---------------------------------------------------------------------------

class TestDarkLaw:
    def test_services_row_ships_disabled_with_the_ceremony_named(self):
        services = (_REPO / "cabinet" / "services.yml").read_text()
        block = services.split("- name: evidence-signing-broker", 1)[1]
        block = block.split("- name: ", 1)[0]
        assert "disabled: true" in block
        reason = block.split("disabled_reason:", 1)[1]
        assert "staged" in reason[:200]
        assert "ceremony" in reason[:600]
        command_line = next(l for l in block.splitlines() if "command:" in l)
        assert "&&" not in command_line  # ONE command (plist wrapper execs one program)

    def test_no_setup_script_references_the_label(self):
        """The dark grep (test_gate_apply_dark twin): nothing under
        cabinet/scripts or cabinet/cron may mention the daemon label —
        only services.yml (fleet truth), the runbook, and tests may.
        os.walk on purpose: the exported tree has no .git."""
        offenders = []
        for root_name in ("scripts", "cron"):
            root = _REPO / "cabinet" / root_name
            if not root.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d != "__pycache__"]
                for name in filenames:
                    path = Path(dirpath) / name
                    if path.suffix == ".pyc" or "tests" in path.parts:
                        continue
                    try:
                        text = path.read_text(errors="ignore")
                    except OSError:
                        continue
                    if LABEL in text:
                        offenders.append(str(path.relative_to(_REPO)))
        assert offenders == [], (
            f"dark daemon referenced by setup surface(s): {offenders}")

    def test_no_script_loads_the_label(self):
        pattern = re.compile(r"launchctl\s+(load|bootstrap).*evidence-signing-broker")
        offenders = []
        for dirpath, dirnames, filenames in os.walk(_REPO / "cabinet"):
            dirnames[:] = [d for d in dirnames if d not in {"__pycache__", "node_modules"}]
            for name in filenames:
                if not name.endswith(".sh"):
                    continue
                path = Path(dirpath) / name
                try:
                    text = path.read_text(errors="ignore")
                except OSError:
                    continue
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    if pattern.search(stripped):
                        offenders.append(str(path.relative_to(_REPO)))
        assert offenders == []

    def test_broker_module_carries_the_threat_honesty(self):
        source = (_REPO / "framework" / "evidence_signing_broker.py").read_text()
        assert "same-OS-user to root" in source
        runbook = (_REPO / "docs" / "runbooks" / "evidence-signing-broker.md").read_text()
        assert "same-OS-user to root" in runbook
        assert "never executed by a build workflow" in runbook
