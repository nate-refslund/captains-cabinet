#!/usr/bin/env python3.12
"""stub_dashboard.py — the health-contract stand-in for the drill's update leg.

The update path's gate is not "did something answer on the port".  It is: the
process answering is MINE, it is the build I just applied, and it started AFTER
I applied it.  An identity-only probe passes an old process that survived a
failed restart, which is the one failure a rollback exists for.

So the gate needs a server whose answer carries a BUILD-TIME stamp and a start
time, and the drill needs to be able to leave a stale process running on
purpose.  A real Next build cannot be staged inside a bounded, node-free drill,
and building one would be measuring npm rather than the update path.  This is
the smallest thing that answers the same contract:

  GET /api/health -> {"ok": true, "service": <marker>, "source_commit": <baked>,
                      "started_at": <iso>, "ts": <iso>}

``source_commit`` is read from --stamp-file ONCE, at start — baked, exactly as
``npm run build`` bakes it.  Writing the stamp file therefore changes nothing
until something restarts the server, which is what makes the gate-red leg
honest: the drill runs an apply whose restart command is a no-op, the old
process keeps answering with the old stamp and the old start time, the gate
must go red, and the rollback must put the tree back.

  serve    --port N --stamp-file F --state-file S [--service NAME]
  restart  --port N --stamp-file F --state-file S [--service NAME]
  stop     --state-file S

Foreground-free by construction: ``serve`` is the child, ``restart``/``stop``
own the lifecycle, and the state file holds the pid so a trap can always reach
it.  Python 3.9 clean, stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HEALTH_PATH = "/api/health"


def _iso(ts: float) -> str:
    """Microsecond resolution on purpose: the gate compares started_at against
    the moment the apply began, and a whole-second stamp makes a process that
    restarted inside the same second indistinguishable from one that never did.
    """
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _make_handler(body: dict):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (stdlib contract)
            if self.path.split("?")[0] != HEALTH_PATH:
                self.send_response(404)
                self.end_headers()
                return
            payload = dict(body)
            payload["ts"] = _iso(time.time())
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, fmt, *a):  # keep the drill's output readable
            return

    return Handler


def cmd_serve(args) -> int:
    stamp = ""
    stamp_file = Path(args.stamp_file)
    if stamp_file.is_file():
        stamp = stamp_file.read_text(encoding="utf-8").strip()
    body = {"ok": True, "service": args.service, "source_commit": stamp,
            "started_at": _iso(time.time())}
    server = HTTPServer(("127.0.0.1", args.port), _make_handler(body))
    if args.state_file:
        Path(args.state_file).write_text(
            json.dumps({"pid": os.getpid(), "port": args.port,
                        "source_commit": stamp, "started_at": body["started_at"]}) + "\n",
            encoding="utf-8")
    server.serve_forever()
    return 0


def _stop(state_file: str) -> None:
    path = Path(state_file)
    if not path.is_file():
        return
    try:
        pid = int(json.loads(path.read_text(encoding="utf-8"))["pid"])
    except Exception:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(0.1)
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def cmd_stop(args) -> int:
    _stop(args.state_file)
    return 0


def cmd_restart(args) -> int:
    """Stop whatever is answering, start a fresh process, and prove it answers.

    The state file is REMOVED before the spawn and the wait is on a real HTTP
    answer carrying the current stamp — not on the file reappearing. A restart
    that returned success because the PREVIOUS run's state file was still on
    disk is the same defect the health gate exists to catch, one layer down.
    """
    _stop(args.state_file)
    state = Path(args.state_file)
    try:
        state.unlink()
    except OSError:
        pass
    want = ""
    stamp_file = Path(args.stamp_file)
    if stamp_file.is_file():
        want = stamp_file.read_text(encoding="utf-8").strip()
    log = state.with_suffix(".log")
    with open(log, "ab") as fh:
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "serve",
             "--port", str(args.port), "--stamp-file", args.stamp_file,
             "--state-file", args.state_file, "--service", args.service],
            stdout=fh, stderr=fh, start_new_session=True)
    deadline = time.time() + 20
    last = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d%s" % (args.port, HEALTH_PATH), timeout=2) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if body.get("service") == args.service and body.get("source_commit") == want:
                return 0
            last = "answered with %r" % (body,)
        except Exception as exc:
            last = repr(exc)
        time.sleep(0.2)
    sys.stderr.write("stub_dashboard: restart did not answer with stamp %r within 20s (%s)\n"
                     % (want, last))
    return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="health-contract stand-in for the drill")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("serve", "restart"):
        s = sub.add_parser(name)
        s.add_argument("--port", type=int, required=True)
        s.add_argument("--stamp-file", required=True)
        s.add_argument("--state-file", required=True)
        s.add_argument("--service", required=True,
                       help="the identity marker the health body must carry")
    s = sub.add_parser("stop")
    s.add_argument("--state-file", required=True)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "serve":
        return cmd_serve(args)
    if args.cmd == "restart":
        return cmd_restart(args)
    return cmd_stop(args)


if __name__ == "__main__":
    sys.exit(main())
