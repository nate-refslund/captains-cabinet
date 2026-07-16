"""Tests for framework.frontdoor.attention_drain — lane cards → front-door intake.

TDD-style, mirroring test_intake.py's isolation discipline: every Redis-backed
test uses UNIQUE test-prefixed keys (cabinet:captain-attention:catn-test-<uuid>
for the source stream, cabinet:frontdoor:intake:test:<uuid> for the target) and
DEL/cleans them in teardown. They NEVER touch the production keys
(cabinet:captain-attention:bakery / :newsletter, cabinet:frontdoor:intake). If
redis-cli cannot reach a server (ping fails), the Redis-backed tests SKIP; the
pure mapping tests (card_to_item / urgency tiers / slug guard) run always.

The drainer is pointed at a test intake stream via env CABINET_FRONTDOOR_STREAM,
so enqueue() lands in an isolated stream we can read + assert on.

Run with REDIS_HOST=localhost to exercise the Redis path:
    REDIS_HOST=localhost python3.12 -m pytest framework/frontdoor/tests/test_attention_drain.py -q
"""
from __future__ import annotations

import os
import uuid

import pytest

from framework.frontdoor import attention_drain, intake


# ---------------------------------------------------------------------------
# Pure mapping tests — no Redis required.
# ---------------------------------------------------------------------------
def test_slug_guard_accepts_valid_and_rejects_bad():
    assert attention_drain._valid_slug("bakery")
    assert attention_drain._valid_slug("bakery-ceo")
    assert attention_drain._valid_slug("a")
    assert attention_drain._valid_slug("x" * 32)
    # bad
    assert not attention_drain._valid_slug("")
    assert not attention_drain._valid_slug("-leading")
    assert not attention_drain._valid_slug("Upper")
    assert not attention_drain._valid_slug("has space")
    assert not attention_drain._valid_slug("semi;colon")
    assert not attention_drain._valid_slug("x" * 33)


@pytest.mark.parametrize("urgency,expected", [
    ("blocking", "ping-now"),
    ("high", "ping-now"),
    ("medium", "batch"),
    ("low", "fyi"),
    ("", "batch"),          # empty → default
    ("weird", "batch"),     # unknown → default
    ("HIGH", "ping-now"),   # case-insensitive
])
def test_urgency_maps_to_tier(urgency, expected):
    card = {"source": "bakery-ceo", "urgency": urgency,
            "summary": "s", "body": "b", "ts": "2026-06-24T05:00:00Z"}
    item = attention_drain.card_to_item(card, project="bakery")
    assert item is not None
    assert item["urgency_tier"] == expected


def test_card_to_item_shapes_a_valid_intake_item():
    card = {"source": "bakery-ceo", "project": "bakery", "urgency": "high",
            "summary": "Sentry blocker", "body": "13k events/24h",
            "ts": "2026-06-24T06:02:12Z"}
    item = attention_drain.card_to_item(card, project="bakery")
    assert item is not None
    # Must pass intake's own validator (the real contract).
    intake.validate_item(item)
    assert item["source"] == "officer:bakery-ceo"
    assert item["kind"] == "captain-attention"
    assert item["payload"]["summary"] == "[bakery] Sentry blocker"
    assert item["payload"]["detail"] == "13k events/24h"
    assert item["payload"]["project"] == "bakery"
    assert item["payload"]["origin_officer"] == "bakery-ceo"


def test_card_with_no_summary_is_unusable():
    card = {"source": "bakery-ceo", "urgency": "high", "summary": "",
            "body": "b", "ts": "2026-06-24T06:00:00Z"}
    assert attention_drain.card_to_item(card, project="bakery") is None


def test_card_missing_ts_gets_a_synthesized_one():
    card = {"source": "x", "urgency": "low", "summary": "s", "body": "b"}
    item = attention_drain.card_to_item(card, project="bakery")
    assert item is not None and item["ts"]  # non-empty → passes intake.validate_item
    intake.validate_item(item)


# ---------------------------------------------------------------------------
# Redis-backed integration — skip if no server.
# ---------------------------------------------------------------------------
def _redis_up() -> bool:
    try:
        return intake._redis().ping()
    except Exception:
        return False


redis_required = pytest.mark.skipif(
    not _redis_up(),
    reason="redis-cli cannot reach a Redis server (set REDIS_HOST=localhost to run)",
)


def _push_card(stream: str, *, source, urgency, summary, body, ts):
    """XADD a captain-attention-shaped card onto a test stream (argv, no shell)."""
    backend = intake._redis()
    fields = {"source": source, "project": stream.split(":")[-1],
              "urgency": urgency, "summary": summary, "body": body, "ts": ts}
    if backend.__class__.__name__ == "_RedisPyBackend":
        backend._c.xadd(stream, fields)
    else:
        args = ["XADD", stream, "*"]
        for k, v in fields.items():
            args += [k, v]
        backend._run(*args)


def _del(*keys):
    backend = intake._redis()
    for k in keys:
        try:
            backend.delete(k)
        except Exception:
            pass


def _is_redispy(backend) -> bool:
    return backend.__class__.__name__ == "_RedisPyBackend"


def _xgroup_create(backend, stream: str, group: str) -> None:
    """Mirror captain-attention.sh push-time creation:
    XGROUP CREATE <stream> <group> 0 MKSTREAM (captain-attention.sh:97,140)."""
    try:
        if _is_redispy(backend):
            backend._c.xgroup_create(stream, group, id="0", mkstream=True)
        else:
            backend._run("XGROUP", "CREATE", stream, group, "0", "MKSTREAM")
    except Exception:
        pass


def _xreadgroup(backend, stream: str, group: str, consumer: str,
                start: str) -> list[tuple[str, dict]]:
    if _is_redispy(backend):
        res = backend._c.xreadgroup(group, consumer, {stream: start}, count=10)
        return intake._flatten_xread(res, stream)
    out = backend._run("XREADGROUP", "GROUP", group, consumer,
                       "COUNT", "10", "STREAMS", stream, start, raw=True)
    return intake._parse_cli_xread(out, stream)


def _xlen(backend, stream: str) -> int:
    if _is_redispy(backend):
        return int(backend._c.xlen(stream))
    return int(backend._run("XLEN", stream, raw=True).strip() or "0")


@pytest.fixture
def isolated_keys(monkeypatch):
    """Unique source + target keys, with env routing intake to the target."""
    uid = uuid.uuid4().hex[:12]
    # project slug must be valid for the drainer to discover it; keep it test-y.
    project = f"catn-test-{uid}"[:32]
    source_stream = f"{attention_drain._ATTENTION_PREFIX}{project}"
    target_stream = f"cabinet:frontdoor:intake:test:{uid}"
    # Hard guards: never point at production.
    assert source_stream not in (
        "cabinet:captain-attention:bakery", "cabinet:captain-attention:newsletter")
    assert target_stream != "cabinet:frontdoor:intake"
    monkeypatch.setenv("CABINET_FRONTDOOR_STREAM", target_stream)
    yield {"project": project, "source": source_stream, "target": target_stream}
    _del(source_stream, target_stream)
    # purge the forwarded markers we created so the dedup set stays clean
    backend = intake._redis()
    try:
        if backend.__class__.__name__ == "_RedisPyBackend":
            members = backend._c.smembers(attention_drain._FORWARDED_SET)
            for m in members:
                m = m if isinstance(m, str) else m.decode()
                if m.startswith(project + ":"):
                    backend._c.srem(attention_drain._FORWARDED_SET, m)
        else:
            out = backend._run("SMEMBERS", attention_drain._FORWARDED_SET, raw=True)
            for m in [ln for ln in out.split("\n") if ln.startswith(project + ":")]:
                backend._run("SREM", attention_drain._FORWARDED_SET, m)
    except Exception:
        pass


@redis_required
def test_drain_forwards_card_into_intake(isolated_keys):
    k = isolated_keys
    _push_card(k["source"], source="bakery-ceo", urgency="high",
               summary="Sentry blocker", body="13k/24h",
               ts="2026-06-24T06:02:12Z")

    res = attention_drain.drain_attention(only_projects={k["project"]})
    assert res["forwarded"] >= 1
    assert k["project"] in res["by_project"]

    # The mapped item must now be drainable from the TARGET intake stream.
    items = intake.drain(consumer="test-reader", stream_key=k["target"])
    assert len(items) == 1
    it = items[0]
    assert it["kind"] == "captain-attention"
    assert it["urgency_tier"] == "ping-now"          # high → ping-now
    assert it["payload"]["summary"] == "[%s] Sentry blocker" % k["project"]
    assert it["payload"]["origin_officer"] == "bakery-ceo"
    intake.validate_item(it)


@redis_required
def test_drain_is_idempotent_no_double_enqueue(isolated_keys):
    k = isolated_keys
    _push_card(k["source"], source="newsletter-ceo", urgency="medium",
               summary="login blocker", body="a user can't log in",
               ts="2026-06-24T05:52:01Z")

    first = attention_drain.drain_attention(only_projects={k["project"]})
    assert first["forwarded"] == 1
    # Second pass: card already ACKed + marked forwarded → nothing new enqueued.
    second = attention_drain.drain_attention(only_projects={k["project"]})
    assert second["forwarded"] == 0

    # Exactly ONE item landed in the intake.
    items = intake.drain(consumer="test-reader2", stream_key=k["target"])
    assert len(items) == 1
    assert items[0]["urgency_tier"] == "batch"       # medium → batch


@redis_required
def test_drain_uses_own_group_not_the_ceo_group(isolated_keys):
    """Production reality (2026-07-11 finding): captain-attention.sh creates
    ceo-reader-<project> at PUSH time (:97,140) and post-tool-use.sh §3b
    (:292-322) consumes the delivery in single_ceo mode — often BEFORE the
    drain runs. The drainer must read via its OWN group, forward exactly
    once, and NEVER XDEL the stream copy while the live CEO group still owes
    it (entry in its PEL, un-ACKed)."""
    k = isolated_keys
    backend = intake._redis()
    ceo_group = "ceo-reader-" + k["project"]

    # Push-time group creation, then the card (captain-attention.sh order).
    _xgroup_create(backend, k["source"], ceo_group)
    _push_card(k["source"], source="bakery-ceo", urgency="low",
               summary="fyi item", body="context", ts="2026-06-24T06:00:00Z")

    # CEO scan consumes the delivery BEFORE the drain; no XACK yet — the
    # entry now sits in the CEO group's PEL (the group is LIVE).
    rows = _xreadgroup(backend, k["source"], ceo_group, "ceo-worker", ">")
    assert len(rows) == 1, "CEO group must receive its own delivery"
    entry_id = rows[0][0]

    # (a) the drainer forwarded exactly once to the intake.
    res = attention_drain.drain_attention(only_projects={k["project"]})
    assert res["forwarded"] == 1
    items = intake.drain(consumer="test-reader-ceo", stream_key=k["target"])
    assert len(items) == 1
    assert items[0]["payload"]["summary"] == "[%s] fyi item" % k["project"]

    # (b) the entry is STILL retrievable by the CEO group: in its PEL, and a
    # '0' re-read returns it WITH its fields (an XDEL'd entry re-reads as
    # id-with-nil-fields — the content would be gone).
    assert attention_drain._entry_in_pel(
        backend, k["source"], ceo_group, entry_id), \
        "drain must not destroy the CEO group's pending delivery"
    rereads = _xreadgroup(backend, k["source"], ceo_group, "ceo-worker", "0")
    by_id = dict(rereads)
    assert entry_id in by_id, "CEO '0' re-read must still return the entry"
    assert by_id[entry_id].get("summary") == "fyi item", \
        "the entry's CONTENT must survive the drain (no XDEL under a live PEL)"

    # (c) a second drain pass does not double-forward.
    second = attention_drain.drain_attention(only_projects={k["project"]})
    assert second["forwarded"] == 0
    assert intake.drain(consumer="test-reader-ceo",
                        stream_key=k["target"]) == []


@redis_required
def test_vestigial_never_read_group_does_not_block_trim(isolated_keys):
    """H2 preserved: a push-time-created but NEVER-read ceo-reader group
    (last-delivered-id 0-0) is vestigial and must not block the trim — after
    forwarding, the stream copy IS retired. (Accepted edge per the 2026-07-11
    ruling: the card's content reached the front door via the forward; only
    the stream copy trims.)"""
    k = isolated_keys
    backend = intake._redis()
    _xgroup_create(backend, k["source"], "ceo-reader-" + k["project"])  # no scan ever
    _push_card(k["source"], source="bakery-ceo", urgency="medium",
               summary="stranded card", body="b", ts="2026-07-11T06:00:00Z")

    res = attention_drain.drain_attention(only_projects={k["project"]})
    assert res["forwarded"] == 1
    items = intake.drain(consumer="test-reader-vg", stream_key=k["target"])
    assert len(items) == 1
    assert _xlen(backend, k["source"]) == 0, \
        "vestigial (never-read) group must not block the H2 trim"


@redis_required
def test_probe_error_fails_safe_to_no_trim(isolated_keys, monkeypatch):
    """A failing group probe must NEVER trim (fail safe — the delivery
    contract outranks queue growth; the 300s hygiene sweeper owns growth),
    but the forward itself still happens."""
    k = isolated_keys
    backend = intake._redis()
    _push_card(k["source"], source="bakery-ceo", urgency="high",
               summary="probe-error card", body="b", ts="2026-07-11T06:01:00Z")

    def _boom(backend, stream):
        raise RuntimeError("probe down")

    monkeypatch.setattr(attention_drain, "_stream_groups", _boom)

    res = attention_drain.drain_attention(only_projects={k["project"]})
    assert res["forwarded"] == 1, "forward must still happen on probe error"
    items = intake.drain(consumer="test-reader-pe", stream_key=k["target"])
    assert len(items) == 1
    assert _xlen(backend, k["source"]) == 1, \
        "probe error must fail safe to NOT trimming"


# ---------------------------------------------------------------------------
# Trim-guard unit tests — no Redis required.
# ---------------------------------------------------------------------------
def test_stream_id_comparison_is_numeric_not_string():
    # The classic trap: lexically '10-2' > '10-10', but 10-2 is the OLDER id.
    assert "10-2" > "10-10"                     # the trap _id_tuple avoids
    assert attention_drain._id_tuple("10-2") < attention_drain._id_tuple("10-10")
    assert attention_drain._id_tuple("10-2") == (10, 2)
    assert attention_drain._id_tuple("9-99") < attention_drain._id_tuple("10-0")
    assert (attention_drain._id_tuple("1783772" + "057092-0")
            > attention_drain._id_tuple("9999" + "99999999-99"))
    assert attention_drain._id_tuple("0-0") == (0, 0)
    with pytest.raises(ValueError):
        attention_drain._id_tuple("not-an-id")


def test_safe_to_trim_contract_unit(monkeypatch):
    """Pins the consumption-aware contract, incl. the 10-2 vs 10-10 case: a
    string compare would call entry 10-2 'newer than' last-delivered 10-10
    (still owed → never trim); the numeric compare knows it was already
    delivered, so the PEL alone decides."""
    monkeypatch.setattr(attention_drain, "_stream_groups",
                        lambda b, s: [("ceo-reader-x", "10-10")])
    pel = {"present": False}
    monkeypatch.setattr(attention_drain, "_entry_in_pel",
                        lambda b, s, g, e: pel["present"])
    # delivered (10-2 <= 10-10 numerically) and ACKed (not in PEL) → safe.
    assert attention_drain._safe_to_trim(None, "st", "10-2") is True
    # delivered but still in the PEL → not safe.
    pel["present"] = True
    assert attention_drain._safe_to_trim(None, "st", "10-2") is False
    # beyond last-delivered (11-0 > 10-10) → not safe, PEL irrelevant.
    pel["present"] = False
    assert attention_drain._safe_to_trim(None, "st", "11-0") is False
    # vestigial (never-read) group never blocks.
    monkeypatch.setattr(attention_drain, "_stream_groups",
                        lambda b, s: [("ceo-reader-x", "0-0")])
    assert attention_drain._safe_to_trim(None, "st", "11-0") is True
    # the drain's own group never blocks (it just read the entry).
    monkeypatch.setattr(
        attention_drain, "_stream_groups",
        lambda b, s: [(attention_drain._DRAIN_GROUP, "1-0")])
    assert attention_drain._safe_to_trim(None, "st", "5-0") is True
    # malformed last-delivered-id → probe error → fail safe.
    monkeypatch.setattr(attention_drain, "_stream_groups",
                        lambda b, s: [("ceo-reader-x", "garbage")])
    assert attention_drain._safe_to_trim(None, "st", "5-0") is False


@redis_required
def test_drain_no_streams_is_clean(monkeypatch):
    """With no captain-attention streams matching, drain returns zeros cleanly."""
    # Point intake target somewhere isolated; don't push any source stream.
    monkeypatch.setenv("CABINET_FRONTDOOR_STREAM",
                       f"cabinet:frontdoor:intake:test:{uuid.uuid4().hex[:8]}")
    res = attention_drain.drain_attention()
    assert res["forwarded"] == 0
    assert isinstance(res["streams"], int)


# Multi-line card bodies are the REAL shape (cards carry numbered courses of
# action). intake._parse_cli_xread's line-pair heuristic mis-aligned id↔content
# for multi-entry streams with multi-line values (observed 2026-06-24: the
# 'Bakery PROD fire' card's summary bled onto the wrong entry id and one card was
# dropped). _parse_single_entry_fields fixes it. This regression test pins it.
_MULTILINE_BODY = (
    "Update to my earlier card. I found ALL 3 bugs already fixed:\n"
    "(1) EU-eligibility hard-block fixed Jun-1 commit fb6e0153 (#413);\n"
    "(2) address autocomplete fixed;\n"
    "(3) resvg label-text fixed.\n\n"
    "DECISIONS FOR YOU:\n"
    "1) Retire the CI + UAT nodes.\n"
    "2) The prod-ship: say the word and I'll stage it.\n"
    "3) The open lane work is outcome-bakery-003 + the Sentry fire."
)


@redis_required
def test_multiline_bodies_do_not_scramble_id_content_alignment(isolated_keys):
    """Three cards with multi-line bodies must each forward with their OWN summary."""
    k = isolated_keys
    expected = {
        "card-A first": "low",
        "card-B second": "medium",
        "card-C third": "high",
    }
    for summ, urg in expected.items():
        _push_card(k["source"], source="bakery-ceo", urgency=urg,
                   summary=summ, body=_MULTILINE_BODY + f"\n[marker for {summ}]",
                   ts="2026-06-24T06:00:00Z")

    res = attention_drain.drain_attention(only_projects={k["project"]})
    assert res["forwarded"] == 3, "all three multi-line-body cards must forward"

    items = intake.drain(consumer="test-reader-ml", stream_key=k["target"])
    assert len(items) == 3, "exactly three items, none dropped, none duplicated"

    # Each forwarded item's summary + tier + body marker must match ITS card —
    # proving no id↔content scramble across the multi-line boundary.
    by_summary = {}
    for it in items:
        s = it["payload"]["summary"]
        by_summary[s] = it
    for summ, urg in expected.items():
        full = f"[{k['project']}] {summ}"
        assert full in by_summary, f"missing card {summ!r}"
        it = by_summary[full]
        tier = {"low": "fyi", "medium": "batch", "high": "ping-now"}[urg]
        assert it["urgency_tier"] == tier, f"{summ}: wrong tier"
        # the body marker proves the RIGHT body landed with the RIGHT summary
        assert f"[marker for {summ}]" in it["payload"]["detail"], \
            f"{summ}: body scrambled onto wrong card"
