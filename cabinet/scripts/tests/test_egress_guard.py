"""Contract tests for the OPT-IN enforced egress allowlist
(cabinet/scripts/egress-guard.sh + cabinet/scripts/egress-proxy.py; config
framework/defaults/egress.yml + instance/config/egress.yml).

Hermetic by construction: every run points CABINET_ROOT at a pytest tmp tree
(so enable/disable/apply write config + state ONLY under tmp, never the real
repo) and CABINET_STATE_DIR at a tmp state dir. NO real external network is
touched — the only endpoints are localhost sinks and a `denied.test` host that
is refused pre-connect (never resolved). The guard is driven by absolute path;
CABINET_PYTHON is pinned to this interpreter so config resolution + the proxy
use the same (yaml-bearing) python.

Proves the four contract claims:
  * enforce=false  -> ALLOW ALL (a request to any host succeeds; nothing installed)
  * enforce=true   -> a non-allowlisted host is BLOCKED (403) and an allowlisted
                      one is PERMITTED (200), over both HTTP-forward and CONNECT
  * install failure + enforce=true -> FAIL CLOSED (non-zero, no proxy env)
  * product hosts resolved GENERICALLY from org_domains (no hardcoded host)
"""
from __future__ import annotations

import os
import plistlib
import re
import shutil
import site
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

yaml = pytest.importorskip("yaml")  # same dep the guard's config resolution uses

REPO = Path(__file__).resolve().parents[3]
GUARD = REPO / "cabinet" / "scripts" / "egress-guard.sh"
PROXY = REPO / "cabinet" / "scripts" / "egress-proxy.py"
OFFICER_ENV_PARSER = REPO / "cabinet" / "scripts" / "lib" / "officer-env.py"
FRAMEWORK_DEFAULT = REPO / "framework" / "defaults" / "egress.yml"
LAUNCHD_TEMPLATE = REPO / "cabinet" / "launchd" / "com.cabinet.egress-proxy.template.plist"


# --------------------------------------------------------------- helpers ----
def _run(args, root: Path, state: Path, extra_env=None):
    # Redirecting HOME hides user-site packages, but adding the complete
    # sys.path to PYTHONPATH is unsafe: it promotes the stdlib directory ahead
    # of the interpreter's bootstrap paths and can make even `import io` fail.
    # Carry only site-package locations so PyYAML remains available without
    # changing Python's standard-library resolution.
    site_paths = [*site.getsitepackages(), site.getusersitepackages()]
    env = {
        **os.environ,
        "CABINET_ROOT": str(root),
        "CABINET_STATE_DIR": str(state),
        "CABINET_PYTHON": sys.executable,   # yaml-bearing interpreter parity
        # HOME is intentionally redirected below, which would otherwise hide
        # this interpreter's user-site PyYAML on macOS system Python.
        "PYTHONPATH": os.pathsep.join(dict.fromkeys(path for path in site_paths if path)),
        "HOME": str(root),                  # keep any fallback under tmp
        # Unit tests own their subprocess lifetime directly. Production macOS
        # resolves auto -> launchd; pin child here so the hermetic suite never
        # registers or removes a real user LaunchAgent.
        "EGRESS_LAUNCH_MODE": "child",
        # Child attestation on Darwin checks that no launchd owner survives a
        # cross-mode transition. Keep that read hermetic too: the seeded stub
        # reports the canonical launchctl service-not-found status (113).
        "EGRESS_LAUNCHCTL": str(root / ".test-launchctl-absent"),
    }
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(GUARD), *args],
        env=env, capture_output=True, text=True, timeout=60,
    )


def _seed_root(tmp_path: Path, org_domains=None) -> Path:
    """A minimal cabinet root: the shipped framework default + an optional
    platform.yml exposing org_domains (the generic product-host source)."""
    root = tmp_path / "root"
    (root / "framework" / "defaults").mkdir(parents=True)
    (root / "instance" / "config").mkdir(parents=True)
    (root / "cabinet" / "launchd").mkdir(parents=True)
    shutil.copy(FRAMEWORK_DEFAULT, root / "framework" / "defaults" / "egress.yml")
    shutil.copy(LAUNCHD_TEMPLATE, root / "cabinet" / "launchd" / LAUNCHD_TEMPLATE.name)
    absent_launchctl = root / ".test-launchctl-absent"
    absent_launchctl.write_text("#!/bin/sh\nexit 113\n", encoding="utf-8")
    absent_launchctl.chmod(0o755)
    if org_domains is not None:
        (root / "instance" / "config" / "platform.yml").write_text(
            "org_domains:\n" + "".join("  - %s\n" % d for d in org_domains),
            encoding="utf-8",
        )
    return root


def _free_port() -> int:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def _write_instance(root: Path, text: str) -> None:
    (root / "instance" / "config" / "egress.yml").write_text(text, encoding="utf-8")


def _ready_port(state: Path) -> int:
    ready = state / "egress" / "proxy.ready"
    for _ in range(50):
        if ready.exists():
            txt = ready.read_text(encoding="utf-8").strip()
            if txt.startswith("READY"):
                return int(txt.split()[1])
        time.sleep(0.1)
    raise AssertionError("proxy never reported ready")


class _Sink(BaseHTTPRequestHandler):
    def do_GET(self):   # noqa: N802
        body = b"SINK-OK"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_GET

    def log_message(self, *a):  # noqa: N802
        return


@pytest.fixture()
def sink():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Sink)
    srv.daemon_threads = True
    t = Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield srv.server_address[1]
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture()
def stop_guard(tmp_path):
    """Ensure any proxy started during a test is torn down."""
    started = []
    yield started
    for root, state in started:
        _run(["stop"], root, state)


def _connect_status(proxy_port: int, target: str) -> str:
    """Send a raw CONNECT and return the status line (exercises do_CONNECT)."""
    s = socket.create_connection(("127.0.0.1", proxy_port), timeout=5)
    try:
        s.sendall(("CONNECT %s HTTP/1.1\r\nHost: %s\r\n\r\n" % (target, target)).encode())
        data = s.recv(4096).decode("latin1", "replace")
        return data.split("\r\n", 1)[0]
    finally:
        s.close()


def _http_via_proxy(proxy_port: int, url: str, headers=None):
    proxy = urllib.request.ProxyHandler({"http": "http://127.0.0.1:%d" % proxy_port})
    opener = urllib.request.build_opener(proxy)
    req = urllib.request.Request(url, headers=headers or {})
    return opener.open(req, timeout=5)


# ------------------------------------------------ 1. default = allow all ----
def test_default_is_allow_all(tmp_path, sink):
    """Shipped default (enforce=false, no instance override): apply installs
    NOTHING and a request to a host succeeds unproxied — i.e. allow all."""
    root = _seed_root(tmp_path)
    state = tmp_path / "state"

    proc = _run(["apply"], root, state)
    assert proc.returncode == 0, proc.stderr
    assert "allow all" in proc.stdout.lower()
    # nothing installed
    assert not (state / "egress" / "proxy.env").exists()
    assert not (state / "egress" / "proxy.pid").exists()

    # a direct request to any host succeeds (unrestricted egress) — modelled by
    # the localhost sink, the only endpoint we may touch in a contained test.
    r = urllib.request.urlopen("http://127.0.0.1:%d/" % sink, timeout=5)
    assert r.status == 200
    assert r.read() == b"SINK-OK"

    st = _run(["status"], root, state)
    assert "enforce:         false" in st.stdout
    assert "proxy:           STOPPED" in st.stdout


# --------------------------------- 2. generic product-host resolution -------
def test_product_hosts_resolved_generically_from_org_domains(tmp_path):
    """allow_product=true derives the captain's OWN hosts from org_domains in
    instance config — no captain/industry host is hardcoded in the framework."""
    root = _seed_root(tmp_path, org_domains=["example-product.test", "sub.brand.test"])
    state = tmp_path / "state"
    st = _run(["status"], root, state)
    assert st.returncode == 0, st.stderr
    # the floor control-plane hosts...
    assert "api.anthropic.com" in st.stdout
    assert "api.telegram.org" in st.stdout
    # ...plus the deployment's own domains, resolved generically
    assert "example-product.test" in st.stdout
    assert "sub.brand.test" in st.stdout
    assert "product_domains: example-product.test sub.brand.test" in st.stdout


# --------------------------------- 3. enforce blocks / permits --------------
def test_enforce_blocks_nonallowlisted_permits_allowlisted(tmp_path, sink, stop_guard):
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    stop_guard.append((root, state))
    # synthetic allowlist: localhost only (product off). The floor hosts
    # (anthropic/telegram) are unioned in by design but are irrelevant here.
    _write_instance(root, "enforce: true\nproxy_port: 0\nallow_product: false\n"
                          "allow_hosts:\n  - localhost\n")

    # The sink listens on an ephemeral port; permit it as a CONNECT target so
    # the CONNECT-permit leg below is exercised under the 443-only default.
    proc = _run(["apply"], root, state,
                extra_env={"EGRESS_CONNECT_PORTS": str(sink)})
    assert proc.returncode == 0, proc.stderr
    assert (state / "egress" / "proxy.env").exists(), "proxy env must be written on success"
    pport = _ready_port(state)

    # PERMIT (HTTP forward): allowlisted localhost -> 200 from the sink
    r = _http_via_proxy(pport, "http://localhost:%d/" % sink)
    assert r.status == 200
    assert r.read() == b"SINK-OK"

    # BLOCK (HTTP forward): non-allowlisted host -> 403, pre-connect
    with pytest.raises(urllib.error.HTTPError) as ei:
        _http_via_proxy(pport, "http://denied.test/")
    assert ei.value.code == 403

    # PERMIT (CONNECT tunnel): allowlisted host on an allowed port -> 200
    assert "200" in _connect_status(pport, "localhost:%d" % sink)
    # BLOCK (CONNECT tunnel): non-allowlisted host -> 403 (host check first)
    assert "403" in _connect_status(pport, "denied.test:80")


def test_generated_proxy_env_is_accepted_by_officer_parser(tmp_path, stop_guard):
    """Pin the egress-writer -> officer-launcher contract, not a copied fixture."""
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    stop_guard.append((root, state))
    _write_instance(
        root,
        "enforce: true\nproxy_port: 0\nallow_product: false\nallow_hosts: []\n",
    )
    scope = root / "cabinet" / "mcp-scope.yml"
    scope.write_text("agents:\n  cos:\n    mcps: []\nuniversal: []\n")

    applied = _run(["apply"], root, state)
    assert applied.returncode == 0, applied.stderr
    rendered = subprocess.run(
        [
            sys.executable,
            str(OFFICER_ENV_PARSER),
            str(state / "egress" / "proxy.env"),
            "--officer",
            "cos",
            "--scope-file",
            str(scope),
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )

    assert rendered.returncode == 0, rendered.stderr
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "NO_PROXY",
        "no_proxy",
    ):
        assert f"export {name}=" in rendered.stdout


def test_plain_http_rewrites_attacker_host_to_validated_authority(tmp_path, stop_guard):
    seen = []

    class HostSink(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            seen.append(self.headers.get("Host"))
            body = b"OK"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # noqa: N802
            return

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), HostSink)
    thread = Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    try:
        root = _seed_root(tmp_path)
        state = tmp_path / "state"
        stop_guard.append((root, state))
        _write_instance(root, "enforce: true\nproxy_port: 0\nallow_product: false\n"
                              "allow_hosts:\n  - localhost\n")
        applied = _run(["apply"], root, state)
        assert applied.returncode == 0, applied.stderr
        pport = _ready_port(state)
        port = upstream.server_address[1]
        response = _http_via_proxy(
            pport,
            f"http://localhost:{port}/",
            headers={"Host": "denied.test"},
        )
        assert response.status == 200
        assert seen == [f"localhost:{port}"]
    finally:
        upstream.shutdown()
        upstream.server_close()


def test_enforce_empty_allowlist_blocks_everything(tmp_path, sink, stop_guard):
    """An extreme but valid config (product off, only the floor) still refuses
    a non-floor host — deny-by-default holds."""
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    stop_guard.append((root, state))
    _write_instance(root, "enforce: true\nproxy_port: 0\nallow_product: false\n")
    proc = _run(["apply"], root, state)
    assert proc.returncode == 0, proc.stderr
    pport = _ready_port(state)
    with pytest.raises(urllib.error.HTTPError) as ei:
        _http_via_proxy(pport, "http://localhost:%d/" % sink)  # not on the floor
    assert ei.value.code == 403


def test_connect_restricted_to_https_port(tmp_path, sink, stop_guard):
    """EG-3: by default CONNECT tunnels ONLY to the HTTPS port (443). An
    allowlisted host must not become a generic TCP tunnel to another port —
    even a port that is actually listening (the sink's ephemeral port) or a
    classic exfil port (:22) is refused (403) pre-connect."""
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    stop_guard.append((root, state))
    _write_instance(root, "enforce: true\nproxy_port: 0\nallow_product: false\n"
                          "allow_hosts:\n  - localhost\n")
    # no EGRESS_CONNECT_PORTS override -> default {443}
    assert _run(["apply"], root, state).returncode == 0
    pport = _ready_port(state)
    # allowlisted host, non-443 port with a live listener -> still 403
    assert "403" in _connect_status(pport, "localhost:%d" % sink)
    # allowlisted host, the SSH port -> 403 (no tunnel to :22)
    assert "403" in _connect_status(pport, "localhost:22")


# --------------------------------- 4. fail-closed ---------------------------
def test_fail_closed_on_install_failure(tmp_path):
    """enforce=true but the proxy backend cannot come up -> guard errors
    non-zero and writes NO proxy env (never silently falls open)."""
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    _write_instance(root, "enforce: true\nproxy_port: 0\n")
    stub = tmp_path / "stub_fail.py"
    stub.write_text("import sys\nsys.exit(1)\n", encoding="utf-8")

    proc = _run(["apply"], root, state, extra_env={"EGRESS_PROXY_SCRIPT": str(stub)})
    assert proc.returncode != 0, "must fail closed, not fall open"
    assert "FAIL-CLOSED" in proc.stderr
    assert not (state / "egress" / "proxy.env").exists(), "egress must not be left open"


def test_fail_closed_missing_backend(tmp_path):
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    _write_instance(root, "enforce: true\nproxy_port: 0\n")
    proc = _run(["apply"], root, state,
                extra_env={"EGRESS_PROXY_SCRIPT": str(tmp_path / "does-not-exist.py")})
    assert proc.returncode != 0
    assert "FAIL-CLOSED" in proc.stderr
    assert not (state / "egress" / "proxy.env").exists()


def test_corrupt_config_fails_closed_leaves_enforcement_up(tmp_path, stop_guard):
    """EG-1: a corrupt (unparseable) instance/config/egress.yml while
    enforcement is running must NOT fall open. `apply` fails closed (non-zero,
    no 'allow all' success) and does NOT tear down the already-running proxy
    or its env — it never silently resolves to the enforce=false default."""
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    stop_guard.append((root, state))
    inst = root / "instance" / "config" / "egress.yml"
    env_file = state / "egress" / "proxy.env"

    # 1. enforce=true, proxy up and env written
    _write_instance(root, "enforce: true\nproxy_port: 0\nallow_product: false\n"
                          "allow_hosts:\n  - localhost\n")
    up = _run(["apply"], root, state)
    assert up.returncode == 0, up.stderr
    assert env_file.exists()
    _ready_port(state)  # confirm it actually came up
    pid = int((state / "egress" / "proxy.pid").read_text(encoding="utf-8").split()[0])

    # 2. corrupt the instance config (unparseable YAML that still says enforce: true)
    inst.write_text("enforce: true\nallow_hosts: [unterminated\n  ::: not yaml :::\n",
                    encoding="utf-8")
    try:
        # 3. apply must FAIL CLOSED — not succeed, not fall to allow-all,
        #    not tear down the running restriction.
        broke = _run(["apply"], root, state)
        assert broke.returncode != 0, "corrupt config while enforcing must not succeed"
        assert "allow all" not in broke.stdout.lower(), "must not report allow-all success"
        assert "FAIL-CLOSED" in broke.stderr
        assert env_file.exists(), "running enforcement must survive an unparseable config"
        os.kill(pid, 0)  # raises if the proxy was torn down; must still be alive
    finally:
        # A corrupt config also breaks `stop`/`disable` resolve; restore a valid
        # config so the proxy can be torn down (this doubles as recovery proof).
        _write_instance(root, "enforce: false\n")
        rec = _run(["apply"], root, state)
        assert rec.returncode == 0, rec.stderr
    assert not env_file.exists(), "valid disable after repair tears the proxy down"


# --------------------------------- 5. enable/disable round-trip -------------
def test_enable_disable_roundtrip(tmp_path, stop_guard):
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    stop_guard.append((root, state))
    inst = root / "instance" / "config" / "egress.yml"
    seeded_default = root / "framework" / "defaults" / "egress.yml"
    seed = seeded_default.read_text(encoding="utf-8")
    seed = re.sub(
        r"^proxy_port:.*$",
        f"proxy_port: {_free_port()}",
        seed,
        count=1,
        flags=re.MULTILINE,
    )
    seeded_default.write_text(seed, encoding="utf-8")
    assert not inst.exists(), "enable must exercise fresh-config materialization"

    en = _run(["enable"], root, state)
    assert en.returncode == 0, en.stderr
    assert "enforce: true" in inst.read_text(encoding="utf-8")
    assert (state / "egress" / "proxy.env").exists()

    dis = _run(["disable"], root, state)
    assert dis.returncode == 0, dis.stderr
    assert "enforce: false" in inst.read_text(encoding="utf-8")
    assert not (state / "egress" / "proxy.env").exists()  # torn down -> allow all
    # comments from the seed survive the flag flips (line-oriented edit)
    assert inst.read_text(encoding="utf-8").count("#") > 5


def test_apply_is_idempotent_and_runtime_state_is_machine_readable(tmp_path, stop_guard):
    """Repeated officer boots reconcile one shared proxy without flapping it."""
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    stop_guard.append((root, state))
    _write_instance(root, "enforce: true\nproxy_port: 0\nallow_product: false\n"
                          "allow_hosts:\n  - localhost\n")

    first = _run(["apply"], root, state)
    assert first.returncode == 0, first.stderr
    first_pid = int((state / "egress" / "proxy.pid").read_text().strip())
    first_port = _ready_port(state)
    ready_text = (state / "egress" / "proxy.ready").read_text().strip()
    assert ready_text == f"READY {first_port} PID {first_pid}"
    assert ((state / "egress" / "proxy.pid").stat().st_mode & 0o777) == 0o600
    assert ((state / "egress" / "proxy.ready").stat().st_mode & 0o777) == 0o600

    second = _run(["apply"], root, state)
    assert second.returncode == 0, second.stderr
    assert int((state / "egress" / "proxy.pid").read_text().strip()) == first_pid
    assert _ready_port(state) == first_port

    runtime = _run(["runtime-state"], root, state)
    assert runtime.returncode == 0, runtime.stderr
    assert runtime.stdout.strip() == "1\t%s" % (state / "egress" / "proxy.env")


def test_launchd_mode_rejects_dynamic_port_before_registration(tmp_path):
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    _write_instance(root, "enforce: true\nproxy_port: 0\nallow_product: false\n")
    proc = _run(
        ["apply"], root, state,
        extra_env={"EGRESS_LAUNCH_MODE": "launchd", "EGRESS_LAUNCHCTL": "/usr/bin/false"},
    )
    assert proc.returncode != 0
    assert "requires a fixed proxy_port" in proc.stderr
    assert not (state / "egress" / "proxy.env").exists()
    assert not (root / "Library" / "LaunchAgents" /
                "com.cabinet.egress-proxy.plist").exists()


def test_launchd_template_substitution_is_one_pass(tmp_path):
    root = _seed_root(tmp_path)
    state = tmp_path / "state-${LOG_FILE}-literal"
    port = _free_port()
    captured = tmp_path / "captured.plist"
    launchctl = tmp_path / "capture-launchctl.py"
    launchctl.write_text(
        """#!/usr/bin/env python3
import os
import shutil
import sys
if len(sys.argv) > 1 and sys.argv[1] == "print":
    raise SystemExit(113)
if len(sys.argv) > 3 and sys.argv[1] == "bootstrap":
    shutil.copyfile(sys.argv[3], os.environ["CAPTURED_PLIST"])
    raise SystemExit(1)
raise SystemExit(1)
""",
        encoding="utf-8",
    )
    launchctl.chmod(0o755)
    _write_instance(root, f"enforce: true\nproxy_port: {port}\nallow_product: false\n")
    proc = _run(
        ["apply"], root, state,
        extra_env={
            "EGRESS_LAUNCH_MODE": "launchd",
            "EGRESS_LAUNCHCTL": str(launchctl),
            "CAPTURED_PLIST": str(captured),
        },
    )
    assert proc.returncode != 0  # registration is intentionally refused
    assert captured.exists(), proc.stderr
    with captured.open("rb") as handle:
        job = plistlib.load(handle)
    args = job["ProgramArguments"]
    ready = args[args.index("--ready-file") + 1]
    assert ready == str(state / "egress" / "proxy.ready")
    assert "${LOG_FILE}" in ready, "replacement text was expanded a second time"


@pytest.mark.parametrize("ports", ["", "0", "65536", "443,garbage", "-1", "44.3"])
def test_guard_rejects_malformed_connect_port_contract(tmp_path, ports):
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    _write_instance(root, "enforce: false\n")
    proc = _run(["status"], root, state,
                extra_env={"EGRESS_CONNECT_PORTS": ports})
    assert proc.returncode != 0
    assert "invalid EGRESS_CONNECT_PORTS" in proc.stderr


def test_guard_canonicalizes_connect_ports_before_attestation(tmp_path, stop_guard):
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    stop_guard.append((root, state))
    _write_instance(root, "enforce: true\nproxy_port: 0\nallow_product: false\n")
    applied = _run(["apply"], root, state,
                   extra_env={"EGRESS_CONNECT_PORTS": "443 443, 8443"})
    assert applied.returncode == 0, applied.stderr
    assert _run(
        ["runtime-state"], root, state,
        extra_env={"EGRESS_CONNECT_PORTS": "443,8443"},
    ).returncode == 0


def test_fixed_port_ready_drift_fails_attestation(tmp_path, stop_guard):
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    stop_guard.append((root, state))
    port = _free_port()
    _write_instance(root, f"enforce: true\nproxy_port: {port}\nallow_product: false\n")
    applied = _run(["apply"], root, state)
    assert applied.returncode == 0, applied.stderr
    pid = int((state / "egress" / "proxy.pid").read_text().strip())
    drift = port + 1 if port < 65535 else port - 1
    (state / "egress" / "proxy.ready").write_text(
        f"READY {drift} PID {pid}\n", encoding="utf-8")
    attested = _run(["runtime-state"], root, state)
    assert attested.returncode != 0
    assert "does not match configured fixed port" in attested.stderr


def test_fixed_port_policy_change_replaces_owner_and_endpoint(tmp_path, stop_guard):
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    stop_guard.append((root, state))
    port_a = _free_port()
    port_b = _free_port()
    while port_b == port_a:
        port_b = _free_port()
    _write_instance(root, f"enforce: true\nproxy_port: {port_a}\nallow_product: false\n")
    first = _run(["apply"], root, state)
    assert first.returncode == 0, first.stderr
    first_pid = int((state / "egress" / "proxy.pid").read_text().strip())
    assert _ready_port(state) == port_a

    _write_instance(root, f"enforce: true\nproxy_port: {port_b}\nallow_product: false\n")
    drifted = _run(["runtime-state"], root, state)
    assert drifted.returncode != 0
    assert "does not match configured fixed port" in drifted.stderr

    replaced = _run(["apply"], root, state)
    assert replaced.returncode == 0, replaced.stderr
    second_pid = int((state / "egress" / "proxy.pid").read_text().strip())
    assert second_pid != first_pid
    assert _ready_port(state) == port_b
    for _ in range(50):
        try:
            os.kill(first_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail("old fixed-port proxy survived policy replacement")


def test_ready_marker_requires_exact_port_and_pid_format(tmp_path, stop_guard):
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    stop_guard.append((root, state))
    port = _free_port()
    _write_instance(root, f"enforce: true\nproxy_port: {port}\nallow_product: false\n")
    applied = _run(["apply"], root, state)
    assert applied.returncode == 0, applied.stderr
    pid = int((state / "egress" / "proxy.pid").read_text().strip())
    (state / "egress" / "proxy.ready").write_text(
        f"READY {port} PID {pid} trailing\n", encoding="utf-8")
    attested = _run(["runtime-state"], root, state)
    assert attested.returncode != 0
    assert "not live/ready" in attested.stderr


def test_status_fails_when_enforcement_is_requested_but_runtime_is_absent(tmp_path):
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    _write_instance(root, "enforce: true\nproxy_port: 8899\nallow_product: false\n")
    proc = _run(["status"], root, state)
    assert proc.returncode != 0
    assert "INVALID/STOPPED" in proc.stdout
    assert "FAIL-CLOSED" in proc.stderr


def test_launchd_stop_does_not_claim_absence_when_supervisor_query_fails(tmp_path):
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    _write_instance(root, "enforce: false\n")
    proc = _run(
        ["stop"], root, state,
        extra_env={"EGRESS_LAUNCH_MODE": "launchd", "EGRESS_LAUNCHCTL": "/usr/bin/false"},
    )
    assert proc.returncode != 0
    assert "state could not be queried" in proc.stderr
    assert "restriction state is not claimed" in proc.stderr


def test_launchd_stop_succeeds_when_service_is_canonically_absent(tmp_path):
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    _write_instance(root, "enforce: false\n")
    egress = state / "egress"
    egress.mkdir(parents=True)
    stale_pid = 999_999_999
    (egress / "proxy.pid").write_text(f"{stale_pid}\n", encoding="utf-8")
    (egress / "proxy.ready").write_text(
        f"READY 8899 PID {stale_pid}\n", encoding="utf-8")
    (egress / "proxy.env").write_text("stale\n", encoding="utf-8")
    installed = root / "Library" / "LaunchAgents" / "com.cabinet.egress-proxy.plist"
    installed.parent.mkdir(parents=True)
    installed.write_text("stale plist evidence\n", encoding="utf-8")

    proc = _run(
        ["stop"], root, state,
        extra_env={
            "EGRESS_LAUNCH_MODE": "launchd",
            "EGRESS_LAUNCHCTL": str(root / ".test-launchctl-absent"),
        },
    )
    assert proc.returncode == 0, proc.stderr
    assert "proxy stopped" in proc.stdout
    assert not installed.exists()
    assert not (egress / "proxy.pid").exists()
    assert not (egress / "proxy.ready").exists()
    assert not (egress / "proxy.env").exists()


def test_disabled_status_detects_launchd_job_without_runtime_markers(tmp_path):
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    _write_instance(root, "enforce: false\n")
    installed = root / "Library" / "LaunchAgents" / "com.cabinet.egress-proxy.plist"
    installed.parent.mkdir(parents=True)
    installed.write_text("leftover\n", encoding="utf-8")
    present = tmp_path / "launchctl-present"
    present.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    present.chmod(0o755)
    status = _run(["status"], root, state,
                  extra_env={"EGRESS_LAUNCHCTL": str(present)})
    assert status.returncode != 0
    assert "LAUNCHD JOB PRESENT" in status.stdout


def test_invalid_launch_mode_fails_teardown_loudly(tmp_path):
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    _write_instance(root, "enforce: false\n")
    proc = _run(["stop"], root, state,
                extra_env={"EGRESS_LAUNCH_MODE": "typo"})
    assert proc.returncode != 0
    assert "invalid EGRESS_LAUNCH_MODE" in proc.stderr
    assert "restriction state is not claimed" in proc.stderr


def test_child_stop_refuses_stale_pid_without_killing_unrelated_process(tmp_path):
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    egress = state / "egress"
    egress.mkdir(parents=True)
    _write_instance(root, "enforce: false\n")
    unrelated = subprocess.Popen(["sleep", "30"])
    try:
        (egress / "proxy.pid").write_text(f"{unrelated.pid}\n", encoding="utf-8")
        (egress / "proxy.ready").write_text(
            f"READY 8899 PID {unrelated.pid}\n", encoding="utf-8")
        (egress / "proxy.env").write_text("forensic-marker\n", encoding="utf-8")
        proc = _run(["stop"], root, state)
        assert proc.returncode != 0
        assert "refusing to kill stale/unattested" in proc.stderr
        assert unrelated.poll() is None, "guard killed a reused/unrelated PID"
        assert (egress / "proxy.pid").exists()
        assert (egress / "proxy.ready").exists()
        assert (egress / "proxy.env").exists()

        # A refused stop must stay dirty on retry; deleting markers would turn
        # this into a dishonest second-stop success while the PID is still up.
        again = _run(["stop"], root, state)
        assert again.returncode != 0
        assert "refusing to kill stale/unattested" in again.stderr
        assert unrelated.poll() is None
        assert (egress / "proxy.pid").exists()
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=5)


def test_launchd_mode_owns_lifetime_and_stop_removes_supervisor(tmp_path, stop_guard):
    """On macOS the one-shot officer launcher must not own the proxy process.

    A fake launchctl gives the guard a distinct supervisor process boundary,
    records bootstrap/print/bootout calls, and starts the real local proxy. This
    pins the production contract without touching the host's actual launchd:
    apply installs a persistent direct LaunchAgent once, a second apply keeps
    the same pid, runtime-state requires plist+job+PID attestation, and stop
    boots out the service rather than trusting a mutable pid file.
    """
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    stop_guard.append((root, state))
    port = _free_port()
    _write_instance(root, f"enforce: true\nproxy_port: {port}\nallow_product: false\n"
                          "allow_hosts:\n  - localhost\n")

    fake = tmp_path / "fake_launchctl.py"
    fake_log = tmp_path / "launchctl.log"
    fake_state = tmp_path / "launchctl.state"
    fake.write_text(
        """#!/usr/bin/env python3
import os
import pathlib
import plistlib
import signal
import subprocess
import sys
import time

log = pathlib.Path(os.environ["FAKE_LAUNCHCTL_LOG"])
state = pathlib.Path(os.environ["FAKE_LAUNCHCTL_STATE"])
args = sys.argv[1:]
with log.open("a", encoding="utf-8") as handle:
    handle.write(" ".join(args) + "\\n")

verb = args[0] if args else ""
if verb == "print":
    if not state.exists():
        raise SystemExit(113)
    pid = int(state.read_text(encoding="utf-8"))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        raise SystemExit(113)
    print("state = running")
    print("    pid = %d" % pid)
    raise SystemExit(0)
if verb == "bootout":
    if state.exists():
        pid = int(state.read_text(encoding="utf-8"))
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        for _ in range(50):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
    state.unlink(missing_ok=True)
    raise SystemExit(0)
if verb != "bootstrap" or len(args) != 3:
    raise SystemExit(64)

with open(args[2], "rb") as handle:
    job = plistlib.load(handle)
command = job["ProgramArguments"]
err_path = job.get("StandardErrorPath", os.devnull)
pathlib.Path(err_path).parent.mkdir(parents=True, exist_ok=True)
with open(err_path, "ab", buffering=0) as err:
    child = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=err,
        start_new_session=True,
        close_fds=True,
    )
state.write_text("%d\\n" % child.pid, encoding="utf-8")
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = {
        "EGRESS_LAUNCH_MODE": "launchd",
        "EGRESS_LAUNCHCTL": str(fake),
        "FAKE_LAUNCHCTL_LOG": str(fake_log),
        "FAKE_LAUNCHCTL_STATE": str(fake_state),
    }

    first = _run(["apply"], root, state, extra_env=env)
    assert first.returncode == 0, first.stderr
    first_pid = int((state / "egress" / "proxy.pid").read_text().strip())
    os.kill(first_pid, 0)
    assert _run(["runtime-state"], root, state, extra_env=env).returncode == 0
    installed = root / "Library" / "LaunchAgents" / "com.cabinet.egress-proxy.plist"
    with installed.open("rb") as handle:
        job = plistlib.load(handle)
    assert job["KeepAlive"] is True
    assert job["RunAtLoad"] is True
    assert job["ProgramArguments"][0] == sys.executable
    assert job["ProgramArguments"][1] == str(PROXY)
    assert job["ProgramArguments"][3] == str(port)
    installed_bytes = installed.read_bytes()

    second = _run(["apply"], root, state, extra_env=env)
    assert second.returncode == 0, second.stderr
    assert int((state / "egress" / "proxy.pid").read_text().strip()) == first_pid
    calls = fake_log.read_text(encoding="utf-8").splitlines()
    assert sum(line.startswith("bootstrap ") for line in calls) == 1
    assert any(line.startswith("print gui/") for line in calls)

    # The running PID is insufficient: a modified installed contract must
    # fail runtime attestation even while the fake supervisor still owns it.
    job["ThrottleInterval"] = 999
    with installed.open("wb") as handle:
        plistlib.dump(job, handle)
    forged = _run(["runtime-state"], root, state, extra_env=env)
    assert forged.returncode != 0
    assert "process supervisor" in forged.stderr
    installed.write_bytes(installed_bytes)
    assert _run(["runtime-state"], root, state, extra_env=env).returncode == 0

    # A process-contract change is serialized as bootout-before-bootstrap and
    # yields a new directly supervised PID; it is not silently reused.
    changed_env = {**env, "EGRESS_CONNECT_PORTS": "443,8443"}
    drifted = _run(["runtime-state"], root, state, extra_env=changed_env)
    assert drifted.returncode != 0
    assert "process supervisor" in drifted.stderr
    changed = _run(["apply"], root, state, extra_env=changed_env)
    assert changed.returncode == 0, changed.stderr
    second_pid = int((state / "egress" / "proxy.pid").read_text().strip())
    assert second_pid != first_pid
    calls = fake_log.read_text(encoding="utf-8").splitlines()
    first_bootout = next(i for i, line in enumerate(calls) if line.startswith("bootout "))
    second_bootstrap = [i for i, line in enumerate(calls) if line.startswith("bootstrap ")][1]
    assert first_bootout < second_bootstrap

    # Cross-mode launchd -> child: stop must still discover and boot out the
    # launchd owner even though the newly requested mode says child.
    child_mode = {**changed_env, "EGRESS_LAUNCH_MODE": "child"}
    stopped = _run(["stop"], root, state, extra_env=child_mode)
    assert stopped.returncode == 0, stopped.stderr
    calls = fake_log.read_text(encoding="utf-8").splitlines()
    assert any(line == "bootout gui/%d/com.cabinet.egress-proxy" % os.getuid()
               for line in calls)
    assert not installed.exists()
    for _ in range(50):
        try:
            os.kill(second_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail("launchd-owned proxy survived explicit stop")

    # Cross-mode child -> launchd: a child-owned proxy is first started on the
    # same fixed endpoint. Applying launchd policy must stop that exact child,
    # then bootstrap a new direct supervisor owner rather than reuse it.
    child_up = _run(["apply"], root, state, extra_env={
        "EGRESS_LAUNCH_MODE": "child",
        "EGRESS_LAUNCHCTL": str(root / ".test-launchctl-absent"),
        "EGRESS_CONNECT_PORTS": "443,8443",
    })
    assert child_up.returncode == 0, child_up.stderr
    child_pid = int((state / "egress" / "proxy.pid").read_text().strip())

    launchd_up = _run(["apply"], root, state, extra_env=changed_env)
    assert launchd_up.returncode == 0, launchd_up.stderr
    final_pid = int((state / "egress" / "proxy.pid").read_text().strip())
    assert final_pid != child_pid
    for _ in range(50):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail("child-owned proxy survived launchd-mode reconciliation")

    final_stop = _run(["disable"], root, state, extra_env=changed_env)
    assert final_stop.returncode == 0, final_stop.stderr
    assert "enforce: false" in (
        root / "instance" / "config" / "egress.yml"
    ).read_text(encoding="utf-8")
    assert not installed.exists()


@pytest.mark.parametrize("artifact", ["proxy.env", "allow.hosts"])
def test_runtime_state_attestation_rejects_tampered_artifact(tmp_path, stop_guard, artifact):
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    stop_guard.append((root, state))
    _write_instance(root, "enforce: true\nproxy_port: 0\nallow_product: false\n"
                          "allow_hosts:\n  - localhost\n")
    applied = _run(["apply"], root, state)
    assert applied.returncode == 0, applied.stderr

    target = state / "egress" / artifact
    target.write_text("forged\n", encoding="utf-8")
    attested = _run(["runtime-state"], root, state)
    assert attested.returncode != 0
    assert "FAIL-CLOSED" in attested.stderr

    repaired = _run(["apply"], root, state)
    assert repaired.returncode == 0, repaired.stderr
    assert _run(["runtime-state"], root, state).returncode == 0


def test_apply_warns_when_proxy_env_unwired(tmp_path, stop_guard):
    """EG-2: enabling enforcement is honest about wiring. While nothing in the
    tree sources proxy.env, apply prints a WARNING (non-fatal) that officers
    already running are not constrained; once a launch wrapper sources it the
    warning stops — so a green 'proxy: RUNNING' is never misread as coverage."""
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    stop_guard.append((root, state))
    _write_instance(root, "enforce: true\nproxy_port: 0\nallow_product: false\n"
                          "allow_hosts:\n  - localhost\n")

    # unwired: apply succeeds (rc 0) but WARNS loudly on stderr
    unwired = _run(["apply"], root, state)
    assert unwired.returncode == 0, unwired.stderr
    assert "WARNING" in unwired.stderr
    assert "proxy env" in unwired.stderr.lower()

    # wire it: a launch wrapper that actually sources proxy.env silences it
    wrapper = root / "cabinet" / "launch-officer.sh"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(
        '#!/bin/bash\n'
        '[ -f "$CABINET_STATE_DIR/egress/proxy.env" ] && . "$CABINET_STATE_DIR/egress/proxy.env"\n'
        'exec "$@"\n',
        encoding="utf-8",
    )
    wired = _run(["apply"], root, state)
    assert wired.returncode == 0, wired.stderr
    assert "WARNING" not in wired.stderr


# --------------------------------- 6. proxy --check matcher -----------------
@pytest.mark.parametrize("allow,host,expect", [
    ("foo.com", "foo.com", 0),          # exact
    ("foo.com", "api.foo.com", 0),      # subdomain
    ("foo.com", "evilfoo.com", 1),      # suffix-confusion must NOT match
    ("foo.com", "denied.test", 1),      # unrelated
    ("api.foo.com", "foo.com", 1),      # parent is not covered by a child entry
])
def test_check_matcher(allow, host, expect):
    proc = subprocess.run(
        [sys.executable, str(PROXY), "--check", host],
        env={**os.environ, "EGRESS_ALLOW_HOSTS": allow},
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == expect, proc.stdout + proc.stderr
    assert (proc.stdout.strip() == ("ALLOW" if expect == 0 else "BLOCK"))


@pytest.mark.parametrize("ports", ["", "0", "65536", "443,nope"])
def test_proxy_backend_rejects_invalid_connect_ports(ports):
    proc = subprocess.run(
        [sys.executable, str(PROXY), "--connect-ports", ports, "--check", "x.test"],
        env={**os.environ, "EGRESS_ALLOW_HOSTS": "x.test"},
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode != 0
    assert "error:" in proc.stderr


# --------------------------------- 7. no secrets in the proxy log -----------
def test_proxy_log_has_no_secrets(tmp_path, stop_guard):
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    stop_guard.append((root, state))
    _write_instance(root, "enforce: true\nproxy_port: 0\nallow_product: false\n"
                          "allow_hosts:\n  - localhost\n")
    assert _run(["apply"], root, state).returncode == 0
    pport = _ready_port(state)

    # a blocked request carrying secrets in the URL query and a header
    with pytest.raises(urllib.error.HTTPError):
        _http_via_proxy(pport, "http://denied.test/?token=SUPERSECRET123",
                        headers={"Authorization": "Bearer SECRETHDR"})

    log = (state / "egress" / "proxy.log").read_text(encoding="utf-8")
    assert "EGRESS-BLOCK denied.test" in log      # host-only line present
    assert "SUPERSECRET123" not in log            # query secret never logged
    assert "SECRETHDR" not in log                 # header secret never logged
    assert "token=" not in log                    # no path/query at all
    assert ((state / "egress" / "proxy.log").stat().st_mode & 0o777) == 0o600


def test_apply_rejects_symlinked_proxy_log(tmp_path):
    root = _seed_root(tmp_path)
    state = tmp_path / "state"
    egress = state / "egress"
    egress.mkdir(parents=True)
    victim = tmp_path / "victim.txt"
    victim.write_text("do-not-touch\n", encoding="utf-8")
    (egress / "proxy.log").symlink_to(victim)
    _write_instance(root, "enforce: true\nproxy_port: 0\nallow_product: false\n")
    applied = _run(["apply"], root, state)
    assert applied.returncode != 0
    assert "proxy log is symlinked" in applied.stderr
    assert victim.read_text(encoding="utf-8") == "do-not-touch\n"
    assert not (egress / "proxy.env").exists()


# --------------------------------- 8. static hygiene ------------------------
def test_guard_shellcheck_clean():
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck not installed")
    proc = subprocess.run(
        ["shellcheck", "-S", "warning", str(GUARD)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_guard_bash_syntax():
    proc = subprocess.run(["bash", "-n", str(GUARD)],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
