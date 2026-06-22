"""framework.frontdoor.run_frontdoor — the send-path runner.

Wires the three send-path modules into ONE pass of the front-door's outbound
leg (docs/cabinet-architecture-cohesive-2026-06-22.md §3, §8):

    intake.drain()  →  composer.compose()  →  channel.send()

This is the "one unified message" path the Chair runs to reach Nate: it drains
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


def run_send_path(
    *,
    since: str | None = None,
    stream_key: str | None = None,
    count: int = 100,
    consumer: str = "chair",
    now: str | None = None,
    http_post: Callable[..., Any] | None = None,
    ack_on_send: bool = True,
    send_fn: Callable[..., dict] | None = None,
    drain_fn: Callable[..., list] | None = None,
    ack_fn: Callable[..., int] | None = None,
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
      send_fn / drain_fn / ack_fn: seams for tests; default to the real module
        functions. ``send_fn`` lets a test assert the gate without importing
        urllib; ``drain_fn``/``ack_fn`` let a test run the full wiring without a
        live Redis.

    Returns a dict:
      {
        'drained':  <int items drained>,
        'item_ids': [<stream ids>],
        'text':     <the composed unified message ('' when nothing drained)>,
        'sent':     <bool — True only on a real confirmed send>,
        'send':     <the channel.send result dict, or None when nothing to send>,
        'acked':    <int ids acked>,
        'allow_sends': <bool — the env gate's value this pass>,
      }
    The token and any token-bearing URL never appear in this result: channel.send
    scrubs them before returning, and this runner only re-surfaces that scrubbed
    dict.
    """
    _drain = drain_fn or intake.drain
    _send = send_fn or channel.send
    _ack = ack_fn or intake.ack

    items = _drain(since=since, stream_key=stream_key, count=count,
                   consumer=consumer)
    item_ids = [it.get("id") for it in items
                if isinstance(it, dict) and it.get("id") is not None]

    # Compose is always safe (pure, no I/O). Even in dev we surface the text so a
    # developer can see exactly what WOULD be sent.
    text = composer.compose(items, now=now)

    result: dict[str, Any] = {
        "drained": len(items),
        "item_ids": item_ids,
        "text": text,
        "sent": False,
        "send": None,
        "acked": 0,
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
