#!/usr/bin/env python3
"""Fixed-policy Unix-socket append broker for officer observations.

Officer sessions are sandboxed away from the Captain-law triplet.  They may
still submit observations, but this unsandboxed broker owns the actual append:
the target is a three-value enum, identity comes from broker startup (never the
request), Captain-format headings are rejected, and every append is stamped
``[trust:officer]``.  Thus an officer can persist an observation but cannot
persist text that is structurally represented as Captain-ratified law.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import hmac
import json
import os
import re
import signal
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path


TARGETS = {
    "captain-patterns": "captain-patterns.md",
    "captain-intents": "captain-intents.md",
    "captain-decisions": "captain-decisions.md",
}
MAX_REQUEST = 64 * 1024
HEADING_RE = re.compile(r"^#{1,2}[ \t]", re.MULTILINE)
OFFICER_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class Refusal(ValueError):
    pass


def _ledger_path(root: Path, target: str) -> Path:
    try:
        name = TARGETS[target]
    except KeyError as exc:
        raise Refusal("unknown target") from exc
    base = (root / "shared" / "interfaces").resolve(strict=True)
    candidate = base / name
    # Do not resolve candidate: O_NOFOLLOW below must observe and reject a
    # symlink rather than silently following it.
    if candidate.parent != base:
        raise Refusal("target escaped interface directory")
    return candidate


def _queue_memory(root: Path, path: Path, officer: str) -> None:
    """Best-effort async ingestion, preserving the old append-interface path."""

    memory = root / "cabinet/scripts/lib/memory.sh"
    hook = root / "cabinet/scripts/hooks/post-file-write-memory.sh"
    if not (memory.is_file() and hook.is_file()):
        return
    script = r'''
      source "$CAPLAW_MEMORY_LIB" 2>/dev/null || exit 0
      POST_FILE_WRITE_MEMORY_LIB=1 source "$CAPLAW_MEMORY_HOOK" 2>/dev/null || exit 0
      declare -f pfwm_queue_watched_file >/dev/null 2>&1 || exit 0
      pfwm_queue_watched_file "$CAPLAW_TARGET" "$CAPLAW_OFFICER" || true
    '''
    env = {
        **os.environ,
        "CABINET_ROOT": str(root),
        "CAPLAW_MEMORY_LIB": str(memory),
        "CAPLAW_MEMORY_HOOK": str(hook),
        "CAPLAW_TARGET": str(path),
        "CAPLAW_OFFICER": officer,
    }
    try:
        subprocess.Popen(
            ["/bin/bash", "-c", script],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
            env=env,
        )
    except OSError:
        pass


def append_observation(root: Path, target: str, content: str, officer: str) -> dict:
    if not OFFICER_RE.fullmatch(officer):
        raise Refusal("invalid broker officer identity")
    if not content.strip():
        raise Refusal("empty entry")
    if len(content.encode("utf-8")) > MAX_REQUEST // 2:
        raise Refusal("entry too large")
    if HEADING_RE.search(content):
        raise Refusal("Captain-format '# ' or '## ' heading is not allowed")

    path = _ledger_path(root, target)
    flags = os.O_WRONLY | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise Refusal(f"ledger open refused: {exc}") from exc
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode):
            raise Refusal("ledger is not a regular file")
        fcntl.flock(fd, fcntl.LOCK_EX)
        before = meta.st_size
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        body = (
            f"\n### officer-note — appended by {officer} @ {stamp} "
            f"[trust:officer]\n\n{content}\n"
        ).encode("utf-8")
        view = memoryview(body)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
        after = os.fstat(fd)
        if after.st_ino != meta.st_ino or after.st_dev != meta.st_dev:
            raise Refusal("ledger identity changed during append")
        response = {
            "ok": True,
            "target": target,
            "officer": officer,
            "bytes": after.st_size - before,
            "entry_sha256": hashlib.sha256(body).hexdigest(),
        }
    finally:
        os.close(fd)
    _queue_memory(root, path, officer)
    return response


def _read_request(conn: socket.socket) -> dict:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = conn.recv(min(8192, MAX_REQUEST + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > MAX_REQUEST:
            raise Refusal("request too large")
        if b"\n" in chunk:
            break
    raw = b"".join(chunks).split(b"\n", 1)[0]
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Refusal("invalid JSON request") from exc
    if not isinstance(value, dict):
        raise Refusal("request must be an object")
    return value


def serve(
    socket_path: Path, root: Path, officer: str, idle_timeout: int, capability: str
) -> int:
    if not OFFICER_RE.fullmatch(officer):
        print("captain-law-broker: invalid officer", file=sys.stderr)
        return 2
    if len(capability) < 32:
        print("captain-law-broker: missing/weak capability", file=sys.stderr)
        return 2
    socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
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
    server.listen(8)
    # Short poll keeps SIGTERM/restart responsive; idle_timeout governs total
    # lifetime, not accept() latency.
    server.settimeout(1)
    last_request = time.monotonic()
    stopping = False

    def _stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
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
                try:
                    request = _read_request(conn)
                    supplied = str(request.get("capability", ""))
                    if not hmac.compare_digest(supplied, capability):
                        raise Refusal("invalid broker capability")
                    response = append_observation(
                        root,
                        str(request.get("target", "")),
                        str(request.get("content", "")),
                        officer,
                    )
                except (Refusal, OSError) as exc:
                    response = {"ok": False, "error": str(exc)}
                conn.sendall(json.dumps(response, separators=(",", ":")).encode() + b"\n")
    finally:
        server.close()
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass
    return 0


def client(socket_path: Path, target: str, content: str) -> int:
    capability = os.environ.get("CABINET_CAPTAIN_LAW_CAPABILITY", "")
    if len(capability) < 32:
        print("REFUSED: Captain-law broker capability is missing", file=sys.stderr)
        return 1
    request = json.dumps(
        {"target": target, "content": content, "capability": capability}
    ).encode() + b"\n"
    if len(request) > MAX_REQUEST:
        print("REFUSED: entry too large", file=sys.stderr)
        return 1
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(5)
    try:
        conn.connect(str(socket_path))
        conn.sendall(request)
        response = _read_request(conn)
    except OSError as exc:
        print(f"REFUSED: Captain-law broker unavailable: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    if not response.get("ok"):
        print(f"REFUSED: {response.get('error', 'broker rejected request')}", file=sys.stderr)
        return 1
    print(
        f"APPENDED: {target} +{response['bytes']} bytes by {response['officer']} "
        f"[trust:officer] (broker sha256 {response['entry_sha256']})"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    server_p = sub.add_parser("serve")
    server_p.add_argument("--socket", type=Path, required=True)
    server_p.add_argument("--root", type=Path, required=True)
    server_p.add_argument("--officer", required=True)
    server_p.add_argument("--idle-timeout", type=int, default=86400)
    client_p = sub.add_parser("client")
    client_p.add_argument("--socket", type=Path, required=True)
    client_p.add_argument("--target", choices=sorted(TARGETS), required=True)
    args = parser.parse_args()
    if args.command == "serve":
        capability = os.environ.pop("CABINET_LAW_BROKER_CAPABILITY", "")
        return serve(
            args.socket, args.root.resolve(), args.officer, args.idle_timeout, capability
        )
    return client(args.socket, args.target, sys.stdin.read())


if __name__ == "__main__":
    raise SystemExit(main())
