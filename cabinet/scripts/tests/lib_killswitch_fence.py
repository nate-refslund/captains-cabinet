"""The sandbox fence for every test that can flip the Captain's emergency stop.

WHY THIS FILE EXISTS (incident 2026-07-27). ``test_killswitch_watchdog.py`` and
``test_kill_switch_events.py`` redirected their children by setting **only**
``REDIS_URL``. The code they drive resolves its endpoint through
``_ks_endpoint`` in ``cabinet/scripts/hooks/killswitch-read.sh``, which PREFERS
``REDIS_HOST``/``REDIS_PORT`` and falls back to ``REDIS_URL`` — and both tests
built their child env with ``dict(os.environ)``, so an ambient
``REDIS_HOST``/``REDIS_PORT`` survived untouched and WON.

Every officer plist exports exactly those two (``cabinet/launchd/*.plist``), so
on the officer runtime's NORMAL environment those test files drove
``kill-switch.sh activate`` against the LIVE control plane. Reproduced against
two disposable servers: the write landed on the ``REDIS_HOST``/``REDIS_PORT``
pair while the test asserted against its own sandbox — i.e. the file arms the
real emergency stop and only THEN fails, so the red tells you nothing about
what it already did.

A second channel was unfenced the same way: ``_ks_marker_path`` resolves the
filesystem stop marker from ``CABINET_ESTOP_MARKER`` else
``CABINET_ROOT``/instance/config/estop, and ``kill-switch.sh deactivate`` does
``rm -f`` on it. ``CABINET_ROOT`` is also exported by the runtime plists, so the
same tests could delete a live armed stop marker. Reproduced.

This is the standing rule "no test may put a live safety switch in its write
set" defeated by a fence keyed on the wrong variable — the fence existed and
did not enclose. The same shape as a golden eval pointed at a dead twin.

WHY THE CHANNEL SET IS DERIVED, NOT LISTED. A hand-maintained list of env vars
is precisely the drift that caused this: ``test_killswitch_fail_closed.py``
already fenced all five channels correctly and documented why, and the
knowledge still failed to reach its two siblings. So :func:`derive_channels`
EXTRACTS the routing variables from the consumer itself
(``hooks/killswitch-read.sh`` — the single-purpose resolver every reader shares,
plus the watchdog's own ``redis_endpoint``). A new routing variable added to the
resolver appears here automatically and, if this module does not know how to
sandbox it, :func:`sandbox_env` REFUSES rather than silently under-fencing.

WHY ISOLATION IS PROVEN, NOT ASSUMED. :func:`assert_isolated` does not
re-implement the resolution rules — it sources the REAL resolver in the exact
child env and asks it where it would go. Whatever variables that resolver
honours, today or tomorrow, are covered by construction. Anything it cannot
prove is a refusal.

FAIL-CLOSED: every failure mode here raises :class:`KillswitchFenceError`
BEFORE the child runs. A test that cannot prove it is pointed at a sandbox does
not get to run against "whatever it finds".

NOTE ON CI: a clean environment exports none of these, so the resolver falls
through to ``REDIS_URL`` and the hole is INVISIBLE — the pre-fix files pass on
every runner. Any guard over this must poison the ambient env deliberately or
it is vacuous. See ``test_killswitch_test_fence.py``.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RESOLVER = REPO / "cabinet" / "scripts" / "hooks" / "killswitch-read.sh"
WATCHDOG = REPO / "cabinet" / "scripts" / "killswitch-watchdog.py"

#: Shell/interpreter internals that appear in the resolver but steer nothing.
_NOT_A_CHANNEL = frozenset({
    "BASH_SOURCE", "PATH", "HOME", "IFS", "PWD", "OLDPWD", "SHELL", "USER",
    "PYTHONDONTWRITEBYTECODE",
})

#: How this module sandboxes each routing channel it knows. Anything
#: :func:`derive_channels` finds that is NOT a key here makes the fence refuse.
_HANDLERS = frozenset({
    "REDIS_HOST", "REDIS_PORT", "REDIS_URL",
    "CABINET_ESTOP_MARKER", "CABINET_ROOT", "KILLSWITCH_KEY",
})


class KillswitchFenceError(AssertionError):
    """Raised when isolation cannot be PROVEN. Never downgrade to a warning."""


def _bash_env_refs(text: str) -> set[str]:
    """Variables the script consumes as EXTERNAL INPUT, not ones it produces.

    Two idioms count, and between them they cover how a shell reads env:
      * read with a default — ``${VAR:-x}`` / ``${VAR:+x}`` / ``${VAR:=x}``,
        which is exactly how an optional inherited variable is consumed; and
      * referenced but never assigned in this file — the bare ``$VAR`` idiom.

    A variable the script ASSIGNS and then reads plainly (``KS_VERDICT``,
    ``KS_REASON``) is an OUTPUT and steers nothing, so it is excluded — but
    ``KILLSWITCH_KEY``, which is assigned FROM its own default expansion, is
    still caught by the first rule.
    """
    referenced = (set(re.findall(r'\$\{([A-Za-z_][A-Za-z0-9_]*)', text))
                  | set(re.findall(r'\$([A-Z][A-Z0-9_]*)', text)))
    read_with_default = set(re.findall(
        r'\$\{([A-Za-z_][A-Za-z0-9_]*):[-+=?]', text))
    assigned = set(re.findall(
        r'^[ \t]*(?:local[ \t]+|export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)=',
        text, re.MULTILINE))
    return read_with_default | (referenced - assigned)


def _py_env_refs(text: str) -> set[str]:
    return set(re.findall(
        r'os\.environ(?:\.get)?\(?\[?["\']([A-Za-z_][A-Za-z0-9_]*)["\']', text))


def _py_function_body(text: str, name: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    inside = False
    for line in lines:
        if not inside:
            if re.match(rf'^def\s+{re.escape(name)}\s*\(', line):
                inside = True
                out.append(line)
            continue
        if line and not line[0].isspace() and not line.startswith(")"):
            break
        out.append(line)
    return "\n".join(out)


def derive_channels() -> set[str]:
    """Every env var that steers a killswitch read/write, read FROM the code.

    Sources, both single-purpose:
      * ``hooks/killswitch-read.sh`` — THE shared reader. Every variable in it
        selects a server, a key or the marker path, so the whole file is the
        routing surface (``kill-switch.sh`` delegates all resolution to it).
      * ``killswitch-watchdog.py::redis_endpoint`` — the watchdog observes on
        its own resolver, which honours ``REDIS_URL`` only.
    """
    if not RESOLVER.is_file():
        raise KillswitchFenceError(
            f"cannot derive killswitch channels: resolver missing at {RESOLVER}")
    found = _bash_env_refs(RESOLVER.read_text(encoding="utf-8"))
    if WATCHDOG.is_file():
        body = _py_function_body(
            WATCHDOG.read_text(encoding="utf-8"), "redis_endpoint")
        found |= _py_env_refs(body)
    return {
        v for v in found
        if v.isupper() and not v.startswith("_") and v not in _NOT_A_CHANNEL
    }


#: The key ``kill-switch.sh`` hardcodes on BOTH write paths (``SET`` at :96,
#: ``DEL`` at :118). ``KILLSWITCH_KEY`` steers only the READ (killswitch-read.sh
#: :142), so it is deliberately NOT offered as a knob here: pointing it at a
#: sandbox key would make ``activate`` arm the LIVE ``cabinet:killswitch`` and
#: then read back a different, empty key — reporting "ACTIVATION FAILED" while
#: having actually armed the real switch. It is pinned to the literal the writer
#: uses so the read and the write can never address different keys.
_WRITER_KEY = "cabinet:killswitch"


def sandbox_env(port, *, marker, base=None, root=None, extra=None):
    """A child env with EVERY derived routing channel pinned at the sandbox.

    ``port``   — the disposable redis this test owns.
    ``marker`` — a tmp path for the filesystem stop marker. NEVER a real tree:
                 ``kill-switch.sh deactivate`` unlinks whatever this resolves to.
    ``root``   — ``CABINET_ROOT``; defaults to this checkout so the scripts still
                 find their own helpers. Safe only because ``CABINET_ESTOP_MARKER``
                 takes precedence over it for the marker path.

    Refuses if the resolver has grown a channel this module cannot sandbox.
    """
    key = _WRITER_KEY
    unknown = derive_channels() - _HANDLERS
    if unknown:
        raise KillswitchFenceError(
            "the killswitch resolver has grown routing channel(s) this fence "
            f"cannot sandbox: {sorted(unknown)}. A test must not run against "
            "whatever those name. Teach lib_killswitch_fence._HANDLERS how to "
            "redirect them (and prove it), then re-run.")

    marker = Path(marker)
    env = dict(os.environ if base is None else base)
    env.update({
        "REDIS_HOST": "127.0.0.1",
        "REDIS_PORT": str(port),
        "REDIS_URL": f"redis://127.0.0.1:{port}",
        "CABINET_ROOT": str(root or REPO),
        "CABINET_ESTOP_MARKER": str(marker),
        "KILLSWITCH_KEY": key,
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    env.update(extra or {})
    assert_isolated(env, port=port, marker=marker, key=key)
    return env


def resolve_in_env(env):
    """Ask the REAL resolver where it would go, in this exact env.

    Not a re-implementation: sources ``killswitch-read.sh`` and reports what its
    own ``_ks_endpoint`` / ``_ks_marker_path`` produce, so any channel it
    honours is covered whether or not this module knows the name.
    """
    if not RESOLVER.is_file():
        raise KillswitchFenceError(f"resolver missing at {RESOLVER}")
    script = (
        'set -u; . "$1" || exit 90; _ks_endpoint || exit 91; '
        'printf "%s\\t%s\\t%s\\t%s\\n" "$_KS_HOST" "$_KS_PORT" '
        '"$(_ks_marker_path)" "$KILLSWITCH_KEY"'
    )
    try:
        proc = subprocess.run(["bash", "-c", script, "_", str(RESOLVER)],
                              env=env, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise KillswitchFenceError(
            f"could not run the killswitch resolver to prove isolation: {exc}")
    if proc.returncode != 0:
        raise KillswitchFenceError(
            "the killswitch resolver refused to report an endpoint "
            f"(rc={proc.returncode}): {proc.stderr.strip()[:200]}")
    parts = proc.stdout.strip("\n").split("\t")
    if len(parts) != 4:
        raise KillswitchFenceError(
            f"unreadable resolver probe frame: {proc.stdout!r}")
    return {"host": parts[0], "port": parts[1],
            "marker": parts[2], "key": parts[3]}


def assert_isolated(env, *, port, marker, key=_WRITER_KEY):
    """Refuse unless the REAL resolver proves this env points at the sandbox.

    Fail-closed and legible: the message names the channel that escaped and
    where it would have gone, because the failure this prevents is a write to
    the live emergency stop.
    """
    got = resolve_in_env(env)
    marker = Path(marker).resolve()

    if got["host"] not in ("127.0.0.1", "localhost"):
        raise KillswitchFenceError(
            f"REFUSING TO RUN: the killswitch resolver would reach host "
            f"{got['host']!r}, not the loopback sandbox. Endpoint channels: "
            f"REDIS_HOST={env.get('REDIS_HOST')!r} "
            f"REDIS_PORT={env.get('REDIS_PORT')!r} "
            f"REDIS_URL={env.get('REDIS_URL')!r}")
    if str(got["port"]) != str(port):
        raise KillswitchFenceError(
            f"REFUSING TO RUN: the killswitch resolver would reach port "
            f"{got['port']}, but this test's sandbox is {port}. An unfenced "
            f"channel is winning — REDIS_HOST={env.get('REDIS_HOST')!r} "
            f"REDIS_PORT={env.get('REDIS_PORT')!r} "
            f"REDIS_URL={env.get('REDIS_URL')!r}. This is the 2026-07-27 "
            "incident: the write would land on a control plane this test does "
            "not own.")
    try:
        resolved_marker = Path(got["marker"]).resolve()
    except OSError as exc:
        raise KillswitchFenceError(f"unresolvable stop-marker path: {exc}")
    if resolved_marker != marker:
        raise KillswitchFenceError(
            f"REFUSING TO RUN: the stop marker would resolve to "
            f"{resolved_marker}, not this test's tmp marker {marker}. "
            "`kill-switch.sh deactivate` unlinks that path — an unfenced "
            f"CABINET_ESTOP_MARKER/CABINET_ROOT would delete a live armed stop.")
    if got["key"] != key:
        raise KillswitchFenceError(
            f"REFUSING TO RUN: the resolver would read key {got['key']!r}, "
            f"not this test's {key!r} (ambient KILLSWITCH_KEY leaking in).")
    return got
