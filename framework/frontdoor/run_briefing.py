"""framework.frontdoor.run_briefing — one pass of the recurring unified briefing.

Scheduled by launchd (cabinet/scripts/run-frontdoor-briefing.sh). Pulls real
signals into the durable intake (morning_synthesis) and runs the send path
(run_frontdoor.run_send_path) → ONE unified message to the Captain on the single
channel, replacing the screenpipe morning-brief DM that the cutover silenced.

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
are DELIBERATELY not touched: a genesis instance has no estate to gather, and
a scratch-instance run on a developer Mac must never consume the LIVE
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
    root = genesis.cabinet_root()
    path = root / "instance" / "memory" / f"first-briefing-{date}.md"
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
        "synthesis": {"skipped": "local-render (genesis has no estate to gather)"},
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
    run_mode: str | None = None,
    local_render: bool = False,
    genesis_fn=None,
) -> dict:
    """Enqueue a fresh synthesis (+ the PM daily recap + the TI-5 digest), then
    run one send pass.

    Returns ``{'synthesis': <enqueue result>, 'recap': <recap result|None>,
    'digest': <tell_digest result>, 'send': <run_send_path result>}``.

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

    Seams: ``enqueue_fn`` overrides the synthesis enqueue; ``recap_fn`` overrides
    the daily-recap enqueue; ``digest_fn`` overrides the TI-5 digest enqueue;
    ``run_mode`` forces AM/PM; ``send_fn`` / ``drain_fn`` / ``ack_fn`` forward to
    run_send_path — all for tests (no real network / Redis / brain). The token
    never appears in the result (channel.send scrubs; run_send_path only
    re-surfaces the scrubbed dict).
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

    # recover_pending=True is the fix for the single-voice comms-awareness gap:
    # surface.py (every 5 min) reads the intake with ">" and surfaces ONLY
    # ping-now in real time, leaving batch/fyi items delivered-but-unacked in the
    # consumer group's PEL "for the briefing to compose". Those items are then no
    # longer ">"-visible, so a plain briefing drain saw nothing and the batch/fyi
    # backlog — comms-officer FYIs, relevant-but-no-reply messages — surfaced
    # NEVER. The briefing is the designated place batch/fyi reaches the Captain, so it
    # recovers that pending backlog, composes it into the one voice, sends, and
    # ACKs. (surface.py is unchanged: still real-time ping-now only.)
    send = run_frontdoor.run_send_path(
        send_fn=send_fn, drain_fn=drain_fn, ack_fn=ack_fn, pending_fn=pending_fn,
        recover_pending=True)
    return {"synthesis": syn, "recap": recap, "digest": digest, "send": send}


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
