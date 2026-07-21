#!/usr/bin/env python3
"""Killswitch send-path eval harness — EVAL-002 (front-door fail-closed).

Mechanical PASS/FAIL law for the KILLSWITCH SEND-PATH golden eval (eval body:
memory/golden-evals/eval-002-killswitch-send-path.md — staged via
docs/proposals/germline-amendment-killswitch-send-eval-2026-07-21.md; that
directory is schg-locked on the live checkout, so the runnable half lives here,
non-germline, wired into cabinet/scripts/run-golden-evals.sh as section
EVAL-002-KILLSWITCH-SEND).

The law it enforces:

  When the Captain's emergency stop is armed (Redis ``cabinet:killswitch`` ==
  ``active``) OR the control plane is unreachable, EVERY front-door Telegram
  send is REFUSED — zero bytes leave the process — and the method returns a
  structured refusal, never raises. A CLEAR switch must not over-block. The
  front door REUSES action_exec's ONE SEC-3 killswitch reader, never a second.

  This is the send-path twin of EVAL-001 (which pins the killswitch at the
  pre-tool-use HOOK layer). EVAL-001 stops an officer's Bash/Write; this stops
  the officer's outbound Telegram — the two layers together mean an armed stop
  halts both what the org DOES and what it SAYS.

Deterministic by design — no network, no Redis, no subprocess. The killswitch
state is driven IN-PROCESS by patching action_exec's reader (the very reader
channel delegates to); the transport is a recording fake that a refused send
must never touch. Hermetic: feed/lessons writes are pointed at a throwaway dir.

Checks:
  C1  active-halts      every public send refuses under killswitch ``active``
                        (zero transport calls, ``sent`` is False, killswitch-cited)
  C2  unreachable-halts every public send refuses when the reader RAISES
                        (Redis down) — fail-closed, never fail-open
  C3  clear-proceeds    every public send reaches the transport under ``clear``
                        (no over-block)
  C4  single-reader     channel defines no second reader AND patching
                        ``action_exec._killswitch_state`` flips the front door

Fail-closed: an unimportable module, a raising send, or a send that transmits
under a halt is a FAIL, never a skip. Only a missing interpreter skips (runner).

SECURITY: --repo-root is operator-supplied, read-only, never interpolated into
a shell. No fixture is executed; the transport is inert.

Usage:
  python3.12 harness.py --self-test [--repo-root DIR]
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]

_TOKEN = "123456:EVAL-BOT-TOKEN-do-not-leak"
_CAPTAIN = "98765432"


def _violation(msg: str) -> None:
    print(f"KILLSWITCH-SEND-EVAL VIOLATION: {msg}")


class _RecordingPost:
    """Records every transport invocation (any arity — the 2-arg JSON post and
    the 4-arg multipart document post). A refused send must leave this EMPTY."""

    def __init__(self):
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return {"ok": True, "result": {"message_id": 42}}


def _active(_key):
    return "active"


def _clear(_key):
    return ""


def _boom(_key):
    raise ConnectionError("redis unreachable")


def _refused(result, post) -> bool:
    """A structured, killswitch-attributed refusal that never touched the wire."""
    return (
        not post.calls
        and result.get("sent") is False
        and "killswitch" in str(result).lower()
    )


def run_self_test(repo_root: Path) -> int:
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        import framework.env as env
        import framework.frontdoor.action_exec as action_exec
        import framework.frontdoor.channel as channel
    except Exception as exc:  # noqa: BLE001 — an unimportable seam is a FAIL
        _violation(f"front-door modules unimportable: {exc!r}")
        return 1

    failures = 0

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        doc = tmp / "secret.txt"
        doc.write_text("classified payload")

        @contextlib.contextmanager
        def _runtime(reader):
            """Simulate the runtime (sends allowed), configured, no Redis
            threading, hermetic feed/lessons, with the killswitch ``reader``
            wired into action_exec's ONE reader slot."""
            with contextlib.ExitStack() as es:
                es.enter_context(mock.patch.dict(os.environ, {
                    "TELEGRAM_COS_TOKEN": _TOKEN,
                    "CAPTAIN_TELEGRAM_ID": _CAPTAIN,
                    "CABINET_FEED_DIR": str(tmp / "feed"),
                    "CABINET_ACTION_LESSONS": str(tmp / "lessons.yml"),
                }, clear=False))
                es.enter_context(mock.patch.object(env, "allow_sends", lambda: True))
                es.enter_context(mock.patch.object(channel, "_last_captain_msg_id", lambda: None))
                es.enter_context(mock.patch.object(action_exec, "_redis_get_strict", reader))
                yield

        @contextlib.contextmanager
        def _observe_runtime(reader):
            """The sticky observe-only doorway runtime. reply_current_observe_only
            and react_current_observe_only are structurally CLOSED whenever
            ``allow_sends()`` is True — they short-circuit to blocked-observe-only
            before any transport. They can reach the wire ONLY in sticky observe
            mode (``allow_sends()`` False AND ``CABINET_OBSERVE_ONLY=1``), with a
            current Captain inbound id present. That is therefore the one mode in
            which the killswitch must be shown to halt them. Same single
            action_exec ``reader``."""
            with contextlib.ExitStack() as es:
                es.enter_context(mock.patch.dict(os.environ, {
                    "TELEGRAM_COS_TOKEN": _TOKEN,
                    "CAPTAIN_TELEGRAM_ID": _CAPTAIN,
                    "CABINET_OBSERVE_ONLY": "1",
                    "CABINET_FEED_DIR": str(tmp / "feed"),
                    "CABINET_ACTION_LESSONS": str(tmp / "lessons.yml"),
                }, clear=False))
                es.enter_context(mock.patch.object(env, "allow_sends", lambda: False))
                es.enter_context(mock.patch.object(channel, "_last_captain_msg_id", lambda: 55))
                es.enter_context(mock.patch.object(action_exec, "_redis_get_strict", reader))
                yield

        # Every public front-door send, each tagged with the runtime that lets it
        # actually reach the transport. All but the two observe-only doorways send
        # under the standard runtime; open_thread rides _gated_method (same
        # _post_one chokepoint as pin/unpin). send_document rides the multipart
        # transport (bypasses _post_one) and carries its own copy of the gate.
        std_sends = [
            ("send", lambda p: channel.send("hi captain", http_post=p), _runtime),
            ("send_poll", lambda p: channel.send_poll("q?", ["a", "b"], http_post=p), _runtime),
            ("send_draft", lambda p: channel.send_draft(7, "streaming", http_post=p), _runtime),
            ("send_rich", lambda p: channel.send_rich(markdown="**hi**", http_post=p), _runtime),
            ("edit_message", lambda p: channel.edit_message(55, "new text", http_post=p), _runtime),
            ("answer_callback", lambda p: channel.answer_callback("c1", "toast", http_post=p), _runtime),
            ("set_typing", lambda p: channel.set_typing("typing", http_post=p), _runtime),
            ("pin", lambda p: channel.pin(55, http_post=p), _runtime),
            ("unpin", lambda p: channel.unpin(55, http_post=p), _runtime),
            ("set_reaction", lambda p: channel.set_reaction(55, "👍", http_post=p), _runtime),
            ("open_thread", lambda p: channel.open_thread("lane-alpha", http_post=p), _runtime),
        ]
        # The two observe-only doorways — live ONLY under _observe_runtime.
        observe_sends = [
            ("reply_current_observe_only",
             lambda p: channel.reply_current_observe_only("hi captain", http_post=p),
             _observe_runtime),
            ("react_current_observe_only",
             lambda p: channel.react_current_observe_only("👍", http_post=p),
             _observe_runtime),
        ]
        doc_send = ("send_document",
                    lambda p: channel.send_document(str(doc), http_post=p), _runtime)
        all_sends = std_sends + observe_sends + [doc_send]

        # C1 — killswitch ACTIVE halts every send.
        for name, invoke, rt in all_sends:
            with rt(_active):
                post = _RecordingPost()
                try:
                    result = invoke(post)
                except Exception as exc:  # noqa: BLE001 — a halt must never raise
                    failures += 1
                    _violation(f"C1 {name}: RAISED under active killswitch: {exc!r}")
                    continue
            if not _refused(result, post):
                failures += 1
                _violation(f"C1 {name}: not refused under ACTIVE "
                           f"(calls={len(post.calls)}, result={result})")

        # C2 — UNREACHABLE control plane halts every send (fail-closed).
        for name, invoke, rt in all_sends:
            with rt(_boom):
                post = _RecordingPost()
                try:
                    result = invoke(post)
                except Exception as exc:  # noqa: BLE001
                    failures += 1
                    _violation(f"C2 {name}: RAISED under unreachable Redis: {exc!r}")
                    continue
            if not _refused(result, post):
                failures += 1
                _violation(f"C2 {name}: not refused when Redis UNREACHABLE "
                           f"(calls={len(post.calls)}, result={result})")

        # C3 — CLEAR switch must NOT over-block: the send reaches the transport.
        for name, invoke, rt in all_sends:
            with rt(_clear):
                post = _RecordingPost()
                result = invoke(post)
            if len(post.calls) < 1 or result.get("sent") is not True:
                failures += 1
                _violation(f"C3 {name}: blocked under CLEAR killswitch "
                           f"(calls={len(post.calls)}, result={result})")

        # C4 — single reader: no second reader in channel, and the halt routes
        # through action_exec's shared _killswitch_state.
        src = Path(channel.__file__).read_text()
        if "def _killswitch_state" in src or "def _redis_get_strict" in src:
            failures += 1
            _violation("C4: channel.py defines a SECOND killswitch reader")
        if "from framework.frontdoor.action_exec import" not in src:
            failures += 1
            _violation("C4: channel.py does not import the shared SEC-3 reader")
        with _runtime(_clear):
            with mock.patch.object(action_exec, "_killswitch_state", lambda getter: "active"):
                post = _RecordingPost()
                result = channel.send("hi", http_post=post)
            if post.calls or result.get("sent") is not False:
                failures += 1
                _violation("C4: front door does not route through "
                           "action_exec._killswitch_state (single reader)")

        # C5 — completeness: EVERY public send routes through the gated chokepoint.
        # Statically, each module-level PUBLIC function that takes an ``http_post``
        # parameter (the send signature; receive() takes http_get, render_markdown
        # neither) must reach the killswitch either by calling a gated spine
        # (_post_one directly, or _send_impl / _gated_method — both of which funnel
        # into _post_one) OR be send_document, which carries its OWN
        # _killswitch_halted gate on the multipart transport. A future wrapper that
        # posts without routing through one of these trips this check — so a new
        # send cannot silently bypass the emergency stop.
        tree = ast.parse(src)
        spines = {"_post_one", "_send_impl", "_gated_method"}

        def _callees(fn):
            return {n.func.id for n in ast.walk(fn)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}

        funcs = {n.name: n for n in tree.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        # Transitivity: the two INDIRECT spines must themselves reach _post_one,
        # else routing "through _send_impl / _gated_method" would be a dead claim.
        for spine in ("_send_impl", "_gated_method"):
            if spine not in funcs or "_post_one" not in _callees(funcs[spine]):
                failures += 1
                _violation(f"C5: gated spine {spine} no longer routes through _post_one")
        for name, fn in funcs.items():
            if name.startswith("_"):
                continue
            arg_names = {a.arg for a in fn.args.args} | {a.arg for a in fn.args.kwonlyargs}
            if "http_post" not in arg_names:
                continue  # not a send
            callees = _callees(fn)
            gated = bool(callees & spines) or (
                name == "send_document" and "_killswitch_halted" in callees)
            if not gated:
                failures += 1
                _violation(f"C5: public send {name} reaches no gated spine and is "
                           f"not send_document — it can bypass the killswitch")

    verdict = "FAIL" if failures else "PASS"
    print(f"KILLSWITCH-SEND-EVAL: {verdict} — {len(all_sends)} front-door sends "
          f"refuse under active & unreachable, proceed under clear; one shared "
          f"SEC-3 reader; every public send statically gated "
          f"({failures} violation(s))")
    return 1 if failures else 0


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(prog="killswitch-send-eval-harness")
    parser.add_argument("--self-test", action="store_true", required=True)
    parser.add_argument("--repo-root", default=str(_REPO_ROOT))
    args = parser.parse_args(argv)
    return run_self_test(Path(args.repo_root))


if __name__ == "__main__":
    sys.exit(main())
