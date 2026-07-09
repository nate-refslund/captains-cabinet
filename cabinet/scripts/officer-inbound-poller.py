#!/usr/bin/env python3
"""officer-inbound-poller.py — the Captain's inbound Telegram bridge for a
Telegram-voice officer (the Chair).

WHY THIS EXISTS
---------------
The Claude Code telegram Channels plugin (``--channels plugin:telegram``) does
NOT reliably deliver DMs to an IDLE officer session: it fetches one update,
injects it, then stalls until that injection is processed — which never happens
while the session sits at its prompt. Result: the Captain DMs the bot and gets
silence (observed 2026-06-23: messages stuck at ``pending_update_count`` while
the Chair was idle).

This poller replaces the plugin's RECEIVE half. It is the SOLE ``getUpdates``
poller for the officer's bot (the officer must therefore launch WITHOUT
``--channels`` — two pollers on one token = Telegram 409 Conflict). On each
Captain message it WAKES the officer's tmux session via ``tmux send-keys`` (the
proven wake path), so the officer runs a turn, interprets the message, and
replies through the existing approval-safe ``framework.frontdoor.channel.send``
(outbound is unchanged and independent of this).

GUARANTEES
----------
* Captain-only: relays ONLY messages whose ``from.id == CAPTAIN_TELEGRAM_ID``.
  Every other sender is skipped (the bot is publicly addressable).
* No loss: the update offset is advanced only AFTER a message is delivered (or
  deliberately skipped); a crash mid-deliver re-delivers on restart rather than
  dropping. Offset persisted to ``TELEGRAM_STATE_DIR/inbound-offset.txt``.
* No mid-turn corruption: delivery is idle-gated — it waits for the pane to be
  at its prompt before injecting.
* Secret hygiene: the bot token is read from env and never logged.

ENV: TELEGRAM_<OFFICER>_TOKEN (or TELEGRAM_BOT_TOKEN), CAPTAIN_TELEGRAM_ID,
     TELEGRAM_STATE_DIR (optional; defaults to the cabinet state path).
USAGE: officer-inbound-poller.py <officer>     # e.g. cos
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid

# Repo root on sys.path so the watchdog can ALSO fire registered triggers — a fired
# reminder/interval reuses the very same tmux wake path as a Captain DM. Fail-safe by
# construction: if the firing module can't be imported, `fire_due_triggers` is a no-op
# and DM receive is completely unaffected.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
try:
    from framework.triggers.firing import fire_due_triggers
except Exception:
    def fire_due_triggers(*_a, **_k):  # firing unavailable → receive path unchanged
        return 0


def log(msg: str) -> None:
    print(f"[inbound-poller] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Update types we request (attention-gateway P3, spec §13). getUpdates delivers
# only the types listed here — message_reaction/poll_answer are NOT in Telegram's
# default set, so they must be named explicitly to arrive at all.
# ---------------------------------------------------------------------------
ALLOWED_UPDATES = ["message", "callback_query", "message_reaction", "poll_answer"]

# Telegram's FIXED reaction whitelist (Bot API 10.1 — verbatim from the plugin
# ACCESS.md / core.telegram.org). setMessageReaction silently ignores anything not
# on it, so any picked emoji that isn't here is substituted with the always-valid
# 👀. Written as literal emoji (space-separated) so the ZWJ sequences (❤‍🔥,
# 👨‍💻, 🤷‍♂/🤷‍♀) survive intact.
ALLOWED_REACTIONS = frozenset(
    "👍 👎 ❤ 🔥 🥰 👏 😁 🤔 🤯 😱 🤬 😢 🎉 🤩 🤮 💩 🙏 👌 🕊 🤡 🥱 🥴 😍 🐳 "
    "❤‍🔥 🌚 🌭 💯 🤣 ⚡ 🍌 🏆 💔 🤨 😐 🍓 🍾 💋 🖕 😈 😴 😭 🤓 👻 👨‍💻 👀 🎃 "
    "🙈 😇 😨 🤝 ✍ 🤗 🫡 🎅 🎄 ☃ 💅 🤪 🗿 🆒 💘 🙉 🦄 😘 💊 🙊 😎 👾 🤷‍♂ 🤷 "
    "🤷‍♀ 😡".split()
)
_EYES = "👀"  # the always-valid default / substitute

# class → deterministic reaction variants (spec §13 UX ruling). variant is chosen
# by message_id so the SAME message always gets the SAME reaction. 📄 (file) is
# NOT on Telegram's whitelist and is substituted to 👀 at pick time.
_REACTION_VOCAB = {
    "question":  ["🤔", _EYES],
    "urgent":    ["⚡", _EYES],
    "file":      ["📄", _EYES],   # 📄 is NOT whitelisted → substitutes to 👀
    "directive": ["🫡", "👌"],
    "default":   [_EYES, "👌", "✍"],
}

_CB_DATA_RE = re.compile(r"[^\w:.|-]")
_FNAME_RE = re.compile(r"[^\w.-]")
_ID_RE = re.compile(r"[^\w-]")


def classify_inbound(text: str, has_attachment: bool = False) -> str:
    """Mechanically classify a Captain message to pick a receipt reaction.

    Deterministic, no LLM: ends-with-'?' or a question opener → question;
    urgency words → urgent; an attachment → file; a short (<=60ch) imperative-ish
    line → directive; else default. Order matches the spec §13 ruling."""
    t = (text or "").strip()
    low = t.lower()
    if low.endswith("?") or low.startswith(
        ("what", "how", "why", "should", "can", "do we", "is ")
    ):
        return "question"
    if any(w in low for w in ("urgent", "asap", "now", "haster")):
        return "urgent"
    if has_attachment:
        return "file"
    if t and len(t) <= 60:  # short imperative-ish directive (no '?' — caught above)
        return "directive"
    return "default"


def pick_reaction(message_id: int, cls: str) -> str:
    """Deterministically pick a whitelist-valid reaction emoji for (id, class).

    Same (message_id, cls) → same emoji (message_id rotates the variant). Any
    non-whitelisted variant (e.g. 📄) is substituted with 👀 so the reaction is
    never silently dropped by Telegram."""
    variants = _REACTION_VOCAB.get(cls, _REACTION_VOCAB["default"])
    emoji = variants[int(message_id) % len(variants)]
    return emoji if emoji in ALLOWED_REACTIONS else _EYES


def sanitize_callback_data(data: str) -> str:
    """Constrain callback_data to ``[\\w:.|-]{0,64}`` so a relayed bracket line
    can't smuggle control characters / newlines into the session."""
    return _CB_DATA_RE.sub("", data or "")[:64]


def sanitize_filename(name: str) -> str:
    """Reduce an inbound filename to ``[\\w.-]`` with no path components and no
    leading dots — traversal-proof (``../evil`` → ``evil``)."""
    base = os.path.basename((name or "").replace("\\", "/"))
    cleaned = _FNAME_RE.sub("_", base).lstrip(".")
    return (cleaned or "file")[:120]


def _sanitize_id(value: str) -> str:
    return _ID_RE.sub("", str(value or ""))[:64]


def format_callback_line(message_id: int, data: str) -> str:
    """One-line, binder-parseable relay of an inline-button tap."""
    return f"[tg-callback message_id={int(message_id)} data={sanitize_callback_data(data)}]"


def format_reaction_line(message_id: int, emoji: str) -> str:
    return f"[tg-reaction message_id={int(message_id)} emoji={emoji}]"


def format_poll_answer_line(poll_id: str, option_ids) -> str:
    ids = ",".join(str(int(o)) for o in (option_ids or []) if isinstance(o, int))
    return f"[tg-poll-answer poll_id={_sanitize_id(poll_id)} options={ids}]"


def format_file_line(path: str, name: str, kind: str) -> str:
    return f"[tg-file path={path} name={sanitize_filename(name)} kind={kind}]"


def _first_reaction_emoji(reactions) -> str:
    """First emoji from a ``new_reaction`` list (``[{type:'emoji', emoji:'👍'}]``)."""
    for r in reactions or []:
        if isinstance(r, dict) and r.get("type") == "emoji" and r.get("emoji"):
            return r["emoji"]
    return ""


_feed_warned_in = False


def feed_append_in(row: dict, log=log) -> None:
    """Append an inbound feed row — same tolerance as channel.py's outbound path.

    Relay NEVER depends on journaling: a missing feed module is bootstrap-tolerated
    (noted once), and an append that RAISES prints a loud JOURNAL-GAP marker but
    the relay proceeds."""
    global _feed_warned_in
    try:
        from framework.attention import feed
    except Exception:
        if not _feed_warned_in:
            log("feed journal not available yet — inbound not journaled (bootstrap)")
            _feed_warned_in = True
        return
    try:
        feed.append_event(row)
    except Exception as exc:
        log(f"JOURNAL-GAP: feed.append_event failed ({type(exc).__name__}: {exc})")


def resolve_inbound_file(msg: dict, *, max_bytes: int = 20 * 1024 * 1024) -> dict | None:
    """First downloadable attachment on a message as ``{kind, file_id, name, size}``.

    Photo (largest size), document, voice, audio — in that order. Returns None for
    no attachment OR one whose declared size exceeds ``max_bytes`` (the ≤20MB
    inbox cap). Pure — no network."""
    if not isinstance(msg, dict):
        return None

    def _capped(size):
        return bool(size) and size > max_bytes

    # Over-cap attachments return a SENTINEL ({"too_large": True, ...}), not
    # None — the Captain's file must never be silently dropped (§13 ruling;
    # review cp3 L3): the caller injects a visible [tg-file-error] line.
    photos = msg.get("photo")
    if isinstance(photos, list) and photos:
        largest = max(
            (p for p in photos if isinstance(p, dict)),
            key=lambda p: p.get("file_size", 0) or 0, default=None,
        )
        if largest and largest.get("file_id"):
            size = largest.get("file_size", 0) or 0
            entry = {"kind": "photo", "file_id": largest["file_id"],
                     "name": f"{largest.get('file_unique_id', 'photo')}.jpg",
                     "size": size}
            if _capped(size):
                entry["too_large"] = True
            return entry
    for key, kind, default_ext in (
        ("document", "document", "bin"),
        ("voice", "voice", "ogg"),
        ("audio", "audio", "mp3"),
    ):
        obj = msg.get(key)
        if isinstance(obj, dict) and obj.get("file_id"):
            size = obj.get("file_size", 0) or 0
            name = obj.get("file_name") or f"{obj.get('file_unique_id', kind)}.{default_ext}"
            entry = {"kind": kind, "file_id": obj["file_id"], "name": name,
                     "size": size}
            if _capped(size):
                entry["too_large"] = True
            return entry
    return None


def inbox_path(state_dir: str, name: str) -> str:
    """A collision-proof, traversal-proof local path under ``<state_dir>/inbox``.

    Prefixes a short unique id and sanitizes the name, then asserts containment so
    a crafted name can never escape the inbox directory."""
    inbox = os.path.realpath(os.path.join(state_dir, "inbox"))
    os.makedirs(inbox, exist_ok=True)
    safe = f"{uuid.uuid4().hex[:8]}-{sanitize_filename(name)}"
    path = os.path.realpath(os.path.join(inbox, safe))
    if os.path.commonpath([inbox, path]) != inbox:
        raise ValueError("refusing inbox path escape")
    return path


def download_inbound_file(att: dict, *, file_api: str, state_dir: str,
                          get_json, fetch_bytes, log=log,
                          max_bytes: int = 20 * 1024 * 1024) -> str | None:
    """``getFile`` → download bytes → save under the inbox. Local path or None.

    ``get_json``/``fetch_bytes`` are injected network seams (tests fake them). The
    token lives inside ``file_api`` and is never logged. Best-effort: any failure
    returns None so the relay still proceeds (path simply absent)."""
    file_id = att.get("file_id")
    if not file_id:
        return None
    meta = get_json("getFile", {"file_id": file_id})
    tg_path = None
    if isinstance(meta, dict):
        tg_path = (meta.get("result") or {}).get("file_path")
    if not tg_path:
        log("getFile returned no file_path — inbound file skipped")
        return None
    try:
        data = fetch_bytes(f"{file_api}/{tg_path}")
    except Exception as exc:
        log(f"inbound file download failed (non-fatal): {type(exc).__name__}")
        return None
    if len(data) > max_bytes:
        log("inbound file exceeds 20MB after download — dropping")
        return None
    local = inbox_path(state_dir, att.get("name") or os.path.basename(tg_path))
    with open(local, "wb") as fh:
        fh.write(data)
    return local


def handle_callback_query(cbq: dict, *, captain, api_post, inject, feed_append, log=log) -> None:
    """Answer an inline-button tap, then relay it into the session as a bracket line.

    answerCallbackQuery fires FIRST (clears the client spinner; harmless even for a
    stray). Relay + feed happen only for the Captain. callback_data is ids-only
    (≤64 bytes) — chain state lives in Redis/ledger, not the button."""
    cq_id = cbq.get("id")
    if cq_id:
        try:
            api_post("answerCallbackQuery", {"callback_query_id": str(cq_id)})
        except Exception as exc:
            log(f"answerCallbackQuery failed (non-fatal): {type(exc).__name__}")
    frm = str((cbq.get("from") or {}).get("id", ""))
    if frm != str(captain):
        log(f"skip callback from={frm or '?'} (not captain)")
        return
    mid = int((cbq.get("message") or {}).get("message_id", 0) or 0)
    data = cbq.get("data", "")
    inject(format_callback_line(mid, data))
    feed_append({"direction": "in", "kind": "callback",
                 "telegram_message_id": mid, "callback_data": sanitize_callback_data(data)})


def handle_message_reaction(upd: dict, *, captain, inject, feed_append, log=log) -> None:
    """Relay a CAPTAIN reaction (👍-as-data for the ≥3-👍 quiet rule) + journal it."""
    mr = upd.get("message_reaction") or {}
    user = str((mr.get("user") or {}).get("id", ""))
    if user != str(captain):
        return
    mid = int(mr.get("message_id", 0) or 0)
    emoji = _first_reaction_emoji(mr.get("new_reaction") or [])
    inject(format_reaction_line(mid, emoji))
    feed_append({"direction": "in", "kind": "reaction",
                 "telegram_message_id": mid, "emoji": emoji})


def handle_poll_answer(upd: dict, *, captain, inject, feed_append, log=log) -> None:
    """Relay a CAPTAIN poll vote (AskUserQuestion-style select) + journal it."""
    pa = upd.get("poll_answer") or {}
    user = str((pa.get("user") or {}).get("id", ""))
    if user != str(captain):
        return
    poll_id = pa.get("poll_id", "")
    option_ids = pa.get("option_ids") or []
    inject(format_poll_answer_line(poll_id, option_ids))
    feed_append({"direction": "in", "kind": "poll_answer",
                 "poll_id": _sanitize_id(poll_id),
                 "options": [int(o) for o in option_ids if isinstance(o, int)]})


def main() -> int:
    officer = sys.argv[1] if len(sys.argv) > 1 else "cos"
    up = officer.upper().replace("-", "_")
    token = os.environ.get(f"TELEGRAM_{up}_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    captain = os.environ.get("CAPTAIN_TELEGRAM_ID")
    state_dir = os.environ.get("TELEGRAM_STATE_DIR") or os.path.expanduser(
        f"~/Library/Application Support/cabinet/telegram-state/{officer}"
    )
    session = f"officer-{officer}"

    if not token:
        log(f"FATAL: TELEGRAM_{up}_TOKEN (or TELEGRAM_BOT_TOKEN) not set"); return 1
    if not captain:
        log("FATAL: CAPTAIN_TELEGRAM_ID not set"); return 1

    os.makedirs(state_dir, exist_ok=True)
    offset_file = os.path.join(state_dir, "inbound-offset.txt")
    try:
        offset = int(open(offset_file).read().strip())
    except Exception:
        offset = 0

    api = f"https://api.telegram.org/bot{token}"
    file_api = f"https://api.telegram.org/file/bot{token}"  # file downloads use /file/bot<token>/<path>
    redis_host = os.environ.get("REDIS_HOST", "localhost")
    log(f"started officer={officer} session={session} captain={captain} offset={offset}")

    def api_post(path: str, payload: dict) -> dict:
        """POST JSON to a Bot API method (e.g. answerCallbackQuery). Token stays in
        `api` and is never logged."""
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{api}/{path}", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 (fixed https host)
            return json.loads(r.read().decode("utf-8") or "{}")

    def get_json(path: str, params: dict) -> dict:
        """GET a Bot API method (e.g. getFile) and parse the JSON body."""
        full = f"{api}/{path}?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(full, timeout=15) as r:  # noqa: S310 (fixed https host)
            return json.loads(r.read().decode("utf-8") or "{}")

    def fetch_bytes(url: str) -> bytes:
        """Download raw bytes (an inbound file). `url` embeds the token via file_api."""
        with urllib.request.urlopen(url, timeout=30) as r:  # noqa: S310 (fixed https host)
            return r.read()

    def fa(row: dict) -> None:
        feed_append_in(row, log)

    def react(message_id: int, emoji: str = "\U0001F440") -> None:
        """Set an emoji reaction on the Captain's message as a read-ack (👀 default).

        Degrade-safe by construction: ANY failure (network, API error, bad id) is
        swallowed — a reaction must NEVER block waking the Chair or advancing the
        offset. The token is read from the enclosing scope and never logged."""
        try:
            body = json.dumps({
                "chat_id": int(captain),
                "message_id": message_id,
                "reaction": [{"type": "emoji", "emoji": emoji}],
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{api}/setMessageReaction", data=body,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            urllib.request.urlopen(req, timeout=10).read()  # noqa: S310 (fixed https host)
        except Exception:
            pass  # read-ack is best-effort; never let it disrupt receive

    def set_last_captain_msg_id(message_id: int) -> None:
        """Record the Captain's latest message_id so the Chair can thread its reply.

        channel.send reads cabinet:last-captain-msg-id to attach reply_parameters.
        Degrade-safe: a redis-cli failure (missing binary, no server) is swallowed —
        threading is a nicety, not a precondition for delivering the DM."""
        try:
            subprocess.run(
                ["redis-cli", "-h", redis_host, "SET",
                 "cabinet:last-captain-msg-id", str(message_id)],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass  # threading id is best-effort; never block receive

    def save_offset(o: int) -> None:
        tmp = offset_file + ".tmp"
        with open(tmp, "w") as f:
            f.write(str(o))
        os.replace(tmp, offset_file)

    def pane_busy() -> bool:
        """True if the officer pane is mid-turn (an active turn shows 'esc to interrupt')."""
        try:
            out = subprocess.run(
                ["tmux", "capture-pane", "-t", session, "-p"],
                capture_output=True, text=True, timeout=10,
            ).stdout
        except Exception:
            return True  # can't read → assume busy (don't inject blindly)
        tail = "\n".join(l for l in out.splitlines() if l.strip())[-1200:]
        return "esc to interrupt" in tail

    def raw_inject(relay: str) -> None:
        """Idle-gate, then inject one line into the officer pane as a turn.
        Shared by deliver() and the P3 bracket-line relays (callback/reaction/poll/
        file). Best-effort, never blocks — waits up to ~5 min for the pane to free."""
        waited = 0
        while pane_busy() and waited < 300:   # wait up to ~5 min for the pane to free
            time.sleep(5); waited += 5
        # text first, then Enter separately (Enter doesn't reliably register fused)
        subprocess.run(["tmux", "send-keys", "-t", session, relay], timeout=10)
        time.sleep(0.5)
        subprocess.run(["tmux", "send-keys", "-t", session, "C-m"], timeout=10)

    def deliver(text: str, quoted: str = "", binder_note: str = "") -> None:
        """Idle-gate, then inject the Captain DM into the officer pane as a turn.
        `quoted` is the message Nate REPLIED TO (Telegram reply-threading) — prefixed
        so the officer sees the exact draft / proposal / message being answered, with
        no need to ask 'which one'. `binder_note` (F0.5) is the mechanical binder
        wire's outcome — when present, recording+delivery ALREADY happened; the
        Chair must harvest lessons only and never double-deliver."""
        note = f" [⚙ {binder_note}]" if binder_note else ""
        if quoted:
            relay = f"\U0001F4E9 Captain DM (Telegram){note} [↩ replying to: “{quoted}”]: {text}"
        else:
            relay = f"\U0001F4E9 Captain DM (Telegram){note}: {text}"
        raw_inject(relay)

    while True:
        try:
            params = urllib.parse.urlencode({
                "offset": offset + 1,
                "timeout": 25,
                "allowed_updates": json.dumps(ALLOWED_UPDATES),
            })
            with urllib.request.urlopen(f"{api}/getUpdates?{params}", timeout=35) as resp:  # noqa: S310 (fixed https host)
                data = json.load(resp)
        except Exception as e:
            log(f"getUpdates error: {e}")
            # Self-heal a 409 Conflict: another getUpdates poller exists (Telegram
            # allows only one per token). This Cabinet is single-Telegram-voice, the
            # officer launches without --channels, and the watchdog is the SOLE poller
            # by design — so any telegram plugin is a stray (e.g. the officer probing
            # its own telegram setup mid-session). Reap it to reclaim the lock.
            # (Revisit if a deployment ever runs >1 telegram-capable officer.)
            if "409" in str(e):
                try:
                    subprocess.run(["pkill", "-f", "plugins/cache/claude-plugins-official/telegram"], timeout=10)
                    log("409 self-heal: reaped stray telegram plugin poller(s)")
                except Exception:
                    pass
            time.sleep(5); continue

        if not data.get("ok"):
            log(f"getUpdates not ok: {data.get('description')}"); time.sleep(5); continue

        for upd in data.get("result", []):
            uid = int(upd.get("update_id", 0))
            cbq = upd.get("callback_query")
            mr = upd.get("message_reaction")
            pa = upd.get("poll_answer")
            # P3 non-message update types (inline taps, reactions, poll votes).
            # Best-effort: swallowed so a poison update can never wedge the loop —
            # the offset still advances below (unlike the message path, which is
            # left to propagate so a crash mid-deliver re-delivers on restart).
            if cbq is not None:
                try:
                    handle_callback_query(cbq, captain=captain, api_post=api_post,
                                          inject=raw_inject, feed_append=fa, log=log)
                except Exception as e:
                    log(f"callback handling (non-fatal): {e}")
            elif mr is not None:
                try:
                    handle_message_reaction(upd, captain=captain, inject=raw_inject,
                                            feed_append=fa, log=log)
                except Exception as e:
                    log(f"reaction handling (non-fatal): {e}")
            elif pa is not None:
                try:
                    handle_poll_answer(upd, captain=captain, inject=raw_inject,
                                       feed_append=fa, log=log)
                except Exception as e:
                    log(f"poll handling (non-fatal): {e}")
            else:
                msg = upd.get("message") or {}
                frm = str((msg.get("from") or {}).get("id", ""))
                text = (msg.get("text") or "").strip()
                caption = (msg.get("caption") or "").strip()
                # Telegram reply-threading: if Nate REPLIED TO a message (a draft, a
                # proposal card, a briefing line), capture what he's answering so the
                # officer has the exact context without having to ask 'which one'.
                rt = msg.get("reply_to_message") or {}
                # FULL quoted text for the binder (2026-07-03): the ·pid· marker sits at
                # the END of draft cards (~900 chars) — the 500-char preview truncation
                # below sliced it off, so every real Captain `send` logged no-pid.
                # Binder gets the untruncated text; the relay keeps the short preview.
                quoted_full = (rt.get("text") or rt.get("caption") or "").strip()
                quoted = quoted_full.replace("\n", " ")
                if len(quoted) > 500:
                    quoted = quoted[:500] + "…"
                att = resolve_inbound_file(msg) if frm == str(captain) else None
                if frm == str(captain) and att is not None and att.get("too_large"):
                    # §13 "never silently dropped" (review cp3 L3): the Chair
                    # is TOLD about the over-cap file instead of nothing. No
                    # continue — the loop-end offset advance must still run.
                    mid = int(msg.get("message_id", 0))
                    set_last_captain_msg_id(mid)
                    fa({"direction": "in", "kind": "file-error",
                        "telegram_message_id": mid, "file_kind": att["kind"]})
                    err_line = (f"[tg-file-error name={sanitize_filename(att.get('name', '?'))} "
                                f"kind={att['kind']} reason=too-large-20mb]")
                    deliver(f"{err_line} {caption}".strip(), quoted, "")
                elif frm == str(captain) and att is not None:
                    # Inbound file (photo/document/voice/audio): download to the inbox
                    # and relay its local path + any caption (was text-only before —
                    # files were silently dropped). Voice transcription, if wired
                    # elsewhere, consumes the same path; we inject it either way.
                    log(f"captain file update_id={uid} kind={att['kind']} "
                        f"name={att.get('name','?')} -> downloading")
                    mid = int(msg.get("message_id", 0))
                    react(mid, pick_reaction(mid, classify_inbound(caption, has_attachment=True)))
                    set_last_captain_msg_id(mid)
                    fa({"direction": "in", "kind": "file", "telegram_message_id": mid,
                        "file_kind": att["kind"]})
                    local = None
                    try:
                        local = download_inbound_file(
                            att, file_api=file_api, state_dir=state_dir,
                            get_json=get_json, fetch_bytes=fetch_bytes, log=log)
                    except Exception as e:
                        log(f"file download error (non-fatal): {e}")
                    if local:
                        body = format_file_line(local, att.get("name", ""), att["kind"])
                    else:
                        body = f"[tg-file kind={att['kind']} download=failed]"
                    deliver(f"{body} {caption}".strip(), quoted, "")
                elif frm == str(captain) and text:
                    log(f"captain msg update_id={uid} ({len(text)} chars{', reply' if quoted else ''}) -> relaying")
                    mid = int(msg.get("message_id", 0))
                    react(mid, pick_reaction(mid, classify_inbound(text)))  # deterministic read-ack
                    set_last_captain_msg_id(mid)   # id the Chair threads replies onto
                    # CHAIR-REPLY-WIRE (2026-07-07, one-bot migration hardening):
                    # a reply threaded onto a Chair message carrying the
                    # ⟦sp:<prompt_id>⟧ marker is a screenpipe pipe-prompt answer —
                    # forward {prompt_id, text} MECHANICALLY onto the
                    # screenpipe:pipe-replies stream (idempotent by update_id; the
                    # sp-bridge consumer group drains it). The relay note tells the
                    # Chair forwarding already happened (never re-forward), and the
                    # marker SKIPS the binder wire below — a pipe answer like a
                    # bare "approve" must never bind a pending cabinet draft.
                    # Fail-safe by construction: any wire error → handled=False →
                    # the DM relays with the reply_bridge discipline path intact.
                    binder_note = ""
                    sp_marker = False
                    try:
                        from framework.frontdoor import sp_reply_wire
                        sp_marker = bool(sp_reply_wire.extract_prompt_id(quoted_full))
                        if sp_marker:
                            sr = sp_reply_wire.handle_captain_reply(text, quoted_full, uid, log=log)
                            if sr.get("handled"):
                                binder_note = sr.get("summary", "")
                            else:
                                log(f"[sp-wire] not handled: reason={sr.get('reason','?')} "
                                    f"pid={sr.get('prompt_id','-')}")
                    except Exception as e:
                        log(f"sp wire unavailable (passthrough preserved): {e}")
                    # F0.5 binder wire (flag-gated): mechanically record the Captain's
                    # approve/edit:/skip: verdict on the pending draft proposal and
                    # deliver on approve/edit — BEFORE the Chair sees the DM. The
                    # relay carries the outcome so the Chair never double-delivers.
                    # Fail-safe by construction: any wire error → handled=False →
                    # this DM relays byte-identically to pre-wire behavior.
                    if not sp_marker and os.environ.get("CABINET_BINDER_WIRED") == "1":
                        try:
                            from framework.frontdoor import binder_wire
                            wr = binder_wire.handle_captain_update(text, quoted_full, log=log)
                            if wr.get("handled"):
                                binder_note = wr.get("summary", "")
                            else:
                                # observability (2026-07-02): the first real Captain reply
                                # relayed with no trace of WHY the binder declined — log the
                                # reason so unmatched grammar/pids are diagnosable from logs.
                                log(f"[binder] not handled: reason={wr.get('reason','?')} pid={wr.get('pid','-')}")
                        except Exception as e:
                            log(f"binder wire unavailable (passthrough preserved): {e}")
                    fa({"direction": "in", "kind": "message", "telegram_message_id": mid})
                    deliver(text, quoted, binder_note)
                else:
                    log(f"skip update_id={uid} from={frm or '?'} (not captain or empty)")
            offset = max(offset, uid)
            save_offset(offset)

        # Fire any due triggers (reminders / intervals) into the pane, reusing the
        # wake path. Runs every poll cycle (~25s granularity). Non-blocking (skips
        # when the pane is busy) and fully wrapped — a trigger error never affects
        # the DM receive loop above.
        try:
            fire_due_triggers(session, pane_busy, log)
        except Exception as e:
            log(f"trigger firing (non-fatal): {e}")


if __name__ == "__main__":
    sys.exit(main())
