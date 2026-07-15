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
import shutil
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
FRAMEWORK_DEFAULT = REPO / "framework" / "defaults" / "egress.yml"


# --------------------------------------------------------------- helpers ----
def _run(args, root: Path, state: Path, extra_env=None):
    env = {
        **os.environ,
        "CABINET_ROOT": str(root),
        "CABINET_STATE_DIR": str(state),
        "CABINET_PYTHON": sys.executable,   # yaml-bearing interpreter parity
        "HOME": str(root),                  # keep any fallback under tmp
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
    shutil.copy(FRAMEWORK_DEFAULT, root / "framework" / "defaults" / "egress.yml")
    if org_domains is not None:
        (root / "instance" / "config" / "platform.yml").write_text(
            "org_domains:\n" + "".join("  - %s\n" % d for d in org_domains),
            encoding="utf-8",
        )
    return root


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

    second = _run(["apply"], root, state)
    assert second.returncode == 0, second.stderr
    assert int((state / "egress" / "proxy.pid").read_text().strip()) == first_pid
    assert _ready_port(state) == first_port

    runtime = _run(["runtime-state"], root, state)
    assert runtime.returncode == 0, runtime.stderr
    assert runtime.stdout.strip() == "1\t%s" % (state / "egress" / "proxy.env")


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
