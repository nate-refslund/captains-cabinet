"""The dashboard is identified, not merely reached (identity-probe area, 2026-08-25).

THE MEASURED FAILURE. On the Captain's Mac an unrelated local Next.js dev
server was listening on 3100. Every probe in the tree asked
``curl -fsS .../api/health`` and read ANY 200 as "the cabinet is up": the
foreign app answered 200 with HTML, so every sensor said green while the real
dashboard was down and nothing was restarting it. The health route has carried
``service: 'cabinet-dashboard'`` since the day it was written — the sensors
just never read it.

So these tests are about the difference between "a socket answered" and "MY
service answered", and they use REAL sockets and REAL curl for that half: a
stub HTTP server that returns the identity JSON, a stub that returns a foreign
200 with HTML, and a closed port. A shimmed curl could not have caught the
original bug, because the original bug was in what curl was ASKED.

The flow half (open-cabinet.sh) does shim curl — deliberately: those arms are
about which branch runs and what gets written, and they must never start a
dashboard, open a browser or wait ten minutes.

Run: python3.12 -m pytest cabinet/scripts/tests/test_dashboard_identity_probe.py -q
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent
_LIB = _SCRIPTS / "lib" / "dashboard.sh"
_OPEN = _SCRIPTS / "open-cabinet.sh"
_TIMEOUT = 60


# ---------------------------------------------------------------------------
# real servers on real ports
# ---------------------------------------------------------------------------


class _Identity(BaseHTTPRequestHandler):
    """What the cabinet dashboard actually returns. Compact separators on
    purpose — that is what Next's Response.json emits, so this stub is the
    real shape and not a friendlier one."""

    def do_GET(self):  # noqa: N802 (http.server API)
        body = json.dumps(
            {"ok": True, "service": "cabinet-dashboard", "ts": "2026-08-25T00:00:00Z"},
            separators=(",", ":"),
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_a):  # silence
        pass


class _Foreign(BaseHTTPRequestHandler):
    """Somebody else's dev server: a cheerful 200 that means nothing to us."""

    def do_GET(self):  # noqa: N802
        body = b"<!DOCTYPE html><html><body>my other app</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_a):
        pass


class _Missing(BaseHTTPRequestHandler):
    """A listener that has the port but no such route — still occupied."""

    def do_GET(self):  # noqa: N802
        self.send_error(404)

    def log_message(self, *_a):
        pass


def _serve(handler):
    srv = HTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, srv.server_address[1]


def _closed_port() -> int:
    """A port nothing is listening on (bound, read, released)."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _state(port: int) -> str:
    res = subprocess.run(
        ["bash", "-c", f'. "{_LIB}"; cabinet_dash_state "http://127.0.0.1:{port}/"'],
        capture_output=True, text=True, timeout=_TIMEOUT,
    )
    return res.stdout.strip()


# ---------------------------------------------------------------------------
# 1) the three states, over real sockets
# ---------------------------------------------------------------------------


def test_my_dashboard_reads_as_mine():
    srv, port = _serve(_Identity)
    try:
        assert _state(port) == "mine"
    finally:
        srv.shutdown()


class _PrettyIdentity(BaseHTTPRequestHandler):
    """The same facts, pretty-printed. The marker is a fact about the JSON,
    not about how a serializer spaced it — a probe that a formatter change can
    blind is a probe waiting to lie."""

    def do_GET(self):  # noqa: N802
        body = json.dumps(
            {"ok": True, "service": "cabinet-dashboard", "ts": "2026-08-25T00:00:00Z"},
            indent=2,
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_a):
        pass


def test_whitespace_in_the_body_cannot_blind_the_probe():
    srv, port = _serve(_PrettyIdentity)
    try:
        assert _state(port) == "mine"
    finally:
        srv.shutdown()


def test_a_foreign_two_hundred_is_not_my_dashboard():
    # THE BUG, as a test: this server answers 200 on /api/health. A bare-200
    # probe called this "up". It is not up; it is not even mine.
    srv, port = _serve(_Foreign)
    try:
        assert _state(port) == "other"
    finally:
        srv.shutdown()


def test_a_listener_without_the_route_is_still_occupied():
    # 404 means someone HAS the port. `curl -f` collapsed this into the same
    # silence as nothing-listening, which is how a port conflict turned into a
    # start attempt that could only fail.
    srv, port = _serve(_Missing)
    try:
        assert _state(port) == "other"
    finally:
        srv.shutdown()


def test_nothing_listening_reads_as_down():
    assert _state(_closed_port()) == "down"


def test_port_free_agrees_with_the_state():
    srv, port = _serve(_Identity)
    try:
        res = subprocess.run(
            ["bash", "-c", f'. "{_LIB}"; cabinet_dash_port_free {port} && echo FREE || echo TAKEN'],
            capture_output=True, text=True, timeout=_TIMEOUT,
        )
        assert res.stdout.strip() == "TAKEN"
    finally:
        srv.shutdown()
    closed = _closed_port()
    res = subprocess.run(
        ["bash", "-c", f'. "{_LIB}"; cabinet_dash_port_free {closed} && echo FREE || echo TAKEN'],
        capture_output=True, text=True, timeout=_TIMEOUT,
    )
    assert res.stdout.strip() == "FREE"


def test_the_marker_is_the_route_s_own_field():
    """The probe and the endpoint must name the same string, or the sensor is
    pointed at nothing. Read both, compare."""
    route = (_SCRIPTS.parent / "dashboard" / "src" / "app" / "api" / "health" / "route.ts").read_text()
    assert "service: 'cabinet-dashboard'" in route, (
        "the health route lost its identity field — every probe in the tree matches it"
    )
    lib = _LIB.read_text()
    assert 'CABINET_DASH_SERVICE="cabinet-dashboard"' in lib


# ---------------------------------------------------------------------------
# 2) the port is single-source
# ---------------------------------------------------------------------------


def _root_with_env(tmp_path: Path, env_body: str) -> Path:
    root = tmp_path / "cab"
    (root / "cabinet").mkdir(parents=True)
    (root / "cabinet" / ".env").write_text(env_body)
    return root


def _port_for(root: Path, env: dict | None = None) -> str:
    res = subprocess.run(
        ["bash", "-c", f'. "{_LIB}"; cabinet_dash_port "{root}"'],
        capture_output=True, text=True, timeout=_TIMEOUT,
        env={**{k: v for k, v in os.environ.items() if k != "CABINET_DASHBOARD_PORT"},
             **(env or {})},
    )
    return res.stdout.strip()


def test_port_comes_from_the_env_file(tmp_path: Path):
    root = _root_with_env(tmp_path, "DASHBOARD_PASSWORD=x\nCABINET_DASHBOARD_PORT=3141\n")
    assert _port_for(root) == "3141"


def test_port_falls_back_to_the_default_when_unrecorded(tmp_path: Path):
    root = _root_with_env(tmp_path, "DASHBOARD_PASSWORD=x\n")
    assert _port_for(root) == "3100"


def test_the_last_recorded_port_wins(tmp_path: Path):
    # Append-only means a moved port is a LATER line, and both readers (this
    # one and `set -a; . .env`) must agree that the later line wins.
    root = _root_with_env(tmp_path, "CABINET_DASHBOARD_PORT=3100\nX=1\nCABINET_DASHBOARD_PORT=3101\n")
    assert _port_for(root) == "3101"
    shell = subprocess.run(
        ["bash", "-c", f'set -a; . "{root}/cabinet/.env"; set +a; echo "$CABINET_DASHBOARD_PORT"'],
        capture_output=True, text=True, timeout=_TIMEOUT,
    )
    assert shell.stdout.strip() == "3101", "the shell sourcing must agree with the sed reader"


def test_explicit_env_beats_the_file(tmp_path: Path):
    root = _root_with_env(tmp_path, "CABINET_DASHBOARD_PORT=3141\n")
    assert _port_for(root, env={"CABINET_DASHBOARD_PORT": "3199"}) == "3199"


@pytest.mark.parametrize("line", [
    'CABINET_DASHBOARD_PORT=\n',
    'CABINET_DASHBOARD_PORT=not-a-port\n',
    'CABINET_DASHBOARD_PORT=999999999\n',
])
def test_a_mangled_value_falls_back_rather_than_producing_a_junk_url(tmp_path: Path, line: str):
    # The degenerate end: whatever is in the file, what comes out is a usable
    # port. A probe that builds a junk URL reports "down" forever.
    root = _root_with_env(tmp_path, line)
    port = _port_for(root)
    assert port.isdigit() and 1 <= int(port) <= 65535, port


def test_recording_a_port_only_ever_appends(tmp_path: Path):
    original = "DASHBOARD_PASSWORD=hunter2\nTELEGRAM_COS_TOKEN=abc\nCABINET_DASHBOARD_PORT=3100\n"
    root = _root_with_env(tmp_path, original)
    env_file = root / "cabinet" / ".env"
    before = env_file.read_bytes()
    res = subprocess.run(
        ["bash", "-c", f'. "{_LIB}"; cabinet_dash_record_port "{root}" 3101 "because"'],
        capture_output=True, text=True, timeout=_TIMEOUT,
    )
    assert res.returncode == 0, res.stderr
    after = env_file.read_bytes()
    # every original byte survives, in place, at the front
    assert after.startswith(before), "the .env was rewritten, not appended to"
    assert b"CABINET_DASHBOARD_PORT=3101" in after
    assert b"because" in after
    assert _port_for(root) == "3101"
    # secrets are still there and the file is still private
    assert b"hunter2" in after
    assert oct(env_file.stat().st_mode)[-3:] == "600"


def test_recording_refuses_a_value_that_is_not_a_port(tmp_path: Path):
    root = _root_with_env(tmp_path, "CABINET_DASHBOARD_PORT=3100\n")
    before = (root / "cabinet" / ".env").read_bytes()
    res = subprocess.run(
        ["bash", "-c", f'. "{_LIB}"; cabinet_dash_record_port "{root}" "3101; rm -rf /"'],
        capture_output=True, text=True, timeout=_TIMEOUT,
    )
    assert res.returncode != 0
    assert (root / "cabinet" / ".env").read_bytes() == before


# ---------------------------------------------------------------------------
# 3) open-cabinet.sh — which branch runs, and what it writes
# ---------------------------------------------------------------------------


def _fake_cabinet(tmp_path: Path, env_body: str) -> Path:
    root = tmp_path / "cab"
    (root / "cabinet" / "scripts" / "lib").mkdir(parents=True)
    (root / "cabinet" / ".env").write_text(env_body)
    for name in ("open-cabinet.sh",):
        (root / "cabinet" / "scripts" / name).write_text(_OPEN.read_text())
        (root / "cabinet" / "scripts" / name).chmod(0o755)
    (root / "cabinet" / "scripts" / "lib" / "dashboard.sh").write_text(_LIB.read_text())
    (root / "cabinet" / "scripts" / "start-dashboard.sh").write_text("#!/bin/bash\nexit 0\n")
    (root / "cabinet" / "scripts" / "start-dashboard.sh").chmod(0o755)
    return root


def _curl_shim(shim_dir: Path, script: str) -> None:
    """A curl that answers from a scripted table keyed by call number.

    `script` is bash: it sees $n (1-based call number) and the argv, and must
    print a body and exit with a curl-shaped code (0 answered, 7 refused).
    """
    (shim_dir / "curl").write_text(
        "#!/bin/bash\n"
        f'echo "$@" >> "{shim_dir}/curl.log"\n'
        f'n=$(cat "{shim_dir}/curl.n" 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > "{shim_dir}/curl.n"\n'
        + script + "\n"
    )
    (shim_dir / "curl").chmod(0o755)


def _shim(shim_dir: Path, name: str, rc: int = 0) -> None:
    (shim_dir / name).write_text(
        "#!/bin/bash\n"
        f'echo "$@" >> "{shim_dir}/{name}.log"\n'
        f"exit {rc}\n"
    )
    (shim_dir / name).chmod(0o755)


def _log(shim_dir: Path, name: str) -> list[str]:
    p = shim_dir / f"{name}.log"
    return p.read_text().splitlines() if p.is_file() else []


def _run_open(root: Path, tmp_path: Path, curl_script: str, tries: str = "1"):
    shim_dir = tmp_path / "shims"
    shim_dir.mkdir(exist_ok=True)
    _curl_shim(shim_dir, curl_script)
    _shim(shim_dir, "open")
    _shim(shim_dir, "nohup")
    _shim(shim_dir, "sleep")
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return subprocess.run(
        ["/bin/bash", str(root / "cabinet" / "scripts" / "open-cabinet.sh")],
        capture_output=True, text=True, timeout=_TIMEOUT,
        env={"HOME": str(home), "PATH": f"{shim_dir}:/usr/bin:/bin",
             "CABINET_OPEN_TRIES": tries},
    ), shim_dir


_MINE = 'echo \'{"ok":true,"service":"cabinet-dashboard"}\'; exit 0'
_FOREIGN = 'echo "<html>not yours</html>"; exit 0'
_REFUSED = "exit 7"


def test_already_running_just_opens_the_browser(tmp_path: Path):
    root = _fake_cabinet(tmp_path, "CABINET_DASHBOARD_PORT=3141\n")
    p, shims = _run_open(root, tmp_path, _MINE)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "already running at http://127.0.0.1:3141/" in p.stdout
    assert _log(shims, "open") == ["http://127.0.0.1:3141/"]
    assert _log(shims, "nohup") == [], "nothing should be started when it is already up"


def test_down_starts_it_on_the_recorded_port(tmp_path: Path):
    root = _fake_cabinet(tmp_path, "CABINET_DASHBOARD_PORT=3141\n")
    # first probe refused, then it comes up
    p, shims = _run_open(root, tmp_path,
                         f'if [ "$n" -le 1 ]; then {_REFUSED}; else {_MINE}; fi', tries="5")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "isn't running" in p.stdout
    started = _log(shims, "nohup")
    assert len(started) == 1 and "start-dashboard.sh" in started[0]
    assert _log(shims, "open") == ["http://127.0.0.1:3141/"]
    # the recorded port was not changed: nothing was in the way
    assert (root / "cabinet" / ".env").read_text() == "CABINET_DASHBOARD_PORT=3141\n"


def test_a_foreign_app_on_the_door_moves_the_cabinet_and_says_so(tmp_path: Path):
    original = "DASHBOARD_PASSWORD=hunter2\nCABINET_DASHBOARD_PORT=3100\n"
    root = _fake_cabinet(tmp_path, original)
    # call 1: the recorded door, held by someone else. call 2: 3100 again while
    # picking (still theirs). call 3: 3101 is free. then it comes up.
    script = (
        f'if [ "$n" -le 2 ]; then {_FOREIGN}; '
        f'elif [ "$n" -eq 3 ]; then {_REFUSED}; '
        f'else {_MINE}; fi'
    )
    p, shims = _run_open(root, tmp_path, script, tries="5")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "in use by another app" in p.stdout
    assert "Nothing of theirs was stopped or changed." in p.stdout
    assert "now answers at http://127.0.0.1:3101/" in p.stdout
    assert _log(shims, "open") == ["http://127.0.0.1:3101/"]
    # written down, append-only, secrets intact
    after = (root / "cabinet" / ".env").read_text()
    assert after.startswith(original)
    assert "CABINET_DASHBOARD_PORT=3101" in after
    assert "hunter2" in after
    # and it was started on the NEW port, never on theirs
    started = _log(shims, "nohup")
    assert len(started) == 1 and "start-dashboard.sh" in started[0]


def test_it_never_answers_and_says_where_to_look(tmp_path: Path):
    root = _fake_cabinet(tmp_path, "CABINET_DASHBOARD_PORT=3141\n")
    p, shims = _run_open(root, tmp_path, _REFUSED, tries="1")
    assert p.returncode == 1
    assert "taking longer than expected" in p.stdout
    assert "hatch-logs" in p.stdout, "a failure must name the log it wrote"
    assert _log(shims, "open") == [], "never open a browser on a door nothing answers"


def test_every_exit_says_something(tmp_path: Path):
    """The property this whole area exists for: no branch ends in silence."""
    root = _fake_cabinet(tmp_path, "CABINET_DASHBOARD_PORT=3141\n")
    for name, script, tries in (
        ("mine", _MINE, "1"),
        ("down-then-up", f'if [ "$n" -le 1 ]; then {_REFUSED}; else {_MINE}; fi', "5"),
        ("never-answers", _REFUSED, "1"),
        ("foreign", _FOREIGN, "1"),
    ):
        p, _ = _run_open(root, tmp_path, script, tries=tries)
        last = [ln for ln in p.stdout.splitlines() if ln.strip()]
        assert last, f"{name}: the run printed nothing at all"
        assert len(" ".join(last)) > 20, f"{name}: {last}"


def test_no_branch_stops_or_kills_anything():
    text = _OPEN.read_text()
    code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    for banned in ("kill ", "pkill", "launchctl", "lsof -ti", "kill-switch"):
        assert banned not in code, f"open-cabinet.sh must never {banned!r}"


# ---------------------------------------------------------------------------
# 4) the bash reader and the python reader must agree
# ---------------------------------------------------------------------------
#
# There are two implementations of "which port does this Cabinet answer on":
# cabinet_dash_port in the bash lib, and _dashboard_url_from_env_file in the
# Telegram poller (which builds the links the operator taps). Two copies of one
# rule drift; these arms are what keeps them honest.


def _python_port(root: Path, env: dict | None = None) -> str:
    src = (_SCRIPTS / "officer-inbound-poller.py").read_text()
    start = src.index("def _dashboard_url_from_env_file")
    end = src.index("\ndef ", start + 10)
    code = "import os\n" + src[start:end]
    prog = (
        code
        + "\nimport json,sys\nprint(_dashboard_url_from_env_file())\n"
    )
    e = {k: v for k, v in os.environ.items() if k != "CABINET_DASHBOARD_PORT"}
    e["CABINET_ROOT"] = str(root)
    e.update(env or {})
    res = subprocess.run(["python3.12", "-c", prog], capture_output=True, text=True,
                         timeout=_TIMEOUT, env=e)
    assert res.returncode == 0, res.stderr
    return res.stdout.strip().rsplit(":", 1)[1]


@pytest.mark.parametrize("body,expected", [
    ("CABINET_DASHBOARD_PORT=3141\n", "3141"),
    ("X=1\n", "3100"),
    ("CABINET_DASHBOARD_PORT=3100\nX=1\nCABINET_DASHBOARD_PORT=3101\n", "3101"),
    ("CABINET_DASHBOARD_PORT=not-a-port\n", "3100"),
    ("CABINET_DASHBOARD_PORT=999999999\n", "3100"),
])
def test_the_two_port_readers_agree(tmp_path: Path, body: str, expected: str):
    root = _root_with_env(tmp_path, body)
    assert _port_for(root) == expected, "the bash reader disagrees"
    assert _python_port(root) == expected, "the python reader disagrees"


def test_both_readers_let_an_explicit_env_win(tmp_path: Path):
    root = _root_with_env(tmp_path, "CABINET_DASHBOARD_PORT=3141\n")
    assert _port_for(root, env={"CABINET_DASHBOARD_PORT": "3199"}) == "3199"
    assert _python_port(root, env={"CABINET_DASHBOARD_PORT": "3199"}) == "3199"


def test_no_probe_or_opener_hardcodes_the_default_port():
    """A hardcoded 3100 in a probe is how a moved dashboard becomes invisible
    to its own tooling. The default belongs in the resolvers and nowhere else."""
    resolvers = {
        _SCRIPTS / "lib" / "dashboard.sh",          # the bash resolver
        _SCRIPTS / "start-dashboard.sh",            # the server's own default
        _SCRIPTS / "officer-inbound-poller.py",     # the python twin
    }
    offenders = []
    for src in sorted(_SCRIPTS.glob("*.sh")) + sorted(_SCRIPTS.glob("lib/*.sh")):
        if src in resolvers:
            continue
        for i, line in enumerate(src.read_text(errors="replace").splitlines(), 1):
            code = line.split("#", 1)[0]
            if "3100" in code and "pick_port" not in code and "3199" not in code:
                offenders.append(f"{src.name}:{i}: {line.strip()}")
    assert not offenders, (
        "a port literal outside the resolvers — derive it from "
        "cabinet_dash_port instead:\n" + "\n".join(offenders)
    )
