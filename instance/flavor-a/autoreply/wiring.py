"""Live wiring for the scoped Kristoffer-UAT auto-reply — ships DISARMED.

``kristoffer_uat.handle_message`` is a pure decision core with every
side-effecting collaborator injected. THIS module supplies the real ones and is
the only place the lane touches Redis / the send backend / Telegram. Keeping the
wiring separate means the core is trivially testable AND the live blast radius is
one small, readable file.

DISARMED BY DEFAULT. Nothing here arms the lane. The arm flag
(``cabinet:autoreply:kristoffer-uat:enabled``) is set ONLY by an explicit
``arm()`` call (which the Captain authorises) — never on import, never as a
side effect of a dry-run or a status check.

The approved SEND BACKEND (single-egress rule, brain-bridge.md): this lane sends
through the SAME backend a human "send" reply already uses —
``framework.frontdoor.chair_drafts.deliver_draft`` (the Chair-owned egress, live
per the 2026-06-24 directive), via a draft stored exactly like a presented
draft. It is NOT a raw Teams/Graph/Make call. If you ever swap this for the brain
``queue_draft`` delivery, that is also an approved backend — the rule is "an
approved backend, fired without the human tap", never a new egress path.

System Python compatible (3.9+): stdlib + in-repo only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from framework.env import captain_name

from . import kristoffer_uat as K

# Repo root is 4 levels up: instance/flavor-a/autoreply/wiring.py -> repo root
# (this cell moved out of framework/ into instance/flavor-a/, so parents[3]).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_REDIS_H = os.environ.get("REDIS_HOST", "localhost")

#: Local audit log (append-only JSONL). Lives under the runtime state dir so it
#: survives restarts and is greppable. Never holds a secret.
AUDIT_LOG = Path(
    os.environ.get("CABINET_AUTOREPLY_LOG")
    or (Path.home() / ".cabinet" / "autoreply" / "kristoffer-uat.jsonl")
)


# ---------------------------------------------------------------------------
# Injected collaborators — the REAL ones.
# ---------------------------------------------------------------------------

def _redis_get(key: str) -> Optional[str]:
    """Read a Redis string (redis-cli subprocess, the repo convention). Any
    failure returns None, which every gate treats as fail-closed (disarmed /
    halted). Never raises."""
    try:
        out = subprocess.run(
            ["redis-cli", "-h", _REDIS_H, "GET", key],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        return out or None
    except Exception:
        return None


def _redis_set(key: str, value: str, ex: Optional[int] = None) -> bool:
    args = ["redis-cli", "-h", _REDIS_H, "SET", key, value]
    if ex:
        args += ["EX", str(int(ex))]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def _redis_del(key: str) -> bool:
    try:
        r = subprocess.run(["redis-cli", "-h", _REDIS_H, "DEL", key],
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def _send_backend(draft: Dict[str, Any]) -> Any:
    """The APPROVED egress: present the bounded ack as a Chair draft, then call
    ``chair_drafts.deliver_draft`` on it — the exact post-approval send path a
    human "send" reply triggers. No new egress; the only difference is that this
    lane (when armed + in-scope) supplies the approval in code.

    Gated underneath by ``framework.env.allow_sends()`` (deliver_draft uses the
    screenpipe send libs, which the runtime env enables) — so a dev/test session
    physically cannot send here either.
    """
    from framework.frontdoor import chair_drafts
    pid = chair_drafts.present_draft(
        person=draft.get("person", "Kristoffer Møller Nielsen"),
        channel_name=draft.get("channel", "teams"),
        draft=draft.get("draft", ""),
        recipient_email=draft.get("recipient_email", "krmoj@step.dk"),
        why=draft.get("why", "scoped Kristoffer-UAT auto-ack"),
        slug=draft.get("slug", K.KRISTOFFER_SLUG),
    )
    return chair_drafts.deliver_draft(pid)


def _copy_to_nate(text: str) -> Any:
    """Send a copy of the auto-ack to the Captain via the cabinet's ONLY Captain
    path (``framework.frontdoor.channel.send``). Itself gated by ``allow_sends()``
    — a non-runtime session returns ``blocked-dev`` (the sample still composes)."""
    from framework.frontdoor import channel
    return channel.send(text)


def _route_bug(item: Dict[str, Any]) -> Any:
    """Route the UAT bug to polads-ceo via the standard officer trigger
    (``notify-officer.sh`` -> Redis stream -> the officer's session). Raises on
    failure so handle_message records ``routed=False`` (the Captain sees it)."""
    officer = item.get("officer", K.ROUTE_OFFICER)
    sender = item.get("sender", "Kristoffer")
    topic = item.get("topic", "")
    ref = item.get("ref", "")
    msg = (f"[Kristoffer UAT auto-reply] new UAT bug from {sender}: {topic}. "
           f"Acked automatically; please triage + work the fix"
           + (f" (ref {ref})" if ref else "") + ". Full text in the thread.")
    script = _REPO_ROOT / "cabinet" / "scripts" / "notify-officer.sh"
    r = subprocess.run(["bash", str(script), officer, msg],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise RuntimeError(f"notify-officer.sh exit {r.returncode}: {r.stderr.strip()[:120]}")
    return {"ok": True}


def _audit(rec: dict) -> None:
    """Append the decision record as JSONL AND mirror to the brain reasoning log
    (best-effort). Local file is the always-on audit; log_reasoning feeds the
    reasoning-review governance loop."""
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG, "a", encoding="utf-8") as fh:
            fh.write(K.jsonl(rec) + "\n")
    except Exception:
        pass
    # Mirror to the brain reasoning log when the helper is importable (runtime).
    try:
        _log_reasoning(rec)
    except Exception:
        pass


def _log_reasoning(rec: dict) -> None:
    """Best-effort bridge to the brain MCP reasoning log so an auto-send is
    auditable exactly like the screenpipe pipes (brain-bridge.md governance).
    Imports the screenpipe agent_reasoning lib directly (the same one the brain
    server wraps) — no network, no MCP round-trip needed from a wiring call."""
    shared = os.path.expanduser("~/.screenpipe/pipes/_shared")
    if shared not in sys.path:
        sys.path.insert(0, shared)
    import agent_reasoning  # type: ignore
    cap = captain_name()
    agent_reasoning.log(
        action=f"autoreply-{rec.get('decision', '')}",
        subject=rec.get("topic", "")[:120],
        rationale=rec.get("reason", "")[:300],
        expectation=f"Kristoffer acked + bug routed to polads-ceo; {cap} copied",
        pipe="autoreply-kristoffer-uat",
        ref=rec.get("ref", ""),
    )


# ---------------------------------------------------------------------------
# Public entry points.
# ---------------------------------------------------------------------------

def process(sender: str, channel: str, text: str, *,
            eta: str = "", ref: str = "") -> dict:
    """LIVE entry: process one inbound Kristoffer Teams message through the gates.

    Wires the real collaborators into ``kristoffer_uat.handle_message``. Because
    the lane ships DISARMED, the default outcome on a genuine UAT report is
    ``disarmed`` (gate 2) — it will NOT send until ``arm()`` has been called.
    Returns the full decision result.
    """
    return K.handle_message(
        sender=sender, channel=channel, text=text,
        redis_get=_redis_get, send_backend=_send_backend,
        copy_to_nate=_copy_to_nate, audit=_audit, route_bug=_route_bug,
        eta=eta, ref=ref, dry_run=False,
    )


def dry_run_sample(sender: str = "krmoj@step.dk", channel: str = "teams",
                   text: str = "",
                   eta: str = "we're aiming to have a fix in the next deploy",
                   ref: str = "") -> dict:
    """Produce a SAMPLE auto-ack and send it to THE CAPTAIN ONLY (clearly labelled
    as a dry-run sample), so they can approve the exact behaviour before the lane
    is armed. Sends NOTHING to Kristoffer, routes NOTHING to polads-ceo. Safe to
    run any time, armed or not — ``dry_run=True`` short-circuits every egress
    except the labelled Captain copy.
    """
    if not text:
        cap = captain_name()
        text = (
            f"Hi {cap} - the publisher VIES auto-fill is broken on "
            "staging: clicking 'fetch company data' returns a 500 and "
            "the form stays empty. Repro: /register, type a CVR, hit "
            "fetch. Expected it to populate name/address.")
    return K.handle_message(
        sender=sender, channel=channel, text=text,
        redis_get=_redis_get, send_backend=_send_backend,
        copy_to_nate=_copy_to_nate, audit=_audit, route_bug=_route_bug,
        eta=eta, ref=ref, dry_run=True,
    )


def arm(ttl_seconds: Optional[int] = None, *, note: str = "") -> dict:
    """ARM the lane — the explicit Captain action. Sets the arm flag to "1".

    This is intentionally a separate, explicit call (never reached from process/
    dry-run): only an operator/Captain-initiated invocation arms auto-send.
    ``ttl_seconds`` (optional) makes the arm auto-expire — a useful safety
    default (e.g. arm for a UAT session, auto-disarm after). Records an audit
    line either way.
    """
    ok = _redis_set(K.ARM_FLAG_KEY, "1", ex=ttl_seconds)
    rec = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lane": "autoreply:kristoffer-uat", "decision": "armed",
        "reason": (note or "armed by operator") + (
            f" (auto-disarm in {ttl_seconds}s)" if ttl_seconds else " (no expiry)"),
        "ok": ok,
    }
    _audit(rec)
    return {"armed": ok, "ttl_seconds": ttl_seconds, "audit": rec}


def disarm(*, note: str = "") -> dict:
    """DISARM the lane immediately — delete the arm flag. The instant kill."""
    ok = _redis_del(K.ARM_FLAG_KEY)
    rec = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lane": "autoreply:kristoffer-uat", "decision": "disarmed",
        "reason": note or "disarmed by operator", "ok": ok,
    }
    _audit(rec)
    return {"disarmed": ok, "audit": rec}


def status() -> dict:
    """Report the lane's live state without changing anything: armed?, global
    killswitch?, audit log path + last few decisions."""
    arm_val = _redis_get(K.ARM_FLAG_KEY)
    armed, arm_reason = K.is_armed(_redis_get)
    clear, ks_reason = K.killswitch_clear(_redis_get)
    last: list = []
    try:
        if AUDIT_LOG.exists():
            lines = AUDIT_LOG.read_text(encoding="utf-8").splitlines()[-5:]
            last = [json.loads(x) for x in lines if x.strip()]
    except Exception:
        last = []
    return {
        "armed": armed, "arm_flag_value": arm_val, "arm_reason": arm_reason,
        "killswitch_clear": clear, "killswitch_reason": ks_reason,
        "arm_flag_key": K.ARM_FLAG_KEY,
        "global_killswitch_key": K.GLOBAL_KILLSWITCH_KEY,
        "audit_log": str(AUDIT_LOG), "recent_decisions": last,
    }


# ---------------------------------------------------------------------------
# CLI (run from the repo root — package parent on PYTHONPATH so `autoreply`
# resolves, cwd supplies the `framework` namespace package):
#   PYTHONPATH=instance/flavor-a python -m autoreply.wiring <status|sample|arm|disarm>
# `sample` is the one the Captain runs to see the exact ack before arming.
# ---------------------------------------------------------------------------

def _main(argv: list) -> int:
    cmd = (argv[0] if argv else "status").lower()
    if cmd == "status":
        print(json.dumps(status(), indent=2, ensure_ascii=False, default=str))
    elif cmd == "sample":
        res = dry_run_sample()
        print(json.dumps({"decision": res["decision"], "ack": res.get("ack"),
                          "nate_copy": res.get("nate_copy"),
                          "copied_to_nate": res.get("copied")},
                         indent=2, ensure_ascii=False, default=str))
    elif cmd == "arm":
        ttl = int(argv[1]) if len(argv) > 1 else None
        print(json.dumps(arm(ttl_seconds=ttl, note="armed via CLI"),
                         indent=2, ensure_ascii=False, default=str))
    elif cmd == "disarm":
        print(json.dumps(disarm(note="disarmed via CLI"),
                         indent=2, ensure_ascii=False, default=str))
    else:
        print("usage: PYTHONPATH=instance/flavor-a python -m autoreply.wiring "
              "<status|sample|arm [ttl_seconds]|disarm>", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
