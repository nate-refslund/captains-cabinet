"""Fix 2 — the '🔎 prep:' block rendering in the propose loop.

run_draft_lane reads TELEGRAM_COS_TOKEN / CAPTAIN_TELEGRAM_ID at import (it is a
launchd script, not a library), so we set dummy env before importing it. We test
ONLY the pure _prep_lines renderer here — no Telegram send, no LLM, no brain. The
live prep gather is exercised by the DRY run; this locks the present-surface
contract: gathered items show as ✓, not-auto-gatherable items as ⚠, and an empty
prep renders nothing (no clutter)."""
import os

os.environ.setdefault("TELEGRAM_COS_TOKEN", "test-token")
os.environ.setdefault("CAPTAIN_TELEGRAM_ID", "0")

from framework.acting import run_draft_lane as rdl  # noqa: E402


class TestPrepLines:
    def test_empty_prep_renders_nothing(self):
        assert rdl._prep_lines(None) == ""
        assert rdl._prep_lines({}) == ""
        assert rdl._prep_lines({"gathered": [], "check_yourself": []}) == ""

    def test_gathered_items_marked_check(self):
        out = rdl._prep_lines({"gathered": ["open commitments with Lena: 2"],
                               "check_yourself": []})
        assert "🔎 prep:" in out
        assert "✓ open commitments with Lena: 2" in out
        assert out.endswith("\n\n")  # trails into the draft block

    def test_check_yourself_items_flagged(self):
        out = rdl._prep_lines(
            {"gathered": [],
             "check_yourself": ["couldn't find the old DPA text - verify manually"]})
        assert "⚠ check yourself: couldn't find the old DPA text" in out

    def test_both_sections_render(self):
        out = rdl._prep_lines(
            {"gathered": ["compared OLD vs NEW DPA -> searched: DPA"],
             "check_yourself": ["the July sommerfest date (no vault hit)"]})
        assert "✓ compared OLD vs NEW DPA" in out
        assert "⚠ check yourself: the July sommerfest date" in out

    def test_caps_at_four_each(self):
        out = rdl._prep_lines(
            {"gathered": [f"g{i}" for i in range(10)],
             "check_yourself": [f"c{i}" for i in range(10)]})
        assert out.count("✓") == 4
        assert out.count("⚠") == 4
