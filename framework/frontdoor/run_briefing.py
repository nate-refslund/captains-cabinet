"""framework.frontdoor.run_briefing — one pass of the recurring unified briefing.

Scheduled by launchd (cabinet/scripts/run-frontdoor-briefing.sh). Pulls real
signals into the durable intake (morning_synthesis) and runs the send path
(run_frontdoor.run_send_path) → ONE unified message to the Captain on the single
channel, replacing the personal-source morning-brief DM that the cutover silenced.

PM augmentation: the wrapper sets ``CABINET_RUN_MODE=PM`` for the evening run
(hour ≥ 17). In PM mode, AFTER the normal synthesis enqueue, we also enqueue the
comprehensive daily recap (framework.frontdoor.daily_recap) — a neutral
synthesis over the get_source() surfaces that folds the long-form recap into
this same unified briefing (its Monday Reflections + vault-note legs were
deleted with egg row R023; boards archived 2026-07-05). The AM run
(CABINET_RUN_MODE unset / "AM") is unchanged. The recap is best-effort: a
failure logs into the result and never blocks the briefing send.

Send-only + gated end-to-end: run_send_path delegates to channel.send, which is
hard-gated on framework.env.allow_sends() (a dev/test session composes but does
NOT send). No reply handling here — the interactive reply→orchestration is the
LLM-Chair capstone.

LOCAL-FIRST genesis receipt (Perfect Cabinet Wave A, Captain 2026-07-09): with
``--local-render`` (or ``run_briefing(local_render=True)``) ONE briefing is
composed from the LOCAL genesis surfaces (framework.onboarding.genesis: the
org-PROPOSED outcome cards, the focus letter, the research-brief status),
written to ``instance/memory/first-briefing-<UTC date>.md`` and printed —
never sent. In this mode the synthesis/recap/digest legs and the Redis intake
are DELIBERATELY not touched: a genesis instance has no LIVE estate to gather
(the DERIVED estate — what the cabinet READ — reaches the cards through
genesis, not through these legs), and a scratch-instance run on a developer
Mac must never consume the LIVE
``cabinet:frontdoor:intake`` consumer-group items (a drain marks them
delivered). The normal path — and the Telegram send through channel.py +
allow_sends — is byte-identical to before and still used when configured.
``--now`` makes the run-immediately contract explicit for wrappers (the module
has no in-code schedule window; launchd owns the cadence).
"""
from __future__ import annotations

import os

from framework import env
from framework.frontdoor import (composer, daily_recap, morning_synthesis,
                                 run_frontdoor, tell_digest)

# Instance-memory layout the frontdoor writes into, declared as a single named
# REL constant — the same convention as framework.onboarding.genesis's
# FIRST_BRIEFING_DIR_REL / LIBRARY_DIR_REL. Keeps the instance-path dependency
# named and greppable in one place rather than scattered Path segments.
_BRIEFINGS_DIR_REL = "instance/memory/briefings"


def _is_pm() -> bool:
    """True when the wrapper flagged this as the evening (PM) run.

    The launchd wrapper sets CABINET_RUN_MODE=PM for hour ≥ 17, else AM. We
    accept any case and treat ONLY an explicit "PM" as PM (default/unset → AM)
    so a missing env never accidentally fires the recap in the morning."""
    return os.environ.get("CABINET_RUN_MODE", "").strip().upper() == "PM"


def _default_digest() -> dict:
    """Production TI-5 digest call: gather the 📈 LOOP readout (per-card-kind
    approve/edit/skip/expired rates + undo-rate trend + latest falsifier-series
    line — lane instrument, 2026-07-05) and enqueue the digest with it.

    Lives HERE, not in tell_digest, because enqueue_digest deliberately never
    auto-gathers the readout (its live-ledger/series reads would make fixtured
    callers non-hermetic — tell_digest.py module header). gather_loop_readout
    never raises (fail-safe: readout absent on error, digest never blocked)."""
    return tell_digest.enqueue_digest(readout=tell_digest.gather_loop_readout())


def _default_needs_you() -> "dict | None":
    """Compose + enqueue the war-room 'Needs you (N)' section from the live
    census. Returns the enqueue receipt, or None when nothing pends (an
    empty shelf renders as silence, not an empty header)."""
    from framework.attention import queue as attention_queue
    from framework.attention import queue_card
    item = queue_card.briefing_needs_you_item(attention_queue.build_queue())
    if item is None:
        return None
    from framework.frontdoor import intake
    return {"needs_you": True, "id": intake.enqueue(item)}


# ---------------------------------------------------------------------------
# Briefing-as-card (ONE-VOICE-RESET, Captain interview 2026-07-11)
#
# When the deployment arms `briefing_card` (instance/config/comms-surface.yml
# or CABINET_BRIEFING_CARD=1 — framework.comms.surface.config), the briefing
# stops sending the composed long body as a (1/N)-chunked Telegram wall:
#
#   * the drain/compose leg still runs UNCHANGED (durable intake, dedup,
#     recover_pending), but its send seam ARCHIVES the composed body to
#     instance/memory/briefings/<UTC stamp>.md — content preserved as DATA
#     (synthesis, PM recap, TI-5 digest text with its undo indexes, every
#     personal-source pipe item). Items are ACKed only after the archive write
#     succeeds (loss-safe: unarchived content stays pending on the stream).
#     The `cabinet:digest:<date>` undo manifest is persisted by the digest
#     leg exactly as before, so `undo <n>` replies keep binding.
#   * ONE briefing card goes out instead (briefing_card.maybe_send → gateway
#     → charter class `briefing` → direct send, edit-in-place per slot):
#     plain headline + "N decisions ready" + the Triage control. Decisions
#     themselves ride the paced single-decision cards, never the briefing.
#   * the "Needs you (N)" intake section is skipped — the same numbers render
#     on the card and the pinned overview (one list, several skins).
#
# The classic text path is byte-identical when the knob is off. The knob is
# ON by default since 2026-07-26 (Captain ratified it 2026-07-11; the value
# had lived only in the instance file the egg deletes) — off is now opt-out.
# ---------------------------------------------------------------------------

def _briefing_card_mode() -> bool:
    """True when briefing-as-card is armed. Fail-closed to the classic text
    path on any config error (a broken knob must not lose the briefing)."""
    try:
        from framework.comms.surface import config as _scfg
        return bool(_scfg.load().get("briefing_card"))
    except Exception:
        return False


def _briefings_dir():
    """The archive home: <repo>/instance/memory/briefings (CABINET_ROOT wins,
    else file-relative — the same root convention the rest of frontdoor uses)."""
    from pathlib import Path
    root = os.environ.get("CABINET_ROOT", "").strip()
    base = Path(root) if root else Path(__file__).resolve().parents[2]
    return base / _BRIEFINGS_DIR_REL


def _archive_briefing_body(text: str) -> str:
    """Write the composed briefing body to a per-run archive file, atomically
    (tmp + os.replace). Returns the path. RAISES on failure — the caller's
    send seam then reports sent=False so the drained items stay PENDING on
    the intake stream (never ACK content that is not durably on disk)."""
    from datetime import datetime, timezone
    d = _briefings_dir()
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    path = d / f"briefing-{stamp}.md"
    body = (f"# Briefing body — {stamp} (archived, not sent)\n\n"
            "This is the data the briefing card summarized. It used to be a "
            "multi-part Telegram message; since 2026-07-11 it lands here and "
            "the card carries the headline.\n\n---\n\n" + text + "\n")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)
    return str(path)


def _archive_send_fn(sink: dict):
    """The card-mode send seam for run_send_path: archive instead of send.
    Mirrors channel.send's calling convention. sent=True ONLY after a
    successful archive write, so ACK semantics stay loss-safe."""
    def _send(text, *, http_post=None):  # http_post ignored — no network here
        try:
            path = _archive_briefing_body(text)
        except Exception as e:  # noqa: BLE001 — report, keep items pending
            return {"status": "error", "sent": False,
                    "error": f"archive failed: {type(e).__name__}: {e}"[:300]}
        sink["archive_path"] = path
        return {"status": "archived", "sent": True, "archive_path": path}
    return _send


def _flatline_notice() -> str:
    """The channel-flatline question for the CARD headline, or "".

    Card mode archives the composed body instead of sending it, so the digest's
    📈 LOOP line — where this question normally rides — never reaches the
    Captain on a card-mode deployment (and the knob is on by default). The
    headline is the one thing that does. ONE engine-minted sentence, no item
    payload text, no marker char; ``tell_digest.flatline_notice`` owns the
    once-per-episode rule and the wording, so the two surfaces cannot drift.
    Fail-open: an alarm must never cost the briefing card."""
    try:
        return tell_digest.flatline_notice()
    except Exception:  # noqa: BLE001
        return ""


def _plain_headline(gather: dict, digest: "dict | None") -> str:
    """One plain sentence for the card: counts only, NEVER item payload text
    (untrusted pipe content must not ride the card surface — the full body
    lives in the archive file). Honest on an archive failure: content that
    did not land on disk is reported as still queued, not as kept.

    Plus, when it fires, the channel-flatline question (``_flatline_notice``)
    — the one captain-facing line that would otherwise land only in the
    archived body nobody reads."""
    n = int(gather.get("drained") or 0)
    if n and gather.get("sent"):
        head = f"Gathered {n} update{'s' if n != 1 else ''} into today's notes (kept on file)"
    elif n:
        head = (f"Gathered {n} update{'s' if n != 1 else ''} — saving them hit "
                "an error, so they stay queued for the next round")
    else:
        head = "Nothing new to gather this round"
    acted = 0
    if isinstance(digest, dict):
        try:
            acted = int(digest.get("acted") or 0)
        except (TypeError, ValueError):
            acted = 0
    if acted:
        head += (f". {acted} thing{'s were' if acted != 1 else ' was'} done for "
                 f"you — reply `undo <n>` to reverse one")
    head += "."
    notice = _flatline_notice()
    if notice:
        head += f" ⚠️ {notice}"
    return head


def _default_briefing_card(headline: str) -> dict:
    """Live card send: briefing_card.maybe_send (re-checks the knob, builds
    the live census, rides the gateway/charter like every officer card)."""
    from framework.comms.surface import briefing_card
    return briefing_card.maybe_send(headline)


def _run_local_render(*, genesis_fn=None, now: str | None = None) -> dict:
    """The LOCAL-FIRST genesis receipt: compose ONE briefing from the local
    genesis surfaces and WRITE it — never send, never touch Redis.

    Items come from ``genesis_fn`` (default:
    ``framework.onboarding.genesis.genesis_intake_items`` — the org-PROPOSED
    outcome cards + focus letter + research-brief status, file reads only).
    The composed markdown lands atomically at
    ``<root>/instance/memory/first-briefing-<UTC date>.md`` (root honors
    ``CABINET_ROOT``, so scratch instances are targeted by env). channel.py is
    never called; the result mirrors run_send_path's shape with
    ``sent: False`` + ``local_render: True`` + ``receipt_path``. Honest empty:
    zero genesis items still write the receipt, saying so plainly."""
    from datetime import datetime, timezone

    from framework.onboarding import genesis  # lazy: only the local path needs it

    gather = genesis_fn or genesis.genesis_intake_items
    items = list(gather() or [])
    text = composer.compose(items, max_per_tier=None)  # the first briefing shows ALL cards

    utcnow = datetime.now(timezone.utc)
    date = utcnow.strftime("%Y-%m-%d")
    stamp = now or utcnow.strftime("%Y-%m-%dT%H:%M:%SZ")
    # Path knowledge lives with the genesis surfaces (layer-sep FINAL-C):
    # onboarding owns WHERE the receipt lands; this module composes the text.
    path = genesis.first_briefing_path(date)
    body = (
        f"# First briefing — {date} (LOCAL-FIRST receipt)\n\n"
        f"- composed: {stamp} on this machine, from local genesis surfaces only\n"
        "- sent: no — the Telegram channel engages post-hatch when configured "
        "(channel.py + allow_sends untouched)\n"
        "- propose-only: every outcome card below is a DRAFT "
        "(captain_ratified: false); ratify by moving it into "
        "instance/config/outcomes.yml\n\n"
        + (text if text else
           "(honest empty — no genesis items were staged; run the genesis "
           "proposal step: python3.12 -m framework.onboarding.genesis)")
        + "\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)

    return {
        "synthesis": {"skipped": "local-render (no live estate; the DERIVED "
                                 "estate reaches the cards through genesis)"},
        "recap": None,
        "digest": {"skipped": "local-render"},
        "send": {
            "drained": len(items), "item_ids": [], "text": text,
            "sent": False, "send": None, "acked": 0, "recovered": 0,
            "allow_sends": env.allow_sends(), "local_render": True,
            "receipt_path": str(path),
        },
    }


def run_briefing(
    *,
    hours: int = 72,
    limit: int = 8,
    enqueue_fn=None,
    send_fn=None,
    drain_fn=None,
    ack_fn=None,
    pending_fn=None,
    recap_fn=None,
    digest_fn=None,
    needs_you_fn=None,
    run_mode: str | None = None,
    local_render: bool = False,
    genesis_fn=None,
    card_mode: bool | None = None,
    card_send_fn=None,
) -> dict:
    """Enqueue a fresh synthesis (+ the PM daily recap + the TI-5 digest +
    the war-room "Needs you (N)" section), then run one send pass.

    Returns ``{'synthesis': <enqueue result>, 'recap': <recap result|None>,
    'digest': <tell_digest result>, 'needs_you': <enqueue receipt|None>,
    'send': <run_send_path result>}``.

    PM-only recap: when this is the evening run (``run_mode == 'PM'``, else the
    CABINET_RUN_MODE env), the daily recap is enqueued AFTER the synthesis so it
    rides the same unified briefing. ``recap`` is None on the AM run.

    TI-5 digest (BOTH runs — the twice-daily act-then-tell surface): the
    ACTED/AWAITING/WATCHING/SELF digest is enqueued before the send pass so it
    rides this same unified briefing, and its ``cabinet:digest:<date>`` manifest
    is persisted first so `undo <n>` / `👍 <n>` replies bind the moment the text
    lands (checkpoint 2026-07-04 Tier-0 #6 — the Captain's ruled flip prerequisite;
    plugs the binder no-pid label leak). The default digest also carries the
    📈 LOOP readout (acceptance/undo rates + falsifier series — see
    ``_default_digest``). Best-effort: a digest failure logs into
    the result and never blocks the briefing. Kill-switch CABINET_TELL_DIGEST=0.

    LOCAL-FIRST genesis receipt: ``local_render=True`` short-circuits to
    ``_run_local_render`` — the briefing is composed from the local genesis
    surfaces (``genesis_fn`` seam; default
    framework.onboarding.genesis.genesis_intake_items), written to
    ``instance/memory/first-briefing-<UTC date>.md`` and returned, with the
    synthesis/recap/digest legs and the Redis intake deliberately untouched
    (module docstring has the why). All other seams are ignored in that mode;
    the normal path below is unchanged.

    BRIEFING-AS-CARD (ONE-VOICE-RESET 2026-07-11): when armed (`briefing_card`
    knob; ``card_mode`` seam overrides), the composed body is ARCHIVED (send
    seam → instance/memory/briefings/, ACK only after the write) and ONE
    briefing card goes out via briefing_card.maybe_send. In that mode the
    result's ``send`` leg reports the CARD delivery — its ``sent`` is True
    only when the card reached the Captain (the launchd wrapper's delivered-
    marker grep keys off exactly that), the raw drain/compose receipt moves
    to ``gather`` (with its own ``sent`` key REMOVED so no other "sent": true
    can satisfy the wrapper), and the needs-you enqueue is skipped (the same
    numbers render on the card + the pinned overview). Knob off = the classic
    path below, byte-identical.

    Seams: ``enqueue_fn`` overrides the synthesis enqueue; ``recap_fn`` overrides
    the daily-recap enqueue; ``digest_fn`` overrides the TI-5 digest enqueue;
    ``run_mode`` forces AM/PM; ``send_fn`` / ``drain_fn`` / ``ack_fn`` forward to
    run_send_path; ``card_mode`` / ``card_send_fn`` override the briefing-card
    knob and card transport — all for tests (no real network / Redis / brain).
    The token never appears in the result (channel.send scrubs; run_send_path
    only re-surfaces the scrubbed dict).
    """
    if local_render:
        return _run_local_render(genesis_fn=genesis_fn)

    enqueue = enqueue_fn or morning_synthesis.enqueue_synthesis
    syn = enqueue(hours=hours, limit=limit)

    is_pm = (run_mode.strip().upper() == "PM") if run_mode is not None else _is_pm()
    recap = None
    if is_pm:
        recap_enqueue = recap_fn or daily_recap.enqueue_daily_recap
        try:
            recap = recap_enqueue()
        except Exception as e:  # best-effort: never block the briefing send
            recap = {"recap": False, "error": str(e)[:300]}

    # TI-5: the act-then-tell digest rides BOTH the 07:30 and 19:30 briefings.
    # Enqueued BEFORE the send pass so this run's drain composes it in. The
    # default path (_default_digest) also carries the 📈 LOOP readout; the
    # digest_fn seam is unchanged and takes no readout.
    digest_enqueue = digest_fn or _default_digest
    try:
        digest = digest_enqueue()
    except Exception as e:  # best-effort: never block the briefing send
        digest = {"digest": False, "error": str(e)[:300]}

    # Briefing-as-card? Resolve ONCE per run (seam wins, else the knob).
    as_card = _briefing_card_mode() if card_mode is None else bool(card_mode)

    # War-room census: the "Needs you (N)" briefing section (command-center
    # §4C) — ONE intake item from the same census every skin renders
    # (SURFACE-PARITY), enqueued before the send pass so this run composes
    # it. Silent when nothing pends. ``needs_you_fn`` seam for tests;
    # best-effort — a census failure never blocks the briefing. In card mode
    # it is SKIPPED: the identical numbers render on the briefing card and
    # the pinned overview, so an intake copy would only duplicate the list
    # into the archive.
    needs_you = None
    if as_card:
        needs_you = {"needs_you": False,
                     "skipped": "briefing-card mode — the numbers render on "
                                "the card + the pinned overview"}
    else:
        try:
            enqueue_item = needs_you_fn or _default_needs_you
            needs_you = enqueue_item()
        except Exception as e:
            needs_you = {"needs_you": False, "error": str(e)[:300]}

    # recover_pending=True is the fix for the single-voice comms-awareness gap:
    # surface.py (every 5 min) reads the intake with ">" and surfaces ONLY
    # ping-now in real time, leaving batch/fyi items delivered-but-unacked in the
    # consumer group's PEL "for the briefing to compose". Those items are then no
    # longer ">"-visible, so a plain briefing drain saw nothing and the batch/fyi
    # backlog — comms-officer FYIs, relevant-but-no-reply messages — surfaced
    # NEVER. The briefing is the designated place batch/fyi reaches the Captain, so it
    # recovers that pending backlog, composes it into the one voice, sends, and
    # ACKs. (surface.py is unchanged: still real-time ping-now only.)
    # Card mode: the drain/compose leg keeps running (durable intake, dedup,
    # recover_pending) but its send seam ARCHIVES the body instead of posting
    # a chunked wall. An explicit test-provided send_fn still wins.
    sink: dict = {}
    effective_send_fn = send_fn
    if as_card and effective_send_fn is None:
        effective_send_fn = _archive_send_fn(sink)

    send = run_frontdoor.run_send_path(
        send_fn=effective_send_fn, drain_fn=drain_fn, ack_fn=ack_fn,
        pending_fn=pending_fn, recover_pending=True)

    if not as_card:
        return {"synthesis": syn, "recap": recap, "digest": digest,
                "needs_you": needs_you, "send": send}

    # ONE briefing card (status + "N decisions ready — Triage"). Best-effort:
    # a card failure is reported honestly (sent=False → the wrapper does not
    # stamp a delivered briefing) but never raises.
    try:
        send_card = card_send_fn or _default_briefing_card
        card = send_card(_plain_headline(
            send, digest if isinstance(digest, dict) else None))
    except Exception as e:  # noqa: BLE001
        card = {"status": "error", "sent": False, "error": str(e)[:300]}
    card = card if isinstance(card, dict) else {"status": "invalid", "sent": False}
    # gate.submit (the live tools.send_card spine) returns {decision, result}
    # — the delivery truth is the inner result; a seam-provided flat dict is
    # used as-is. Keep the gate's routing reason when the card did NOT send,
    # so a quiet-routed/suppressed card is diagnosable from the run output.
    card_decision = card.get("decision") if isinstance(card.get("decision"), dict) else {}
    if isinstance(card.get("result"), dict):
        card = card["result"]

    # Honest delivered-marker: in card mode the ONLY "sent" key in the whole
    # result is the CARD's (the gather leg's own sent/send keys are dropped —
    # its outcome is the "archived" fields), so the launchd wrapper's
    # '"sent": true' grep can never be satisfied by the archive leg.
    gather = {k: v for k, v in send.items() if k not in ("sent", "send", "text")}
    return {
        "synthesis": syn, "recap": recap, "digest": digest,
        "needs_you": needs_you,
        "gather": gather,
        "send": {
            "mode": "briefing-card",
            "sent": bool(card.get("sent")),
            "card_status": str(card.get("status") or ""),
            "card_message_ids": list(card.get("message_ids") or []),
            **({} if card.get("sent") else {"card_why": str(
                card.get("error") or card_decision.get("reason") or "")[:200]}),
            "gathered": send.get("drained"),
            "recovered": send.get("recovered"),
            "acked": send.get("acked"),
            "archive_path": sink.get("archive_path"),
        },
    }


def _parse_args(argv=None):
    """CLI flags (additive; a ZERO-ARG invocation — the launchd wrapper's call —
    behaves exactly as before these flags existed).

    --now           run one briefing pass immediately. The module already runs
                    immediately when invoked (launchd owns the cadence; there
                    is no in-code schedule window) — the flag makes that
                    contract explicit for wrappers like first-briefing.sh.
    --local-render  the LOCAL-FIRST genesis receipt: compose from the local
                    genesis surfaces, write instance/memory/
                    first-briefing-<UTC date>.md, print to stdout — never send,
                    never touch Redis (see _run_local_render).
    """
    import argparse
    ap = argparse.ArgumentParser(prog="framework.frontdoor.run_briefing")
    ap.add_argument("--now", action="store_true",
                    help="run one briefing pass immediately (explicit "
                         "run-now contract; bypasses any wrapper scheduling)")
    ap.add_argument("--local-render", action="store_true", dest="local_render",
                    help="compose locally from genesis surfaces and write "
                         "instance/memory/first-briefing-<UTC date>.md instead "
                         "of sending (no Redis, no Telegram)")
    return ap.parse_args(argv)


if __name__ == "__main__":  # pragma: no cover — invoked by the launchd wrapper
    import json
    args = _parse_args()
    out = run_briefing(local_render=args.local_render)
    printable = {
        "synthesis": out["synthesis"],
        "recap": {k: v for k, v in (out["recap"] or {}).items()
                  if k not in ("item", "preview")} if out["recap"] else None,
        "digest": {k: v for k, v in (out["digest"] or {}).items()
                   if k != "manifest"},
        "send": {k: v for k, v in out["send"].items() if k != "text"},
    }
    print(json.dumps(printable, indent=2, default=str))
    if args.local_render:
        # Shell-consumable receipt handle (first-briefing.sh parses this line),
        # then the composed briefing itself — "print to stdout instead of send".
        print(f"FIRST_BRIEFING_RECEIPT={out['send']['receipt_path']}")
        if out["send"]["text"]:
            print("\n--- first briefing (local render, NOT sent) ---\n")
            print(out["send"]["text"])
