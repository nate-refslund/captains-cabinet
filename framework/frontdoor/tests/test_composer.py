"""Unit tests for framework.frontdoor.composer — the PURE intake->message function.

Composer is fully pure: no Redis, no env, no network, no clock unless injected.
So these tests need NO mocking of siblings, NO fixtures touching production
state. They assert: deterministic output, correct tier grouping (incl. the
default-to-'batch' fallback), provenance (source + why) in the output, empty
list -> '', stable ordering (tier then ts), conservative forward (nothing
dropped), and secret-safety (composer never reads env / never emits tokens).
"""
from __future__ import annotations

from framework.frontdoor import composer


# --- helpers -----------------------------------------------------------------

def _item(*, source="morning-brief", kind="brief", ts="2026-06-22T07:00:00Z",
          tier="batch", summary="a summary", why="because", **extra):
    """Build a canonical-shape intake item dict for tests."""
    payload = {"summary": summary}
    payload.update(extra.pop("payload_extra", {}))
    context = {"why": why, "sources": [source], "audience": None,
               "thread_ref": None}
    context.update(extra.pop("context_extra", {}))
    item = {
        "id": extra.pop("id", "1700000000000-0"),
        "source": source,
        "kind": kind,
        "ts": ts,
        "urgency_tier": tier,
        "payload": payload,
        "context": context,
        "correlation_id": extra.pop("correlation_id", ""),
    }
    item.update(extra)
    return item


# --- group_by_tier -----------------------------------------------------------

def test_group_by_tier_three_buckets():
    items = [
        _item(tier="ping-now", summary="urgent"),
        _item(tier="batch", summary="normal"),
        _item(tier="fyi", summary="info"),
    ]
    grouped = composer.group_by_tier(items)
    assert set(grouped.keys()) == {"ping-now", "batch", "fyi"}
    assert grouped["ping-now"][0]["payload"]["summary"] == "urgent"
    assert grouped["batch"][0]["payload"]["summary"] == "normal"
    assert grouped["fyi"][0]["payload"]["summary"] == "info"


def test_group_by_tier_missing_tier_defaults_to_batch():
    bad = _item(summary="no-tier")
    del bad["urgency_tier"]
    grouped = composer.group_by_tier([bad])
    assert grouped["batch"][0]["payload"]["summary"] == "no-tier"
    assert grouped["ping-now"] == []
    assert grouped["fyi"] == []


def test_group_by_tier_invalid_tier_defaults_to_batch():
    bad = _item(tier="whenever", summary="garbage-tier")
    grouped = composer.group_by_tier([bad])
    assert grouped["batch"][0]["payload"]["summary"] == "garbage-tier"


def test_group_by_tier_empty_list():
    grouped = composer.group_by_tier([])
    assert grouped == {"ping-now": [], "batch": [], "fyi": []}


# --- render_item -------------------------------------------------------------

def test_render_item_carries_source_and_why():
    line = composer.render_item(
        _item(source="commitment-ledger", summary="call Frederik",
              why="owed since Tue"))
    assert "commitment-ledger" in line
    assert "call Frederik" in line
    assert "owed since Tue" in line


def test_render_item_handles_missing_why():
    it = _item(summary="bare summary")
    it["context"] = {}  # no why
    line = composer.render_item(it)
    assert "bare summary" in line
    # no crash, no stray None
    assert "None" not in line


def test_render_item_handles_missing_payload_summary():
    it = _item()
    it["payload"] = {}
    line = composer.render_item(it)
    assert isinstance(line, str)
    assert "None" not in line


# --- compose: determinism / ordering -----------------------------------------

def test_compose_deterministic():
    items = [
        _item(tier="batch", ts="2026-06-22T08:00:00Z", summary="b"),
        _item(tier="ping-now", ts="2026-06-22T07:00:00Z", summary="a"),
        _item(tier="fyi", ts="2026-06-22T09:00:00Z", summary="c"),
    ]
    first = composer.compose(items)
    second = composer.compose(list(reversed(items)))
    assert first == second  # order-independent input -> identical output


def test_compose_tier_order_ping_then_batch_then_fyi():
    items = [
        _item(tier="fyi", summary="FYI_LINE"),
        _item(tier="batch", summary="BATCH_LINE"),
        _item(tier="ping-now", summary="PING_LINE"),
    ]
    out = composer.compose(items)
    assert out.index("PING_LINE") < out.index("BATCH_LINE") < out.index("FYI_LINE")


def test_compose_within_tier_ordered_by_ts():
    items = [
        _item(tier="batch", ts="2026-06-22T09:00:00Z", summary="LATER"),
        _item(tier="batch", ts="2026-06-22T07:00:00Z", summary="EARLIER"),
    ]
    out = composer.compose(items)
    assert out.index("EARLIER") < out.index("LATER")


# --- compose: conservative forward (nothing dropped) -------------------------

def test_compose_forwards_all_items():
    items = [_item(summary=f"item-{i}", ts=f"2026-06-22T0{i}:00:00Z")
             for i in range(1, 6)]
    out = composer.compose(items)
    for i in range(1, 6):
        assert f"item-{i}" in out


def test_forward_judge_default_true():
    assert composer.forward_judge(_item()) is True


# --- compose: empty + provenance ---------------------------------------------

def test_compose_empty_list_returns_empty_string():
    assert composer.compose([]) == ""


def test_compose_provenance_present_for_every_item():
    items = [
        _item(source="inbox-triage", summary="reply to Lisa", why="awaiting you"),
        _item(source="deploy-alert", tier="ping-now", summary="prod failed",
              why="build red"),
    ]
    out = composer.compose(items)
    assert "inbox-triage" in out and "awaiting you" in out
    assert "deploy-alert" in out and "build red" in out


# --- secret-safety: composer never introduces/echoes env secrets -------------

def test_compose_never_reads_env_token(monkeypatch):
    # Even if a token-like env var exists, the pure composer must not pull it in.
    monkeypatch.setenv("TELEGRAM_COS_TOKEN", "123:SECRETTOKENVALUE")
    out = composer.compose([_item(summary="hello")])
    assert "SECRETTOKENVALUE" not in out


def test_compose_passes_through_payload_text_without_inventing_secrets():
    # If a producer accidentally puts a token-like string in payload, composer
    # may surface that producer text — but must not ADD any env secret of its
    # own. We assert the env secret is absent; the producer's own string is its
    # responsibility, not the composer's.
    accidental = "9999:LOOKS_LIKE_A_TOKEN"
    out = composer.compose([_item(summary=accidental)])
    # composer faithfully forwards producer content (conservative)...
    assert accidental in out
    # ...but never reaches into the environment for a real secret.
    import os
    assert os.environ.get("TELEGRAM_COS_TOKEN", "__none__") not in out


# --- tier label visibility ---------------------------------------------------

def test_compose_labels_only_nonempty_tiers():
    # Only batch items present -> ping-now / fyi headers should not appear as
    # populated sections (composer should not render empty tier sections).
    items = [_item(tier="batch", summary="only-batch")]
    out = composer.compose(items)
    assert "only-batch" in out
    # Empty tier headers must be SUPPRESSED (verifier finding: this assertion
    # was missing). Only the batch label may appear.
    assert composer._TIER_LABELS["batch"] in out
    assert composer._TIER_LABELS["ping-now"] not in out
    assert composer._TIER_LABELS["fyi"] not in out


def test_compose_exact_line_format():
    """Pin the contract line format '• [source] summary — why' so a regression
    that drops the bullet, the [brackets], or the em-dash separator is caught
    (verifier finding: no test pinned the exact format)."""
    items = [_item(source="morning-brief", summary="the summary", why="the why")]
    out = composer.compose(items)
    assert "• [morning-brief] the summary — the why" in out


def test_compose_now_is_a_noop():
    """`now` is accepted for symmetry but must not change output (verifier
    finding: no test pinned this)."""
    items = [_item(summary="x"), _item(tier="ping-now", summary="y")]
    assert composer.compose(items) == composer.compose(
        items, now="2026-06-22T09:00:00Z")
