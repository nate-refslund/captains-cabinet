"""daily_recap — the PM front-door source as a neutral synthesis skeleton:
get_source()-surface evidence gather + labeled-section synthesis + batch intake
item, with the dry-mode tripwire.

Egg plan R023 (2026-07-07): the Monday Activity/Reflections legs and the
obsidian-sync vault-note render are DELETED from the module (boards archived
2026-07-05), so these tests pin the compressed shape — no Monday, no vault, the
single live side effect is the intake enqueue. Evidence is injected via the
``entries=`` seam; the gather tests patch the bound source's methods on the
``get_source()`` singleton (the same pattern test_morning_synthesis.py uses).
The LLM is ALWAYS a stub returning the labeled-section PLAIN TEXT the real model
emits — no network, no key. The parsing regression stays: the synth must parse a
long, multiline, quote-bearing response (the inline-JSON approach discarded it
on 2026-06-23) and dry mode must enqueue NOTHING.
"""
from framework.frontdoor import daily_recap as dr
from framework.sources import get_source

# --- injected day evidence (the gather_day_evidence shape) -------------------
_ENTRIES = [
    {"surface": "find_threads",
     "text": "QA lead: “is the acme-shop checkout flow ready for the vendor review?”"},
    {"surface": "briefing_commitments",
     "text": "owed to QA lead: review pricing widget v2 PR #34 (due 2026-06-23)"},
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
# (a) gather_day_evidence — the neutral enumeration of get_source() surfaces.
# ---------------------------------------------------------------------------
def _thread(person, text, kind="direct"):
    return {"slug": person.lower(), "person": person,
            "last": {"text": text}, "audience": {"kind": kind}}


def _cmt(person, text, due=""):
    return {"person": person, "text": text, "due": due, "status": "open"}


def test_gather_enumerates_both_surfaces(monkeypatch):
    monkeypatch.setattr(get_source(), "find_threads", lambda hours=24: [
        _thread("QA Lead", "is the checkout flow ready?"),
        _thread("Vendor Group", "release notes attached", kind="group"),
    ])
    monkeypatch.setattr(get_source(), "briefing_commitments",
                        lambda direction="owed_by_captain": [
                            _cmt("QA Lead", "review PR #34", "2026-06-23"),
                            _cmt("Vendor", "send the deck"),  # undated → no due suffix
                        ])
    ev = dr.gather_day_evidence()
    assert [e["surface"] for e in ev] == ["find_threads", "find_threads",
                                          "briefing_commitments",
                                          "briefing_commitments"]
    assert ev[0]["text"].startswith("QA Lead: “is the checkout flow ready?”")
    assert "(group)" in ev[1]["text"]                 # non-direct audience tagged
    assert ev[2]["text"] == "owed to QA Lead: review PR #34 (due 2026-06-23)"
    assert ev[3]["text"] == "owed to Vendor: send the deck"


def test_gather_is_best_effort_per_surface(monkeypatch):
    def boom(hours=24):
        raise RuntimeError("source down")
    monkeypatch.setattr(get_source(), "find_threads", boom)
    monkeypatch.setattr(get_source(), "briefing_commitments",
                        lambda direction="owed_by_captain": [_cmt("A", "thing")])
    ev = dr.gather_day_evidence()
    assert [e["surface"] for e in ev] == ["briefing_commitments"]


def test_gather_empty_source_is_empty(monkeypatch):
    # The null / clean-room source shape: every surface returns [] → no evidence.
    monkeypatch.setattr(get_source(), "find_threads", lambda hours=24: [])
    monkeypatch.setattr(get_source(), "briefing_commitments",
                        lambda direction="owed_by_captain": [])
    assert dr.gather_day_evidence() == []


def test_gather_respects_caps(monkeypatch):
    monkeypatch.setattr(get_source(), "find_threads", lambda hours=24: [
        _thread(f"P{i}", "hello") for i in range(30)])
    monkeypatch.setattr(get_source(), "briefing_commitments",
                        lambda direction="owed_by_captain": [
                            _cmt(f"C{i}", "owe thing") for i in range(30)])
    ev = dr.gather_day_evidence(thread_cap=3, commitment_cap=2)
    assert len([e for e in ev if e["surface"] == "find_threads"]) == 3
    assert len([e for e in ev if e["surface"] == "briefing_commitments"]) == 2


def test_build_recap_defaults_to_gather(monkeypatch):
    """No entries injected → build_recap gathers from the source seam."""
    monkeypatch.setattr(dr, "gather_day_evidence", lambda **kw: list(_ENTRIES))
    recap = dr.build_recap(today="2026-06-23", llm=_long_llm)
    assert recap is not None and recap["evidence_count"] == 2


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
    assert recap["evidence_count"] == 2


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
    """LLM returns None (no key / null dispatch) or "" → None, no crash."""
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
# (c) empty evidence → clean no-op.
# ---------------------------------------------------------------------------
def test_empty_evidence_no_op(monkeypatch):
    """No evidence today → synth returns None, enqueue reports skipped, NO LLM
    call, NO enqueue."""
    tripwire = {"llm": 0, "enqueue": 0}

    def _no_llm(*a, **k):
        tripwire["llm"] += 1
        return _LONG_RESPONSE
    monkeypatch.setattr(dr.intake, "enqueue",
                        lambda *a, **k: tripwire.__setitem__("enqueue", tripwire["enqueue"] + 1))

    # synth path
    assert dr.synthesize_recap("2026-06-23", [], llm=_no_llm) is None
    # full enqueue path with empty injected evidence
    out = dr.enqueue_daily_recap(dry=False, today="2026-06-23", llm=_no_llm, entries=[])
    assert out["recap"] is False
    assert "skipped" in out and out["enqueued"] is None
    assert tripwire == {"llm": 0, "enqueue": 0}


# ---------------------------------------------------------------------------
# (d) dry=True enqueues NOTHING — tripwire intake.enqueue.
# ---------------------------------------------------------------------------
def test_dry_run_does_zero_enqueues(monkeypatch):
    """dry=True must synthesize + return the item + a preview, but never call
    intake.enqueue. Any call fails the test."""
    def _boom_enqueue(*a, **k):
        raise AssertionError("dry=True must NOT enqueue")

    monkeypatch.setattr(dr.intake, "enqueue", _boom_enqueue)

    out = dr.enqueue_daily_recap(dry=True, today="2026-06-23", llm=_long_llm, entries=_ENTRIES)

    assert out["recap"] is True and out["dry"] is True
    assert out["enqueued"] is None
    # the would-be intake item is present + the preview carries the briefing text
    assert out["item"]["source"] == "daily-recap" and out["item"]["urgency_tier"] == "batch"
    assert out["preview"]["evidence_count"] == 2
    assert out["preview"]["intake_item_summary"].startswith("📓 Daily recap — 2026-06-23")
    assert "The day ran nearly" in out["preview"]["intake_item_summary"]


def test_live_run_enqueues_once(monkeypatch):
    """dry=False calls intake.enqueue exactly once with the recap item and
    returns the telemetry. The enqueue seam is stubbed — no real Redis. There
    are no other side-effect seams left (the Monday/vault legs are deleted)."""
    calls = {"enqueue": 0}

    def _fake_enqueue(item, **k):
        calls["enqueue"] += 1
        assert item["source"] == "daily-recap"
        return "1700000000000-0"

    monkeypatch.setattr(dr.intake, "enqueue", _fake_enqueue)

    out = dr.enqueue_daily_recap(dry=False, today="2026-06-23", llm=_long_llm, entries=_ENTRIES)

    assert out["recap"] is True and out["dry"] is False
    assert out["enqueued"] == "1700000000000-0"
    assert calls == {"enqueue": 1}


def test_recap_item_shape_is_long_form_for_composer():
    """The intake item is batch-tier with a long-form summary the composer renders
    as a ▸ titled section (so the PM briefing shows the full recap)."""
    from framework.frontdoor import composer, intake

    recap = dr.synthesize_recap("2026-06-23", _ENTRIES, llm=_long_llm)
    item = dr._recap_item("2026-06-23", recap)
    intake.validate_item(item)  # satisfies the canonical intake contract
    assert item["source"] == "daily-recap" and item["urgency_tier"] == "batch"
    assert composer.render_item(item).startswith("▸ daily-recap")
