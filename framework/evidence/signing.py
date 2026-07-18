"""Signer seam for the evidence store (HP-1: key custody behind a broker).

This is a LEAF module by law: it imports nothing from ``recorder``,
``verifier``, or ``identity`` (the recorder imports *it*), and it depends on
the standard library only.  It owns exactly one decision — WHERE evidence
signatures come from:

* **Local mode (the default, and the only pre-ceremony mode).**  No signing
  config exists, or the config does not declare ``mode: broker`` → the
  recorder's own key loader runs unchanged and every signature is computed
  in-process, byte-identical to the pre-seam recorder.  Unconfigured means
  UNCHANGED — the dark-by-default law.
* **Broker mode (armed only by the HP-1 deploy ceremony).**  The config
  declares ``mode: broker`` and names a Unix socket served by
  ``framework/evidence_signing_broker.py`` running as a SEPARATE OS user
  that holds the HMAC key.  The RECORDER's signatures are minted and its
  signature checks answered over the socket; the key never crosses it; the
  local key-create path is never invoked (a locally minted second key would
  split-brain the store).  A dead or refusing broker is a typed,
  fail-closed ``EvidenceError`` — NEVER a silent local fallback, because a
  fallback is a downgrade attack (kill the daemon, forge locally).

  SCOPE HONESTY: this seam brokers the recorder's sign/verify call sites
  ONLY.  The independent verifier (``verifier.py`` — which the recorder
  invokes in-path on every append, and which the officer read doorway
  runs) still reads ``<store_root>/.signing-key`` directly, so the key
  must REMAIN at the store root even in broker mode until the verifier
  grows its own broker seam.  The broker's boolean verify verbs exist for
  exactly that follow-up; until it lands, HP-1 is NOT fully achieved (the
  key stays readable to the verifying user) and the deploy ceremony is
  BLOCKED on it — docs/runbooks/evidence-signing-broker.md names the
  precondition.

Config resolution is store-adjacent geometry, not an environment variable
(no environment variable may bear behavior — recorder MAX_TRIAL_EVENTS law):
``<store_root>/../../config/evidence-signing.yml``.  For the production
store that path lands in the deployment overlay's ``config/`` directory;
for scratch and test stores it resolves to an absent path, which is local
mode by construction — hermetic tests need no fencing.

THREAT HONESTY (state it, never hide it): HP-1 raises the forgery bar from
same-OS-user to root.  Root can still forge events, anchors, watermarks,
the broker's request log, and the key itself; that residual is accepted and
stated, and external anchoring (framework/evidence_anchor.py) exists for
after-the-fact detection.  Before the deploy ceremony the signing config
does not exist and cannot be immutability-locked (locks skip absent paths),
so a same-user writer could create one: the reachable damage is
evidence-plane denial (loud, fail-closed) or pointing signing at an
attacker's socket — which grants nothing beyond the same-user forgery power
that exists today without HP-1.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import socket
from pathlib import Path
from typing import Any, Callable

# Deliberate byte-exact duplicates of the recorder's frozen v1 signing
# formats (the leaf law forbids importing them; the germline seam test pins
# equality so they can never drift).  These formats are frozen by stored-
# store compatibility: changing them breaks verification of every existing
# event, so they are constants of the format, not tunables.
EVENT_MESSAGE_PREFIX = "event"
TRIAL_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
TRIAL_ID_RE = re.compile(TRIAL_ID_PATTERN)
HEX64_RE = re.compile(r"^[a-f0-9]{64}$")

CONFIG_DIR_NAME = "config"
CONFIG_FILE_NAME = "evidence-signing.yml"
MAX_CONFIG_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
BROKER_TIMEOUT_S = 5.0

# Bound sequence numbers accepted on the wire.  The recorder's per-trial
# envelope is 500; recovery re-verification may exceed it slightly on legacy
# over-cap trials, so the wire bound is generous while still refusing
# absurd values.
MAX_WIRE_SEQUENCE = 1_000_000


class SigningError(RuntimeError):
    """Typed signing failure; mirrors the recorder's error shape (.code)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def canonical(value: Any, error_cls: type[Exception] = SigningError) -> bytes:
    """Byte-exact twin of the recorder's canonical JSON serialization."""
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise error_cls(
            "payload_unserializable",
            "The evidence payload could not be serialized for hashing.",
        ) from exc


def event_message(trial_id: str, sequence: int, event_hash: str) -> bytes:
    """The frozen v1 event-signature preimage."""
    return f"{EVENT_MESSAGE_PREFIX}\n{trial_id}\n{sequence}\n{event_hash}".encode("utf-8")


def object_message(
    purpose: str, value: dict[str, Any], error_cls: type[Exception] = SigningError
) -> bytes:
    """The frozen v1 object-signature preimage."""
    return purpose.encode("utf-8") + b"\n" + canonical(value, error_cls)


class LocalKeySigner:
    """In-process signer over the store's own key — the pre-seam behavior.

    Every digest it produces is byte-identical to the recorder's original
    inline ``hmac.new(key, message, sha256)`` calls; the seam test pins the
    known-answer vectors.
    """

    mode = "local"

    def __init__(self, key: bytes, error_cls: type[Exception] = SigningError):
        # Public on purpose: the recorder re-exposes it for the captain-
        # capability token seam.  Broker mode has no such attribute — the
        # key never exists in this process there.
        self.key = key
        self._key = key
        self._error_cls = error_cls

    def event_signature(self, trial_id: str, sequence: int, event_hash: str) -> str:
        return hmac.new(
            self._key, event_message(trial_id, sequence, event_hash), hashlib.sha256
        ).hexdigest()

    def object_signature(self, purpose: str, value: dict[str, Any]) -> str:
        return hmac.new(
            self._key, object_message(purpose, value, self._error_cls), hashlib.sha256
        ).hexdigest()

    def verify_event(
        self, trial_id: str, sequence: int, event_hash: str, signature: str
    ) -> bool:
        expected = self.event_signature(trial_id, sequence, event_hash)
        return hmac.compare_digest(str(signature), expected)

    def verify_object(
        self, purpose: str, value: dict[str, Any], signature: str
    ) -> bool:
        expected = self.object_signature(purpose, value)
        return hmac.compare_digest(str(signature), expected)


class BrokerSigner:
    """Socket client for the out-of-process signing broker (HP-1 armed mode).

    One newline-framed JSON request per connection (the captain-law-broker
    house protocol).  Sign verbs return the MAC for the recorder to embed;
    verify verbs return booleans only.  Every failure is typed and
    fail-closed: an unreachable broker refuses the evidence operation rather
    than falling back to a local key (which broker mode does not load).
    """

    mode = "broker"

    def __init__(
        self,
        socket_path: str,
        error_cls: type[Exception] = SigningError,
        identity: str | None = None,
    ):
        self._socket_path = socket_path
        self._error_cls = error_cls
        # Optional CLAIMED identity from the signing config.  The broker
        # checks the claim against the kernel-attested peer uid map and
        # refuses a mismatch — the claim can narrow, never widen.
        self._identity = identity or None

    # -- transport ---------------------------------------------------------
    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._identity is not None:
            payload = {**payload, "identity": self._identity}
        try:
            raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        except (TypeError, ValueError) as exc:
            raise self._error_cls(
                "payload_unserializable",
                "The evidence payload could not be serialized for hashing.",
            ) from exc
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(BROKER_TIMEOUT_S)
        try:
            conn.connect(self._socket_path)
            conn.sendall(raw)
            chunks: list[bytes] = []
            size = 0
            while True:
                chunk = conn.recv(8192)
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise self._error_cls(
                        "signing_broker_protocol",
                        "The evidence signing broker returned an oversized response.",
                    )
                if b"\n" in chunk:
                    break
        except OSError as exc:
            # Deliberately path-free: no socket path in evidence-plane errors.
            raise self._error_cls(
                "signing_broker_unavailable",
                "The evidence signing broker is unavailable; the evidence "
                "operation was refused (fail-closed, no local fallback).",
            ) from exc
        finally:
            conn.close()
        try:
            response = json.loads(b"".join(chunks).split(b"\n", 1)[0])
        except (UnicodeDecodeError, ValueError) as exc:
            raise self._error_cls(
                "signing_broker_protocol",
                "The evidence signing broker returned an invalid response.",
            ) from exc
        if not isinstance(response, dict):
            raise self._error_cls(
                "signing_broker_protocol",
                "The evidence signing broker returned an invalid response.",
            )
        if response.get("ok") is not True:
            refusal = str(response.get("refusal") or "unspecified")
            raise self._error_cls(
                "signing_broker_refused",
                f"The evidence signing broker refused the request ({refusal}).",
            )
        return response

    def _signature_from(self, response: dict[str, Any]) -> str:
        signature = response.get("signature")
        if not isinstance(signature, str) or not HEX64_RE.fullmatch(signature):
            raise self._error_cls(
                "signing_broker_protocol",
                "The evidence signing broker returned an invalid signature.",
            )
        return signature

    # -- verbs -------------------------------------------------------------
    def event_signature(self, trial_id: str, sequence: int, event_hash: str) -> str:
        return self._signature_from(self._request({
            "verb": "sign-event",
            "trial_id": trial_id,
            "sequence": sequence,
            "event_hash": event_hash,
        }))

    def object_signature(self, purpose: str, value: dict[str, Any]) -> str:
        return self._signature_from(self._request({
            "verb": "sign-object",
            "purpose": purpose,
            "payload": value,
        }))

    def verify_event(
        self, trial_id: str, sequence: int, event_hash: str, signature: str
    ) -> bool:
        # A shape-invalid triple or signature can never verify; answering
        # False locally keeps parity with local-mode recompute-and-compare
        # (which also yields a mismatch, not a refusal) and keeps malformed
        # bytes off the socket.
        if (
            not isinstance(trial_id, str)
            or not TRIAL_ID_RE.fullmatch(trial_id)
            or isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or not 1 <= sequence <= MAX_WIRE_SEQUENCE
            or not isinstance(event_hash, str)
            or not HEX64_RE.fullmatch(event_hash)
            or not isinstance(signature, str)
            or not HEX64_RE.fullmatch(signature)
        ):
            return False
        response = self._request({
            "verb": "verify-event",
            "trial_id": trial_id,
            "sequence": sequence,
            "event_hash": event_hash,
            "signature": signature,
        })
        return response.get("valid") is True

    def verify_object(
        self, purpose: str, value: dict[str, Any], signature: str
    ) -> bool:
        if not isinstance(signature, str) or not HEX64_RE.fullmatch(signature):
            return False
        response = self._request({
            "verb": "verify-object",
            "purpose": purpose,
            "payload": value,
            "signature": signature,
        })
        return response.get("valid") is True


def parse_scalars(text: str) -> dict[str, str]:
    """Parse top-level ``key: value`` scalars from the tiny config format.

    Full-line comments and blank lines are skipped; indented lines belong to
    nested blocks (the broker daemon parses those itself) and are ignored
    here.  This is deliberately not a YAML engine: the config grammar is
    fixed and anything outside it simply does not bind.
    """
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1] in (" ", "\t"):
            continue
        match = re.match(r"^([a-z_]+):\s*(.*?)\s*$", line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def config_path_for(store_root: Path) -> Path:
    return Path(store_root).parent.parent / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def load_signing_config(
    store_root: Path, error_cls: type[Exception] = SigningError
) -> dict[str, str] | None:
    """Load the signing config; ``None`` means absent → local mode.

    A config that is PRESENT but unreadable fails closed: broker intent
    cannot be ruled out, and guessing local on an anomaly would be the
    downgrade path.
    """
    path = config_path_for(store_root)
    try:
        if not path.is_file():
            return None
    except OSError:
        return None
    if path.is_symlink():
        raise error_cls(
            "signing_config_invalid",
            "The evidence signing configuration must not be a symbolic link.",
        )
    try:
        raw = path.read_bytes()[: MAX_CONFIG_BYTES + 1]
    except OSError as exc:
        raise error_cls(
            "signing_config_unreadable",
            "The evidence signing configuration exists but cannot be read.",
        ) from exc
    if len(raw) > MAX_CONFIG_BYTES:
        raise error_cls(
            "signing_config_invalid",
            "The evidence signing configuration is oversized.",
        )
    return parse_scalars(raw.decode("utf-8", errors="replace"))


def resolve_signer(
    store_root: Path,
    key_loader: Callable[[], bytes],
    error_cls: type[Exception] = SigningError,
) -> LocalKeySigner | BrokerSigner:
    """Resolve the store's signer.  Absent/non-broker config = local mode.

    ``key_loader`` is invoked ONLY in local mode, so broker mode can never
    mint or read a local key (the split-brain guard: the recorder's
    load-or-create branch is unreachable when a broker holds custody).
    """
    config = load_signing_config(store_root, error_cls)
    if not config or config.get("mode") != "broker":
        # Includes the absent-file default and any config that does not
        # declare broker intent: behavior stays byte-identical to the
        # pre-seam recorder.  (A same-user writer creating a junk config
        # pre-ceremony buys denial or a broker redirect, never a quiet
        # capability gain — see the module docstring.)
        return LocalKeySigner(key_loader(), error_cls)
    socket_path = os.path.expanduser(config.get("socket") or "")
    if not socket_path:
        raise error_cls(
            "signing_config_invalid",
            "The evidence signing configuration declares broker mode "
            "without a socket path; signing is refused (fail-closed).",
        )
    return BrokerSigner(socket_path, error_cls, identity=config.get("identity"))
