"""voice_charset — the LOSSLESS contract, pinned.

This suite exists because of what the module used to do. Until 2026-07-28
``normalize_charset`` enforced a Danish-keyboard character whitelist and
DROPPED everything outside it, in ``framework/`` — i.e. in every cabinet, in
every country. It runs on the Captain's own edited outbound text
(``framework/frontdoor/binder_wire.py`` -> ``routed.edit_text``, immediately
before delivery) and it never raises, so the loss was silent and landed
OUTSIDE the org, where it could not be walked back.

There was no test. A whitelist with no test is a rule nobody has to defend, so
these arms are written to FAIL against the pre-change implementation:
every non-Latin script assertion below returned ``''`` or ``' '`` under the old
code (measured, not assumed), and ``test_restrict_to_charset_is_the_seam``
does not exist there at all.
"""
from __future__ import annotations

from framework.acting.voice_charset import normalize_charset, restrict_to_charset


# Every one of these came back empty, or as a single space, under the
# whitelist. They are the reason the whitelist could not stay in framework/.
_SCRIPTS = {
    "polish": "Zażółć gęślą jaźń, Łódź",
    "turkish": "Güneş ışığı, Ğğ İi Şş",
    "greek": "Καλημέρα κόσμε",
    "cyrillic": "Здравствуйте, коллеги",
    "japanese": "契約書を確認してください",
    "chinese": "请确认合同",
    "korean": "계약서를 확인해 주세요",
    "arabic": "مرحبا بالعالم",
    "hebrew": "שלום עולם",
    "devanagari": "नमस्ते दुनिया",
    "thai": "สวัสดีชาวโลก",
    "vietnamese": "Xin chào thế giới",
}


class TestLosslessForEveryScript:
    def test_no_script_is_dropped(self):
        """THE contract: framework text normalization privileges no writing
        system. Nothing here is even partially lost."""
        for name, text in _SCRIPTS.items():
            assert normalize_charset(text) == text, name

    def test_no_script_loses_characters(self):
        """Belt to the braces above: an equality that held by both sides being
        empty would be vacuous, so assert the payload survives by LENGTH too."""
        for name, text in _SCRIPTS.items():
            out = normalize_charset(text)
            assert len(out) == len(text) and out.strip(), name

    def test_danish_and_emoji_still_survive(self):
        for text in ("blåbær på øen", "café naïve", "5€ + 3$",
                     "ship 🚀👍", "DK 🇩🇰", "dev 👨‍💻"):
            assert normalize_charset(text) == text


class TestTypographyStillNormalized:
    """The half of the old behaviour that was script-agnostic and stays: fancy
    typography folds to plain keyboard equivalents, in any script."""

    def test_dashes_bullets_arrows_quotes_ellipsis(self):
        assert normalize_charset("a — b") == "a - b"
        assert normalize_charset("a ― b") == "a - b"          # horizontal bar
        assert normalize_charset("a⸺b") == "a - b"            # two-em dash
        assert normalize_charset("5 − 3") == "5 - 3"          # math minus
        assert normalize_charset("build A → ship") == "build A -> ship"
        assert normalize_charset("wait…") == "wait..."
        assert normalize_charset("“x” det’s") == '"x" det\'s'
        assert normalize_charset("  • nested") == "  - nested"

    def test_typography_folds_inside_a_non_latin_sentence(self):
        """The fold is orthogonal to script — the CJK payload is untouched
        while the em-dash and ellipsis still normalize."""
        assert normalize_charset("契約 — 確認…") == "契約 - 確認..."

    def test_idempotent_and_total(self):
        once = normalize_charset("a — b → c\n• d")
        assert normalize_charset(once) == once
        assert normalize_charset("") == ""
        assert normalize_charset(None) is None
        assert normalize_charset(123) == 123


class TestRestrictToCharsetIsTheSeam:
    """The mechanism the framework keeps: the caller supplies the set. Nothing
    in framework/ calls this with a set of its own — a deployment that wants a
    restricted output charset owns that decision in its own layer."""

    def test_caller_supplied_set_is_what_restricts(self):
        ascii_lower = frozenset("abcdefghijklmnopqrstuvwxyz ")
        assert restrict_to_charset("abc", ascii_lower) == "abc"
        assert restrict_to_charset("abc", frozenset("ab")) == "ab"

    def test_decomposes_before_dropping(self):
        latin = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ")
        assert restrict_to_charset("café", latin) == "cafe"     # NFKD, mark stripped
        assert restrict_to_charset("ＡBC", latin) == "ABC"      # fullwidth
        assert restrict_to_charset("m²", latin) == "m2"
        assert restrict_to_charset("a中b", latin) == "ab"       # no equivalent -> dropped

    def test_emoji_are_kept_unless_the_caller_says_otherwise(self):
        latin = frozenset("abcdefghijklmnopqrstuvwxyz ")
        assert restrict_to_charset("ship 🚀", latin) == "ship 🚀"
        assert restrict_to_charset("ship 🚀", latin, keep_emoji=False) == "ship "

    def test_total_on_bad_input(self):
        assert restrict_to_charset("", frozenset("a")) == ""
        assert restrict_to_charset(None, frozenset("a")) is None
        assert restrict_to_charset(123, frozenset("a")) == 123

    def test_framework_itself_never_calls_it_with_a_set(self):
        """The forcing function: the day framework code passes its OWN character
        set to this seam, the specific is back — under a nicer name."""
        import re
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]  # framework/
        callers = []
        for p in sorted(root.rglob("*.py")):
            parts = p.relative_to(root).parts
            if "tests" in parts or "__pycache__" in parts:
                continue
            if p.name.startswith("test_") or p.name == "voice_charset.py":
                continue  # the defining module names the seam; callers are the risk
            text = p.read_text(encoding="utf-8", errors="replace")
            if re.search(r"\brestrict_to_charset\s*\(", text):
                callers.append(p.relative_to(root).as_posix())
        assert callers == [], (
            "framework/ must not restrict its own output charset — the set "
            "belongs to the deployment: %s" % callers)
