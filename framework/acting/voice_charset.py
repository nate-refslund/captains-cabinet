"""voice_charset — captain-voice charset rule (framework-vendored copy).

VENDORED 2026-07-02 (CI 2861900…) from ~/.screenpipe/pipes/_shared/voice_charset.py
so flavor-B / CI installs get the SAME one implementation without the screenpipe
estate. The _shared copy remains live for the pipes until the A3 re-point turns
it into a re-export of this file — until then, changes go to BOTH (they are
byte-synced below this header; drift check: diff the two files minus this block).

Origin rule (Captain, 2026-06-25): write only with characters on a normal
Danish keyboard, PLUS emojis.

The captain's rule (2026-06-25, refined): "write only with characters on a normal
Danish keyboard, PLUS emojis." So instead of an ever-growing substitution
table, normalize_charset() enforces a CHARSET WHITELIST with an emoji-safe
catch-all:
  1. FAST PATH  — a small map for the common offenders, giving nice results
     (em/en/any dash -> " - ", bullet glyphs -> "-", arrows -> "->",
      ellipsis -> "...", curly quotes -> '/' , NBSP -> space).
  2. WHITELIST  — the Danish-keyboard charset is kept verbatim: a-z A-Z, 0-9,
     ae/oe/aa (the three Danish letters, both cases), the accented Latin
     reachable via dead keys, standard punctuation/symbols (incl. EUR), space,
     newline. EMOJIS are kept too (the captain uses them) and NEVER stripped.
  3. CATCH-ALL  — any char NOT whitelisted and NOT an emoji is decomposed
     (unicodedata NFKD, combining marks stripped) and only the resulting
     keyboard chars are kept; if nothing keyboard-friendly results, the char is
     dropped. So an unanticipated fancy char (a CJK char, a math symbol, a
     rare dash variant the fast path missed) is caught, not leaked — the table
     never has to grow again.

Idempotent: keyboard-only text (incl. emojis + ae/oe/aa) passes through
unchanged. Pure string transform: no I/O, never raises, only `re` +
`unicodedata` deps so it imports cleanly with NO screenpipe deps — which is why
both screenpipe's draft_lib AND the cabinet's acting adapter import this one
implementation instead of each restating it (the E-2 de-duplication: the whole
point of the charset reframe was that the table never grows again, so two copies
would re-introduce drift).
"""
from __future__ import annotations
import re
import unicodedata as _ud

# Danish-keyboard punctuation/symbols (AltGr-reachable EUR + the usual set).
_KB_PUNCT = set(" \t\n\r" + ".,;:!?-_'\"()[]{}/\\@#%&=+*<>$€|~^`")
# Accented Latin letters a normal DK keyboard produces via dead keys (acute,
# grave, circumflex, diaeresis, tilde, cedilla) + sharp-s, both cases.
_KB_ACCENTED = set(
    "éèêëáàâäïîíì"
    "óòôöúùûüçñýÿ"
    "ÉÈÊËÁÀÂÄÏÎÍÌ"
    "ÓÒÔÖÚÙÛÜÇÑÝß"
)
# The three Danish letters, both cases (must be whitelisted explicitly: NFKD
# would otherwise decompose å -> 'a' and lose them).
_KB_DANISH = set("æøåÆØÅ")


def _is_emoji(ch: str) -> bool:
    """True when `ch` is part of an emoji (incl. flags, dingbats, skin-tone
    modifiers, ZWJ and variation selectors so multi-codepoint emoji sequences
    survive intact). Emojis are NEVER normalized or dropped."""
    o = ord(ch)
    return (
        0x1F000 <= o <= 0x1FAFF or          # emoticons/pictographs/transport/supplemental
        0x2600 <= o <= 0x27BF or            # misc symbols + dingbats
        0x1F1E6 <= o <= 0x1F1FF or          # regional indicators (flags)
        0x1F3FB <= o <= 0x1F3FF or          # skin-tone modifiers
        0x2B00 <= o <= 0x2BFF or            # misc symbols & arrows (stars, etc.)
        o in (0x200D, 0xFE0F, 0xFE0E) or    # ZWJ + variation selectors
        o in (0x203C, 0x2049, 0x2122, 0x2139, 0x2194, 0x2195, 0x2196, 0x2197,
              0x2198, 0x2199, 0x21A9, 0x21AA, 0x231A, 0x231B, 0x2328, 0x23CF,
              0x24C2, 0x25AA, 0x25AB, 0x25B6, 0x25C0, 0x2934, 0x2935) or
        0x23E9 <= o <= 0x23FA or
        0x25FB <= o <= 0x25FE
    )


def _in_keyboard_charset(ch: str) -> bool:
    """True when `ch` is directly producible on a normal Danish keyboard."""
    if ch in _KB_PUNCT or ch in _KB_DANISH or ch in _KB_ACCENTED:
        return True
    return ch.isascii() and (ch.isalnum() or ch in _KB_PUNCT)


def _catch_all_char(ch: str) -> str:
    """Map a non-keyboard, non-emoji char to its keyboard equivalent via NFKD
    (combining marks stripped, only keyboard chars kept), or '' to drop it."""
    nfkd = _ud.normalize("NFKD", ch)
    return "".join(c for c in nfkd
                   if not _ud.combining(c) and _in_keyboard_charset(c))


# FAST PATH — common offenders, run before the catch-all for nicer results.
_FP_ARROW_RE = re.compile(r"[→⟶➜➔⇒➙➞]")
# Any Unicode dash/hyphen variant (category Pd) + math-minus -> spaced hyphen.
_FP_DASH_RE = re.compile(
    r"\s*[‐‑‒–—―−⸺⸻"
    r"﹘﹣－⸗⸚]\s*")
_FP_BULLET_LINE_RE = re.compile(
    r"(?m)^([ \t]*)[•‣·▪●⁃∙◦․]\s*")
_FP_BULLET_INLINE_RE = re.compile(r"[•‣▪●⁃∙◦]")
_FP_ELLIPSIS_RE = re.compile(r"…")
_FP_DQUOTE_RE = re.compile(r"[“”„‟«»]")
_FP_SQUOTE_RE = re.compile(r"[‘’‚‛‹›]")
_FP_NBSP_RE = re.compile(r"[      ]")


def _apply_fast_path(text: str) -> str:
    text = _FP_ARROW_RE.sub("->", text)
    text = _FP_DASH_RE.sub(" - ", text)
    text = _FP_BULLET_LINE_RE.sub(r"\1- ", text)
    text = _FP_BULLET_INLINE_RE.sub("-", text)
    text = _FP_ELLIPSIS_RE.sub("...", text)
    text = _FP_DQUOTE_RE.sub('"', text)
    text = _FP_SQUOTE_RE.sub("'", text)
    text = _FP_NBSP_RE.sub(" ", text)
    return text


def normalize_charset(text: str) -> str:
    """Enforce the Danish-keyboard-plus-emoji charset: run the fast-path map, then
    sweep every remaining char — keep it if it's keyboard-producible OR an emoji,
    else map it through the NFKD catch-all (or drop). The single source of truth
    for the teams-message-voice-formatting charset rule. Total: any error or
    non-str input returns the input unchanged."""
    if not text or not isinstance(text, str):
        return text
    try:
        text = _apply_fast_path(text)
        out = []
        for ch in text:
            if _in_keyboard_charset(ch) or _is_emoji(ch):
                out.append(ch)
            else:
                out.append(_catch_all_char(ch))  # keyboard equivalent or '' (drop)
        return "".join(out)
    except Exception:
        return text
