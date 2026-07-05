"""framework.frontdoor.run_frontdoor — the send-path runner.

Wires the three send-path modules into ONE pass of the front-door's outbound
leg (docs/cabinet-architecture-cohesive-2026-06-22.md §3, §8):

    intake.drain()  →  composer.compose()  →  channel.send()

This is the "one unified message" path the Chair runs to reach the Captain: it drains
captain-bound items off the durable Redis intake, weaves them into ONE
provenance-bearing message grouped by urgency tier, and sends that single
message to CAPTAIN_TELEGRAM_ID.

Safety — the env gate is honored end-to-end:
  * ``channel.send`` is itself hard-gated on ``framework.env.allow_sends()`` as
    its FIRST line, so a dev/test/build session physically cannot send (it
    returns ``blocked-dev`` with zero network call). This runner does NOT
    re-implement that gate — it calls the one switch.
  * In dev the runner still DRAINS and COMPOSES (capture + unification are
    always safe) and returns the composed text so a developer can see exactly
    what *would* be sent — but ``send_result.status == 'blocked-dev'`` and
    nothing leaves the machine.
  * ACK policy is fail-safe: items are ack'd ONLY after a real send
    (``sent == True``). In dev (blocked) or on a send error the drained items
    stay PENDING on the stream so the next runtime drain recovers them —
    upholding the "durable intake — nothing lost" invariant (§7). The caller
    may override with ``ack_on_send=False`` to leave acking to a later
    reply-binder step.

The runner intentionally imports ``composer`` and ``channel`` (it is the
wiring layer); the modules below it stay independent of each other.
"""
from __future__ import annotations

from typing import Any, Callable

from framework import env
from framework.frontdoor import channel, composer, intake


# Per-tier item cap for the composed briefing. Keeps the unified message a TIGHT
# digest (top items per tier + a roll-up of the rest) instead of dumping the whole
# intake backlog — the 2026-06-29 failure rendered a 77-item wall. ping-now is
# never capped (the composer exempts it). 5 mirrors the well-formed manual
# briefing's section depth. Override via run_send_path(max_per_tier=…).
_DEFAULT_MAX_PER_TIER = 5


def run_send_path(
    *,
    since: str | None = None,
    stream_key: str | None = None,
    count: int = 100,
    consumer: str = "chair",
    now: str | None = None,
    http_post: Callable[..., Any] | None = None,
    ack_on_send: bool = True,
    recover_pending: bool = False,
    max_per_tier: int | None = _DEFAULT_MAX_PER_TIER,
    send_fn: Callable[..., dict] | None = None,
    drain_fn: Callable[..., list] | None = None,
    ack_fn: Callable[..., int] | None = None,
    pending_fn: Callable[..., list] | None = None,
) -> dict:
    """Run ONE pass of the front-door send path: drain → compose → send.

    Args:
      since: optional ISO-8601 floor passed to ``drain`` (items with ts >= since).
        NOTE the documented intake footgun: ``drain(since=)`` filters AFTER the
        consumer-group delivery marks ALL new entries pending, so older
        sub-floor items are consumed into pending limbo (recoverable only via
        ``drain_pending``). Prefer leaving ``since`` None for the routine Chair
        drain and let the composer/ts-ordering handle recency; pass ``since``
        only when you deliberately want the post-delivery floor.
      stream_key / count / consumer: forwarded to ``intake.drain`` (stream_key
        override exists for test isolation).
      now: forwarded to ``composer.compose`` (interface symmetry; no-op today).
      http_post: injectable transport forwarded to ``channel.send`` (tests pass
        a mock; the default is the real urllib wrapper, never reached in dev
        because the gate short-circuits first).
      ack_on_send: when True (default), ack the drained item ids ONLY after a
        confirmed send (sent == True). False leaves acking to a later step.
      recover_pending: when True, FIRST recover items already delivered-but-
        unacked to this consumer (``intake.drain_pending``) and prepend them
        (deduped by id, oldest first) to the fresh ``>`` drain. This is the
        BRIEFING's backstop: the every-5-min ``surface.py`` loop reads ``>`` and
        surfaces ONLY ping-now in real time, deliberately leaving batch/fyi
        items PENDING "for the briefing to compose". But pending items are no
        longer ``>``-visible (the consumer group already delivered them), so a
        plain ``>`` drain at briefing time sees nothing and the batch/fyi backlog
        (comms-officer FYIs, relevant-no-reply items) would surface NEVER. With
        this flag the briefing recovers + composes + sends + ACKs that backlog —
        closing the single-voice comms-awareness gap. Default False so the bare
        send path (and surface.py's own ping-now pass) keep their prior behavior.
      max_per_tier: cap on item lines rendered per (non-ping-now) tier so the
        composed briefing stays a TIGHT digest — top N most-recent shown in full,
        the rest folded into one source-counted roll-up line. Defaults to
        ``_DEFAULT_MAX_PER_TIER`` (the 2026-06-29 fix for the 77-item wall); pass
        None to render every item (the prior uncapped behavior).
      send_fn / drain_fn / ack_fn / pending_fn: seams for tests; default to the
        real module functions. ``send_fn`` lets a test assert the gate without
        importing urllib; ``drain_fn``/``ack_fn``/``pending_fn`` let a test run
        the full wiring without a live Redis.

    Returns a dict:
      {
        'drained':  <int items drained (pending-recovered + fresh)>,
        'item_ids': [<stream ids>],
        'text':     <the composed unified message ('' when nothing drained)>,
        'sent':     <bool — True only on a real confirmed send>,
        'send':     <the channel.send result dict, or None when nothing to send>,
        'acked':    <int ids acked>,
        'recovered': <int pending items recovered (0 unless recover_pending)>,
        'allow_sends': <bool — the env gate's value this pass>,
      }
    The token and any token-bearing URL never appear in this result: channel.send
    scrubs them before returning, and this runner only re-surfaces that scrubbed
    dict.
    """
    _drain = drain_fn or intake.drain
    _send = send_fn or channel.send
    _ack = ack_fn or intake.ack
    _pending = pending_fn or intake.drain_pending

    recovered: list[dict] = []
    if recover_pending:
        try:
            recovered = _pending(stream_key=stream_key, consumer=consumer) or []
        except Exception:
            recovered = []  # best-effort: a recovery hiccup never blocks the send

    fresh = _drain(since=since, stream_key=stream_key, count=count,
                   consumer=consumer)

    # Merge recovered (oldest, surface.py-abandoned batch/fyi) ahead of fresh,
    # deduped by stream id so an item that is BOTH pending and freshly delivered
    # is composed + acked exactly once.
    items: list[dict] = []
    seen: set = set()
    for it in list(recovered) + list(fresh):
        if not isinstance(it, dict):
            continue
        mid = it.get("id")
        if mid is not None and mid in seen:
            continue
        if mid is not None:
            seen.add(mid)
        items.append(it)

    item_ids = [it.get("id") for it in items
                if isinstance(it, dict) and it.get("id") is not None]

    # Compose is always safe (pure, no I/O). Even in dev we surface the text so a
    # developer can see exactly what WOULD be sent. max_per_tier keeps it a tight
    # digest (top N per tier + a roll-up of the rest) — see _DEFAULT_MAX_PER_TIER.
    text = composer.compose(items, now=now, max_per_tier=max_per_tier)

    result: dict[str, Any] = {
        "drained": len(items),
        "item_ids": item_ids,
        "text": text,
        "sent": False,
        "send": None,
        "acked": 0,
        "recovered": len(recovered),
        "allow_sends": env.allow_sends(),
    }

    # Nothing composed (empty drain or everything judged-out) -> the Chair sends
    # nothing. Items (if any were drained) stay pending for the next pass.
    if not text:
        return result

    # channel.send is the trust boundary: it gates on allow_sends() FIRST and
    # returns blocked-dev with zero network call in dev. We do not duplicate the
    # gate — we honor its result.
    send_result = _send(text, http_post=http_post)
    result["send"] = send_result
    result["sent"] = bool(send_result.get("sent"))

    # Fail-safe ack: only after a confirmed send. In dev (blocked-dev) or on a
    # send error, the drained items remain pending so a later runtime drain
    # recovers them — nothing lost.
    if ack_on_send and result["sent"] and item_ids:
        result["acked"] = _ack(item_ids, stream_key=stream_key)

    return result


if __name__ == "__main__":  # pragma: no cover - manual dev invocation
    # Manual one-shot for a developer. In dev this composes + prints the would-be
    # message; it never sends (the gate short-circuits channel.send).
    import json

    out = run_send_path()
    # The result dict is already token-safe (channel.send scrubs); print it.
    printable = {k: v for k, v in out.items() if k != "text"}
    print(json.dumps(printable, indent=2, default=str))
    if out["text"]:
        print("\n--- composed message (NOT sent in dev) ---\n")
        print(out["text"])
