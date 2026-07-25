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

import hashlib
import html
import json
import os
import re
import socket
import subprocess
import sys
import time
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

# Telegram sendMessage hard-limits the `text` field at 4096 UTF-16 code units. A
# longer message returns HTTP 400 and is LOST (observed 2026-06-29 07:30: the
# briefing assembled 77 intake items into one body far over the limit → 400 →
# the Captain got no briefing). We chunk anything over this ceiling into multiple
# sequential sends. Slightly under 4096 to leave headroom for the optional
# "(i/N)" continuation marker we prepend to multi-part chunks.
_TELEGRAM_LIMIT = 4096
_CHUNK_BUDGET = 3900

# Telegram accepts reactions only from this fixed Bot API set.  Validate at the
# transport boundary so invalid/multi-emoji input makes zero network calls.
_ALLOWED_REACTION_EMOJI = frozenset(
    "👍 👎 ❤ 🔥 🥰 👏 😁 🤔 🤯 😱 🤬 😢 🎉 🤩 🤮 💩 🙏 👌 🕊 🤡 🥱 🥴 😍 🐳 "
    "❤‍🔥 🌚 🌭 💯 🤣 ⚡ 🍌 🏆 💔 🤨 😐 🍓 🍾 💋 🖕 😈 😴 😭 🤓 👻 👨‍💻 👀 🎃 "
    "🙈 😇 😨 🤝 ✍ 🤗 🫡 🎅 🎄 ☃ 💅 🤪 🗿 🆒 💘 🙉 🦄 😘 💊 🙊 😎 👾 🤷‍♂ 🤷 "
    "🤷‍♀ 😡".split()
)


def _observe_reply_fits_one_message(text: str) -> bool:
    """True only when ``text`` stays on the transport's one-chunk path."""

    return (
        0 < len(text) <= _CHUNK_BUDGET
        and len(text.encode("utf-16-le")) // 2 <= _TELEGRAM_LIMIT
    )


def _hard_wrap(line: str, limit: int) -> list[str]:
    """Last-resort split of a SINGLE over-long line (no newline to break on).

    Only reached when one line alone exceeds ``limit`` (rare — a giant unbroken
    paragraph). Splits on whitespace where possible so we never sever a word, and
    falls back to a hard character cut for a single token longer than ``limit``.
    """
    out: list[str] = []
    rest = line
    while len(rest) > limit:
        cut = rest.rfind(" ", 0, limit)
        if cut <= 0:  # no breakable space in the window → hard character cut
            cut = limit
        out.append(rest[:cut])
        rest = rest[cut:].lstrip(" ")
    if rest:
        out.append(rest)
    return out


def _split_for_telegram(text: str, limit: int = _CHUNK_BUDGET) -> list[str]:
    """Split ``text`` into <=``limit``-char chunks on natural boundaries.

    Breaks on paragraph (blank-line) boundaries first, then single-line
    boundaries, NEVER mid-line — so a provenance bullet or a tier header is never
    severed. Only an individual line that is itself longer than ``limit`` is
    hard-wrapped (``_hard_wrap``), and only as a last resort. A message that
    already fits returns ``[text]`` unchanged (single-send path, no marker).
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current:
            chunks.append(current)
            current = ""

    # Preserve paragraph structure: split on blank lines, keep the separator
    # semantics by rejoining with "\n\n" within a chunk when both fit.
    for para in text.split("\n\n"):
        # A whole paragraph that fits onto the current chunk (with the blank-line
        # separator) stays joined for readability.
        candidate = para if not current else current + "\n\n" + para
        if len(candidate) <= limit:
            current = candidate
            continue
        # The paragraph doesn't fit alongside what's buffered → start it fresh.
        flush()
        if len(para) <= limit:
            current = para
            continue
        # The paragraph alone is too big → break it line by line.
        for line in para.split("\n"):
            cand = line if not current else current + "\n" + line
            if len(cand) <= limit:
                current = cand
                continue
            flush()
            if len(line) <= limit:
                current = line
                continue
            # A single line longer than the limit → hard-wrap it.
            for piece in _hard_wrap(line, limit):
                if current:
                    flush()
                chunks.append(piece)
    flush()
    return chunks or [text]


def _token() -> str:
    """Read the bot token from env ONLY. Never logged, printed, or returned."""
    # Clean officer launchers project the role-selected token under the
    # canonical generic name and deliberately remove raw per-role aliases.
    # Keep the historical CoS name as a compatibility fallback for services
    # and tests that have not yet moved to the clean launcher.
    return os.environ.get("TELEGRAM_BOT_TOKEN", "") or os.environ.get(
        "TELEGRAM_COS_TOKEN", ""
    )


def _captain_id() -> str:
    """Read the captain chat id from env ONLY. The sole permitted recipient."""
    return os.environ.get("CAPTAIN_TELEGRAM_ID", "")


def _base() -> str:
    return (os.environ.get(_TELEGRAM_BASE_ENV) or _DEFAULT_TELEGRAM_BASE).rstrip("/")


# Redis key holding the Captain's most-recent message_id (written by the inbound
# watchdog on every Captain DM). Reading it lets a reply thread onto that message.
_LAST_CAPTAIN_MSG_KEY = "cabinet:last-captain-msg-id"

# Unforgeable-by-argument module capability for the two observe-only current-
# message operations.  It is never accepted by a public function or MCP schema.
_OBSERVE_CURRENT_CAP = object()


def _observe_current_allowed(capability: object | None) -> bool:
    """Dedicated exception to CABINET_ENV=dev for current-message reply/react.

    It exists only while the sticky observe posture is active AND ordinary
    sends are disabled.  Thus it cannot become a generic allow_sends bypass in
    runtime, and no caller can choose a recipient/message id.
    """

    return (
        capability is _OBSERVE_CURRENT_CAP
        and os.environ.get("CABINET_OBSERVE_ONLY") == "1"
        and not env.allow_sends()
    )


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
    # Redact the selected transport token *and* any Telegram token aliases that
    # coexist in a legacy/non-clean process.  Clean officer launchers project a
    # single TELEGRAM_BOT_TOKEN, but maintenance commands and older services can
    # still carry both the generic and per-role names.  Scrubbing only the token
    # chosen by _token() would let a stale alias escape in callback text/errors.
    candidates = {token} if token else set()
    candidates.update(
        value
        for key, value in os.environ.items()
        if key.startswith("TELEGRAM_") and key.endswith("_TOKEN") and value
    )
    for candidate in candidates:
        s = s.replace(candidate, "<redacted-token>")
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
        # Surface Telegram's own error description (never carries the token) so
        # callers can distinguish benign 400s — e.g. editMessageText's "message
        # is not modified" (a no-op, not a failure). _post_one scrubs the result
        # regardless, so a token that ever leaked into a body cannot escape.
        raise RuntimeError(f"telegram HTTP {exc.code}{_http_error_detail(exc)}") from None
    except Exception as exc:  # pragma: no cover - network path
        raise RuntimeError(f"telegram transport error: {type(exc).__name__}") from None


def _http_error_detail(exc: urllib.error.HTTPError) -> str:  # pragma: no cover - network path
    """Best-effort Telegram error ``description`` (``": <desc>"`` or ``""``).

    Telegram returns ``{"ok": false, "error_code": N, "description": "..."}`` on a
    4xx. Reading it lets callers act on the *reason* (e.g. the not-modified no-op)
    without another round-trip. Any read/parse failure yields ``""`` — the caller
    still gets ``telegram HTTP <code>`` exactly as before."""
    try:
        obj = json.loads(exc.read().decode("utf-8", "replace"))
        desc = obj.get("description") if isinstance(obj, dict) else None
        return f": {desc}" if desc else ""
    except Exception:
        return ""


# Transport-retry budget for a TRANSIENT network failure (the request never got
# a real HTTP response — urllib URLError, socket timeout/error, ConnectionError).
# The 2026-06-30 07:30 briefing failed with "telegram transport error: URLError":
# the Mac slept 02:28→08:04, launchd ran the calendar-scheduled briefing the
# instant it woke (08:04:29), and api.telegram.org would not resolve because
# mDNSResponder/the network stack was still coming up. The first send hit a dead
# resolver, was NOT retried (only HTTP 400 was), and the briefing was LOST.
#
# A briefing can tolerate a few seconds, so we retry the post on transport-level
# failures with short exponential backoff. Sleeps are 1s, 3s (between 3 attempts)
# → worst-case ~4s of backoff plus the per-attempt urlopen timeout (15s each);
# total budget stays well under the briefing's launchd slot and the watchdog's
# 240s deadline. An HTTP 4xx is NEVER transport-retried here — it reached
# Telegram and was rejected (a payload bug); 400 keeps its own plain-text
# fallback below. On all-attempts-failed we return the SAME error shape as a
# single failure, so the caller leaves the intake PENDING (no false-ACK).
_TRANSPORT_RETRY_ATTEMPTS = 3
_TRANSPORT_BACKOFF_S = (1, 3)  # waits BETWEEN attempts; len == attempts - 1

# Transient transport exception types: the request never received an HTTP
# response. urllib wraps most of these in URLError, but a directly-injected
# socket/connection error is covered too. NOTE: urllib.error.HTTPError IS a
# subclass of URLError but is deliberately EXCLUDED — it carries an HTTP status
# (the request reached Telegram), so it is handled by the 400 path, never retried
# as transport.
_TRANSIENT_EXC = (urllib.error.URLError, socket.timeout, socket.gaierror,
                  ConnectionError, TimeoutError, OSError)


def _is_transient_transport(exc: BaseException, scrubbed: str) -> bool:
    """True iff ``exc`` is a transport-level failure (no HTTP response received).

    Two signals, either suffices:
      * the exception type is a known transient transport error AND not an
        ``HTTPError`` (which carries a status code — that reached Telegram); or
      * the scrubbed message contains the default transport's transport-error
        marker ("transport error") and is NOT an HTTP-status error ("HTTP 4"/5).
    The string check covers the default ``_default_http_post`` wrapper (which
    raises a plain ``RuntimeError("telegram transport error: …")`` so no token
    leaks) and any caller/test that mimics it. An HTTP 4xx/5xx never matches —
    the request got a response and must not be transport-retried."""
    if isinstance(exc, urllib.error.HTTPError):
        return False  # has a status code → reached Telegram, not a transport miss
    if isinstance(exc, _TRANSIENT_EXC):
        return True
    s = scrubbed.lower()
    if "http 4" in s or "http 5" in s:
        return False  # an HTTP-status error surfaced as text → not transport
    return "transport error" in s


# --- SEC-3 killswitch (fail-closed) at the front-door transport --------------
# The Captain's emergency stop must halt EVERY outbound send. We REUSE the one
# killswitch reader in the codebase — action_exec's ``_killswitch_state`` over
# ``_redis_get_strict`` (Redis ``GET cabinet:killswitch``) — instead of reading
# the key here, so the front door and the action executor can NEVER disagree
# about whether the stop is armed. Both an ACTIVE switch and an UNREACHABLE
# control plane HALT (a missing safety switch is exposure, not ambiguity —
# mirrors pre-tool-use.sh / SEC-3 in action_exec).
_KILLSWITCH_REFUSED = "front-door send refused — killswitch %s (fail-closed)"


def _killswitch_halted() -> "str | None":
    """Return "active" | "unreachable" when the front door must fail CLOSED, else
    None (clear).

    Delegates to action_exec's single SEC-3 reader (imported lazily to avoid any
    module-load cycle). ``_killswitch_state`` already maps a raising getter
    (Redis down) to "unreachable"; the outer guard additionally fails closed if
    the reader itself is unavailable — a killswitch that cannot be read is
    treated as armed, never as a silent open door. Never raises."""
    try:
        from framework.frontdoor.action_exec import (
            _killswitch_state,
            _redis_get_strict,
        )
        state = _killswitch_state(_redis_get_strict)
    except Exception:  # noqa: BLE001 — an unreadable killswitch fails CLOSED
        return "unreachable"
    return None if state == "clear" else state


def _post_one(post, url: str, payload: dict, token: str, *, sleep=None,
              retry_plain_400: bool = True) -> tuple:
    """POST ONE message payload; sanitize, retry transient transport, fall back
    to plain text on a 400.

    Returns ``(ok, scrubbed_response, scrubbed_error)``:
      * ``ok`` True  → ``scrubbed_response`` is the token-safe body, error None.
      * ``ok`` False → ``scrubbed_error`` is the token-safe error, response None.

    Two distinct robustness layers, by failure class (a network blip and a
    payload bug are NOT the same failure):

      1. TRANSIENT TRANSPORT (the request never got an HTTP response — URLError,
         socket timeout/error, ConnectionError): retry the SAME post up to
         ``_TRANSPORT_RETRY_ATTEMPTS`` times with short exponential backoff
         (``_TRANSPORT_BACKOFF_S``). This is the 2026-06-30 fix — a briefing that
         fires the instant the Mac wakes hits a not-yet-ready resolver, and a
         retry a second later succeeds. An HTTP 4xx is NOT in this class.

      2. HTTP 400 (the request reached Telegram and was rejected — typically a
         markdown/entity parse glitch): retry ONCE as PLAIN text, stripping any
         ``parse_mode`` so a bad-markup body still delivers. Today's payload sets
         no parse_mode, so this is a safety net for any future formatted send.

    A successful FIRST post returns immediately with no retry and no sleep — the
    normal path is byte-identical to before. ALL failures are scrubbed of the
    token-bearing URL before they leave this function (``send`` is the trust
    boundary; this preserves it). ``sleep`` is injectable so tests run instantly.
    """
    # SEC-3 killswitch (fail-closed) — THE single chokepoint. Every dict-payload
    # front-door send funnels through _post_one (send / send_poll / send_draft /
    # send_rich / edit_message / answer_callback / set_typing / pin / unpin /
    # set_reaction), so an armed stop OR an unreachable control plane refuses
    # ALL of them here, BEFORE any network side effect. Returned as an ok=False
    # tuple — every caller already surfaces that as a structured refusal dict —
    # so the halt never raises. (send_document uses the multipart transport and
    # carries its own copy of this gate.)
    _halt = _killswitch_halted()
    if _halt:
        return False, None, _KILLSWITCH_REFUSED % _halt

    # Resolve the backoff sleeper at CALL time (not as a bound default) so a test
    # patching ``channel.time.sleep`` is honored and the suite pays no real wait.
    if sleep is None:
        sleep = time.sleep

    # (1) Transport-retry loop. A non-transport failure (e.g. HTTP 400) breaks out
    #     immediately to the 400/plain-text fallback below — it is never slept on
    #     or transport-retried. The LAST attempt does not sleep after failing.
    last_err = None
    for attempt in range(_TRANSPORT_RETRY_ATTEMPTS):
        try:
            resp = post(url, payload)
            return True, _scrub(resp, token), None
        except BaseException as exc:  # noqa: BLE001 — must sanitize ALL failures
            last_err = _scrub(exc, token)
            if not _is_transient_transport(exc, last_err):
                break  # not a transient blip → fall through to the 400 handler
            if attempt < len(_TRANSPORT_BACKOFF_S):
                sleep(_TRANSPORT_BACKOFF_S[attempt])
            # else: this was the final attempt — fall through, report last_err

    first_err = last_err or "telegram send failed"

    # (2) Retry once as PLAIN text on an apparent 400 (formatting/parse glitch).
    # We detect 400 from the scrubbed message (HTTPError surfaces as "telegram
    # HTTP 400" from the default transport). Strip parse_mode so a bad-markup body
    # still delivers as plain text. (Reached only for a non-transient failure or
    # an exhausted transport-retry; a 400 is non-transient so it lands here on its
    # first occurrence, exactly as before.)
    # retry_plain_400=False (edits): a 400 must surface VERBATIM — for
    # editMessageText the "message is not modified" 400 is the caller's noop
    # signal, and the strip-parse_mode retry would instead "succeed" by
    # rewriting the standing card as raw markup (review cp3 M1).
    if "400" in first_err and retry_plain_400:
        plain = {k: v for k, v in payload.items() if k != "parse_mode"}
        try:
            resp = post(url, plain)
            return True, _scrub(resp, token), None
        except BaseException as exc2:  # noqa: BLE001 — sanitize the retry too
            return False, None, _scrub(exc2, token)

    return False, None, first_err


# ---------------------------------------------------------------------------
# Feed journal at the transport layer (attention-gateway P3, spec §4.3/§4.10.2).
# Every successful send/edit is journaled so the org can ask "what did we already
# send about this?" — the dedup data, undo receipts, and comms-retro stats are
# all made of these rows. Journaling can NEVER unmake a delivery: a missing feed
# module is bootstrap-tolerated, and an append that RAISES prints a loud
# JOURNAL-GAP marker but the send still returns success (delivery beats
# journaling; gaps must be visible, not silent).
# ---------------------------------------------------------------------------
_feed_import_warned = False


def _msgid_of(resp: object) -> int | None:
    """Pull Telegram's assigned ``result.message_id`` from a RAW (pre-scrub)
    response, or None. message_id is always an integer, so it never carries the
    token — safe to surface and to key the standing-card index on."""
    if isinstance(resp, dict):
        result = resp.get("result")
        if isinstance(result, dict):
            mid = result.get("message_id")
            if isinstance(mid, bool):  # bool is an int subclass — reject it
                return None
            if isinstance(mid, int):
                return mid
    return None


def _feed_row_out(text: str, default_kind: str, message_id: int | None,
                  chat: str, feed_meta: dict | None) -> dict:
    """Build an outbound feed row: transport facts win over caller ``feed_meta``.

    ``feed_meta`` carries the situation context (situation_key, class, urgency,
    mode, charter_version, gate_trace, …). The delivery facts — message_id, chat,
    content length/hash, direction — are authoritative from the transport and are
    set AFTER spreading feed_meta so they can't be forged by it. ``kind`` defaults
    to the call site's ``default_kind`` but honors an explicit ``feed_meta['kind']``."""
    row = dict(feed_meta or {})
    row["direction"] = "out"
    row["kind"] = (feed_meta or {}).get("kind", default_kind)
    row["telegram_message_id"] = message_id
    row["chat"] = chat
    row["content_len"] = len(text or "")
    row["content_hash"] = hashlib.sha1((text or "").encode("utf-8")).hexdigest()
    return row


def _journal_out(row_fn) -> None:
    """Append an outbound feed row — best-effort, never fails a send.

    Takes a THUNK (``row_fn() -> dict``) so row CONSTRUCTION runs inside the
    same swallow as the append (review cp3 L1: a construction crash must not
    fail a delivered send either). Lazy import so a bootstrap box without the
    feed module still sends: an ImportError is noted ONCE on stderr and
    swallowed. Any other failure prints a loud ``JOURNAL-GAP`` marker (a
    delivered-but-unjournaled send is a real gap and must be visible) and
    returns normally — the message is out."""
    global _feed_import_warned
    try:
        from framework.attention import feed
    except Exception:
        if not _feed_import_warned:
            print("[channel] feed journal module not available yet — outbound "
                  "sends are not being journaled (bootstrap tolerance)",
                  file=sys.stderr)
            _feed_import_warned = True
        return
    try:
        feed.append_event(row_fn())
    except Exception as exc:  # delivery already happened — surface, never raise
        print(f"[channel] JOURNAL-GAP: feed journaling failed "
              f"({type(exc).__name__}: {exc}) — message DELIVERED but NOT journaled",
              file=sys.stderr)


def _contact_heartbeat_out() -> None:
    """Emit the Captain-contact dead-man heartbeat (D1) — outbound leg.

    THE PLACEMENT IS THE POINT. This fires at the one place in the tree where
    outbound delivery is genuinely CONFIRMED: every chunk accepted by the
    transport with a real message id assigned. It is unreachable from the
    failure paths — a killswitch-refused send, a ``blocked-dev`` send, and a
    partial multi-chunk failure all return BEFORE this line, so none of them can
    launder itself into a heartbeat.

    WHAT THE HEARTBEAT HONESTLY MEANS: "the Captain's transport accepted this
    message." That is strictly stronger than the two producer-side artifacts the
    watchdog has had to make do with (a marker the Chair stamps when it BELIEVES
    it delivered, and a ``sent: True`` log line), and it is deliberately NOT a
    claim that the Captain read or answered anything. Those three are different
    facts and this codebase has historically collapsed them; the inbound leg is
    what speaks to the Captain actually being there.

    Best-effort in the strongest sense: the message is already out, so nothing
    here may raise, and ``deadman.emit`` is contractually non-raising anyway.
    Unconfigured deployments no-op silently (INERT by default). We stay quiet on
    a failed ping too — the honest consequence is that the off-machine watcher
    stops seeing pings and alarms, which is the correct outcome rather than a
    log line nobody reads."""
    try:
        from framework.liveness import deadman

        deadman.emit(deadman.EVENT_CAPTAIN_OUTBOUND)
    except Exception:
        pass  # the send SUCCEEDED; a heartbeat must never cost a delivered message


# ---------------------------------------------------------------------------
# Conservative Markdown → Telegram-HTML (opt-in via send(..., markdown=True)).
# Everything is html.escape-d FIRST, so untrusted text can never inject markup;
# only the five supported tokens become tags. Plain text (no tokens) is returned
# byte-identical with parse_mode=None — the default path is unchanged.
# ---------------------------------------------------------------------------
_MD_FENCE = re.compile(r"```(.*?)```", re.S)
_MD_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)
_MD_ITALIC = re.compile(r"(?<![\*\w])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\*\w])")
_MD_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")


def _has_markdown(text: str) -> bool:
    return bool(
        _MD_FENCE.search(text) or _MD_INLINE_CODE.search(text)
        or _MD_BOLD.search(text) or _MD_ITALIC.search(text) or _MD_LINK.search(text)
    )


def render_markdown(text: str) -> tuple[str, str | None]:
    """Return ``(rendered, parse_mode)`` for a message body.

    No supported token present → ``(text, None)`` unchanged (Telegram renders it
    verbatim, so raw ``<script>`` in plain text is inert — no parse_mode, no
    interpretation). Any token present → the whole string is html.escape-d and
    the five tokens (**bold**, *italic*, `code`, ```blocks```, [text](url)) become
    Telegram HTML tags, returned with ``"HTML"``. Code content is protected from
    the bold/italic/link passes and escaped on restore, so markup inside code is
    shown literally."""
    if not text or not _has_markdown(text):
        return text, None

    stash: dict[str, tuple[str, str]] = {}

    def _protect(kind: str, content: str) -> str:
        key = f"\x00{kind}{len(stash)}\x00"  # NUL-fenced, survives html.escape untouched
        stash[key] = (kind, content)
        return key

    tmp = _MD_FENCE.sub(lambda m: _protect("PRE", m.group(1)), text)
    tmp = _MD_INLINE_CODE.sub(lambda m: _protect("CODE", m.group(1)), tmp)
    tmp = html.escape(tmp, quote=False)
    tmp = _MD_BOLD.sub(lambda m: f"<b>{m.group(1)}</b>", tmp)
    tmp = _MD_ITALIC.sub(lambda m: f"<i>{m.group(1)}</i>", tmp)
    tmp = _MD_LINK.sub(
        lambda m: f'<a href="{m.group(2).replace(chr(34), "&quot;")}">{m.group(1)}</a>',
        tmp,
    )
    for key, (kind, content) in stash.items():
        esc = html.escape(content, quote=False)
        tmp = tmp.replace(key, f"<pre>{esc}</pre>" if kind == "PRE" else f"<code>{esc}</code>")
    return tmp, "HTML"


def _send_impl(text: str, *, http_post=None, reply_to: int | None = None,
               silent: bool = False, reply_markup: dict | None = None,
               feed_meta: dict | None = None, markdown: bool = False,
               thread_id: int | None = None, effect_id: str | None = None,
               _observe_cap: object | None = None) -> dict:
    """Send ``text`` to the Captain via Telegram — the ONLY front-door send path.

    Gated by ``env.allow_sends()`` as the FIRST line: a non-runtime session
    physically cannot send (no network call, returns ``blocked-dev``).

    A message over Telegram's 4096-char limit is split into multiple ≤-limit
    chunks (on line/paragraph boundaries, numbered "(i/N)") and sent
    sequentially; ``sent`` is True only if EVERY chunk delivered, and a partial
    failure returns ``status='error'`` with ``sent_chunks`` (how many landed
    before the failure) so the caller does not falsely ACK. A normal-length
    message is sent as ONE post exactly as before.

    Optional keyword args (all default to today's behavior when omitted):
      * ``reply_to`` — thread onto THIS specific message_id (true threading);
        otherwise fall back to the Captain's latest message (inbound watchdog).
      * ``silent`` — ``disable_notification`` (batch/FYI tiers send without a ping).
      * ``reply_markup`` — an inline-keyboard dict, JSON-encoded onto the payload.
      * ``feed_meta`` — situation context stamped onto the feed journal row.
      * ``markdown`` — opt into conservative Markdown→Telegram-HTML rendering.

    Returns a dict with at least ``status`` and ``sent`` — ``response`` for a
    single send, or ``chunks``/``responses`` for a multi-part one — plus
    ``message_ids`` (the Telegram message_ids assigned, for the standing-card
    index / feed). The token and the token-bearing request URL are guaranteed
    absent from the return value and from any error path.
    """
    # (1) THE GATE — checked first, before reading any secret or touching net.
    if not env.allow_sends() and not _observe_current_allowed(_observe_cap):
        return {"status": "blocked-dev", "sent": False}

    token = _token()
    chat_id = _captain_id()
    if not token or not chat_id:
        return {"status": "error", "sent": False, "error": "telegram not configured"}

    post = http_post or _default_http_post
    url = f"{_base()}/bot{token}/sendMessage"

    # Thread anchor: an explicit reply_to threads onto THAT exact message (true
    # threading — fixes the always-last-message anchor); otherwise fall back to
    # the Captain's latest message (set by the inbound watchdog). Only the
    # fallback consults Redis. allow_sending_without_reply=True means a
    # stale/deleted id still delivers (just unthreaded) rather than erroring. The
    # anchor is shared across every chunk of a multi-part message.
    anchor_id = reply_to if reply_to is not None else _last_captain_msg_id()
    reply_parameters = None
    if anchor_id is not None:
        reply_parameters = {
            "message_id": anchor_id,
            "allow_sending_without_reply": True,
        }

    # Opt-in Markdown → Telegram HTML. Plain text is returned byte-identical with
    # parse_mode=None, so the default path (markdown=False) is exactly unchanged.
    body_text, parse_mode = render_markdown(text) if markdown else (text, None)

    # Telegram hard-limits a single message at 4096 chars; over that it 400s and
    # the message is LOST. Split an over-limit body into multiple ≤4096 chunks on
    # line/paragraph boundaries (never mid-line) and send them sequentially. A
    # normal-length message yields exactly ONE chunk → identical behavior to
    # before (single post, no marker, same payload).
    chunks = _split_for_telegram(body_text)
    multipart = len(chunks) > 1

    responses = []
    message_ids: list[int | None] = []
    for idx, chunk in enumerate(chunks, start=1):
        # Number multi-part chunks so the Captain sees ordering; a single-chunk
        # (normal-length) message is sent verbatim with NO marker.
        body = f"({idx}/{len(chunks)}) {chunk}" if multipart else chunk
        payload = {"chat_id": chat_id, "text": body}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if silent:
            payload["disable_notification"] = True
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup)
        if reply_parameters is not None:
            payload["reply_parameters"] = reply_parameters
        # C0: route a lane's card into its own DM thread (message_thread_id,
        # from open_thread) and/or add ONE reserved effect (ping-now tier).
        if thread_id is not None:
            payload["message_thread_id"] = int(thread_id)
        if effect_id:
            payload["message_effect_id"] = str(effect_id)
        # Capture the RAW (pre-scrub) response so we can read the integer
        # message_id Telegram assigned. The wrapper is transparent to _post_one's
        # scrub/retry — it only observes the successful body.
        captured: list = []

        def _cap(u, d, _sink=captured):
            resp = post(u, d)
            _sink.append(resp)
            return resp

        ok, sent_resp, err = _post_one(_cap, url, payload, token)
        if not ok:
            # A chunk failed even after the plain-text retry — stop and report.
            # Earlier chunks already delivered; surfacing the failure (rather than
            # a false success) lets the caller leave the intake items PENDING so a
            # later pass redelivers, instead of ACKing a partial briefing away.
            return {
                "status": "error",
                "sent": False,
                "error": err,
                "chunks": len(chunks),
                "sent_chunks": idx - 1,
                "message_ids": message_ids,
            }
        responses.append(sent_resp)
        message_ids.append(_msgid_of(captured[-1]) if captured else None)

    # Feed journal at the transport layer — one row per send(), carrying the
    # FINAL delivered message_id and the content hash. Runs only after every
    # chunk landed; a journal failure never unmakes the delivery.
    _journal_out(lambda: _feed_row_out(
        text, "message", message_ids[-1] if message_ids else None, chat_id, feed_meta))

    # D1 outbound dead-man: CONFIRMED delivery is the trigger. Placed after the
    # last chunk landed and after journaling, so the heartbeat can only follow a
    # real delivery — see _contact_heartbeat_out for why this exact line.
    _contact_heartbeat_out()

    if multipart:
        return {"status": "sent", "sent": True, "chunks": len(chunks),
                "responses": responses, "message_ids": message_ids}
    return {"status": "sent", "sent": True, "response": responses[0],
            "message_ids": message_ids}


def send(text: str, *, http_post=None, reply_to: int | None = None,
         silent: bool = False, reply_markup: dict | None = None,
         feed_meta: dict | None = None, markdown: bool = False,
         thread_id: int | None = None, effect_id: str | None = None) -> dict:
    """Ordinary one-door send. It never receives the observe-only capability."""

    return _send_impl(
        text,
        http_post=http_post,
        reply_to=reply_to,
        silent=silent,
        reply_markup=reply_markup,
        feed_meta=feed_meta,
        markdown=markdown,
        thread_id=thread_id,
        effect_id=effect_id,
    )


def reply_current_observe_only(text: str, *, http_post=None) -> dict:
    """Reply to the latest Captain inbound during observe-only dogfood.

    The current inbound id comes from the watchdog-owned Redis key. There is no
    chat-id or message-id parameter, and the recipient remains the fixed
    CAPTAIN_TELEGRAM_ID. Outside observe+dev this dedicated doorway is closed.
    """

    if not _observe_current_allowed(_OBSERVE_CURRENT_CAP):
        return {"status": "blocked-observe-only", "sent": False}
    body = str(text)
    if not _observe_reply_fits_one_message(body):
        return {
            "status": "error",
            "sent": False,
            "error": f"observe reply must fit one message (1..{_CHUNK_BUDGET} characters)",
        }
    message_id = _last_captain_msg_id()
    if message_id is None:
        return {
            "status": "error",
            "sent": False,
            "error": "no current Captain inbound message",
        }
    return _send_impl(
        body,
        http_post=http_post,
        reply_to=message_id,
        feed_meta={"kind": "observe-reply", "reply_to": message_id},
        _observe_cap=_OBSERVE_CURRENT_CAP,
    )


def edit_message(message_id: int, text: str, *, reply_markup: dict | None = None,
                 http_post=None, feed_meta: dict | None = None,
                 markdown: bool = False) -> dict:
    """Edit a standing message in place (``editMessageText``) — same gate as send.

    Standing cards flip state (``open → acted ✓``) by editing ONE message instead
    of posting a new one; Telegram edits do not notify. Security model is
    identical to ``send()``: gated FIRST by ``allow_sends()``, recipient is always
    ``CAPTAIN_TELEGRAM_ID`` (never a parameter), token + token-bearing URL scrubbed
    from every return/error path.

    A ``"message is not modified"`` 400 (the new text equals the current text) is
    a NO-OP, not a failure — it returns ``{"status": "noop", "sent": False}`` so
    an idempotent re-render is harmless. ``feed_meta`` is journaled with
    ``kind="edit"``.
    """
    if not env.allow_sends():
        return {"status": "blocked-dev", "sent": False}

    token = _token()
    chat_id = _captain_id()
    if not token or not chat_id:
        return {"status": "error", "sent": False, "error": "telegram not configured"}

    body_text, parse_mode = render_markdown(text) if markdown else (text, None)
    payload = {"chat_id": chat_id, "message_id": int(message_id), "text": body_text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup)

    post = http_post or _default_http_post
    url = f"{_base()}/bot{token}/editMessageText"
    captured: list = []

    def _cap(u, d, _sink=captured):
        resp = post(u, d)
        _sink.append(resp)
        return resp

    ok, sent_resp, err = _post_one(_cap, url, payload, token,
                                   retry_plain_400=False)
    if not ok:
        # "message is not modified" is Telegram telling us the edit was a no-op
        # (identical text) — not an error. retry_plain_400=False above is what
        # guarantees this 400 arrives here verbatim instead of being "fixed"
        # by the parse-strip retry into a raw-markup rewrite (cp3 M1).
        if "not modified" in (err or "").lower():
            return {"status": "noop", "sent": False}
        return {"status": "error", "sent": False, "error": err}

    # editMessageText returns the edited Message (has message_id) or bare `true`;
    # fall back to the message_id we were handed (it IS the target) when absent.
    mid = (_msgid_of(captured[-1]) if captured else None) or int(message_id)
    _journal_out(lambda: _feed_row_out(text, "edit", mid, chat_id, feed_meta))
    return {"status": "sent", "sent": True, "response": sent_resp, "message_ids": [mid]}


def answer_callback(callback_query_id: str, text: str = "", *, http_post=None) -> dict:
    """Acknowledge an inline-button tap (``answerCallbackQuery``) — gate + scrub.

    Always safe to call: it stops the client's loading spinner and (optionally)
    shows a short toast. Gated by ``allow_sends()`` FIRST; the toast ``text`` is
    token-scrubbed before it leaves. No chat_id is involved (the answer routes to
    the callback), so only the token is required."""
    if not env.allow_sends():
        return {"status": "blocked-dev", "sent": False}

    token = _token()
    if not token:
        return {"status": "error", "sent": False, "error": "telegram not configured"}

    payload = {"callback_query_id": str(callback_query_id)}
    if text:
        payload["text"] = _scrub(text, token)

    post = http_post or _default_http_post
    url = f"{_base()}/bot{token}/answerCallbackQuery"
    ok, sent_resp, err = _post_one(post, url, payload, token)
    if not ok:
        return {"status": "error", "sent": False, "error": err}
    return {"status": "sent", "sent": True, "response": sent_resp}


def send_poll(question: str, options: list, *, is_anonymous: bool = False,
              allows_multiple_answers: bool = False, quiz_correct: int | None = None,
              silent: bool = False, feed_meta: dict | None = None,
              http_post=None) -> dict:
    """Send a native Telegram poll — the AskUserQuestion-style select surface.

    Same gate + scrub + feed-journal discipline as ``send``: ``allow_sends()``
    first, recipient always ``CAPTAIN_TELEGRAM_ID``. ``options`` is 1-12 short
    strings; a ``quiz_correct`` index turns it into a quiz. Non-anonymous by
    default so the vote arrives structured on ``poll_answer`` (the poller
    relays it). Returns the poll's ``message_ids`` for later stop/reference."""
    if not env.allow_sends():
        return {"status": "blocked-dev", "sent": False}
    token = _token()
    chat_id = _captain_id()
    if not token or not chat_id:
        return {"status": "error", "sent": False, "error": "telegram not configured"}
    opts = [str(o)[:100] for o in (options or [])][:12]
    if len(opts) < 1:
        return {"status": "error", "sent": False, "error": "poll needs >=1 option"}
    # Bot API 7.3+ (May 2024): sendPoll `options` is an Array of InputPollOption
    # objects ({"text": ...}), NOT bare strings — a bare-string array is rejected
    # (cp-gauntlet HIGH). Each option text is already capped to the 1-100 char limit.
    payload = {"chat_id": chat_id, "question": str(question)[:300],
               "options": json.dumps([{"text": o} for o in opts]),
               "is_anonymous": bool(is_anonymous),
               "allows_multiple_answers": bool(allows_multiple_answers)}
    if quiz_correct is not None:
        payload["type"] = "quiz"
        payload["correct_option_id"] = int(quiz_correct)
    if silent:
        payload["disable_notification"] = True
    post = http_post or _default_http_post
    url = f"{_base()}/bot{token}/sendPoll"
    # Capture the RAW (pre-scrub) response so we can read result.message_id —
    # _post_one returns the SCRUBBED string, which _msgid_of can't parse (same
    # wrapper pattern send()/edit_message use).
    captured: list = []

    def _cap(u, d, _sink=captured):
        resp = post(u, d)
        _sink.append(resp)
        return resp

    ok, sent_resp, err = _post_one(_cap, url, payload, token)
    if not ok:
        return {"status": "error", "sent": False, "error": err}
    mid = _msgid_of(captured[-1]) if captured else None
    _journal_out(lambda: _feed_row_out(str(question), "poll", mid, chat_id, feed_meta))
    return {"status": "sent", "sent": True, "response": sent_resp,
            "message_ids": [mid] if mid else []}


def set_typing(action: str = "typing", *, http_post=None) -> dict:
    """Show the ``typing…`` (or ``upload_photo``, ``record_voice`` …) status in
    the Captain's chat via ``sendChatAction``. Ephemeral (clears after ~5s or
    on the next message), so it is NOT feed-journaled — fire it before a
    reply that takes a noticeable moment to compose (the investigation-bar
    gather). Gate + scrub like every other send; best-effort by nature."""
    if not env.allow_sends():
        return {"status": "blocked-dev", "sent": False}
    token = _token()
    chat_id = _captain_id()
    if not token or not chat_id:
        return {"status": "error", "sent": False, "error": "telegram not configured"}
    payload = {"chat_id": chat_id, "action": str(action)}
    post = http_post or _default_http_post
    url = f"{_base()}/bot{token}/sendChatAction"
    ok, sent_resp, err = _post_one(post, url, payload, token)
    if not ok:
        return {"status": "error", "sent": False, "error": err}
    return {"status": "sent", "sent": True}


def _gated_method(method: str, payload_extra: dict, *, http_post=None,
                  capture=False, _observe_cap: object | None = None) -> dict:
    """Shared spine for the small Captain-chat Bot API methods (pin, unpin,
    forum-topic): allow_sends() gate FIRST, recipient always CAPTAIN_TELEGRAM_ID,
    token + URL scrubbed on every path. ``capture`` returns the raw result dict
    (for methods whose result carries an id we need, e.g. createForumTopic)."""
    if not env.allow_sends() and not _observe_current_allowed(_observe_cap):
        return {"status": "blocked-dev", "sent": False}
    token = _token()
    chat_id = _captain_id()
    if not token or not chat_id:
        return {"status": "error", "sent": False, "error": "telegram not configured"}
    # chat_id LAST so payload_extra can NEVER override the recipient — the
    # invariant "recipient is never a parameter" is structural on this shared
    # spine, not just a convention (review cp1 nit-1).
    payload = {**payload_extra, "chat_id": chat_id}
    post = http_post or _default_http_post
    url = f"{_base()}/bot{token}/{method}"
    captured: list = []

    def _cap(u, d, _sink=captured):
        resp = post(u, d)
        _sink.append(resp)
        return resp

    # retry_plain_400=False: these methods carry no parse_mode, so the
    # plain-text 400 retry would just re-POST an identical (doomed) payload.
    ok, sent_resp, err = _post_one(_cap if capture else post, url, payload, token,
                                   retry_plain_400=False)
    if not ok:
        return {"status": "error", "sent": False, "error": err}
    out = {"status": "sent", "sent": True, "response": sent_resp}
    if capture and captured and isinstance(captured[-1], dict):
        # The RAW (pre-scrub) result — intentionally unscrubbed because a
        # Telegram ForumTopic/pin result carries NO token (only ints/strings),
        # same precedent as _msgid_of reading the raw integer message_id.
        out["result"] = captured[-1].get("result")
    return out


def pin(message_id: int, *, silent: bool = True, http_post=None) -> dict:
    """Pin a message to the top of the Captain's DM (``pinChatMessage``) — used
    for the standing decision-queue card so it survives scrollback. In a
    private chat a pin is ALWAYS silent (no notification regardless), so
    ``silent`` is a no-op there but kept for interface symmetry. Gate + scrub."""
    extra = {"message_id": int(message_id)}
    if silent:
        extra["disable_notification"] = True
    return _gated_method("pinChatMessage", extra, http_post=http_post)


def unpin(message_id: "int | None" = None, *, http_post=None) -> dict:
    """Unpin one message (``unpinChatMessage``) or, with no id, the most recent
    pin. Gate + scrub."""
    extra = {"message_id": int(message_id)} if message_id is not None else {}
    return _gated_method("unpinChatMessage", extra, http_post=http_post)


def open_thread(name: str, *, icon_color: "int | None" = None, http_post=None) -> dict:
    """Open a per-lane thread in the Captain's DM (``createForumTopic`` —
    supported in a private chat since Bot API 9.4). Returns the new
    ``message_thread_id`` under ``thread_id`` so ``send(..., thread_id=...)``
    can route a lane's cards (one thread per configured lane) into their own
    thread without a group. Requires forum-topic mode enabled on the
    bot's private chats (getMe.has_topics_enabled); a channel/bot without it
    returns an error the caller degrades from (single-stream, as today)."""
    extra = {"name": str(name)[:128]}
    if icon_color is not None:
        extra["icon_color"] = int(icon_color)
    res = _gated_method("createForumTopic", extra, http_post=http_post, capture=True)
    if res.get("sent") and isinstance(res.get("result"), dict):
        tid = res["result"].get("message_thread_id")
        if isinstance(tid, int):
            res["thread_id"] = tid
    return res


def set_reaction(message_id: int, emoji: "str | None", *, http_post=None) -> dict:
    """Set (or clear) the bot's single reaction on a message
    (``setMessageReaction``). This is the LLM-CONTEXTUAL react layer (an officer
    picks an emoji that fits the message) that supersedes the poller's instant
    deterministic receipt-reaction. ``emoji=None``/"" clears the reaction.
    Gate + scrub via the shared spine; a non-whitelisted emoji is rejected by
    Telegram and surfaces as an error the caller degrades from."""
    value = str(emoji) if emoji else ""
    if value and value not in _ALLOWED_REACTION_EMOJI:
        return {"status": "error", "sent": False, "error": "unsupported Telegram reaction"}
    extra = {"message_id": int(message_id)}
    if value:
        extra["reaction"] = json.dumps([{"type": "emoji", "emoji": value}])
    else:
        extra["reaction"] = json.dumps([])   # clear
    return _gated_method("setMessageReaction", extra, http_post=http_post)


def react_current_observe_only(emoji: "str | None", *, http_post=None) -> dict:
    """React to the latest Captain inbound through the observe-only doorway."""

    if not _observe_current_allowed(_OBSERVE_CURRENT_CAP):
        return {"status": "blocked-observe-only", "sent": False}
    value = str(emoji) if emoji else ""
    if value not in _ALLOWED_REACTION_EMOJI:
        return {"status": "error", "sent": False, "error": "unsupported Telegram reaction"}
    message_id = _last_captain_msg_id()
    if message_id is None:
        return {
            "status": "error",
            "sent": False,
            "error": "no current Captain inbound message",
        }
    extra = {"message_id": message_id}
    extra["reaction"] = json.dumps([{"type": "emoji", "emoji": value}])
    return _gated_method(
        "setMessageReaction",
        extra,
        http_post=http_post,
        _observe_cap=_OBSERVE_CURRENT_CAP,
    )


def send_draft(draft_id: int, text: str = "", *, thread_id: "int | None" = None,
               http_post=None) -> dict:
    """Stream a live draft into the Captain's chat (``sendMessageDraft``) — the
    real "Thinking…" indicator.

    Empty ``text`` shows Telegram's "Thinking…" placeholder; calling again with
    the SAME ``draft_id`` animates/replaces it in place (this is how you stream a
    reply as it composes). EPHEMERAL: the draft is a ~30s preview that Telegram
    discards — to PERSIST the finished message you MUST call ``send()`` (a normal
    sendMessage) afterwards. So it is NOT feed-journaled (nothing was delivered).
    Private-chat only; available to all bots since Bot API 9.5 (empty text since
    10.0). ``draft_id`` must be non-zero. Same gate + scrub as every send."""
    if not env.allow_sends():
        return {"status": "blocked-dev", "sent": False}
    token = _token()
    chat_id = _captain_id()
    if not token or not chat_id:
        return {"status": "error", "sent": False, "error": "telegram not configured"}
    payload = {"chat_id": chat_id, "draft_id": int(draft_id) or 1, "text": str(text or "")}
    if thread_id is not None:
        payload["message_thread_id"] = int(thread_id)
    post = http_post or _default_http_post
    url = f"{_base()}/bot{token}/sendMessageDraft"
    # retry_plain_400=False: no parse_mode here, so the plain-text 400 retry would
    # just re-POST an identical doomed payload.
    ok, sent_resp, err = _post_one(post, url, payload, token, retry_plain_400=False)
    if not ok:
        return {"status": "error", "sent": False, "error": err}
    return {"status": "sent", "sent": True}


def send_rich(markdown: "str | None" = None, *, html: "str | None" = None,
              silent: bool = False, reply_markup: dict | None = None,
              feed_meta: dict | None = None, http_post=None) -> dict:
    """Send a Rich Message (``sendRichMessage``, Bot API 10.1): tables, collapsible
    ``<details>``, headings, task lists — the structured surface a multi-step
    course-of-action card renders best in.

    Provide EXACTLY ONE of ``markdown`` or ``html`` (the ``InputRichMessage`` body):
    a table is a GFM pipe table (``| a | b |``) or ``<table>``; a collapsible is
    ``<details><summary>…</summary>…</details>``. It is a REAL, persisted message,
    so it carries the full ``send`` discipline — ``allow_sends()`` gate first,
    recipient always ``CAPTAIN_TELEGRAM_ID``, token/URL scrubbed, feed-journaled
    (``kind="rich"``). Telegram limits: 32768 chars, 500 blocks, 20 columns/table,
    16 nesting levels — an overflow returns a 400 the caller degrades from (fall
    back to ``send()``). Clients older than 10.1 render a plain-text fallback."""
    if not env.allow_sends():
        return {"status": "blocked-dev", "sent": False}
    token = _token()
    chat_id = _captain_id()
    if not token or not chat_id:
        return {"status": "error", "sent": False, "error": "telegram not configured"}
    if bool(markdown) == bool(html):
        return {"status": "error", "sent": False,
                "error": "send_rich needs exactly one of markdown or html"}
    # InputRichMessage: exactly one of markdown/html. JSON-encoded like every
    # other complex Bot API param (reply_markup, poll options).
    rich = {"markdown": markdown} if markdown else {"html": html}
    payload = {"chat_id": chat_id, "rich_message": json.dumps(rich)}
    if silent:
        payload["disable_notification"] = True
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup)
    post = http_post or _default_http_post
    url = f"{_base()}/bot{token}/sendRichMessage"
    captured: list = []

    def _cap(u, d, _sink=captured):
        resp = post(u, d)
        _sink.append(resp)
        return resp

    ok, sent_resp, err = _post_one(_cap, url, payload, token, retry_plain_400=False)
    if not ok:
        return {"status": "error", "sent": False, "error": err}
    mid = _msgid_of(captured[-1]) if captured else None
    _journal_out(lambda: _feed_row_out(markdown or html or "", "rich", mid, chat_id, feed_meta))
    return {"status": "sent", "sent": True, "response": sent_resp,
            "message_ids": [mid] if mid else []}


def _default_multipart_post(url: str, fields: dict, filename: str, content: bytes) -> dict:
    """Default transport: POST a multipart/form-data body (one file + fields).

    Pure-stdlib multipart (no ``requests`` dependency). Same leak discipline as
    ``_default_http_post``: errors are raised as a plain RuntimeError WITHOUT the
    token-bearing URL; ``send_document`` sanitizes again as a backstop.
    """
    boundary = "----CabinetBoundary" + os.urandom(12).hex()
    pre = []
    for k, v in fields.items():
        pre.append(
            f"--{boundary}\r\nContent-Disposition: form-data; "
            f'name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8")
        )
    pre.append(
        f"--{boundary}\r\nContent-Disposition: form-data; "
        f'name="document"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n".encode("utf-8")
    )
    body = b"".join(pre) + content + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (fixed https host)
            raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:  # pragma: no cover - network path
        raise RuntimeError(f"telegram HTTP {exc.code}") from None
    except Exception as exc:  # pragma: no cover - network path
        raise RuntimeError(f"telegram transport error: {type(exc).__name__}") from None


def send_document(file_path: str, *, caption: str | None = None, http_post=None,
                  feed_meta: dict | None = None) -> dict:
    """Send a file to the Captain via Telegram sendDocument — same gate as ``send``.

    Identical security model to ``send()``: gated FIRST by ``env.allow_sends()``
    (a non-runtime session physically cannot send), the recipient is ALWAYS
    ``CAPTAIN_TELEGRAM_ID`` (never a parameter), and the token + token-bearing URL
    are scrubbed from every return value and error path. ``caption`` is optional
    text shown with the document. ``feed_meta`` is journaled with ``kind="document"``.
    Returns a dict with ``status`` + ``sent``.

    The file is read from ``file_path`` on the local disk; a read failure returns
    a clean ``error`` result (no send attempted). ``http_post`` is injectable for
    tests so nothing hits the real host.
    """
    # (1) THE GATE — checked first, before reading any secret or touching net.
    if not env.allow_sends():
        return {"status": "blocked-dev", "sent": False}

    token = _token()
    chat_id = _captain_id()
    if not token or not chat_id:
        return {"status": "error", "sent": False, "error": "telegram not configured"}

    # SEC-3 killswitch (fail-closed): send_document is the ONE front-door send on
    # the multipart transport, so it bypasses _post_one and carries its own copy
    # of the gate — checked BEFORE any disk read or network post (a halted
    # document send does zero I/O). Same single reader as _post_one.
    _halt = _killswitch_halted()
    if _halt:
        return {"status": "halted", "sent": False, "halted": "killswitch",
                "killswitch": _halt, "error": _KILLSWITCH_REFUSED % _halt}

    try:
        with open(file_path, "rb") as fh:
            content = fh.read()
        filename = os.path.basename(file_path) or "document"
    except Exception as exc:  # cannot read file — never attempt a send
        return {"status": "error", "sent": False,
                "error": f"cannot read file: {type(exc).__name__}"}

    fields = {"chat_id": chat_id}
    if caption:
        fields["caption"] = caption

    post = http_post or _default_multipart_post
    url = f"{_base()}/bot{token}/sendDocument"
    try:
        resp = post(url, fields, filename, content)
    except BaseException as exc:  # noqa: BLE001 — must sanitize ALL failures
        return {"status": "error", "sent": False, "error": _scrub(exc, token)}

    mid = _msgid_of(resp)  # raw response, pre-scrub — safe integer
    _journal_out(lambda: _feed_row_out(caption or "", "document", mid, chat_id, feed_meta))
    return {"status": "sent", "sent": True, "response": _scrub(resp, token),
            "message_ids": [mid]}


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
