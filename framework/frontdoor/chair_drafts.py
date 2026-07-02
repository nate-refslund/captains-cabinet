"""Chair-owned draft flow.

Captain directive (2026-06-24, "make the drafts end here in this chat"): ALL
outbound drafts present in the Chair chat (@NateHQChairBot) via present_draft()
and deliver post-approval via deliver_draft(), using the screenpipe send libs
(email_lib / teams_graph_lib) directly. The screenpipe bot is no longer in the
approval path — it is back-end (capture/index) only.

Approval gate is preserved: deliver_draft() is the egress and runs ONLY after
Nate replies 'send' to a presented draft in the Chair chat. The Chair reply
handler (cos session, via the inbound watchdog's reply-threading) maps a
'send'/'edit:'/'skip:' reply back to the pid and calls deliver_draft().
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time

from framework.frontdoor import channel

_SHARED = os.path.expanduser("~/.screenpipe/pipes/_shared")
_REDIS_H = os.environ.get("REDIS_HOST", "localhost")


def _r(*args: str) -> str:
    return subprocess.run(
        ["redis-cli", "-h", _REDIS_H, *args], capture_output=True, text=True
    ).stdout.strip()


def _load_shared_env() -> None:
    """email_lib / teams_graph_lib read Graph/Make creds from _shared/.env."""
    envf = os.path.join(_SHARED, ".env")
    if not os.path.exists(envf):
        return
    for line in open(envf, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _apply_signature(draft: str, channel_name: str) -> str:
    """Close every email with Nate's exact default signature (never Teams).
    Uses draft_lib.ensure_signature (idempotent — won't double-sign)."""
    try:
        if _SHARED not in sys.path:
            sys.path.insert(0, _SHARED)
        import draft_lib
        return draft_lib.ensure_signature(draft, channel_name)
    except Exception:
        return draft


def present_draft(person: str, channel_name: str, draft: str,
                  recipient_email: str = "", subject: str = "",
                  why: str = "", slug: str = "") -> str:
    """Present a draft in the Chair chat with a short pid; store it for delivery.

    Returns the pid. Nate replies 'send' (or 'send <pid>') in the Chair chat to
    deliver, 'edit: <text>' to send his version, 'skip: <why>' to drop it.
    """
    draft = _apply_signature(draft, channel_name)
    pid = hashlib.sha1(f"{person}{draft}{time.time()}".encode()).hexdigest()[:6]
    payload = {
        "slug": slug or person.lower().replace(" ", "-"),
        "person": person, "draft": draft, "channel": channel_name,
        "recipient_email": recipient_email, "subject": subject,
        "last_subject": subject, "why": why, "lane": "send-1to1-reply",
    }
    _r("SET", f"cabinet:draft:{pid}", json.dumps(payload, ensure_ascii=False),
       "EX", "604800")
    via = "Teams" if channel_name.lower() == "teams" else "email"
    dest = f" <{recipient_email}>" if recipient_email else ""
    # B-2 defense-in-depth (cp2 re-review 2026-07-03): strip the marker char from
    # the (possibly external) display name so it can't forge a second ·…· marker.
    safe_person = (person or "").replace("·", "")
    blocks = [f"✍️ Draft {via} to *{safe_person}*{dest}  ·{pid}·", "", draft]
    if why:
        blocks += ["", f"_{why}_"]
    blocks += ["", f"Reply *send* / *edit: <text>* / *skip: <why>*  (or `send {pid}`)"]
    channel.send("\n".join(blocks))
    return pid


def _strip_subject(s: str) -> str:
    """Normalize a subject for thread-matching (drop SV:/Re:/VS:/Fwd: prefixes)."""
    import re
    return re.sub(r'^((sv|re|vs|fw|fwd|ang)\s*:\s*)+', '', (s or '').strip(),
                  flags=re.I).strip().lower()


def _to_html(text: str) -> str:
    """Plain-text draft -> minimal HTML that PRESERVES line breaks. Both the
    Graph /reply and the HTML send path render HTML, which collapses raw
    newlines (the bug that flattened the first Morten reply into one line)."""
    import html as _h
    return _h.escape(text or "").replace("\n", "<br>\n")


def _resolve_thread_gid(addr: str, subject: str):
    """Find the most recent inbox message FROM addr matching this subject so the
    reply threads into it (Captain 2026-06-24: "that's how the final email should
    work"). Returns (graph_id, conversationId), or (None, None) when there is no
    thread to reply into — then deliver_draft sends a fresh email. Best-effort:
    any Graph hiccup degrades to a fresh send."""
    try:
        import email_lib as _el
    except Exception:
        return None, None
    want = _strip_subject(subject)
    if not want or not addr:
        return None, None
    r = _el.msgraph_call(url="/v1.0/me/mailFolders/inbox/messages", top=120,
                         select="id,conversationId,subject,from,receivedDateTime",
                         orderby="receivedDateTime desc")
    for m in (r.get("value") if isinstance(r, dict) else None) or []:
        f = ((m.get("from") or {}).get("emailAddress", {}) or {})
        if str(f.get("address", "")).lower() != (addr or "").lower():
            continue
        cs = _strip_subject(m.get("subject"))
        if cs and (cs == want or want in cs or cs in want):
            return m.get("id"), m.get("conversationId")
    return None, None


def _verify_sent(conv: str):
    """Confirm a /reply landed in Sent Items under the original conversation."""
    try:
        import email_lib as _el
    except Exception:
        return None
    s = _el.msgraph_call(url="/v1.0/me/mailFolders/sentitems/messages", top=5,
                         select="conversationId,sentDateTime", orderby="sentDateTime desc")
    for m in (s.get("value") if isinstance(s, dict) else None) or []:
        if m.get("conversationId") == conv:
            return {"ok": True, "sent": True, "threaded": True}
    return None


def deliver_draft(pid: str, override_text: str = "", dry_run: bool = False) -> dict:
    """Send the stored draft via the screenpipe send libs. Post-approval egress —
    call ONLY after Nate approved in the Chair chat. Clears the draft on success.

    dry_run=True wires everything (load draft, env, import the send lib) but does
    NOT send — used to verify the path without an actual egress.
    """
    raw = _r("GET", f"cabinet:draft:{pid}")
    if not raw:
        return {"ok": False, "error": f"no draft {pid} (expired or already sent)"}
    p = json.loads(raw)
    text = override_text or p.get("draft", "")
    addr = p.get("recipient_email", "")
    is_teams = (p.get("channel") or "").lower() == "teams"
    subject = (p.get("subject") or "").strip() or (
        f"Re: {p.get('last_subject')}".strip() if p.get("last_subject") else "Re: (din besked)")
    _load_shared_env()
    if _SHARED not in sys.path:
        sys.path.insert(0, _SHARED)
    try:
        if is_teams:
            import teams_graph_lib as _tg  # noqa: F401  (import-check in dry_run)
            if dry_run:
                return {"ok": True, "dry_run": True, "via": "Teams", "dest": addr}
            res = _tg.send_teams_to_email(addr, text, name=p.get("person"))
        else:
            import email_lib as _el
            if not addr:
                return {"ok": False, "error": f"no email for {p.get('person')}"}
            gid, conv = _resolve_thread_gid(addr, subject)
            if dry_run:
                return {"ok": True, "dry_run": True, "via": "email", "dest": addr,
                        "subject": subject, "threaded": bool(gid)}
            html = _to_html(text)
            if gid:
                # Guard: if a reply already exists in this thread, NEVER resend
                # (the 4x-Morten incident). And retries=0 below: a /reply is not
                # idempotent, so the proxy must never auto-retry it.
                if _verify_sent(conv):
                    res = {"ok": True, "sent": True, "threaded": True, "note": "already-replied"}
                else:
                    _el.msgraph_call(
                        url="/v1.0/me/messages/" + gid + "/reply", method="POST",
                        body={"message": {"body": {"contentType": "HTML", "content": html}}},
                        retries=0)
                    res = _verify_sent(conv) or {"ok": True, "sent": True, "threaded": True}
            else:
                res = _el.send_email(addr, subject, html, content_type="HTML")  # no thread -> fresh
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    if isinstance(res, dict) and res.get("ok"):
        _r("DEL", f"cabinet:draft:{pid}")
        res["dest"] = addr or p.get("person")
        res["via"] = "Teams" if is_teams else "email"
    return res
