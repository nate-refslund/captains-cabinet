"""channel.py — the ONLY Telegram send path for the cabinet front-door.

``send(text)`` delivers a single message to the Captain via the Telegram Bot
HTTP API, HARD-GATED by ``framework.env.allow_sends()``:

  * In dev/test/build (the default), ``allow_sends()`` is False, so ``send()``
    returns ``{'status': 'blocked-dev', 'sent': False}`` with ZERO network call.
    The single switch — there is no other way to suppress sends, and no way to
    accidentally send from a non-runtime session.
  * In the runtime (``CABINET_ENV=runtime``), ``send()`` POSTs to
    ``https://api.telegram.org/bot<token>/sendMessage`` with the body
    ``{chat_id: CAPTAIN_TELEGRAM_ID, text}``.

Security invariants (non-negotiable):
  - The recipient is ALWAYS ``CAPTAIN_TELEGRAM_ID``. It is NOT a parameter;
    no third-party recipient can ever be addressed through this path.
  - ``TELEGRAM_COS_TOKEN`` is read from the environment ONLY. The token (and the
    token-bearing request URL) is SCRUBBED from every return value and from every
    raised/propagated exception — the bot URL embeds the token, so any error must
    be sanitized before it leaves this module.

``receive()`` documents the inbound seam (the Chair is the sole long-poll poller,
arch §7); the implementation is deferred to a later slice.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from framework import env

# Telegram API base; overridable for tests so nothing ever hits the real host
# even if a test forgets to inject http_post. (Not used by the default urllib
# wrapper unless explicitly set.)
_TELEGRAM_BASE_ENV = "TELEGRAM_API_BASE"
_DEFAULT_TELEGRAM_BASE = "https://api.telegram.org"

# Marker used to scrub token-bearing URLs out of anything we surface.
_URL_PREFIX = "api.telegram.org/bot"


def _token() -> str:
    """Read the bot token from env ONLY. Never logged, printed, or returned."""
    return os.environ.get("TELEGRAM_COS_TOKEN", "")


def _captain_id() -> str:
    """Read the captain chat id from env ONLY. The sole permitted recipient."""
    return os.environ.get("CAPTAIN_TELEGRAM_ID", "")


def _base() -> str:
    return (os.environ.get(_TELEGRAM_BASE_ENV) or _DEFAULT_TELEGRAM_BASE).rstrip("/")


# Redis key holding the Captain's most-recent message_id (written by the inbound
# watchdog on every Captain DM). Reading it lets a reply thread onto that message.
_LAST_CAPTAIN_MSG_KEY = "cabinet:last-captain-msg-id"


def _last_captain_msg_id() -> int | None:
    """Best-effort: read the Captain's latest message_id from Redis for threading.

    Dependency-light (redis-cli subprocess, same convention as chair_drafts.py)
    and DEGRADE-SAFE: any failure — no redis-cli binary, no server, empty/non-int
    value — returns None, and ``send`` then posts a plain (unthreaded) message
    exactly as before. This never carries a secret and never raises.
    """
    host = os.environ.get("REDIS_HOST", "localhost")
    try:
        out = subprocess.run(
            ["redis-cli", "-h", host, "GET", _LAST_CAPTAIN_MSG_KEY],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        return int(out) if out else None
    except Exception:
        return None  # threading is a nicety; fall back to a plain send


def _scrub(text: object, token: str) -> str:
    """Remove the token (and any token-bearing telegram URL) from a string.

    Defense in depth: we both redact the exact token value and collapse any
    ``api.telegram.org/bot...`` URL fragment, so a leaked message that embedded
    the token in a URL cannot escape even if the token string itself was
    transformed.
    """
    s = str(text)
    if token:
        s = s.replace(token, "<redacted-token>")
    # Collapse any residual token-bearing URL fragment.
    while _URL_PREFIX in s:
        start = s.index(_URL_PREFIX)
        # find end of the bot<token>/... path segment up to next whitespace
        end = start + len(_URL_PREFIX)
        while end < len(s) and not s[end].isspace():
            end += 1
        s = s[:start] + "api.telegram.org/<redacted>" + s[end:]
    return s


def _default_http_post(url: str, data: dict) -> dict:
    """Default transport: POST JSON to ``url`` and return the parsed body.

    Used only in the runtime; tests inject their own ``http_post``. Any error is
    raised as a plain RuntimeError WITHOUT the token-bearing URL in its message —
    ``send()`` sanitizes again as a backstop, but we never originate a leak here.
    """
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 (fixed https host)
            raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:  # pragma: no cover - network path
        raise RuntimeError(f"telegram HTTP {exc.code}") from None
    except Exception as exc:  # pragma: no cover - network path
        raise RuntimeError(f"telegram transport error: {type(exc).__name__}") from None


def send(text: str, *, http_post=None) -> dict:
    """Send ``text`` to the Captain via Telegram — the ONLY front-door send path.

    Gated by ``env.allow_sends()`` as the FIRST line: a non-runtime session
    physically cannot send (no network call, returns ``blocked-dev``).

    Returns a dict with at least ``status`` and ``sent``. The token and the
    token-bearing request URL are guaranteed absent from the return value and
    from any error path.
    """
    # (1) THE GATE — checked first, before reading any secret or touching net.
    if not env.allow_sends():
        return {"status": "blocked-dev", "sent": False}

    token = _token()
    chat_id = _captain_id()
    if not token or not chat_id:
        return {"status": "error", "sent": False, "error": "telegram not configured"}

    post = http_post or _default_http_post
    url = f"{_base()}/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}

    # Thread onto the Captain's latest message when we know it (set by the inbound
    # watchdog). allow_sending_without_reply=True means a stale/deleted id still
    # delivers (just unthreaded) rather than erroring. Unknown id -> plain send.
    last_id = _last_captain_msg_id()
    if last_id is not None:
        payload["reply_parameters"] = {
            "message_id": last_id,
            "allow_sending_without_reply": True,
        }

    try:
        resp = post(url, payload)
    except BaseException as exc:  # noqa: BLE001 — must sanitize ALL failures
        # Never let a token-bearing message escape. Re-shape into a clean result.
        return {
            "status": "error",
            "sent": False,
            "error": _scrub(exc, token),
        }

    # Sanitize the response too — a producer-supplied mock or a real body could
    # echo the URL/token; ``send`` is the trust boundary.
    safe_resp = _scrub(resp, token)
    return {"status": "sent", "sent": True, "response": safe_resp}


def _default_http_get(url: str, params: dict, timeout: int) -> dict:
    """Default transport: GET ``url?params`` and return the parsed body.

    Errors are raised as plain RuntimeError WITHOUT the token-bearing URL —
    ``receive()`` also fails safe, but we never originate a leak.
    """
    full = url + "?" + urllib.parse.urlencode(params, doseq=True)
    try:
        with urllib.request.urlopen(full, timeout=timeout) as resp:  # noqa: S310 (fixed https host)
            raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:  # pragma: no cover - network path
        raise RuntimeError(f"telegram HTTP {exc.code}") from None
    except Exception as exc:  # pragma: no cover - network path
        raise RuntimeError(f"telegram transport error: {type(exc).__name__}") from None


def receive(*, offset=None, timeout: int = 0, limit: int = 100, http_get=None) -> tuple:
    """Poll Telegram getUpdates for the CAPTAIN's messages only.

    The Chair is the sole poller (arch §7). Returns ``(messages, next_offset)``:
      * ``messages`` — list of ``{update_id, message_id, text, ts}`` from
        ``CAPTAIN_TELEGRAM_ID`` ONLY. Any other chat is ignored (Corridor:
        validate the sender; never act on unauthorized traffic).
      * ``next_offset`` — highest seen ``update_id + 1``; pass it back next call
        so updates are not reprocessed. Unchanged when nothing new arrives.

    Reading inbound is always safe, so this is NOT gated by ``allow_sends()``
    (that gates only outbound). Token is read from env and NEVER logged or
    returned; any transport failure fails safe to ``([], offset)`` — no leak,
    offset preserved so nothing is skipped.
    """
    token = _token()
    captain = _captain_id()
    if not token or not captain:
        return [], offset

    params: dict = {"timeout": timeout, "limit": limit,
                    "allowed_updates": json.dumps(["message"])}
    if offset is not None:
        params["offset"] = offset

    get = http_get or _default_http_get
    url = f"{_base()}/bot{token}/getUpdates"
    try:
        resp = get(url, params, timeout + 10)
    except BaseException:
        # Fail safe — never surface a token-bearing error; keep the offset.
        return [], offset

    messages = []
    next_offset = offset
    for upd in (resp.get("result") or []):
        uid = upd.get("update_id")
        if uid is not None:
            next_offset = uid + 1  # advance past EVERY update, even ignored ones
        msg = upd.get("message") or {}
        chat = msg.get("chat") or {}
        if str(chat.get("id")) != str(captain):
            continue  # not the Captain — ignore (do not act on it)
        text = msg.get("text")
        if not text:
            continue
        messages.append({
            "update_id": uid,
            "message_id": msg.get("message_id"),
            "text": text,
            "ts": msg.get("date"),
        })
    return messages, next_offset
