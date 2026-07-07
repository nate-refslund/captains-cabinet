"""GOLDEN PIN for ``daily_recap.render_vault_note`` — the obsidian-sync safety net.

WHY THIS TEST EXISTS (read before touching it).
``framework/frontdoor/daily_recap.render_vault_note`` builds the canonical
``1-Daily/YYYY-MM-DD.md`` note. ``daily_recap`` writes that note **byte-identical**
to obsidian-sync's ``sync_daily_summaries`` so obsidian-sync's next 30-min run
sha256-matches and SKIPS — no duplicate, no churn (see daily_recap.py §3b). A
SINGLE byte of render drift breaks that convergence: obsidian-sync would rewrite
the note on every run forever.

The SOURCE-ADAPTER migration
(``docs/plans/source-adapter-boundary-2026-07-05.md`` §5 Phase 2 step 4; §6
"frontdoor · egress" row, HOTTEST) moves ``daily_recap``'s screenpipe coupling
behind ``framework.sources`` — INCLUDING where ``render_vault_note`` reads the
reflections-board id (today ``_sp().CONFIG["reflections_board"]["id"]``). The spec
mandates: *"pin the daily-note render with a golden hash test BEFORE moving it"*
(§6). This file is that pin. It freezes TODAY's render as the golden so the
migration MUST reproduce it byte-for-byte. **A red hash here == the render
changed == the invariant broke.**

CONTRACT FOR THE MIGRATOR (P2-FRONT):
  * ``_GOLDEN_SHA_*`` and ``_EXPECTED_*`` below are FROZEN. Do NOT edit them to
    make a red test pass — a changed hash means ``render_vault_note`` drifted;
    fix the code, not the golden.
  * If your migration repoints WHERE the reflections-board id comes from (away
    from ``dr._sp``), change ONLY the ``_stub_board_id`` fixture to feed the
    SAME id (``_REFLECTIONS_BOARD_ID``) through the new seam. The rendered bytes
    — and thus the hashes — must stay identical.

Fully hermetic: fixed injected inputs, the board id stubbed the same way
``test_daily_recap.py::_stub_sp`` stubs it — no live vault, no Monday, no LLM,
no screenpipe, no key.
"""
import hashlib
import types

import pytest

from framework.frontdoor import daily_recap as dr

# The real reflections-board id (documented in daily_recap.py:470 + registered
# in test_no_launcher_hardcode's shrink-only allowlist for this file). This exact
# value produced the frozen hashes below and appears verbatim in the WITH_ID
# render's _Source link. If migration moves where render_vault_note reads it,
# feed THIS SAME value through the new seam — the hashes must not move.
_REFLECTIONS_BOARD_ID = 5096013783


@pytest.fixture
def _stub_board_id(monkeypatch):
    """Inject the reflections-board id render_vault_note needs, WITHOUT screenpipe.

    Today render_vault_note reads it via
    ``dr._sp().CONFIG["reflections_board"]["id"]`` — the same seam
    ``test_daily_recap.py::_stub_sp`` uses. THE ONE PLACE TO REPOINT if the
    SOURCE-ADAPTER migration moves that read to ``framework.sources.get_source()``
    or a config resolver: change this fixture to feed ``_REFLECTIONS_BOARD_ID``
    through the new seam. Do NOT change the goldens.
    """
    stub = types.SimpleNamespace(
        CONFIG={"reflections_board": {"id": _REFLECTIONS_BOARD_ID}},
        load_env=lambda *a, **k: None,
    )
    monkeypatch.setattr(dr, "_sp", lambda: stub)


# --- FIXED, injected render inputs (no live vault / LLM / Monday) -----------
# A representative recap dict (the shape synthesize_recap returns): a
# multi-paragraph, quote-bearing summary + bulleted findings/actions/notes,
# mirroring a real busy day — so the golden exercises multiline bodies + the
# em-dash / embedded-quote bytes obsidian-sync must reproduce.
_DATE = "2026-06-23"
_MONDAY_ID = "4210987654"
_RECAP = {
    "headline": "Shipped acme-shop checkout flow + reviewed pricing widget v2 PR",
    "summary": (
        "The day ran nearly around the clock. From 09:30 the captain drove the "
        "checkout-flow branch, wrestling the taxCategory validation gate — an "
        "explicit merchant declaration, not auto-set from country.\n\n"
        'By 14:00 focus shifted to pricing widget v2 (PR #34). A "PriceCard" '
        "data-* prop issue and a frozen undo button both surfaced.\n\n"
        "Energy held through the afternoon."
    ),
    "findings": (
        "- VAT auto-fill is still flaky on the merchant path\n"
        "- taxCategory must stay an explicit declaration (spec §7.1)"
    ),
    "actions": (
        "- Merge PR #34 once MONDAY_API_KEY is rotated\n"
        "- Block auto-inference of taxCategory before merge"
    ),
    "notes": (
        "- QA flagged the vendor DPA as a launch blocker\n"
        "- ~17 active hours; top tools: Claude Code, VS Code"
    ),
    "productivity": 9,
    "energy": 6,
    "slot_count": 2,
}

# --- FROZEN GOLDENS — the invariant P2-FRONT must reproduce byte-for-byte ----
# Computed from TODAY's render_vault_note (originally frozen on branch
# feat/source-adapter-p2; re-frozen 2026-07-07 by the egg-plan R036 fixture
# neutralization, which changed ONLY the injected _RECAP content above — the
# render logic was untouched and the literals below were regenerated from the
# real render). Do NOT edit to make a red test pass — a changed value means
# the render drifted.
_GOLDEN_SHA_WITH_ID = "ffd01c75f0542469ff6fa653cab3d8727d0ebe4f2de154a19929cece7923f112"
_GOLDEN_SHA_PENDING = "f2fde606c24533cce4eb8bd6221b07c4fddb61b5d355f1b97fa0597e48464432"

# The exact rendered bytes for each case (auto-generated from the real render,
# not hand-typed). A readable diff when a byte drifts; self-verified against the
# frozen hashes by test_frozen_literals_match_frozen_hashes below.
_EXPECTED_WITH_ID = (
    '---\n'
    'type: daily\n'
    'date: 2026-06-23\n'
    'productivity: 9\n'
    'energy: 6\n'
    'tags:\n'
    '  - daily\n'
    '  - synced\n'
    'source: monday-daily-summary\n'
    'monday_id: 4210987654\n'
    '---\n'
    '\n'
    '# 2026-06-23 — Daily Summary\n'
    '\n'
    '_Source: [Monday item 4210987654](https://step-network.monday.com/boards/5096013783/pulses/4210987654)_\n'
    '\n'
    '## Summary\n'
    'The day ran nearly around the clock. From 09:30 the captain drove the checkout-flow branch, wrestling the taxCategory validation gate — an explicit merchant declaration, not auto-set from country.\n'
    '\n'
    'By 14:00 focus shifted to pricing widget v2 (PR #34). A "PriceCard" data-* prop issue and a frozen undo button both surfaced.\n'
    '\n'
    'Energy held through the afternoon.\n'
    '\n'
    '## Key findings\n'
    '- VAT auto-fill is still flaky on the merchant path\n'
    '- taxCategory must stay an explicit declaration (spec §7.1)\n'
    '\n'
    '## Actions\n'
    '- Merge PR #34 once MONDAY_API_KEY is rotated\n'
    '- Block auto-inference of taxCategory before merge\n'
    '\n'
    '## Notes\n'
    '- QA flagged the vendor DPA as a launch blocker\n'
    '- ~17 active hours; top tools: Claude Code, VS Code\n'
    '\n'
    '## Meetings on this day\n'
    '```dataview\n'
    'TABLE WITHOUT ID file.link AS Meeting, attendees, project\n'
    'FROM "2-Meetings"\n'
    'WHERE date = date("2026-06-23")\n'
    '```\n'
)

_EXPECTED_PENDING = (
    '---\n'
    'type: daily\n'
    'date: 2026-06-23\n'
    'productivity: 9\n'
    'energy: 6\n'
    'tags:\n'
    '  - daily\n'
    '  - synced\n'
    'source: monday-daily-summary\n'
    'monday_id:\n'
    '---\n'
    '\n'
    '# 2026-06-23 — Daily Summary\n'
    '\n'
    '_Source: (pending Monday sync)_\n'
    '\n'
    '## Summary\n'
    'The day ran nearly around the clock. From 09:30 the captain drove the checkout-flow branch, wrestling the taxCategory validation gate — an explicit merchant declaration, not auto-set from country.\n'
    '\n'
    'By 14:00 focus shifted to pricing widget v2 (PR #34). A "PriceCard" data-* prop issue and a frozen undo button both surfaced.\n'
    '\n'
    'Energy held through the afternoon.\n'
    '\n'
    '## Key findings\n'
    '- VAT auto-fill is still flaky on the merchant path\n'
    '- taxCategory must stay an explicit declaration (spec §7.1)\n'
    '\n'
    '## Actions\n'
    '- Merge PR #34 once MONDAY_API_KEY is rotated\n'
    '- Block auto-inference of taxCategory before merge\n'
    '\n'
    '## Notes\n'
    '- QA flagged the vendor DPA as a launch blocker\n'
    '- ~17 active hours; top tools: Claude Code, VS Code\n'
    '\n'
    '## Meetings on this day\n'
    '```dataview\n'
    'TABLE WITHOUT ID file.link AS Meeting, attendees, project\n'
    'FROM "2-Meetings"\n'
    'WHERE date = date("2026-06-23")\n'
    '```\n'
)


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Self-consistency: the FROZEN literals hash to the FROZEN goldens. Runs with NO
# code path — guards the pin against a literal/hash edit that drifts them apart
# (someone edits _EXPECTED_* but not _GOLDEN_SHA_*, or vice versa).
# ---------------------------------------------------------------------------
def test_frozen_literals_match_frozen_hashes():
    assert _sha(_EXPECTED_WITH_ID) == _GOLDEN_SHA_WITH_ID
    assert _sha(_EXPECTED_PENDING) == _GOLDEN_SHA_PENDING


# ---------------------------------------------------------------------------
# The golden: render_vault_note reproduces the frozen bytes for BOTH src_line
# branches (a real Monday pulse id, and the pending-sync fallback).
# ---------------------------------------------------------------------------
def test_render_vault_note_golden_with_monday_id(_stub_board_id):
    note = dr.render_vault_note(_DATE, _RECAP, _MONDAY_ID)
    assert note == _EXPECTED_WITH_ID          # readable diff on drift
    assert _sha(note) == _GOLDEN_SHA_WITH_ID  # the frozen byte-pin
    # the coupling this case pins: the reflections-board id lands in the _Source
    # link, so a migration that mis-sources it drifts the hash.
    assert (f"/boards/{_REFLECTIONS_BOARD_ID}/pulses/{_MONDAY_ID}") in note


def test_render_vault_note_golden_pending_sync(_stub_board_id):
    note = dr.render_vault_note(_DATE, _RECAP, None)
    assert note == _EXPECTED_PENDING
    assert _sha(note) == _GOLDEN_SHA_PENDING
    # monday_id=None → the board id is NOT emitted; the fallback src_line is.
    assert "_Source: (pending Monday sync)_" in note
    assert str(_REFLECTIONS_BOARD_ID) not in note


# ---------------------------------------------------------------------------
# Input-contract guard: the fixed _RECAP must carry every field render_vault_note
# reads. If the render starts reading a new recap key, the golden inputs must
# grow to stay faithful — this fails loudly rather than silently under-pinning.
# ---------------------------------------------------------------------------
def test_recap_fixture_covers_every_field_render_reads():
    for key in ("summary", "findings", "actions", "notes", "productivity", "energy"):
        assert key in _RECAP, f"golden _RECAP is missing render input {key!r}"
