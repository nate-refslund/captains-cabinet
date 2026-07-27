"""No test may reach a safety switch it does not own — beyond Python.

WHY THIS FILE EXISTS. ``test_killswitch_test_fence.py`` closed the Python
emergency-stop writers and said, in its own docstring, exactly what it could
NOT see: shell tests, raw ``redis-cli`` writes that never name the script, and
every OTHER safety switch. That honesty is why the following were findable at
all — each was reproduced against disposable servers and a throwaway checkout
before being fixed (2026-07-27):

* ``test_tamper_drill.py`` armed the evidence judging-freeze at the REAL
  checkout and cleaned up with ``finally: _thaw(_REPO_ROOT)``. With a genuine
  Captain freeze armed, its own freeze was a no-op (first-freeze-wins), its
  assertion failed, and the ``finally`` DELETED the Captain's marker anyway —
  bypassing the token-gated ``captain_clear`` the marker names as the only way
  out. Reproduced: ``set_by="captain"``, ``uchg`` set, gone after one run.
* Seven ``cabinet/tests/hook-regression/*.sh`` harnesses opened with an
  unconditional ``redis-cli -h redis -p 6379 DEL <safety key>``
  (``cabinet:killswitch`` in fw042, the CTO review-gate keys in the other six).
  Measured on this fleet: the ``redis`` hostname does not resolve, so that line
  did NOTHING — the arrange step every probe depends on had never once run —
  while the hook under test read whatever plane the AMBIENT
  ``REDIS_HOST``/``REDIS_PORT`` named, i.e. the live one on an officer box.
  Where ``redis`` DOES resolve (the watchdog container's docker network) the
  same line is a live clear of the Captain's emergency stop.

THE RULE THIS FILE ENFORCES, and why it is shaped this way: **a test may not
address a control plane by hardcoded literal.** Not "may not name these keys" —
a key list is the drift that caused the original incident, and it would have
covered fw042 while leaving its six identical siblings open. The endpoint rule
is derivation-free: loopback with a port the test chose is a sandbox; a named
host, or the live default port written as a literal, is somebody else's server.

WHAT THIS FILE DOES **NOT** SEE — stated because a guard read as total coverage
is worse than no guard:

* **Runtime-composed endpoints.** A host/port assembled from variables at
  runtime reads as a variable here and is not flagged. The behavioural arm
  catches those by EFFECT, but only for the files it runs.
* **Only fw042 is run behaviourally.** The emergency stop is the switch worth
  the wall-clock; the six CTO review-gate harnesses are covered structurally
  only, because running all seven costs minutes in a unit-test job.
* **Non-redis switches other than the judging freeze** — observe-only,
  captain-vetoes, the act-first kind freeze — have no arm here.
* **The dashboard TypeScript suite** is not scanned.
* ``cabinet/scripts/test-escalation.sh --live`` writes the real switch BY
  DESIGN; it is fenced by a pre-flight refusal in the script itself, not here.
* This file scans EXECUTABLE lines only: a full-line comment naming a literal
  endpoint is prose, not a write, and the comments explaining this very fix
  would otherwise trip the guard that polices it.

NON-VACUITY. Every detector is exercised against synthetic known-bad and
known-good input in the same run, so a detector that silently stopped matching
anything fails instead of reporting a clean sweep. The behavioural arms arm a
CANARY — a freeze marker and a redis key on servers this test owns — because on
a fresh checkout and a clean environment (every CI runner) both defects are
INVISIBLE: no freeze is armed to destroy, and the ``redis`` hostname does not
resolve. The hole is open exactly where it is not tested.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_freeze_fence as fzfence  # noqa: E402

_HAVE_REDIS = all(shutil.which(t) for t in ("redis-server", "redis-cli"))
needs_redis = pytest.mark.skipif(
    not _HAVE_REDIS, reason="redis-server/redis-cli not on PATH")

#: Loopback is a sandbox when the test chose the port; a NAMED host never is.
_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})

#: The port the live control plane listens on. A test writing this as a bare
#: literal has addressed the fleet's server, whatever it meant to do.
_LIVE_PORT = "6379"

_REDIS_INVOCATION = re.compile(r"redis-cli|redis-server")
_PORT_LITERAL = re.compile(r"""(?:^|[\s'"(\[,])-p[\s'",\]]*['"]?\b""" + _LIVE_PORT + r"\b")
_HOST_FLAG = re.compile(r"""-h(?P<sep>['"\s,\]]+)(?P<q>['"]?)(?P<host>[A-Za-z0-9._-]+)""")


def _executable_part(line: str) -> str:
    """The part of a source line that can actually run.

    Full-line comments are prose. Anything else is kept whole — an inline `#`
    could sit inside a quoted string, and dropping the tail there would make
    the detector LESS sensitive, which is the wrong direction for a guard.
    """
    return "" if line.lstrip().startswith("#") else line


def _is_test_surface(rel: str) -> bool:
    return (rel.startswith("cabinet/tests/")
            or rel.startswith("cabinet/scripts/tests/")
            or rel.startswith("cabinet/scripts/lib/tests/")
            or re.match(r"cabinet/scripts/test-[^/]+\.sh$", rel) is not None
            or "/tests/" in rel
            or rel.endswith(".test.ts"))


def hardcoded_endpoints(text: str, *, shell: bool) -> list[tuple[int, str]]:
    """Redis invocations addressing a literal endpoint. Line numbers + reason.

    ``shell`` distinguishes ``-h redis`` (a literal in a shell command) from
    ``"-h", host`` (a Python variable), which is why the Python arm requires
    the value to be quoted before calling it a literal.
    """
    out: list[tuple[int, str]] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _executable_part(raw)
        if not _REDIS_INVOCATION.search(line):
            continue
        reasons = []
        if _PORT_LITERAL.search(line):
            reasons.append(f"literal -p {_LIVE_PORT}")
        for m in _HOST_FLAG.finditer(line):
            host = m.group("host")
            if not shell and not m.group("q"):
                continue          # a bare token in Python source is a variable
            if host not in _LOOPBACK:
                reasons.append(f"literal -h {host}")
        if reasons:
            out.append((lineno, ", ".join(sorted(set(reasons)))))
    return out


def _tracked(pattern: str = "") -> list[str]:
    argv = ["git", "ls-files"] + ([pattern] if pattern else [])
    return subprocess.run(argv, cwd=str(REPO), capture_output=True,
                          text=True, timeout=120).stdout.split()


# ---------------------------------------------------------------------------
# Detector non-vacuity — checked before any clean sweep is believed
# ---------------------------------------------------------------------------

def test_endpoint_detector_flags_known_bad_and_spares_known_good():
    """The exact pre-fix line must be caught, and every sandbox idiom spared.

    A detector that quietly stopped matching would turn this whole file into a
    green light, which is the failure mode it exists to prevent.
    """
    bad_shell = 'redis-cli -h redis -p 6379 DEL "cabinet:killswitch" >/dev/null 2>&1'
    assert hardcoded_endpoints(bad_shell, shell=True), "pre-fix line not detected"
    reasons = hardcoded_endpoints(bad_shell, shell=True)[0][1]
    assert "literal -h redis" in reasons and f"literal -p {_LIVE_PORT}" in reasons

    good = [
        'redis-cli -h 127.0.0.1 -p "$SANDBOX_PORT" PING',
        'redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET k',
        'redis-cli -h "${REDIS_HOST:-127.0.0.1}" -p "${REDIS_PORT:-6379}" GET k',
        'redis-cli -p "$port" --raw KEYS "*"',
    ]
    for sample in good:
        assert not hardcoded_endpoints(sample, shell=True), f"false positive: {sample}"

    # Python: a bare identifier is a variable; a quoted value is a literal.
    assert not hardcoded_endpoints('["redis-cli", "-h", _HOST, "-p", str(port)]',
                                   shell=False)
    assert hardcoded_endpoints('["redis-cli", "-h", "redis", "-p", "6379"]',
                               shell=False)

    # A full-line comment is prose, not a write.
    assert not hardcoded_endpoints('  # redis-cli -h redis -p 6379 DEL x', shell=True)
    assert hardcoded_endpoints('redis-cli -h redis -p 6379 DEL x  # trailing',
                               shell=True)


def test_freeze_detector_flags_known_bad_and_spares_known_good():
    assert _freeze_writers_in("ef.freeze(root, 'x')")
    assert _freeze_writers_in("evidence_freeze.freeze(root, 'x')")
    assert _freeze_writers_in("ef._lift_immutable(marker)")
    assert not _freeze_writers_in("# ef.freeze(root, 'x')")
    assert not _freeze_writers_in("assert ef.is_frozen(root) is False")

    # The real-checkout-argument rule: both pre-fix lines, and nothing else.
    assert _real_root_freeze_writes('    ef.freeze(_REPO_ROOT, "x", set_by="p")')
    assert _real_root_freeze_writes("        _thaw(_REPO_ROOT)")
    assert _real_root_freeze_writes("    evidence_freeze.freeze(CABINET_ROOT, 'x')")
    assert not _real_root_freeze_writes("    evidence_freeze.freeze(tmp_path, 'x')")
    assert not _real_root_freeze_writes("    marker = evidence_freeze.freeze(planes.tmp, 'x')")
    assert not _real_root_freeze_writes("    assert not ef.is_frozen(_REPO_ROOT)")
    assert not _real_root_freeze_writes("    assert fzfence.fingerprint(_REPO_ROOT) == before")
    assert not _real_root_freeze_writes("    # ef.freeze(_REPO_ROOT, 'x')")


_FREEZE_WRITE = re.compile(
    r"(?:\bef|\bevidence_freeze)\.(?:freeze|_lift_immutable|captain_clear)\s*\(")

#: A freeze WRITE verb handed something that resolves to a real checkout. This
#: is the argument-shaped rule, and it is the one that works in every layer:
#: `framework/tests/` cannot import a `cabinet/` test library without breaking
#: layer separation, so "must import the fence" cannot be the repo-wide rule.
#: `is_frozen`, `freeze-status` and `fingerprint` are READS and do not match.
#: ``(?<![A-Za-z0-9])_*`` and not ``\b``: the helper that destroyed the freeze
#: was named ``_thaw``, and ``\b`` does not match between ``_`` and ``t`` — the
#: detector would have missed the exact line it exists to catch. ``is_frozen``
#: still does not match (``frozen`` is not a verb here), so reads stay free.
_REPO_ROOT_ARG = re.compile(
    r"(?<![A-Za-z0-9])_*(?:freeze|unfreeze|thaw|lift_immutable|captain_clear)\w*\s*\(\s*"
    r"(?:str\(\s*)?(?P<arg>_?REPO_ROOT|_?REPO|CABINET_ROOT|_?ROOT)\b")


def _freeze_writers_in(text: str) -> list[int]:
    return [i for i, raw in enumerate(text.splitlines(), 1)
            if _FREEZE_WRITE.search(_executable_part(raw))]


def _real_root_freeze_writes(text: str) -> list[tuple[int, str]]:
    return [(i, raw.strip()[:110])
            for i, raw in enumerate(text.splitlines(), 1)
            if _REPO_ROOT_ARG.search(_executable_part(raw))]


# ---------------------------------------------------------------------------
# Structural — the whole tracked test surface, every language
# ---------------------------------------------------------------------------

def test_no_test_addresses_a_hardcoded_control_plane():
    scanned = 0
    offenders: dict[str, list[tuple[int, str]]] = {}
    for rel in _tracked():
        if not _is_test_surface(rel):
            continue
        path = REPO / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "redis" not in text:
            continue
        scanned += 1
        hits = hardcoded_endpoints(text, shell=rel.endswith((".sh", ".bash")))
        if hits:
            offenders[rel] = hits
    assert scanned >= 10, (
        f"only {scanned} redis-touching test files scanned — the detector or the "
        "path predicate is broken, and a guard that inspects nothing is not a guard.")
    assert not offenders, (
        "these tests address a redis endpoint by hardcoded literal, i.e. a "
        f"control plane they do not own: {json.dumps(offenders, indent=2)}\n"
        "Use the hermetic fixtures/redis-cli stub on PATH (hook harnesses) or a "
        "sandbox port the test started itself.")


def _freeze_writer_files() -> list[str]:
    writers = []
    for rel in _tracked("*.py"):
        name = Path(rel).name
        if not name.startswith("test_") or name == Path(__file__).name:
            continue
        text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        if _freeze_writers_in(text):
            writers.append(rel)
    return writers


def test_no_test_hands_a_real_checkout_to_a_freeze_write():
    """Repo-wide, every layer: the pre-fix defect, as a rule about the argument.

    ``ef.freeze(_REPO_ROOT, ...)`` and ``_thaw(_REPO_ROOT)`` are the two lines
    that destroyed a Captain freeze. Both pass something that resolves to a real
    checkout to a write verb, and that is the property worth forbidding —
    ``framework/tests/`` cannot import a ``cabinet/`` test library without
    breaking layer separation, so "must import the fence" cannot be the
    repo-wide rule. Reads (``is_frozen``, ``freeze-status``) are untouched.
    """
    offenders: dict[str, list[tuple[int, str]]] = {}
    for rel in _tracked("*.py"):
        name = Path(rel).name
        if not name.startswith("test_") or name == Path(__file__).name:
            continue
        hits = _real_root_freeze_writes(
            (REPO / rel).read_text(encoding="utf-8", errors="replace"))
        if hits:
            offenders[rel] = hits
    assert not offenders, (
        "these tests hand a REAL CHECKOUT root to a judging-freeze write verb: "
        f"{json.dumps(offenders, indent=2)}\n"
        "`freeze()` is first-freeze-wins, so with a Captain freeze already armed "
        "the test's own freeze is a no-op and its cleanup deletes the CAPTAIN's "
        "marker — bypassing the token-gated unfreeze. Use a tmp root "
        "(lib_freeze_fence.pseudo_root for subprocess drills).")


def test_cabinet_freeze_writers_go_through_the_fence():
    """Stricter arm where the fence is importable without crossing layers."""
    writers = _freeze_writer_files()
    assert writers, (
        "found NO test that writes the judging-freeze marker — the detector is "
        "broken, and a guard that matches nothing is not a guard.")
    unfenced = [rel for rel in writers
                if rel.startswith("cabinet/")
                and "lib_freeze_fence" not in (REPO / rel).read_text(
                    encoding="utf-8", errors="replace")]
    assert not unfenced, (
        "these cabinet tests set or clear the judging-freeze marker without "
        f"going through lib_freeze_fence: {unfenced}. `_lift_immutable`+unlink "
        "is `captain_clear` with the token check removed.")


# ---------------------------------------------------------------------------
# Behavioural — the incidents, as permanent arms
# ---------------------------------------------------------------------------

def test_tamper_drill_cannot_destroy_an_armed_freeze_it_did_not_set(tmp_path):
    """Run the drill's own test file against a CANARY checkout whose freeze is
    already armed, and prove the marker is still there afterwards.

    This is the only arm that tests the property rather than a proxy for it:
    not "does the file import the fence" but "can this file delete a freeze it
    did not set". On a fresh checkout there is no freeze to destroy, so the
    canary is the whole point.
    """
    canary = tmp_path / "canary-checkout"
    (canary / "cabinet" / "scripts" / "tests").mkdir(parents=True)
    (canary / "framework").symlink_to(REPO / "framework", target_is_directory=True)
    for rel in ("cabinet/scripts/evidence-tamper-drill.py",
                "cabinet/scripts/evidence-anchor.py",
                "cabinet/scripts/tests/test_tamper_drill.py",
                "cabinet/scripts/tests/lib_freeze_fence.py"):
        shutil.copy2(REPO / rel, canary / rel)
    lib = REPO / "cabinet" / "scripts" / "lib" / "triggers.sh"
    if lib.is_file():
        (canary / "cabinet" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
        shutil.copy2(lib, canary / "cabinet" / "scripts" / "lib" / "triggers.sh")

    sys.path.insert(0, str(REPO))
    from framework import evidence_freeze

    marker = evidence_freeze.freeze(
        canary, "canary: a Captain freeze this test must not touch",
        set_by="captain-canary")
    assert evidence_freeze.is_frozen(canary)
    before = marker.read_bytes()

    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         str(canary / "cabinet" / "scripts" / "tests" / "test_tamper_drill.py")],
        cwd=str(canary), env=env, capture_output=True, text=True, timeout=900)
    try:
        assert evidence_freeze.is_frozen(canary), (
            "A TEST DELETED AN ARMED JUDGING FREEZE it did not set. On a real "
            "checkout that is the Captain's freeze, and clearing it is "
            f"token-gated Captain-only.\n{run.stdout[-3000:]}")
        assert marker.read_bytes() == before, (
            f"the armed freeze marker was rewritten by the test run\n{run.stdout[-3000:]}")
        assert run.returncode == 0, (
            "the tamper-drill tests must also PASS with a freeze armed at their "
            f"checkout's root:\n{run.stdout[-3000:]}\n{run.stderr[-2000:]}")
    finally:
        evidence_freeze._lift_immutable(marker)
        marker.unlink(missing_ok=True)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@needs_redis
def test_hook_harness_cannot_reach_a_control_plane_it_does_not_own(tmp_path):
    """Run fw042 with the officer runtime's environment AND a resolver that
    makes its hardcoded hostname resolve, then prove the canary never moved.

    The shim is the point. ``redis-cli -h redis -p 6379 DEL cabinet:killswitch``
    is a silent no-op wherever that hostname does not resolve — every runner,
    this fleet — and a live emergency-stop clear wherever it does, which is
    exactly the deployment ``cabinet/Dockerfile.watchdog`` builds. Testing it
    only where it cannot fire is the "what does the test environment guarantee
    that production does not" trap, so the environment is made representative
    instead.
    """
    port = _free_port()
    data = tmp_path / "canary-redis"
    data.mkdir()
    proc = subprocess.Popen(
        ["redis-server", "--port", str(port), "--bind", "127.0.0.1",
         "--save", "", "--appendonly", "no", "--dir", str(data)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def cli(*args):
        return subprocess.run(["redis-cli", "-p", str(port), *args],
                              capture_output=True, text=True,
                              timeout=15).stdout.strip()
    try:
        for _ in range(100):
            if cli("PING") == "PONG":
                break
            time.sleep(0.05)
        else:  # pragma: no cover - environment failure
            pytest.skip("canary redis did not come up")

        shim = tmp_path / "shim"
        shim.mkdir()
        real_cli = shutil.which("redis-cli")
        (shim / "redis-cli").write_text(
            "#!/bin/bash\n"
            "# Makes the docker hostname resolve, as it does in the watchdog\n"
            "# container, so a hardcoded endpoint is not silently inert here.\n"
            'a=(); for x in "$@"; do\n'
            '  if [ "$x" = redis ]; then a+=(127.0.0.1);\n'
            f'  elif [ "$x" = 6379 ]; then a+=({port});\n'
            '  else a+=("$x"); fi\n'
            "done\n"
            f'exec {real_cli} "${{a[@]}}"\n',
            encoding="utf-8")
        (shim / "redis-cli").chmod(0o755)

        cli("SET", "cabinet:killswitch", "active")     # the Captain's stop
        cli("SET", "canary:sentinel", "untouched")     # a non-empty baseline
        before = cli("DBSIZE")

        env = dict(os.environ)
        env.update({                       # the officer runtime's normal env
            "PATH": f"{shim}:{env['PATH']}",
            "REDIS_HOST": "127.0.0.1",
            "REDIS_PORT": str(port),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        env.pop("REDIS_URL", None)

        run = subprocess.run(
            ["bash", str(REPO / "cabinet" / "tests" / "hook-regression"
                         / "fw042-v37-adversary.sh")],
            cwd=str(REPO), env=env, capture_output=True, text=True, timeout=900)

        assert cli("GET", "cabinet:killswitch") == "active", (
            "A SHELL TEST CLEARED AN ARMED EMERGENCY STOP on a control plane it "
            "does not own. On an officer box that is the Captain's stop, and "
            f"deactivation is Captain-side only.\n{run.stdout[-3000:]}")
        assert cli("DBSIZE") == before, (
            f"canary keyspace changed ({before} -> {cli('DBSIZE')}); the harness "
            f"wrote to a control plane it does not own.\n{run.stdout[-3000:]}")
        assert run.returncode == 0, (
            "fw042 must also PASS hermetically, with an armed stop on the "
            f"ambient control plane:\n{run.stdout[-4000:]}\n{run.stderr[-2000:]}")
    finally:
        proc.kill()
        proc.wait(timeout=10)
