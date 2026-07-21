"""channel.py — SEC-3 killswitch fail-closed on the front-door SEND path.

Safety contract under test (fail-closed, non-negotiable): when the Captain's
emergency stop is armed (Redis ``cabinet:killswitch`` == ``active``) OR the
control plane is unreachable (a missing safety switch is exposure, not
ambiguity), EVERY front-door send is REFUSED — zero bytes leave the process —
and the method returns a structured refusal (never raises).

The killswitch state is driven through action_exec's ONE SEC-3 reader
(``_killswitch_state`` / ``_redis_get_strict``) — the front door reuses that
reader, it does not invent a second one. Existing runtime-send tests stay
hermetic because ``conftest`` defaults that reader to ``clear``; these tests
override it per-case.

RED proof (pre-gate): with no killswitch check in channel.py the send proceeds
and hits the injected recording transport, so ``post.calls == []`` fails.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import framework.env as env
import framework.frontdoor.action_exec as action_exec
import framework.frontdoor.channel as channel

TOKEN = "123456:SECRET-BOT-TOKEN-do-not-leak"
CAPTAIN = "98765432"


class _RecordingPost:
    """Records every transport invocation (any arity: 2-arg JSON post OR the
    4-arg multipart document post) and returns a canned 200 body. A refused
    send must leave ``calls`` EMPTY."""

    def __init__(self, response=None):
        self.calls = []
        self._response = response or {"ok": True, "result": {"message_id": 42}}

    def __call__(self, *args):
        self.calls.append(args)
        return self._response


def _runtime(monkeypatch):
    """Simulate the runtime (sends allowed), configured, no Redis threading."""
    monkeypatch.setattr(env, "allow_sends", lambda: True)
    monkeypatch.setenv("TELEGRAM_COS_TOKEN", TOKEN)
    monkeypatch.setenv("CAPTAIN_TELEGRAM_ID", CAPTAIN)
    monkeypatch.setattr(channel, "_last_captain_msg_id", lambda: None)


# --- killswitch drivers (through action_exec's ONE reader) -------------------

def _arm_active(monkeypatch):
    monkeypatch.setattr(action_exec, "_redis_get_strict", lambda key: "active")


def _arm_unreachable(monkeypatch):
    def _boom(key):
        raise ConnectionError("redis unreachable")
    monkeypatch.setattr(action_exec, "_redis_get_strict", _boom)


def _arm_clear(monkeypatch):
    monkeypatch.setattr(action_exec, "_redis_get_strict", lambda key: "")


# --- every public front-door send that funnels through _post_one -------------

_DICT_SENDS = [
    ("send",            lambda post: channel.send("hi captain", http_post=post)),
    ("send_poll",       lambda post: channel.send_poll("q?", ["a", "b"], http_post=post)),
    ("send_draft",      lambda post: channel.send_draft(7, "streaming", http_post=post)),
    ("send_rich",       lambda post: channel.send_rich(markdown="**hi**", http_post=post)),
    ("edit_message",    lambda post: channel.edit_message(55, "new text", http_post=post)),
    ("answer_callback", lambda post: channel.answer_callback("cbq-1", "toast", http_post=post)),
    ("set_typing",      lambda post: channel.set_typing("typing", http_post=post)),
    ("pin",             lambda post: channel.pin(55, http_post=post)),
    ("unpin",           lambda post: channel.unpin(55, http_post=post)),
    ("set_reaction",    lambda post: channel.set_reaction(55, "👍", http_post=post)),
    ("open_thread",     lambda post: channel.open_thread("lane-alpha", http_post=post)),
]
_IDS = [n for n, _ in _DICT_SENDS]


@pytest.mark.parametrize("name,invoke", _DICT_SENDS, ids=_IDS)
def test_dict_send_refused_when_killswitch_active(monkeypatch, name, invoke):
    _runtime(monkeypatch)
    _arm_active(monkeypatch)
    post = _RecordingPost()
    result = invoke(post)
    assert post.calls == [], f"{name} hit the network with killswitch ACTIVE"
    assert result.get("sent") is False, f"{name} reported sent under killswitch"
    assert "killswitch" in str(result).lower(), f"{name} refusal not attributed to killswitch"


@pytest.mark.parametrize("name,invoke", _DICT_SENDS, ids=_IDS)
def test_dict_send_refused_when_redis_unreachable(monkeypatch, name, invoke):
    """Fail-closed: an unreachable control plane refuses too (never fail-open)."""
    _runtime(monkeypatch)
    _arm_unreachable(monkeypatch)
    post = _RecordingPost()
    result = invoke(post)
    assert post.calls == [], f"{name} hit the network with control plane UNREACHABLE"
    assert result.get("sent") is False, f"{name} reported sent while Redis unreachable"
    assert "killswitch" in str(result).lower()


@pytest.mark.parametrize("name,invoke", _DICT_SENDS, ids=_IDS)
def test_dict_send_proceeds_when_killswitch_clear(monkeypatch, name, invoke):
    """Control: a clear switch must NOT over-block — the send reaches transport."""
    _runtime(monkeypatch)
    _arm_clear(monkeypatch)
    post = _RecordingPost()
    invoke(post)
    assert len(post.calls) >= 1, f"{name} was blocked with killswitch CLEAR (over-block)"


# --- send_document: the ONE send on the multipart transport (bypasses _post_one)

def test_send_document_refused_when_active(monkeypatch, tmp_path):
    _runtime(monkeypatch)
    _arm_active(monkeypatch)
    doc = tmp_path / "secret.txt"
    doc.write_text("classified payload")
    post = _RecordingPost()
    result = channel.send_document(str(doc), caption="c", http_post=post)
    assert post.calls == [], "send_document exfiltrated a file with killswitch ACTIVE"
    assert result.get("sent") is False
    assert "killswitch" in str(result).lower()


def test_send_document_refused_when_unreachable(monkeypatch, tmp_path):
    _runtime(monkeypatch)
    _arm_unreachable(monkeypatch)
    doc = tmp_path / "secret.txt"
    doc.write_text("classified payload")
    post = _RecordingPost()
    result = channel.send_document(str(doc), caption="c", http_post=post)
    assert post.calls == [], "send_document sent a file while control plane UNREACHABLE"
    assert result.get("sent") is False
    assert "killswitch" in str(result).lower()


def test_send_document_gate_precedes_disk_read(monkeypatch):
    """A halted document send does ZERO disk I/O: an armed killswitch refuses a
    non-existent path with a killswitch reason, not the file-read error path."""
    _runtime(monkeypatch)
    _arm_active(monkeypatch)
    post = _RecordingPost()
    result = channel.send_document("/nonexistent/never/created.bin", http_post=post)
    assert post.calls == []
    assert result.get("sent") is False
    assert "killswitch" in str(result).lower()
    assert "cannot read" not in str(result).lower()


def test_send_document_proceeds_when_clear(monkeypatch, tmp_path):
    _runtime(monkeypatch)
    _arm_clear(monkeypatch)
    doc = tmp_path / "ok.txt"
    doc.write_text("data")
    post = _RecordingPost()
    result = channel.send_document(str(doc), http_post=post)
    assert len(post.calls) == 1
    assert result.get("sent") is True


# --- single-reader + leak-safety properties ----------------------------------

def test_channel_has_no_second_killswitch_reader():
    """The SEC-3 killswitch reader lives ONLY in action_exec. The front door must
    DELEGATE to it — never define its own state reader or strict Redis getter
    (a key literal inside an explanatory comment is fine; a second *reader* is
    not). Paired with test_send_halt_routes_through_action_exec_reader, which
    proves the halt behaviorally depends on that one reader."""
    src = Path(channel.__file__).read_text()
    assert "def _killswitch_state" not in src, "channel defines a second killswitch reader"
    assert "def _redis_get_strict" not in src, "channel defines a second strict Redis getter"
    assert "from framework.frontdoor.action_exec import" in src, (
        "channel must import the shared SEC-3 reader from action_exec")
    assert "_killswitch_state" in src and "_redis_get_strict" in src


def test_send_halt_routes_through_action_exec_reader(monkeypatch):
    """Patching action_exec's shared ``_killswitch_state`` flips the front door —
    proof it reuses that single reader rather than a private copy."""
    _runtime(monkeypatch)
    monkeypatch.setattr(action_exec, "_killswitch_state", lambda getter: "active")
    post = _RecordingPost()
    result = channel.send("hi", http_post=post)
    assert post.calls == []
    assert result.get("sent") is False


def test_refusal_carries_no_token(monkeypatch):
    _runtime(monkeypatch)
    _arm_active(monkeypatch)
    post = _RecordingPost()
    result = channel.send("hi", http_post=post)
    assert TOKEN not in str(result)


# --- observe-only doorways: live ONLY in sticky observe mode -----------------
# reply_current_observe_only / react_current_observe_only short-circuit to
# blocked-observe-only whenever allow_sends() is True — the ONE mode in which
# they reach the transport is sticky observe (allow_sends() False AND
# CABINET_OBSERVE_ONLY=1, with a current Captain inbound id). That is where the
# killswitch must halt them too; the standard _runtime cannot exercise them.

def _observe_runtime(monkeypatch):
    monkeypatch.setattr(env, "allow_sends", lambda: False)
    monkeypatch.setenv("TELEGRAM_COS_TOKEN", TOKEN)
    monkeypatch.setenv("CAPTAIN_TELEGRAM_ID", CAPTAIN)
    monkeypatch.setenv("CABINET_OBSERVE_ONLY", "1")
    monkeypatch.setattr(channel, "_last_captain_msg_id", lambda: 55)


_OBSERVE_SENDS = [
    ("reply_current_observe_only",
     lambda post: channel.reply_current_observe_only("hi captain", http_post=post)),
    ("react_current_observe_only",
     lambda post: channel.react_current_observe_only("👍", http_post=post)),
]
_OBSERVE_IDS = [n for n, _ in _OBSERVE_SENDS]


@pytest.mark.parametrize("name,invoke", _OBSERVE_SENDS, ids=_OBSERVE_IDS)
def test_observe_doorway_refused_when_killswitch_active(monkeypatch, name, invoke):
    _observe_runtime(monkeypatch)
    _arm_active(monkeypatch)
    post = _RecordingPost()
    result = invoke(post)
    assert post.calls == [], f"{name} hit the network with killswitch ACTIVE"
    assert result.get("sent") is False
    assert "killswitch" in str(result).lower(), f"{name} refusal not attributed to killswitch"


@pytest.mark.parametrize("name,invoke", _OBSERVE_SENDS, ids=_OBSERVE_IDS)
def test_observe_doorway_refused_when_redis_unreachable(monkeypatch, name, invoke):
    _observe_runtime(monkeypatch)
    _arm_unreachable(monkeypatch)
    post = _RecordingPost()
    result = invoke(post)
    assert post.calls == [], f"{name} hit the network with control plane UNREACHABLE"
    assert result.get("sent") is False
    assert "killswitch" in str(result).lower()


@pytest.mark.parametrize("name,invoke", _OBSERVE_SENDS, ids=_OBSERVE_IDS)
def test_observe_doorway_proceeds_when_killswitch_clear(monkeypatch, name, invoke):
    """Control: in observe mode a clear switch must NOT over-block."""
    _observe_runtime(monkeypatch)
    _arm_clear(monkeypatch)
    post = _RecordingPost()
    invoke(post)
    assert len(post.calls) >= 1, f"{name} was blocked with killswitch CLEAR (over-block)"


# --- structural completeness: no public send can bypass the gate -------------

def test_every_public_send_routes_through_the_gated_chokepoint():
    """Completeness ratchet (finding cp1-P3): EVERY module-level PUBLIC function
    in channel.py that takes an ``http_post`` parameter — the send signature;
    receive() takes http_get, render_markdown neither — must reach the SEC-3
    killswitch. It does so either by calling a gated spine (``_post_one``
    directly, or ``_send_impl`` / ``_gated_method`` which both funnel into
    ``_post_one``) OR by being ``send_document``, which carries its own
    ``_killswitch_halted`` gate on the multipart transport. A future send wrapper
    that posts without routing through one of these fails HERE — it cannot
    silently bypass the emergency stop. Paired with the harness C5 check so both
    the golden-eval runner and the unit suite enforce completeness."""
    src = Path(channel.__file__).read_text()
    tree = ast.parse(src)
    spines = {"_post_one", "_send_impl", "_gated_method"}

    def callees(fn):
        return {n.func.id for n in ast.walk(fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}

    funcs = {n.name: n for n in tree.body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    # The two INDIRECT spines must themselves reach _post_one, else "routes
    # through _send_impl / _gated_method" would be a hollow guarantee.
    for spine in ("_send_impl", "_gated_method"):
        assert spine in funcs, f"gated spine {spine} vanished from channel.py"
        assert "_post_one" in callees(funcs[spine]), \
            f"gated spine {spine} no longer routes through _post_one"

    public_sends = {
        name: fn for name, fn in funcs.items()
        if not name.startswith("_")
        and "http_post" in ({a.arg for a in fn.args.args}
                            | {a.arg for a in fn.args.kwonlyargs})
    }
    # Guard the guard: the discovery must actually find the send surface (a
    # refactor that renamed http_post everywhere would otherwise vacuously pass).
    assert {"send", "send_document", "open_thread",
            "reply_current_observe_only", "react_current_observe_only"} <= set(public_sends)
    for name, fn in public_sends.items():
        cs = callees(fn)
        gated = bool(cs & spines) or (name == "send_document" and "_killswitch_halted" in cs)
        assert gated, (
            f"public send {name} reaches no gated spine {sorted(spines)} and is "
            f"not send_document — it can bypass the killswitch")
