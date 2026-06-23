"""composer renders long-form (rewired pipe DM) items as titled sections; short
items stay provenance bullets."""
from framework.frontdoor import composer


def test_short_item_is_a_bullet():
    item = {"source": "awaiting-reply", "kind": "thread", "ts": "t",
            "payload": {"summary": "Lisa awaits reply"}, "context": {"why": "no reply yet"}}
    out = composer.render_item(item)
    assert out.startswith("• [awaiting-reply] Lisa awaits reply")
    assert "no reply yet" in out


def test_multiline_item_is_a_section():
    long_text = "🌅 Morning brief\n- item one\n- item two"
    item = {"source": "morning-brief", "kind": "pipe-dm", "ts": "t",
            "payload": {"summary": long_text}}
    out = composer.render_item(item)
    assert out.startswith("▸ morning-brief\n")     # titled section, not a bullet
    assert "🌅 Morning brief" in out
    assert "- item one" in out                      # pipe's own formatting preserved


def test_long_single_line_is_a_section():
    item = {"source": "deep-research", "kind": "pipe-dm", "ts": "t",
            "payload": {"summary": "y" * 250}}
    assert composer.render_item(item).startswith("▸ deep-research\n")
