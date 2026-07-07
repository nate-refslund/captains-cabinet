"""daily_recap — the PM front-door source: labeled-section synthesis + idempotent
Monday/vault side-effects + intake item, with the dry-mode write tripwire.

The screenpipe libs (sp_lib / commitments_lib) are lazy-imported inside the
module, so these tests never need them: we inject the module's own seams
(``entries=`` / ``llm=`` / ``today=``) and monkeypatch ``dr._sp`` to a tiny CONFIG
stub. The LLM is ALWAYS a stub returning the labeled-section PLAIN TEXT the real
model emits — no network, no key. The whole point of the regression: the synth
must parse a long, multiline, quote-bearing response (the inline-JSON approach
discarded it on 2026-06-23) and dry mode must write NOTHING.
"""
import types

import pytest

from framework.frontdoor import daily_recap as dr


# --- a CONFIG stub so _recap_item / render_vault_note can read board ids without
#     importing the real sp_lib (which isn't present in the cabinet test env). ---
_FAKE_CONFIG = {
    "activity_board": {
        "id": 5091999365,
        "groups": {"halfhourly": "group_mm0pks0g"},
        "columns": {
            "name": "name", "activity_summary": "sum", "tasks_actions": "ta",
            "date": "d", "hour": "h", "minute": "mi", "focus_type": "ft",
            "productivity": "p", "energy": "e", "apps": "ap", "entry_type": "et",
        },
    },
    "reflections_board": {
        "id": 5096013783,
        "groups": {"daily": "group_mm34sx2v"},
        "columns": {
            "entry_type": "et", "date": "d", "summary": "s", "findings": "f",
            "actions": "a", "notes": "n", "productivity": "p", "energy": "e",
        },
    },
}


@pytest.fixture(autouse=True)
def _stub_sp(monkeypatch):
    """Every test gets a CONFIG-only sp stub (no Monday, no env)."""
    stub = types.SimpleNamespace(CONFIG=_FAKE_CONFIG, load_env=lambda *a, **k: None)
    monkeypatch.setattr(dr, "_sp", lambda: stub)


def _slot(time, summary):
    """One raw Activity item (the shape fetch_today_halfhourly returns)."""
    cols = {
        "name": f"slot {time}", "sum": summary, "ta": "did a thing", "d": "2026-06-23",
        "h": time.split(":")[0], "mi": time.split(":")[1], "ft": "Deep Work",
        "p": "8", "e": "7", "ap": "VS Code", "et": "Half-Hourly",
    }
    return {"id": time, "name": f"slot {time}",
            "column_values": [{"id": k, "text": v} for k, v in cols.items()]}


_ENTRIES = [
    _slot("09:30", "worked on the acme-shop checkout flow"),
    _slot("14:00", "reviewed pricing widget v2 PR #34"),
]

# A representative LONG, multiline, quote-bearing labeled-section response — the
# format the real model emits, and exactly what broke the prior inline-JSON parse
# (literal newlines + a double-quote inside SUMMARY).
_LONG_RESPONSE = '''```text
HEADLINE: Shipped acme-shop checkout flow + reviewed pricing widget v2 PR

SUMMARY:
The day ran nearly around the clock. From 09:30 the captain drove the checkout-flow
branch, wrestling the taxCategory validation gate — an explicit merchant
declaration, not auto-set from country.

By 14:00 focus shifted to pricing widget v2 (PR #34). A "PriceCard" data-* prop
issue and a frozen undo button both surfaced.

Energy held through the afternoon.

FINDINGS:
- VAT auto-fill is still flaky on the merchant path
- taxCategory must stay an explicit declaration (spec §7.1)

ACTIONS:
- Merge PR #34 once MONDAY_API_KEY is rotated
- Block auto-inference of taxCategory before merge

NOTES:
- QA flagged the vendor DPA as a launch blocker
- ~17 active hours; top tools: Claude Code, VS Code

PRODUCTIVITY: 9
ENERGY: 6
```'''


def _long_llm(user, system, max_tokens=dr._RECAP_MAX_TOKENS):
    """Stub LLM: ignores input, returns the long labeled-section response. Also
    asserts we prompt for PLAIN TEXT (not JSON) and never leak voice/nate_model."""
    assert "PLAIN TEXT" in system and "Do NOT use JSON" in system
    assert "voice" not in system.lower() and "nate_model" not in system.lower()
    return _LONG_RESPONSE


# ---------------------------------------------------------------------------
# (b) _synthesize parses a representative long/multiline labeled response.
# ---------------------------------------------------------------------------
def test_synthesize_parses_long_multiline_response():
    recap = dr.synthesize_recap("2026-06-23", _ENTRIES, llm=_long_llm)
    assert recap is not None  # the 2026-06-23 bug: this was None (recap discarded)
    assert recap["headline"].startswith("Shipped acme-shop")
    # multi-paragraph SUMMARY survived (internal blank lines + the embedded quote)
    assert recap["summary"].count("\n") >= 2
    assert "taxCategory" in recap["summary"]
    assert '"PriceCard"' in recap["summary"]
    assert "- VAT auto-fill is still flaky on the merchant path" in recap["findings"]
    assert "- Merge PR #34 once MONDAY_API_KEY is rotated" in recap["actions"]
    assert "vendor DPA" in recap["notes"]
    assert recap["productivity"] == 9 and recap["energy"] == 6
    assert recap["slot_count"] == 2


def test_synthesize_truncated_response_still_recaps():
    """A response cut off MID-SUMMARY (the max_tokens failure) must STILL produce a
    recap — the labeled-section parser degrades gracefully where truncated inline
    JSON was unrecoverable. Missing trailing sections default cleanly."""
    truncated = ("HEADLINE: Busy day\n\nSUMMARY:\nThe day ran nearly around the "
                 "clock and then the output was cut off right he")
    recap = dr.synthesize_recap("2026-06-23", _ENTRIES,
                                llm=lambda u, s, max_tokens=0: truncated)
    assert recap is not None
    assert recap["summary"].startswith("The day ran nearly")
    assert recap["findings"] == "_(none)_"          # absent section → clean default
    assert recap["productivity"] == 5 and recap["energy"] == 5  # absent ratings → default


def test_synthesize_none_bullets_normalize():
    resp = ("HEADLINE: Quiet\n\nSUMMARY:\nLight day.\n\nFINDINGS:\n- (none)\n\n"
            "ACTIONS:\n- (none)\n\nNOTES:\n- (none)\n\nPRODUCTIVITY: 3\nENERGY: 4")
    recap = dr.synthesize_recap("2026-06-23", _ENTRIES, llm=lambda u, s, max_tokens=0: resp)
    assert recap["findings"] == "_(none)_"
    assert recap["actions"] == "_(none)_"
    assert recap["notes"] == "_(none)_"
    assert recap["productivity"] == 3 and recap["energy"] == 4


def test_synthesize_discards_when_no_summary():
    """No parseable SUMMARY → None (don't surface a broken recap)."""
    assert dr.synthesize_recap(
        "2026-06-23", _ENTRIES,
        llm=lambda u, s, max_tokens=0: "HEADLINE: x\nPRODUCTIVITY: 5\nENERGY: 5") is None


def test_synthesize_handles_unavailable_llm():
    """LLM returns None (no key) or "" → None, no crash."""
    assert dr.synthesize_recap("2026-06-23", _ENTRIES, llm=lambda u, s, max_tokens=0: None) is None
    assert dr.synthesize_recap("2026-06-23", _ENTRIES, llm=lambda u, s, max_tokens=0: "") is None


def test_coerce_rating_tolerant():
    assert dr._coerce_rating("8") == 8
    assert dr._coerce_rating("8/10") == 8
    assert dr._coerce_rating("7 (high)") == 7
    assert dr._coerce_rating("12") == 10          # clamp high
    assert dr._coerce_rating("0") == 1            # clamp low
    assert dr._coerce_rating("nope") == 5         # default
    assert dr._coerce_rating(None) == 5


# ---------------------------------------------------------------------------
# (c) empty slots → clean no-op.
# ---------------------------------------------------------------------------
def test_empty_slots_no_op(monkeypatch):
    """No activity today → synth returns None, enqueue reports skipped, NO LLM call,
    NO writes, NO enqueue."""
    tripwire = {"llm": 0, "monday": 0, "vault": 0, "enqueue": 0}

    def _no_llm(*a, **k):
        tripwire["llm"] += 1
        return _LONG_RESPONSE
    monkeypatch.setattr(dr, "_write_monday", lambda *a, **k: tripwire.__setitem__("monday", tripwire["monday"] + 1))
    monkeypatch.setattr(dr, "_write_vault", lambda *a, **k: tripwire.__setitem__("vault", tripwire["vault"] + 1))
    monkeypatch.setattr(dr.intake, "enqueue", lambda *a, **k: tripwire.__setitem__("enqueue", tripwire["enqueue"] + 1))

    # synth path
    assert dr.synthesize_recap("2026-06-23", [], llm=_no_llm) is None
    # full enqueue path with empty injected entries
    out = dr.enqueue_daily_recap(dry=False, today="2026-06-23", llm=_no_llm, entries=[])
    assert out["recap"] is False
    assert "skipped" in out and out["enqueued"] is None
    assert out["monday"] is None and out["vault"] is None
    assert tripwire == {"llm": 0, "monday": 0, "vault": 0, "enqueue": 0}


# ---------------------------------------------------------------------------
# (a) dry=True does ZERO writes — tripwire _write_monday/_write_vault/enqueue.
# ---------------------------------------------------------------------------
def test_dry_run_does_zero_writes(monkeypatch):
    """dry=True must synthesize + return the item + a preview, but call NEITHER
    _write_monday NOR _write_vault NOR intake.enqueue. Any call fails the test."""
    def _boom_monday(*a, **k):
        raise AssertionError("dry=True must NOT write Monday")

    def _boom_vault(*a, **k):
        raise AssertionError("dry=True must NOT write the vault")

    def _boom_enqueue(*a, **k):
        raise AssertionError("dry=True must NOT enqueue")

    monkeypatch.setattr(dr, "_write_monday", _boom_monday)
    monkeypatch.setattr(dr, "_write_vault", _boom_vault)
    monkeypatch.setattr(dr.intake, "enqueue", _boom_enqueue)

    out = dr.enqueue_daily_recap(dry=True, today="2026-06-23", llm=_long_llm, entries=_ENTRIES)

    assert out["recap"] is True and out["dry"] is True
    assert out["enqueued"] is None and out["monday"] is None and out["vault"] is None
    # the would-be intake item is present + the preview carries Monday + vault content
    assert out["item"]["source"] == "daily-recap" and out["item"]["urgency_tier"] == "batch"
    assert out["preview"]["monday"]["board"] == 5096013783
    assert out["preview"]["monday"]["summary"].startswith("The day ran nearly")
    assert out["preview"]["vault"]["path"].endswith("1-Daily/2026-06-23.md")
    # vault preview is the real obsidian-sync-format note
    assert "source: monday-daily-summary" in out["preview"]["vault"]["content"]
    assert "## Summary" in out["preview"]["vault"]["content"]


def test_live_run_writes_both_and_enqueues(monkeypatch):
    """dry=False calls _write_monday, _write_vault, AND intake.enqueue exactly once,
    threading the new Monday item id into the vault note, and returns the telemetry.
    All write seams are stubbed — no real Monday / vault / Redis."""
    calls = {"monday": 0, "vault": 0, "enqueue": 0, "monday_id_in_note": None}

    def _fake_monday(date, recap):
        calls["monday"] += 1
        return {"action": "create", "item_id": "777",
                "url": "https://step-network.monday.com/x/777"}

    def _fake_vault(date, content):
        calls["vault"] += 1
        # the live path must thread the Monday item id into the note
        calls["monday_id_in_note"] = "monday_id: 777" in content
        return {"action": "written", "path": f"/v/1-Daily/{date}.md"}

    def _fake_enqueue(item, **k):
        calls["enqueue"] += 1
        assert item["source"] == "daily-recap"
        return "1700000000000-0"

    monkeypatch.setattr(dr, "_write_monday", _fake_monday)
    monkeypatch.setattr(dr, "_write_vault", _fake_vault)
    monkeypatch.setattr(dr.intake, "enqueue", _fake_enqueue)

    out = dr.enqueue_daily_recap(dry=False, today="2026-06-23", llm=_long_llm, entries=_ENTRIES)

    assert out["recap"] is True and out["dry"] is False
    assert out["enqueued"] == "1700000000000-0"
    assert out["monday"]["item_id"] == "777"
    assert out["vault"]["action"] == "written"
    assert calls == {"monday": 1, "vault": 1, "enqueue": 1, "monday_id_in_note": True}


def test_recap_item_shape_is_long_form_for_composer():
    """The intake item is batch-tier with a long-form summary the composer renders
    as a ▸ titled section (so the PM briefing shows the full recap)."""
    from framework.frontdoor import composer, intake

    recap = dr.synthesize_recap("2026-06-23", _ENTRIES, llm=_long_llm)
    item = dr._recap_item("2026-06-23", recap)
    intake.validate_item(item)  # satisfies the canonical intake contract
    assert item["source"] == "daily-recap" and item["urgency_tier"] == "batch"
    assert composer.render_item(item).startswith("▸ daily-recap")
