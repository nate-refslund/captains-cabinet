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
* Inline taps are INSTANT + MECHANICAL (2026-07-11): every callback_query is
  answerCallbackQuery'd on dequeue (verb toast; expired ids logged once,
  never retried) and applied server-side via
  ``framework.comms.surface.tap_wire`` — defer/pacing taps park + flip the
  card durably, Approve/No ride the dashboard's verdict door. The tmux
  bracket-line relay remains the fail-open floor and the Chair's
  lesson-harvest channel (⚙-noted when already applied).
* No loss: the update offset is advanced only AFTER a message is delivered (or
  deliberately skipped); a crash mid-deliver re-delivers on restart rather than
  dropping. Offset persisted to ``TELEGRAM_STATE_DIR/inbound-offset.txt``.
* Durable inbound archive (2026-07-17): every relayed Captain utterance (and
  onboarding-routed Captain DMs) is appended VERBATIM, dm_id-stamped, to
  ``CABINET_CAPTAIN_INBOUND_DIR`` day files (default
  ``~/Library/Application Support/cabinet/captain-inbound``) — see
  ``archive_captain_dm``. LOUD on failure (ARCHIVE-GAP) but never blocks
  delivery. The 30-entry redis ring remains a Chair nicety only.
* No mid-turn corruption: delivery is idle-gated — it waits for the pane to be
  at its prompt before injecting.
* /killswitch is MECHANICAL (captain-controls plan 2026-07-17): the Captain's
  /killswitch text is answered from THIS process with the standing
  emergency-stop card (fresh status + Halt/Resume taps through the
  allowlisted verb door); the taps execute cabinet/scripts/kill-switch.sh
  via the poller-only ``ks_exec`` seam with CABINET_OFFICER=captain-telegram,
  so the script's own audit row carries telegram provenance. The Chair is
  never in that loop — the card must work precisely when officers are halted
  (EVAL-001b stays an officer-session refusal, a different door).
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
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import NamedTuple

# Repo root on sys.path so the watchdog can ALSO fire registered triggers — a fired
# reminder/interval reuses the very same tmux wake path as a Captain DM. Fail-safe by
# construction: if the firing module can't be imported, `fire_due_triggers` is a no-op
# and DM receive is completely unaffected.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# ── Captain-DM capture seam (fixed 2026-07-16) ───────────────────────────────
# The germline capture/encoder/retrieval hooks (capture-captain-dm.sh,
# captain-rule-encoder.sh, pre-captain-dm.sh) fire on UserPromptSubmit ONLY when
# the prompt carries a <channel source="telegram" ... chat_id="<captain>"> tag —
# the shape the Claude Code Channels plugin emitted. This poller SUPERSEDED that
# plugin (it stalled at the prompt) but relayed plain lines, so every inbound
# Captain DM silently failed capture from 2026-06-23 until this fix. We now emit
# the tag the hooks already parse, sourcing chat_id from the SAME config they read
# so the match holds for the generated/sane config format.
def _neutralize_channel_tag(s: str) -> str:
    """Defang any literal ``<channel …>`` opener/closer in human-facing prefix
    text (the reply-preview / binder note) by swapping its ASCII ``<`` for ‹
    (U+2039). The germline hooks use FIRST-match regexes, so a channel tag the
    Captain merely QUOTED (an officer-echoed example) would otherwise pre-empt the
    real body tag below and get captured instead. Visually near-identical; the
    real tag is built from ASCII ``<`` and is unaffected."""
    return re.sub(r'<(/?)channel\b', r'‹\1channel', s) if s else s


def build_captain_channel_relay(chat_id: str, mid: int, text: str,
                                *, note: str = "", quoted: str = "") -> str:
    """The officer-pane relay line for one inbound Captain DM.

    The Captain's raw ``text`` is wrapped in the plugin-compatible
    ``<channel source="telegram" chat_id=… message_id=…>…</channel>`` tag the
    germline capture hooks gate on (chat_id match) and extract the body from
    (clean text between the tags — the 📩 prefix and reply-note stay OUTSIDE so
    they never pollute the captured message). The prefix fields are run through
    ``_neutralize_channel_tag`` so a quoted/echoed tag can't pre-empt the real
    one. Pure + module-level so the poller↔hook contract test can pin the shape."""
    reply = f' [↩ replying to: “{_neutralize_channel_tag(quoted)}”]' if quoted else ""
    tag = (f'<channel source="telegram" chat_id="{chat_id}" '
           f'message_id="{mid}">{text}</channel>')
    return f"\U0001F4E9 Captain DM (Telegram){_neutralize_channel_tag(note)}{reply}: {tag}"


def resolve_hook_chat_id(repo_root: str = _REPO_ROOT) -> str:
    """The ``captain_telegram_chat_id`` the germline capture hooks read — from
    ``instance/config/product.yml`` THEN ``platform.yml``, first match wins (the
    exact file order + precedence capture-captain-dm.sh / pre-captain-dm.sh use:
    ``grep … product.yml platform.yml | head -1``). Emitted verbatim in the
    channel tag so the hooks' ``chat_id="…"`` gate matches for the sane/generated
    config format (double-quoted value, no inline comment — what assemble-config
    emits). Returns "" when unset in both, whereupon the hooks default-deny."""
    cfg = os.path.join(repo_root, "instance", "config")
    for name in ("product.yml", "platform.yml"):
        try:
            with open(os.path.join(cfg, name), encoding="utf-8") as fh:
                for line in fh:
                    m = re.match(r'\s*captain_telegram_chat_id:\s*["\']?([^"\'#\s]+)', line)
                    if m:
                        return m.group(1)
        except OSError:
            continue
    return ""
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
_ONBOARDING_INTENT_RE = re.compile(
    r"^\s*/?(?:onboard|onboarding|orientation)\b", re.IGNORECASE
)


class OnboardingForwardResult(NamedTuple):
    """Explicit local-skin result; truthiness is intentionally not overloaded."""

    handled: bool
    delivered: bool


def onboarding_forward_disposition(result: OnboardingForwardResult) -> str:
    """Return ``ack`` | ``retry`` | ``fallback`` for the sole poller.

    ``retry`` is distinct from ``fallback``: the canonical state machine has
    already handled the stable update id, but its reply did not land. Relaying
    that same command through the Chair would create a second interpretation;
    instead the poller retains the offset and retries the idempotent route.
    """
    if not result.handled:
        return "fallback"
    return "ack" if result.delivered else "retry"

# ---------------------------------------------------------------------------
# getUpdates timing — ONE source so the pair can never drift into the
# read<long-poll inversion that turns every quiet poll into a timeout storm.
# The socket read must outlive the server-side hold by a response margin;
# a lapsed read is a NETWORK event (flaky uplink), not a config error — its
# damage is bounded by re-polling immediately (no extra sleep) so a queued
# tap isn't pushed past Telegram's ~15s answerCallbackQuery window (the
# 2026-07-09 line-1394 failure: storm-delayed dequeue → 400 expired id).
# ---------------------------------------------------------------------------
LONG_POLL_S = 25                      # Telegram-side getUpdates hold
READ_TIMEOUT_S = LONG_POLL_S + 10     # socket read = hold + response margin
ACK_TIMEOUT_S = 5                     # answerCallbackQuery must be INSTANT —
                                      # a slow ack is as bad as none

_EXPIRED_ACK_MARKERS = ("query is too old", "query id is invalid",
                        "response timeout expired")


def _ack_expired(exc: Exception) -> bool:
    """True when an answerCallbackQuery failure means the callback id is past
    Telegram's answer window (HTTP 400 "query is too old and response timeout
    expired or query ID is invalid"). Expired is FINAL — a retry can never
    succeed, so the caller logs once and moves on to applying the tap."""
    if getattr(exc, "code", None) != 400:
        return False
    body = ""
    try:
        if hasattr(exc, "read"):
            body = exc.read().decode("utf-8", "replace")
    except Exception:
        body = ""
    body = (body or str(exc)).lower()
    return any(m in body for m in _EXPIRED_ACK_MARKERS)


def answer_callback_now(api_post, cq_id, toast: str = "", *, log=log) -> str:
    """Ack ONE inline-button tap the instant it is dequeued — before any other
    handling. Returns ``ok`` | ``expired`` | ``failed`` (journaled truth).

    One attempt, short timeout, verb-appropriate ``toast`` so the Captain SEES
    the tap land. An EXPIRED id (past Telegram's window) is logged once and
    NEVER retried; exactly one retry for a transient (non-expired) blip —
    a flaky-network ack failure must not leave the spinner hanging when a
    second attempt would clear it."""
    payload = {"callback_query_id": str(cq_id)}
    if toast:
        payload["text"] = str(toast)[:200]
    for attempt in (0, 1):
        try:
            api_post("answerCallbackQuery", payload)
            return "ok"
        except Exception as exc:
            if _ack_expired(exc):
                log("callback ack expired (id past Telegram's answer window) "
                    "— not retrying; applying the tap anyway")
                return "expired"
            if attempt:
                log(f"answerCallbackQuery failed after retry (non-fatal): "
                    f"{type(exc).__name__}")
    return "failed"


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


def is_onboarding_update(update: dict) -> bool:
    """True for a canonical onboarding command or inline onboarding tap.

    This is intentionally a narrow lexical router, not a second journey state
    machine. The authenticated dashboard route remains the sole Telegram skin
    over ``framework.onboarding.journey``.
    """
    callback = update.get("callback_query") or {}
    if str(callback.get("data") or "").startswith("onboard:"):
        return True
    message = update.get("message") or {}
    text = str(message.get("text") or message.get("caption") or "")
    return bool(_ONBOARDING_INTENT_RE.search(text))


def forward_onboarding_update(
    update: dict,
    *,
    dashboard_url: str,
    webhook_secret: str,
    opener=urllib.request.urlopen,
    timeout: float = 10,
) -> OnboardingForwardResult:
    """POST one polled onboarding update to the local authenticated skin.

    Telegram cannot call the loopback-only Mac dashboard as a public webhook,
    while Telegram permits only one getUpdates poller. This adapter lets that
    sole poller hand only onboarding updates to the same route used by webhook
    deployments. The webhook secret is sent only to a validated loopback URL;
    Unavailability returns ``handled=False`` so the caller preserves the
    existing visible Chair relay. An explicit delivery failure returns
    ``handled=True, delivered=False`` so the caller retains its offset and
    retries this same idempotent update without a second LLM interpretation.
    """
    unavailable = OnboardingForwardResult(False, False)
    if not is_onboarding_update(update) or not webhook_secret:
        return unavailable
    try:
        parsed = urllib.parse.urlparse(dashboard_url)
    except ValueError:
        return unavailable
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return unavailable
    base = dashboard_url.rstrip("/")
    endpoint = f"{base}/api/telegram/provisioning-webhook"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(update, separators=(",", ":")).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Telegram-Bot-Api-Secret-Token": webhook_secret,
        },
        method="POST",
    )
    status = 0
    body = b""
    try:
        with opener(request, timeout=timeout) as response:
            status = int(getattr(response, "status", response.getcode()))
            body = response.read(4096)
    except urllib.error.HTTPError as exc:
        # The route deliberately returns 503 when Telegram reply delivery
        # fails. HTTPError is still a readable response; preserve its explicit
        # handled/delivered body so the local poller retries instead of taking
        # the Chair fallback and consuming the update.
        status = int(exc.code)
        try:
            body = exc.read(4096)
        except Exception:
            return unavailable
    except Exception:
        return unavailable
    try:
        parsed_body = json.loads(body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError):
        return unavailable
    if parsed_body.get("handled") is not True:
        return unavailable
    delivered = parsed_body.get("delivered") is True
    if not 200 <= status < 300 and delivered:
        return unavailable
    return OnboardingForwardResult(True, delivered)


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


# ---------------------------------------------------------------------------
# /killswitch — the emergency-stop control card (captain-controls plan,
# ratified 2026-07-17, Phase 1). MECHANICAL by necessity: when the switch is
# ACTIVE every officer is halted (EVAL-001), so the card must come from THIS
# process — the poller is the captain-held Telegram factor's door. Execution
# always rides the sanctioned script (audit rows + read-back verification are
# ITS contract); this file never touches the redis key directly.
# ---------------------------------------------------------------------------
KILLSWITCH_CMD_RE = re.compile(r"^\s*/killswitch(?:@\w{1,64})?\s*$",
                               re.IGNORECASE)
KILL_SWITCH_SCRIPT = os.path.join(_REPO_ROOT, "cabinet", "scripts",
                                  "kill-switch.sh")
#: The audit-row actor for taps/commands arriving on the captain's Telegram —
#: kill-switch.sh records ${CABINET_OFFICER:-captain}, so this is how a flip
#: from the phone stays distinguishable from a terminal flip in the ledger.
KS_TELEGRAM_ACTOR = "captain-telegram"
_KS_ACTIONS = frozenset({"activate", "deactivate", "status"})
KS_SCRIPT_TIMEOUT_S = 30


def is_killswitch_command(text: str) -> bool:
    """True for the bare /killswitch bot command (optional @botname suffix).
    Anchored — the word inside a sentence is conversation for the Chair,
    never a control command."""
    return bool(KILLSWITCH_CMD_RE.match(text or ""))


def run_kill_switch(action: str, *, script: "str | None" = None,
                    actor: str = KS_TELEGRAM_ACTOR,
                    timeout: int = KS_SCRIPT_TIMEOUT_S,
                    env: "dict | None" = None) -> "tuple[int, str]":
    """Execute ONE sanctioned kill-switch.sh action → ``(rc, output)``.

    The ONLY place this file shells to the emergency surface. ``action`` is a
    closed set (activate | deactivate | status — anything else raises: taps
    map verbs to fixed strings, so an open string here would be a bug, not
    input). ``CABINET_OFFICER`` is set to ``actor`` so the SCRIPT's own audit
    row (kill_switch_activated/_deactivated) records telegram provenance —
    the audit trail belongs to the script, never to this caller. Output is
    stdout+stderr combined verbatim (the card quotes the script's own words).
    Never raises on execution failure — a broken/missing/timed-out script
    returns a LOUD non-zero tuple so the card can say so (an exception here
    would degrade to the generic relay floor and hide the failure)."""
    if action not in _KS_ACTIONS:
        raise ValueError(f"unsanctioned kill-switch action: {action!r}")
    run_env = dict(os.environ if env is None else env)
    run_env["CABINET_OFFICER"] = actor
    try:
        p = subprocess.run(["bash", script or KILL_SWITCH_SCRIPT, action],
                           capture_output=True, text=True, timeout=timeout,
                           env=run_env)
    except Exception as exc:  # noqa: BLE001 — loud tuple beats an exception
        return 1, (f"kill-switch.sh did not run ({type(exc).__name__}) — "
                   "NOT verified")
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    combined = out + ("\n" + err if err else "")
    return p.returncode, combined.strip()


def killswitch_command_reply(*, api_post, chat_id, ks_run=run_kill_switch,
                             log=log) -> bool:
    """Answer /killswitch with the standing control card — a FRESH status
    read + Halt/Resume buttons minted through the allowlisted verb enum
    (killswitch_card → decision_card.cb). Returns True when the card was
    sent; False lets the caller fall open to the Chair relay so the
    Captain's command is never silently consumed."""
    try:
        from framework.comms.surface import killswitch_card as kc
        rc, out = ks_run("status")
        face = kc.render(rc, out)
        api_post("sendMessage", {
            "chat_id": int(chat_id), "text": face["text"],
            "reply_markup": {"inline_keyboard": face["keyboard"]}})
        return True
    except Exception as exc:  # noqa: BLE001 — fail-open to the Chair relay
        log(f"killswitch card send failed (falling back to relay): "
            f"{type(exc).__name__}: {exc}")
        return False


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


def captain_inbound_archive_dir() -> str:
    """Resolve the durable captain-inbound archive dir — same env-override
    contract as the feed/events/undo family (CABINET_CAPTAIN_INBOUND_DIR;
    default under ~/Library/Application Support/cabinet/). The repo-root
    conftest fences the env var so pytest can never write the live archive."""
    return os.environ.get("CABINET_CAPTAIN_INBOUND_DIR") or os.path.expanduser(
        "~/Library/Application Support/cabinet/captain-inbound")


# In-process idempotency for archive appends (one poller per BOT TOKEN —
# 409-reaping is per token, so a second telegram-voice officer would be a
# second writer; the row's ``officer`` field keeps their day-file rows
# attributable). Cleared past a sane bound — a duplicate row after a clear
# (or a crash-mid-deliver restart, which re-runs the whole update) is
# HARMLESS by contract: rows are verbatim-identical and readers key on
# dm_id. Bound chosen far above any realistic poller lifetime.
_ARCHIVED_DM_IDS: set = set()
_ARCHIVE_DEDUP_MAX = 4096


def archive_captain_dm(chat_id, message_id, text, *, kind="text", update_id=0,
                       tg_date=0, quoted="", file_kind="", file_name="",
                       officer="", log=log) -> str:
    """Append one Captain utterance VERBATIM to the durable inbound archive.

    THE 30-ring (cabinet:captain:recent-msgs) is a Chair nicety with a ~30-msg
    half-life and 280-char truncation — by 2026-07-16, 8 of 26 traced Captain
    messages were unrecoverable verbatim. This archive is the truth surface the
    captain-message-effect design builds on (Tier-2 case ledger source, every
    metric's denominator): append-only day files
    ``inbound-YYYY-MM-DD.jsonl`` (UTC) under ``captain_inbound_archive_dir()``,
    one JSON row per utterance, ``ensure_ascii=False`` so Danish text stays
    verbatim, fsync'd (captain-DM rates make that free).

    dm_id = ``tg-<chat_id>-<message_id>`` — message_id is chat-scoped in
    Telegram, so callers MUST pass the CHAT id (``msg["chat"]["id"]``), not
    the sender id, for the pair to be globally stable. READERS DEDUP BY
    dm_id: the receive loop re-delivers a whole update after a
    crash-mid-deliver restart (poller header contract), so the same utterance
    MAY append twice with identical content; the in-process set above only
    trims the common case. The matching reader is
    ``cabinet/scripts/lib/captain_inbound.py`` (CLI:
    ``cabinet/scripts/captain-inbound.py latest|get|search [--semantic]``).

    KNOWN EXCLUSIONS (deliberate): callback taps / reactions / poll votes are
    decisions, not utterances — they are feed-journaled instead. Unsupported
    media kinds (video/sticker/…) are not relayed (pre-existing) and not
    archived — the archive records what the officer actually saw.
    Onboarding-routed Captain DMs ARE archived (kind="onboarding") even
    though they bypass the relay — they are Tier-0 anchor source material.
    /killswitch commands likewise archive (kind="killswitch") despite the
    mechanical card reply — an emergency-stop request is exactly the
    utterance whose verbatim record must survive.

    Degrade-safe but LOUD: an archive failure never blocks delivery (a Captain
    message must reach the officer even with a broken disk), but it logs an
    ``ARCHIVE-GAP`` marker — unlike the ring's silent pass — because a gap in
    a truth surface must be visible. A failed append is NOT marked deduped, so
    the crash-before-offset-save replay retries it; once delivery succeeds and
    the offset advances, a missed row is a permanent, log-visible gap
    (accepted: delivery outranks the journal). Returns the dm_id either way."""
    dm_id = f"tg-{_sanitize_id(str(chat_id))}-{int(message_id)}"
    if dm_id in _ARCHIVED_DM_IDS:
        return dm_id
    row = {
        "v": 1,                            # row schema version
        "dm_id": dm_id,
        "chat_id": _sanitize_id(str(chat_id)),
        "message_id": int(message_id),
        "update_id": int(update_id),
        "officer": officer or "",          # receiving bot's officer (multi-writer attribution)
        "kind": kind,                      # text | file | file-error | onboarding | killswitch
        "text": text or "",               # the utterance, UNTRUNCATED
        "quoted": quoted or "",           # reply-to context, UNTRUNCATED
        "file_kind": file_kind or "",
        "file_name": sanitize_filename(file_name) if file_name else "",
        "tg_date": int(tg_date or 0),      # Telegram's own timestamp
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        d = captain_inbound_archive_dir()
        os.makedirs(d, exist_ok=True)
        path = os.path.join(
            d, "inbound-" + time.strftime("%Y-%m-%d", time.gmtime()) + ".jsonl")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        if len(_ARCHIVED_DM_IDS) >= _ARCHIVE_DEDUP_MAX:
            _ARCHIVED_DM_IDS.clear()
        _ARCHIVED_DM_IDS.add(dm_id)
    except Exception as exc:
        log(f"ARCHIVE-GAP: captain-inbound append failed for {dm_id} "
            f"({type(exc).__name__}: {exc}) — delivery unaffected")
    return dm_id


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


def handle_callback_query(cbq: dict, *, captain, api_post, inject, feed_append,
                          log=log, apply_tap=None) -> None:
    """Instant-ack an inline-button tap, then apply it MECHANICALLY.

    Order is law (tap pipeline fix 2026-07-11):
      1. answerCallbackQuery fires FIRST, on dequeue, before ANY other
         handling — one attempt + short timeout via ``answer_callback_now``,
         with a verb-appropriate toast (``tap_wire.classify`` is pure). An
         expired id (storm-delayed dequeue) is logged once, never retried.
      2. Captain check — a stray's tap is acked (spinner cleared) but never
         applied, journaled, or relayed (the bot is publicly addressable).
      3. Mechanical apply (``tap_wire.apply_tap``): defer/pacing taps park
         the card + flip its face + advance pacing durably; Approve/No route
         the SAME server-side verdict door the dashboard uses. NO LLM in the
         loop. Fail-open by construction: if the framework import or the
         apply itself breaks, the tap falls back to the pre-wire bracket-line
         relay so DM receive never degrades.
      4. Feed journal (ack state + apply outcome), then the bracket-line
         relay ONLY where the Chair is still needed (decision receipts for
         lesson-harvest, edit/undo follow-ups, foreign buttons).

    callback_data stays ids-only (≤64 bytes, ``[\\w:.|-]``) — chain state
    lives in Redis/ledger/census, never in the button."""
    data = cbq.get("data", "")
    toast = ""
    tap_wire = None
    try:
        from framework.comms.surface import tap_wire as _tw
        tap_wire = _tw
        toast = _tw.classify(data)[2]
    except Exception:
        toast = ""   # framework unavailable → spinner-clear ack + relay path

    cq_id = cbq.get("id")
    ack_state = "skipped"
    if cq_id:
        ack_state = answer_callback_now(api_post, cq_id, toast, log=log)

    frm = str((cbq.get("from") or {}).get("id", ""))
    if frm != str(captain):
        log(f"skip callback from={frm or '?'} (not captain)")
        return
    mid = int((cbq.get("message") or {}).get("message_id", 0) or 0)

    result = None
    if apply_tap is not None or tap_wire is not None:
        try:
            result = (apply_tap or tap_wire.apply_tap)(data, message_id=mid)
        except Exception as e:  # fail-open: relay is the floor, never less
            log(f"tap-wire apply failed (falling back to relay): "
                f"{type(e).__name__}: {e}")
            result = None
    result = result if isinstance(result, dict) else {}
    handled = bool(result.get("handled"))
    relay = bool(result.get("relay", True))
    summary = str(result.get("summary") or "")

    if handled or (result.get("mode") and result["mode"] != "foreign"):
        log(f"tap-wire: mode={result.get('mode')} handled={handled} "
            f"ack={ack_state} {summary}"[:300])

    row = {"direction": "in", "kind": "callback", "telegram_message_id": mid,
           "callback_data": sanitize_callback_data(data), "ack": ack_state}
    for k in ("mode", "item_id", "outcome"):
        if result.get(k):
            row[k] = str(result[k])[:120]
    feed_append(row)

    if relay or not handled:
        line = format_callback_line(mid, data)
        if handled and summary:
            # the ⚙ note = "already applied mechanically; harvest lessons,
            # never double-deliver" (same contract as the binder-wire DM note)
            line = f"{line} [⚙ {summary[:160]}]"
        inject(line)


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

    # Capture-seam chat_id (2026-07-16): emit the value the germline hooks gate
    # on (instance/config product.yml→platform.yml) so their chat_id match holds
    # by construction; env CAPTAIN_TELEGRAM_ID is the from.id relay gate (same
    # number in practice). Warn on any drift so this seam cannot silently re-break.
    hook_chat_id = resolve_hook_chat_id()
    tag_chat_id = hook_chat_id or captain
    if hook_chat_id and str(hook_chat_id) != str(captain):
        log(f"WARNING capture-seam: instance/config captain_telegram_chat_id "
            f"({hook_chat_id}) != CAPTAIN_TELEGRAM_ID env ({captain}); emitting "
            f"{hook_chat_id} in the channel tag (hooks gate on the yml value).")
    elif not hook_chat_id:
        log("WARNING capture-seam: instance/config/{product,platform}.yml has no "
            "captain_telegram_chat_id — the germline capture hooks default-deny, "
            "so Captain DMs will NOT be captured until it is set.")

    os.makedirs(state_dir, exist_ok=True)
    offset_file = os.path.join(state_dir, "inbound-offset.txt")
    try:
        offset = int(open(offset_file).read().strip())
    except Exception:
        offset = 0

    api = f"https://api.telegram.org/bot{token}"
    file_api = f"https://api.telegram.org/file/bot{token}"  # file downloads use /file/bot<token>/<path>
    redis_host = os.environ.get("REDIS_HOST", "localhost")
    dashboard_url = os.environ.get("CABINET_DASHBOARD_URL", "http://127.0.0.1:3100")
    onboarding_webhook_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    log(f"started officer={officer} session={session} captain={captain} offset={offset}")

    def api_post(path: str, payload: dict, timeout: "float | None" = None) -> dict:
        """POST JSON to a Bot API method (e.g. answerCallbackQuery). Token stays in
        `api` and is never logged. The ack path gets the SHORT deadline by
        default — an instant ack is the whole point (ACK_TIMEOUT_S)."""
        t = timeout or (ACK_TIMEOUT_S if path == "answerCallbackQuery" else 10)
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{api}/{path}", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=t) as r:  # noqa: S310 (fixed https host)
            return json.loads(r.read().decode("utf-8") or "{}")

    def apply_tap_live(data: str, *, message_id=None) -> dict:
        """The poller's live tap_wire binding: mechanical apply + the tapped
        card's keyboard receipt (editMessageReplyMarkup — content-preserving,
        same transport class as the poller's receipt reactions; journaled by
        the caller's feed row). Recipient is ALWAYS the Captain's chat.
        Kill-switch seams (2026-07-17): ``edit_text`` repaints the standing
        /killswitch card in place; ``ks_exec`` is THE poller-only door to
        kill-switch.sh (telegram-provenance audit actor) — tap_wire refuses
        kill-switch verbs without it, so no other importer inherits the
        flip."""
        from framework.comms.surface import tap_wire

        def _mark(mid2: int, kb: list) -> None:
            api_post("editMessageReplyMarkup", {
                "chat_id": int(captain), "message_id": int(mid2),
                "reply_markup": {"inline_keyboard": kb}})

        def _edit_text(mid2: int, text2: str, kb: list) -> None:
            api_post("editMessageText", {
                "chat_id": int(captain), "message_id": int(mid2),
                "text": text2,
                "reply_markup": {"inline_keyboard": kb}})

        return tap_wire.apply_tap(data, message_id=message_id,
                                  edit_markup=_mark, edit_text=_edit_text,
                                  ks_exec=run_kill_switch)

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

    def record_recent_msg(message_id: int, text: str) -> None:
        """Push (id, text, ts) onto a bounded ring so the Chair can resolve ANY
        recent Captain message to its id — not just the latest.

        channel.send threads onto cabinet:last-captain-msg-id (the LATEST) only;
        this ring (cabinet:captain:recent-msgs, newest-first, last 30) lets the
        Chair target an EARLIER message by content and pass its id to
        channel.send(reply_to=…). Fixes the always-reply-to-latest bug — the Chair
        had no way to see an earlier message's id. Degrade-safe: any redis-cli
        failure is swallowed; the ring is a nicety, never a precondition for
        delivering the DM."""
        try:
            entry = json.dumps({"id": int(message_id),
                                "text": (text or "")[:280],
                                "ts": int(time.time())})
            subprocess.run(
                ["redis-cli", "-h", redis_host, "LPUSH",
                 "cabinet:captain:recent-msgs", entry],
                capture_output=True, timeout=10,
            )
            subprocess.run(
                ["redis-cli", "-h", redis_host, "LTRIM",
                 "cabinet:captain:recent-msgs", "0", "29"],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass  # ring is best-effort; never block receive

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

    def deliver(text: str, quoted: str = "", binder_note: str = "", mid: int = 0) -> None:
        """Idle-gate, then inject the Captain DM into the officer pane as a turn.
        `quoted` is the message the Captain REPLIED TO (Telegram reply-threading) — prefixed
        so the officer sees the exact draft / proposal / message being answered, with
        no need to ask 'which one'. `binder_note` (F0.5) is the mechanical binder
        wire's outcome — when present, recording+delivery ALREADY happened; the
        Chair must harvest lessons only and never double-deliver. The raw Captain
        text is wrapped in the <channel source="telegram" …> tag the germline
        capture hooks require (build_captain_channel_relay)."""
        note = f" [⚙ {binder_note}]" if binder_note else ""
        raw_inject(build_captain_channel_relay(tag_chat_id, mid, text,
                                               note=note, quoted=quoted))

    while True:
        try:
            params = urllib.parse.urlencode({
                "offset": offset + 1,
                "timeout": LONG_POLL_S,
                "allowed_updates": json.dumps(ALLOWED_UPDATES),
            })
            with urllib.request.urlopen(f"{api}/getUpdates?{params}", timeout=READ_TIMEOUT_S) as resp:  # noqa: S310 (fixed https host)
                data = json.load(resp)
        except Exception as e:
            # A bare socket read-timeout on the long-poll is EXPECTED under a
            # flaky uplink (the LONG_POLL_S hold returned nothing and the
            # READ_TIMEOUT_S socket read then lapsed) — it is not an error,
            # so it does not spam the log at error level. It already burned
            # READ_TIMEOUT_S while updates queued server-side, so re-poll
            # IMMEDIATELY: every extra second pushes a queued tap closer to
            # Telegram's ~15s answerCallbackQuery window (line-1394 failure
            # mode). Anything else (HTTP status, 409, DNS) logs loudly and
            # keeps the 5s backoff.
            _timeout_blip = ("timed out" in str(e).lower()
                             and "409" not in str(e))
            if _timeout_blip:
                continue
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

        retry_onboarding = False
        for upd in data.get("result", []):
            uid = int(upd.get("update_id", 0))
            if is_onboarding_update(upd):
                forwarded = forward_onboarding_update(
                    upd,
                    dashboard_url=dashboard_url,
                    webhook_secret=onboarding_webhook_secret,
                )
                disposition = onboarding_forward_disposition(forwarded)
                if disposition == "ack":
                    # No source path, purpose, or callback data in logs. The
                    # route already sent the canonical reply and recorded its
                    # surface evidence; advancing the offset is the ACK.
                    # Captain MESSAGE-updates routed here still archive
                    # (kind="onboarding") — onboarding answers are Tier-0
                    # anchor source material and part of the archive's
                    # every-utterance contract; taps stay excluded (not
                    # utterances). Best-effort like the whole archive.
                    ob_msg = upd.get("message") or {}
                    ob_frm = str((ob_msg.get("from") or {}).get("id", ""))
                    ob_text = str(ob_msg.get("text") or ob_msg.get("caption") or "")
                    if ob_frm == str(captain) and ob_text:
                        chat_dm = str((ob_msg.get("chat") or {}).get("id") or ob_frm)
                        ob_mid = int(ob_msg.get("message_id", 0))
                        archive_captain_dm(chat_dm, ob_mid, ob_text,
                                           kind="onboarding", update_id=uid,
                                           tg_date=ob_msg.get("date", 0),
                                           officer=officer)
                    log(f"onboarding update_id={uid} routed to canonical local skin")
                    offset = max(offset, uid)
                    save_offset(offset)
                    continue
                if disposition == "retry":
                    # Do not process a later update from this batch: advancing
                    # past it would make Telegram discard the failed one. The
                    # stable update_id makes the canonical action idempotent on
                    # the next poll; only visible reply delivery is retried.
                    log(f"onboarding update_id={uid} reply delivery failed — retaining offset for canonical retry")
                    retry_onboarding = True
                    break
                # Recovery floor: preserve the pre-existing visible relay/tap
                # path. A missing dashboard or secret must be diagnosable, but
                # must never silently consume the Captain's command.
                log(f"onboarding update_id={uid} local skin unavailable — preserving Chair relay fallback")
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
                                          inject=raw_inject, feed_append=fa, log=log,
                                          apply_tap=apply_tap_live)
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
                # Telegram reply-threading: if the Captain REPLIED TO a message (a draft, a
                # proposal card, a briefing line), capture what they're answering so the
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
                    record_recent_msg(mid, caption)   # ring: file msgs resolvable by caption/id too
                    chat_dm = str((msg.get("chat") or {}).get("id") or frm)
                    archive_captain_dm(chat_dm, mid, caption, kind="file-error",
                                       update_id=uid, tg_date=msg.get("date", 0),
                                       quoted=quoted_full, file_kind=att["kind"],
                                       file_name=att.get("name", ""), officer=officer)
                    fa({"direction": "in", "kind": "file-error",
                        "telegram_message_id": mid, "file_kind": att["kind"]})
                    err_line = (f"[tg-file-error name={sanitize_filename(att.get('name', '?'))} "
                                f"kind={att['kind']} reason=too-large-20mb]")
                    deliver(f"{err_line} {caption}".strip(), quoted, "", mid=mid)
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
                    record_recent_msg(mid, caption)   # ring: file msgs resolvable by caption/id too
                    chat_dm = str((msg.get("chat") or {}).get("id") or frm)
                    archive_captain_dm(chat_dm, mid, caption, kind="file",
                                       update_id=uid, tg_date=msg.get("date", 0),
                                       quoted=quoted_full, file_kind=att["kind"],
                                       file_name=att.get("name", ""), officer=officer)
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
                    deliver(f"{body} {caption}".strip(), quoted, "", mid=mid)
                elif frm == str(captain) and is_killswitch_command(text):
                    # /killswitch → the mechanical emergency-stop card from
                    # THIS process (captain-controls plan 2026-07-17). Never
                    # routed through the Chair: with the switch ACTIVE the
                    # officer is halted, so a relayed command would answer
                    # exactly when it matters least. Card-send failure falls
                    # OPEN to the status-quo Chair relay below — the command
                    # is never silently consumed.
                    log(f"captain /killswitch update_id={uid} -> control card")
                    mid = int(msg.get("message_id", 0))
                    set_last_captain_msg_id(mid)
                    record_recent_msg(mid, text)
                    chat_dm = str((msg.get("chat") or {}).get("id") or frm)
                    archive_captain_dm(chat_dm, mid, text, kind="killswitch",
                                       update_id=uid, tg_date=msg.get("date", 0),
                                       quoted=quoted_full, officer=officer)
                    sent = killswitch_command_reply(api_post=api_post,
                                                    chat_id=captain, log=log)
                    fa({"direction": "in", "kind": "killswitch-command",
                        "telegram_message_id": mid,
                        "card": "sent" if sent else "send-failed"})
                    if not sent:
                        deliver(text, quoted, "", mid=mid)
                elif frm == str(captain) and text:
                    log(f"captain msg update_id={uid} ({len(text)} chars{', reply' if quoted else ''}) -> relaying")
                    mid = int(msg.get("message_id", 0))
                    react(mid, pick_reaction(mid, classify_inbound(text)))  # deterministic read-ack
                    set_last_captain_msg_id(mid)   # id the Chair threads replies onto
                    record_recent_msg(mid, text)   # ring: Chair can target THIS msg later by content
                    chat_dm = str((msg.get("chat") or {}).get("id") or frm)
                    archive_captain_dm(chat_dm, mid, text, kind="text",
                                       update_id=uid, tg_date=msg.get("date", 0),
                                       quoted=quoted_full, officer=officer)
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
                        _flavor_a_dir = os.path.join(_REPO_ROOT, "instance", "flavor-a")
                        if _flavor_a_dir not in sys.path:
                            sys.path.insert(0, _flavor_a_dir)
                        from flavor_a import screenpipe_reply_wire as sp_reply_wire
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
                    deliver(text, quoted, binder_note, mid=mid)
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
        if retry_onboarding:
            # A hard Telegram outage must not hot-loop the local Dashboard or
            # starve due-trigger maintenance. One second keeps callback retries
            # prompt while bounding repeated send attempts.
            time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
