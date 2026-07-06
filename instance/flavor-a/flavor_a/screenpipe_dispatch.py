"""``flavor_a.screenpipe_dispatch`` — the Flavor-A personal-DISPATCH adapter (SRC-3).

``ScreenpipeDispatch`` is the launcher-neutral ``PersonalDispatch`` for THIS
deployment (captain Nate, Flavor-A / screenpipe brain). It OWNS the WRITE/actuator
half of the frontdoor egress — the screenpipe send libs + the vault daily-note
write + the captain's Monday board client + the synthesis LLM — that framework
CORE must not name. Framework's ``framework.frontdoor.chair_drafts`` and
``framework.frontdoor.daily_recap`` reach it ONLY through
``framework.sources.get_dispatch()``; framework itself names no screenpipe lib.

The method bodies are the FORMER ``chair_drafts`` send path + ``daily_recap``
vault-write / Monday-client / LLM-model bodies, re-homed here **byte-identical**
(source-adapter-boundary spec §5 P2.4, §6 "frontdoor · egress" HOTTEST row): on
Nate's instance every send + every note render is byte-for-byte what ran when
those bodies lived in ``framework/``, so every existing frontdoor test — and the
``test_daily_recap_golden.py`` obsidian-sync hash-pin — stays green.

Method map (launcher-neutral name ← the framework body it re-homes):
  * ``ensure_signature`` ← ``chair_drafts._apply_signature`` (``draft_lib.ensure_signature``)
  * ``deliver``          ← ``chair_drafts.deliver_draft``'s SEND execution
                           (``email_lib`` Graph thread-resolution + reply/fresh +
                           verify-sent, ``teams_graph_lib.send_teams_to_email``);
                           the redis draft GET/DEL stays cabinet-side in framework.
  * ``write_daily_note`` ← ``daily_recap._write_vault`` (OBSIDIAN_VAULT_PATH,
                           marker-guarded, sha256 write-if-changed)
  * ``daily_note_path``  ← ``daily_recap._vault_path`` (dry-preview path)
  * ``monday``           ← ``daily_recap._sp`` (``sp_lib`` with env loaded)
  * ``llm_model``        ← ``daily_recap._raw_llm``'s ``commitments_lib.LLM_MODEL``

**Instance-scoped by construction.** This module MAY import the screenpipe
``_shared`` libs — the coupling ``framework/`` CORE must not have. It is bound only
through ``instance/config/sources.yml`` (``dispatch:``) + ``get_dispatch()``;
framework never imports it. It satisfies ``framework.sources.base.PersonalDispatch``
**structurally** (a ``runtime_checkable`` ``Protocol`` — no inheritance).

**Cheap + side-effect-free to construct.** Every screenpipe lib is imported
**lazily** inside the method that uses it (mirroring the former framework bodies),
and the ``~/.screenpipe`` ``sys.path`` insert + ``_shared/.env`` load happen only
on first send/board/model use — so ``get_dispatch()`` → ``ScreenpipeDispatch()``
neither touches ``sys.path`` nor imports a lib nor crashes until a caller actually
dispatches. ``daily_note_path`` is pure path arithmetic (no screenpipe), so a dry
preview is safe on any box. Zero-arg constructible (the ``sources.yml`` contract).

py3.9-compatible: ``from __future__ import annotations`` + ``typing.Optional``,
no ``match``/``case``; module-load imports are stdlib only.
"""
from __future__ import annotations

import hashlib
import html as _html
import os
import re
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# The screenpipe estate lives OUTSIDE the cabinet tree. The send libs
# (email_lib / teams_graph_lib / draft_lib) and the daily-recap libs (sp_lib /
# commitments_lib) resolve off ``~/.screenpipe/pipes[/_shared]`` on sys.path —
# the exact paths the former framework bodies used (chair_drafts._SHARED,
# daily_recap._PIPES/_SHARED). Added LAZILY (never at import) so constructing the
# adapter is side-effect-free.
# ---------------------------------------------------------------------------
_PIPES = os.path.expanduser("~/.screenpipe/pipes")
_SHARED = os.path.join(_PIPES, "_shared")


def _ensure_shared_path() -> None:
    """Put ``~/.screenpipe/pipes`` + ``~/.screenpipe/pipes/_shared`` on sys.path
    (idempotent) so the screenpipe libs import — the superset of what
    chair_drafts (``_SHARED``) and daily_recap (``_PIPES`` + ``_SHARED``) each
    inserted. Extra entries are harmless; this only fixes WHERE the libs resolve."""
    for _p in (_PIPES, _SHARED):
        if _p not in sys.path:
            sys.path.insert(0, _p)


def _load_shared_env() -> None:
    """email_lib / teams_graph_lib read Graph/Make creds from ``_shared/.env``.
    Byte-identical to the former ``chair_drafts._load_shared_env``:
    ``os.environ.setdefault`` (never overrides a set var), quote-stripped."""
    envf = os.path.join(_SHARED, ".env")
    if not os.path.exists(envf):
        return
    for line in open(envf, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ---------------------------------------------------------------------------
# Email-thread helpers — re-homed verbatim from chair_drafts (used by deliver()).
# ---------------------------------------------------------------------------
def _strip_subject(s: str) -> str:
    """Normalize a subject for thread-matching (drop SV:/Re:/VS:/Fwd: prefixes)."""
    return re.sub(r'^((sv|re|vs|fw|fwd|ang)\s*:\s*)+', '', (s or '').strip(),
                  flags=re.I).strip().lower()


def _to_html(text: str) -> str:
    """Plain-text draft -> minimal HTML that PRESERVES line breaks. Both the
    Graph /reply and the HTML send path render HTML, which collapses raw
    newlines (the bug that flattened the first Morten reply into one line)."""
    return _html.escape(text or "").replace("\n", "<br>\n")


def _resolve_thread_gid(addr: str, subject: str):
    """Find the most recent inbox message FROM addr matching this subject so the
    reply threads into it. Returns (graph_id, conversationId), or (None, None)
    when there is no thread to reply into — then deliver() sends a fresh email.
    Best-effort: any Graph hiccup degrades to a fresh send."""
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


def _verify_sent(conv):
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


# ---------------------------------------------------------------------------
# Vault daily-note path — re-homed verbatim from daily_recap._vault_path. Pure
# path arithmetic (no screenpipe import), so a dry preview is safe anywhere.
# ---------------------------------------------------------------------------
def _vault_path() -> Path:
    return Path(os.environ.get(
        "OBSIDIAN_VAULT_PATH", str(Path.home() / "Obsidian" / "screenpipe-brain")))


class ScreenpipeDispatch:
    """Flavor-A ``PersonalDispatch`` — the real screenpipe egress/actuator adapter
    (re-homed ``chair_drafts`` send + ``daily_recap`` write/board/model bodies,
    byte-identical to today). Bound via ``instance/config/sources.yml`` (``dispatch:``);
    framework reaches it only through ``framework.sources.get_dispatch()``. It
    satisfies ``framework.sources.base.PersonalDispatch`` structurally."""

    # -- OUTBOUND PREP -------------------------------------------------------
    #    ← chair_drafts._apply_signature (draft_lib.ensure_signature), verbatim.
    def ensure_signature(self, text, channel):
        """Close an email draft with the captain's exact default signature (never
        Teams). ``draft_lib.ensure_signature`` is idempotent — won't double-sign.
        Any failure (lib absent / import error) returns the draft unchanged — the
        SAME fail-open the former ``chair_drafts._apply_signature`` had."""
        try:
            _ensure_shared_path()
            import draft_lib
            return draft_lib.ensure_signature(text, channel)
        except Exception:
            return text

    # -- POST-APPROVAL EGRESS ------------------------------------------------
    #    ← chair_drafts.deliver_draft's SEND execution, verbatim. The redis draft
    #    GET/DEL stays cabinet-side in framework; this does ONLY the send and
    #    returns the SAME result dict (dest/via set on the ok path) framework
    #    used to build inline.
    def deliver(self, record, override_text="", dry_run=False):
        """Send the stored draft via the screenpipe send libs. Post-approval
        egress — framework calls this ONLY after the captain approved in the Chair
        chat. ``record`` is the parsed ``cabinet:draft:<pid>`` dict.

        ``dry_run=True`` wires everything (subject calc, env, import the send lib)
        but does NOT send — used to verify the path without an actual egress."""
        p = record or {}
        text = override_text or p.get("draft", "")
        addr = p.get("recipient_email", "")
        is_teams = (p.get("channel") or "").lower() == "teams"
        subject = (p.get("subject") or "").strip() or (
            f"Re: {p.get('last_subject')}".strip() if p.get("last_subject") else "Re: (din besked)")
        _load_shared_env()
        _ensure_shared_path()
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
            res["dest"] = addr or p.get("person")
            res["via"] = "Teams" if is_teams else "email"
        return res

    # -- VAULT DAILY-NOTE WRITE ----------------------------------------------
    #    ← daily_recap._write_vault (OBSIDIAN_VAULT_PATH, marker-guarded, sha256
    #    write-if-changed), verbatim — the obsidian-sync byte-match invariant.
    def write_daily_note(self, date, content):
        """Write the daily note if (and only if) its bytes changed (sha256 compare).

        Returns {"action": written|unchanged|skipped, "path": ...}. Skips (never
        creates a stray note) when the vault isn't present/marked — matching
        obsidian-sync's ABORT_NO_VAULT guard. Path-jailed under the vault root."""
        vault = _vault_path()
        if not vault.exists() or not (vault / ".obsidian-vault-marker").exists():
            return {"action": "skipped", "path": str(vault), "reason": "no vault marker"}
        path = vault / "1-Daily" / f"{date}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        new_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        old_hash = (hashlib.sha256(path.read_bytes()).hexdigest()
                    if path.exists() else None)
        if new_hash == old_hash:
            return {"action": "unchanged", "path": str(path)}
        path.write_text(content)
        return {"action": "written", "path": str(path)}

    def daily_note_path(self, date):
        """The path the daily note WOULD be written to for ``date`` (dry preview —
        no write). Byte-identical to the former ``daily_recap`` dry-preview
        ``str(_vault_path() / "1-Daily" / f"{date}.md")``."""
        return str(_vault_path() / "1-Daily" / f"{date}.md")

    # -- FLAVOR-A BACKEND ACCESSORS (concrete extras — not in the Protocol) ---
    #    The daily-recap pipe reaches the captain's board client + synthesis model
    #    through these; a clean-room / Flavor-B box binds NullPersonalDispatch,
    #    whose stubs return None / "" so the recap degrades to "nothing to recap".
    def monday(self):
        """The captain's Monday board client (``sp_lib`` with env loaded) — the
        activity-board READ + reflections-board upsert the daily recap rides.
        Byte-identical to the former ``daily_recap._sp``: ``sp_lib.load_env`` is
        idempotent + cheap, re-run each access so a long-lived session re-reads a
        rotated token."""
        _ensure_shared_path()
        import sp_lib
        sp_lib.load_env(_SHARED)
        return sp_lib

    def llm_model(self):
        """The daily-recap synthesis model id (``commitments_lib.LLM_MODEL``) — the
        exact model the former ``daily_recap._raw_llm`` used. A string constant; the
        ANTHROPIC_API_KEY the recap curl needs is loaded by ``monday()`` earlier in
        the flow (``sp_lib.load_env``), exactly as today."""
        _ensure_shared_path()
        import commitments_lib
        return commitments_lib.LLM_MODEL

    # -- PROTOCOL COMPLETENESS (not the frontdoor egress path) ---------------
    #    The frontdoor egress uses deliver()/ensure_signature()/write_daily_note()
    #    above. The brain-MCP surface (queue_draft / append_agent_inbox /
    #    agent_reasoning) is a SEPARATE path, not routed through this dispatch — so
    #    these satisfy the Protocol as documented no-ops (mirroring the null
    #    dispatch) rather than pretending to a wiring that lives elsewhere.
    def queue_draft(self, *args, **kw):
        """Not this dispatch's path — the brain-MCP ``queue_draft`` tool is the
        officers' outbound gate (brain-bridge.md). The Chair egress uses
        ``deliver()`` after in-chat approval. No-op here."""
        return None

    def append_note(self, *args, **kw):
        """Not this dispatch's path — vault appends go via the brain-MCP
        ``append_agent_inbox`` tool; the daily-note write is ``write_daily_note``.
        No-op here."""
        return None

    def log_reasoning(self, **kw):
        """Not this dispatch's path — the agent-reasoning log is written by the
        autoreply wiring, not the frontdoor egress. No-op here."""
        return None
