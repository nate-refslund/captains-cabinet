"""Evidence signing broker — out-of-process HMAC key custody (HP-1).

Same-OS-user key custody is the NAMED residual of the evidence recorder: an
attacker running as the officer user can read ``.signing-key`` and forge a
consistent store.  This daemon closes that residual by holding the key in a
separate OS user and serving signature minting/verification over a Unix
socket, so officer-context processes can record and verify evidence without
ever being able to read the key.  (Scope honesty: the recorder's signing
seam consumes these verbs today; the independent verifier still reads the
store-root key directly until its own broker seam lands, so the key stays
AT the store root even in broker mode and the deploy ceremony is blocked on
that follow-up — see framework/evidence/signing.py and the runbook.)

This module is intentionally NOT part of the germline ``framework/evidence``
package (the evidence_anchor.py / evidence_mirror.py precedent): it is the
custody boundary AROUND the store, staged dark until the deploy ceremony.
It follows the cabinet/scripts/captain-law-broker.py house shape — identity
fixed at daemon start, newline-framed single JSON object per connection,
typed refusals, umask-guarded 0600 socket in a 0700 directory — and adds
what key custody needs on top:

* **Peer-credential authentication.**  Every connection's peer uid is read
  from the kernel (``SO_PEERCRED`` on Linux, ``LOCAL_PEERCRED`` on macOS)
  and must map to an identity in the broker's start-time allowlist.  If the
  platform offers neither mechanism the broker REFUSES TO SERVE — peer
  credentials are a requirement, not best-effort.
* **Event-hash-shaped payloads only.**  ``sign-event`` carries
  ``{trial_id, sequence, event_hash}`` and the broker constructs the frozen
  ``event\\n…`` preimage ITSELF — arbitrary caller bytes are never MAC'd.
  ``sign-object`` serves ONLY the ``anchor`` purpose with an exact payload
  schema; ``control`` and ``purge`` signing is refused in v1 (officer
  context losing control/purge minting is a strict tightening — store
  birth, configuration, and purges become broker-user/ceremony operations).
* **Boolean verification.**  ``verify-event`` / ``verify-object`` answer
  ``valid: true|false`` and never return a MAC, so verification cannot be
  used as a minting oracle for purposes the caller may not sign.
* **Divergence refusal.**  Re-requesting a signature for the SAME
  ``(trial_id, sequence)`` with a DIFFERENT event hash is the history-
  rewrite shape and is refused loudly; identical re-requests stay
  idempotent because crash recovery legitimately re-verifies the same
  triple.  The memory is bounded (oldest triples age out); the request log
  below is the durable record.
* **An independent request log.**  Every request appends one JSONL row
  (ts, uid, identity, verb, ids, outcome) to a broker-owned log — the
  second record that makes bulk re-signing visible.  A request that cannot
  be logged is refused: signing without a record would defeat the log's
  purpose.  Key bytes and the key path never appear in any response, log
  row, or error message.

THREAT HONESTY (stated, not hidden): HP-1 raises the forgery bar from
same-OS-user to root.  Root can still forge events, anchors, watermarks,
this broker's request log, and the key itself; a compromise of the broker
user is a key compromise.  Those residuals are accepted and stated, and
external anchoring (framework/evidence_anchor.py) exists for after-the-fact
detection.

STAGED-DARK LAW: the ``evidence-signing-broker`` row in cabinet/services.yml
ships ``disabled: true`` and its ONLY enable path is the documented Captain
sudo deploy ceremony (docs/runbooks/evidence-signing-broker.md) — creating
the broker OS user, relocating the key, and installing a
/Library/LaunchDaemons plist with ``UserName``.  Removing the disabled flag
and generating LaunchAgents would run the broker as the officer user:
functional, but zero isolation — false comfort, not security.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import stat
import struct
import sys
import time
from collections import OrderedDict
from pathlib import Path

from framework.evidence.signing import (
    HEX64_RE,
    MAX_WIRE_SEQUENCE,
    TRIAL_ID_RE,
    LocalKeySigner,
    SigningError,
    canonical,
    parse_scalars,
)

MAX_REQUEST = 64 * 1024
MAX_PAYLOAD_CANONICAL_BYTES = 32 * 1024
MAX_UPDATED_AT_LEN = 40
IDENTITY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

# The anchor payload schema the recorder produces (deliberate duplicate of
# the recorder's ANCHOR_SCHEMA; the broker test pins equality).  sign-object
# serves exactly this shape and nothing else.
ANCHOR_SCHEMA_VALUE = "cabinet.evidence-anchor/v1"
ANCHOR_PAYLOAD_KEYS = frozenset({
    "schema", "trial_id", "sequence", "event_hash", "event_signature",
    "updated_at",
})

SIGNABLE_PURPOSES = frozenset({"anchor"})
VERIFIABLE_PURPOSES = frozenset({"anchor", "control", "purge", "watermark"})

# In-code rate-limit constants (code-constant law: never env-derived).  The
# serve() arguments exist so tests can exercise the refusal without a long
# burst; the daemon defaults are these constants.
RATE_CAPACITY = 300
RATE_REFILL_PER_S = 50.0

# Bounded divergence memory: oldest (trial, sequence) → hash triples age out
# past this many entries, so divergence refusal is a fast tripwire within
# the window while the request log stays the durable record.
MINTED_MEMORY = 8192

# macOS peer credentials: getsockopt(SOL_LOCAL, LOCAL_PEERCRED) fills
# struct xucred {u_int cr_version; uid_t cr_uid; short cr_ngroups;
# gid_t cr_groups[16];} — 76 bytes, cr_version must be XUCRED_VERSION.
SOL_LOCAL = 0
LOCAL_PEERCRED = 0x0001
XUCRED_VERSION = 0
XUCRED_SIZE = 76


class Refusal(ValueError):
    """A typed broker refusal; ``str(exc)`` is the wire refusal code."""


def peer_cred_supported() -> bool:
    return hasattr(socket, "SO_PEERCRED") or sys.platform == "darwin"


def _parse_xucred(data: bytes) -> int | None:
    if len(data) < 8:
        return None
    version, uid = struct.unpack_from("II", data, 0)
    if version != XUCRED_VERSION:
        return None
    return uid


def peer_uid(conn: socket.socket) -> int | None:
    """Kernel-attested peer uid, or ``None`` when it cannot be established."""
    if hasattr(socket, "SO_PEERCRED"):
        try:
            data = conn.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
            )
        except OSError:
            return None
        if len(data) < struct.calcsize("3i"):
            return None
        _pid, uid, _gid = struct.unpack("3i", data)
        return uid
    if sys.platform == "darwin":
        try:
            data = conn.getsockopt(SOL_LOCAL, LOCAL_PEERCRED, XUCRED_SIZE)
        except OSError:
            return None
        return _parse_xucred(data)
    return None


class _RateLimiter:
    def __init__(self, capacity: int, refill_per_s: float):
        self._capacity = float(capacity)
        self._refill = float(refill_per_s)
        self._buckets: dict[int, tuple[float, float]] = {}

    def allow(self, uid: int) -> bool:
        now = time.monotonic()
        tokens, last = self._buckets.get(uid, (self._capacity, now))
        tokens = min(self._capacity, tokens + (now - last) * self._refill)
        if tokens < 1.0:
            self._buckets[uid] = (tokens, now)
            return False
        self._buckets[uid] = (tokens - 1.0, now)
        return True


def load_broker_config(path: Path) -> dict:
    """Parse the broker's start-time config (socket/key/log + identities).

    The identity map binds kernel peer uids to attested identity names and
    is FIXED at daemon start — never influenced by a request.
    """
    if path.is_symlink():
        raise ValueError("broker config must not be a symbolic link")
    text = path.read_text(encoding="utf-8")
    scalars = parse_scalars(text)
    identities: dict[int, str] = {}
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line[:1] in (" ", "\t"):
            in_block = stripped == "identities:"
            continue
        if not in_block:
            continue
        match = re.match(r"^([0-9]{1,10}):\s*([a-z0-9][a-z0-9._-]{0,63})\s*$", stripped)
        if not match:
            raise ValueError("broker config has an invalid identities entry")
        identities[int(match.group(1))] = match.group(2)
    config = {
        "socket": os.path.expanduser(scalars.get("socket") or ""),
        "key": os.path.expanduser(scalars.get("key") or ""),
        "log": os.path.expanduser(scalars.get("log") or ""),
        "identities": identities,
    }
    for name in ("socket", "key", "log"):
        if not config[name]:
            raise ValueError(f"broker config is missing '{name}'")
    if not identities:
        raise ValueError("broker config names no identities")
    return config


def _load_key(path: Path) -> bytes:
    """Load the HMAC key with the recorder's own safety posture.

    Error text is deliberately path-free: the key location never appears in
    output, logs, or exceptions.
    """
    try:
        if path.is_symlink():
            raise ValueError("signing key unsafe")
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise ValueError("signing key unsafe")
        key = path.read_bytes()
    except OSError as exc:
        raise ValueError("signing key unavailable") from exc
    if len(key) < 32:
        raise ValueError("signing key invalid")
    return key


class BrokerCore:
    """Validation + signing core, transport-free so tests can drive it."""

    def __init__(
        self,
        key: bytes,
        identities: dict[int, str],
        *,
        rate_capacity: int = RATE_CAPACITY,
        rate_refill_per_s: float = RATE_REFILL_PER_S,
    ):
        self._signer = LocalKeySigner(key, SigningError)
        self._identities = dict(identities)
        self._limiter = _RateLimiter(rate_capacity, rate_refill_per_s)
        self._minted: OrderedDict[tuple[str, int], str] = OrderedDict()

    # -- field validators --------------------------------------------------
    @staticmethod
    def _trial_id(value: object) -> str:
        if not isinstance(value, str) or not TRIAL_ID_RE.fullmatch(value):
            raise Refusal("bad_trial_id")
        return value

    @staticmethod
    def _sequence(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise Refusal("bad_sequence")
        if not 1 <= value <= MAX_WIRE_SEQUENCE:
            raise Refusal("bad_sequence")
        return value

    @staticmethod
    def _hex64(value: object, code: str) -> str:
        if not isinstance(value, str) or not HEX64_RE.fullmatch(value):
            raise Refusal(code)
        return value

    @staticmethod
    def _shape(request: dict, required: set[str]) -> None:
        allowed = required | {"verb", "identity"}
        keys = set(request)
        if not required <= keys or not keys <= allowed:
            raise Refusal("request_shape")

    def _payload(self, value: object) -> dict:
        if not isinstance(value, dict):
            raise Refusal("bad_payload")
        try:
            encoded = canonical(value, SigningError)
        except SigningError as exc:
            raise Refusal("bad_payload") from exc
        if len(encoded) > MAX_PAYLOAD_CANONICAL_BYTES:
            raise Refusal("payload_oversize")
        return value

    def _anchor_schema(self, payload: dict) -> None:
        if set(payload) != set(ANCHOR_PAYLOAD_KEYS):
            raise Refusal("anchor_schema")
        if payload.get("schema") != ANCHOR_SCHEMA_VALUE:
            raise Refusal("anchor_schema")
        try:
            self._trial_id(payload.get("trial_id"))
            self._sequence(payload.get("sequence"))
            self._hex64(payload.get("event_hash"), "anchor_schema")
            self._hex64(payload.get("event_signature"), "anchor_schema")
        except Refusal as exc:
            raise Refusal("anchor_schema") from exc
        updated_at = payload.get("updated_at")
        if not isinstance(updated_at, str) or not 1 <= len(updated_at) <= MAX_UPDATED_AT_LEN:
            raise Refusal("anchor_schema")

    def _divergence_check(self, trial_id: str, sequence: int, event_hash: str) -> None:
        known = self._minted.get((trial_id, sequence))
        if known is not None and known != event_hash:
            raise Refusal("sign_divergence")
        self._minted[(trial_id, sequence)] = event_hash
        self._minted.move_to_end((trial_id, sequence))
        while len(self._minted) > MINTED_MEMORY:
            self._minted.popitem(last=False)

    # -- request handling --------------------------------------------------
    def identity_for(self, uid: int | None) -> str:
        if uid is None:
            raise Refusal("peer_cred_unavailable")
        identity = self._identities.get(uid)
        if identity is None:
            raise Refusal("peer_unmapped")
        return identity

    def handle(self, uid: int | None, request: object) -> dict:
        """Validate and execute one request; raises ``Refusal`` on any no."""
        identity = self.identity_for(uid)
        if not self._limiter.allow(uid):  # uid is attested by now
            raise Refusal("rate_limited")
        if not isinstance(request, dict):
            raise Refusal("request_shape")
        claimed = request.get("identity")
        if claimed is not None and claimed != identity:
            raise Refusal("identity_mismatch")
        verb = request.get("verb")
        if verb == "sign-event":
            self._shape(request, {"trial_id", "sequence", "event_hash"})
            trial_id = self._trial_id(request.get("trial_id"))
            sequence = self._sequence(request.get("sequence"))
            event_hash = self._hex64(request.get("event_hash"), "bad_event_hash")
            self._divergence_check(trial_id, sequence, event_hash)
            return {
                "ok": True,
                "signature": self._signer.event_signature(trial_id, sequence, event_hash),
            }
        if verb == "verify-event":
            self._shape(request, {"trial_id", "sequence", "event_hash", "signature"})
            trial_id = self._trial_id(request.get("trial_id"))
            sequence = self._sequence(request.get("sequence"))
            event_hash = self._hex64(request.get("event_hash"), "bad_event_hash")
            signature = self._hex64(request.get("signature"), "bad_signature")
            return {
                "ok": True,
                "valid": self._signer.verify_event(trial_id, sequence, event_hash, signature),
            }
        if verb == "sign-object":
            self._shape(request, {"purpose", "payload"})
            purpose = request.get("purpose")
            if purpose not in VERIFIABLE_PURPOSES:
                raise Refusal("purpose_unknown")
            if purpose not in SIGNABLE_PURPOSES:
                # control/purge/watermark minting stays off the socket:
                # rollback laundering (a re-signed lowered watermark) and
                # officer-context store-governance minting are exactly the
                # powers HP-1 removes.
                raise Refusal("purpose_not_served")
            payload = self._payload(request.get("payload"))
            self._anchor_schema(payload)
            return {"ok": True, "signature": self._signer.object_signature(purpose, payload)}
        if verb == "verify-object":
            self._shape(request, {"purpose", "payload", "signature"})
            purpose = request.get("purpose")
            if purpose not in VERIFIABLE_PURPOSES:
                raise Refusal("purpose_unknown")
            payload = self._payload(request.get("payload"))
            signature = self._hex64(request.get("signature"), "bad_signature")
            return {
                "ok": True,
                "valid": self._signer.verify_object(purpose, payload, signature),
            }
        raise Refusal("unknown_verb")


def _append_log(log_path: Path, row: dict) -> None:
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(log_path, flags, 0o600)
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode):
            raise OSError("log is not a regular file")
        encoded = json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        view = memoryview(encoded.encode("utf-8"))
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _log_row(uid: int | None, identity: str | None, request: object, outcome: str) -> dict:
    row: dict = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "uid": uid,
        "identity": identity,
        "outcome": outcome,
    }
    if isinstance(request, dict):
        row["verb"] = request.get("verb") if isinstance(request.get("verb"), str) else None
        for field in ("trial_id", "sequence", "event_hash", "purpose"):
            value = request.get(field)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                row[field] = value
    return row


def _read_request(conn: socket.socket) -> object:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = conn.recv(min(8192, MAX_REQUEST + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > MAX_REQUEST:
            raise Refusal("oversize")
        if b"\n" in chunk:
            break
    raw = b"".join(chunks).split(b"\n", 1)[0]
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise Refusal("malformed_request") from exc


def serve(
    config_path: Path,
    *,
    idle_timeout: int = 86400,
    rate_capacity: int = RATE_CAPACITY,
    rate_refill_per_s: float = RATE_REFILL_PER_S,
    ready_fd: int | None = None,
) -> int:
    if not peer_cred_supported():
        # Peer credentials are a REQUIREMENT: without them any local process
        # could speak for any identity, so the broker refuses to serve.
        print(
            "evidence-signing-broker: peer credentials unavailable on this "
            "platform; refusing to serve (fail closed)",
            file=sys.stderr,
        )
        return 2
    try:
        config = load_broker_config(config_path)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        print(f"evidence-signing-broker: bad config: {exc}", file=sys.stderr)
        return 2
    try:
        key = _load_key(Path(config["key"]))
    except ValueError as exc:
        # Path-free by design; see _load_key.
        print(f"evidence-signing-broker: {exc}", file=sys.stderr)
        return 2
    log_path = Path(config["log"])
    core = BrokerCore(
        key,
        config["identities"],
        rate_capacity=rate_capacity,
        rate_refill_per_s=rate_refill_per_s,
    )

    socket_path = Path(config["socket"])
    # Staged same-user posture: 0700 directory, 0600 socket (captain-law-
    # broker parity).  The deploy ceremony loosens the REAL daemon to a
    # 0750 dir + 0660 group-shared socket so the officer user can connect —
    # the peer-credential allowlist above is the actual boundary there.
    socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        socket_path.parent.chmod(0o700)
    except OSError:
        pass
    try:
        socket_path.unlink()
    except FileNotFoundError:
        pass
    old_umask = os.umask(0o177)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(socket_path))
    finally:
        os.umask(old_umask)
    os.chmod(socket_path, 0o600)
    server.listen(16)
    server.settimeout(1)
    last_request = time.monotonic()
    stopping = False

    def _stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    if ready_fd is not None:
        try:
            os.write(ready_fd, b"ready\n")
            os.close(ready_fd)
        except OSError:
            pass
    try:
        while not stopping:
            if time.monotonic() - last_request >= idle_timeout:
                break
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            last_request = time.monotonic()
            with conn:
                conn.settimeout(5)
                uid: int | None = None
                identity: str | None = None
                request: object = None
                try:
                    uid = peer_uid(conn)
                    try:
                        identity = core.identity_for(uid)
                    except Refusal:
                        identity = None
                    request = _read_request(conn)
                    response = core.handle(uid, request)
                    outcome = "ok"
                except Refusal as exc:
                    response = {"ok": False, "refusal": str(exc)}
                    outcome = str(exc)
                    if str(exc) == "sign_divergence":
                        row = request if isinstance(request, dict) else {}
                        print(
                            "evidence-signing-broker: SIGN DIVERGENCE "
                            f"uid={uid} trial={row.get('trial_id')} "
                            f"sequence={row.get('sequence')} — same (trial, "
                            "sequence) requested with a different hash; "
                            "refused and recorded",
                            file=sys.stderr,
                        )
                except OSError:
                    response = {"ok": False, "refusal": "io_error"}
                    outcome = "io_error"
                # The log is load-bearing: a request that cannot be recorded
                # is not served (fail closed) — signing without the second
                # record would defeat the record.
                try:
                    _append_log(log_path, _log_row(uid, identity, request, outcome))
                except OSError:
                    response = {"ok": False, "refusal": "log_unavailable"}
                try:
                    conn.sendall(
                        json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n"
                    )
                except OSError:
                    pass
    finally:
        server.close()
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evidence-signing-broker",
        description="Out-of-process evidence signing (HP-1). Staged dark; "
        "armed only by the documented Captain deploy ceremony.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    serve_p = sub.add_parser("serve")
    serve_p.add_argument("--config", type=Path, required=True)
    serve_p.add_argument("--idle-timeout", type=int, default=86400)
    serve_p.add_argument("--rate-capacity", type=int, default=RATE_CAPACITY)
    serve_p.add_argument("--rate-refill", type=float, default=RATE_REFILL_PER_S)
    serve_p.add_argument(
        "--ready-fd", type=int, default=None,
        help="fd to write a readiness line to once listening (test harness)",
    )
    args = parser.parse_args(argv)
    return serve(
        args.config,
        idle_timeout=args.idle_timeout,
        rate_capacity=args.rate_capacity,
        rate_refill_per_s=args.rate_refill,
        ready_fd=args.ready_fd,
    )


if __name__ == "__main__":
    raise SystemExit(main())
