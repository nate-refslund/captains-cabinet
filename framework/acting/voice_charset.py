"""voice_charset — outbound text normalization for the acting/frontdoor lanes.

WHAT THIS DOES, and what it deliberately no longer does
-------------------------------------------------------
``normalize_charset()`` applies SCRIPT-AGNOSTIC typography normalization: the
Unicode dash family, bullet glyphs, arrows, ellipsis, curly quotes and
non-breaking spaces are folded to their plain-keyboard equivalents, then the
result is NFC-composed. It is lossless for every writing system: nothing is
dropped, and text in any script comes back intact.

REMOVED 2026-07-28 — the Danish-keyboard CHARSET WHITELIST.
Until this date the framework copy also enforced a whitelist ("write only with
characters on a normal Danish keyboard, plus emojis", a launching-Captain style
rule from 2026-06-25) and DROPPED every character outside it. That rule is a
legitimate INSTANCE preference and a framework invariant it must never have
been: ``framework/`` is the seed for ANY captain in ANY country, and a
character whitelist is a set of permitted human expression.

The consequence was measured, not theorized. ``normalize_charset`` runs at
``framework/frontdoor/binder_wire.py`` on ``routed.edit_text`` — the Captain's
OWN typed edit of an outbound message — immediately before delivery, and it
never raises, so the loss was silent and outward-facing:

    Polish   'Zazolc gesla jazn - Lodz' lost its L-stroke
    Turkish  lost the dotless i
    Greek / Cyrillic / CJK / Arabic / Hebrew / Devanagari  ->  '' or ' '

A Greek, Russian, Japanese, Arabic, Hebrew or Hindi operator's first act of
trusting the cabinet with an outbound message was the act that broke.

THE SEAM THAT REPLACES IT. A deployment that genuinely wants a restricted
output charset calls ``restrict_to_charset(text, allowed)`` and supplies the
set. The framework knows that a deployment MAY restrict its output charset; it
does not know WHICH charset — that is the difference between a mechanism and a
specific. The launching deployment's Danish-keyboard set now lives with the
personal-source adapter in ``instance/flavor-a/`` (``normalize_voice``), which
is where a per-captain style rule belongs, and its behaviour is unchanged.

Idempotent. Pure string transform: no I/O, never raises, only ``re`` and
``unicodedata``, so it imports cleanly with no adapter-specific deps.
"""
from __future__ import annotations
import re
import unicodedata as _ud


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
    """SCRIPT-AGNOSTIC outbound typography normalization. Folds the Unicode
    dash family, bullets, arrows, ellipsis, curly quotes and non-breaking
    spaces to plain-keyboard equivalents, then NFC-composes.

    LOSSLESS BY CONTRACT: no character is dropped and no script is privileged.
    Greek, Cyrillic, CJK, Arabic, Hebrew and Devanagari text comes back intact
    — see the module docstring for what this used to do instead, and why a
    character whitelist could not stay in ``framework/``. Total: any error or
    non-str input returns the input unchanged."""
    if not text or not isinstance(text, str):
        return text
    try:
        return _ud.normalize("NFC", _apply_fast_path(text))
    except Exception:
        return text


def restrict_to_charset(text: str, allowed, keep_emoji: bool = True) -> str:
    """THE SEAM, not a policy: fold ``text`` onto the caller's ``allowed``
    character set. A character outside the set is NFKD-decomposed (combining
    marks stripped) and only the resulting in-set characters are kept; if
    nothing survives, it is dropped.

    The framework knows a deployment MAY want a restricted output charset. It
    does NOT know which characters — ``allowed`` is supplied by the caller, and
    nothing in ``framework/`` calls this with a set of its own. A deployment
    whose captain writes on one keyboard layout wires it in its own layer (the
    launching deployment does exactly that in ``instance/flavor-a/``).

    Restricting an outbound charset is LOSSY by construction: characters the
    caller did not allow do not survive. That is the caller's decision to make
    and to own, which is precisely why it is a parameter. Total: any error or
    non-str input returns the input unchanged."""
    if not text or not isinstance(text, str):
        return text
    try:
        allowed_set = frozenset(allowed)
        out = []
        for ch in text:
            if ch in allowed_set or (keep_emoji and _is_emoji(ch)):
                out.append(ch)
                continue
            nfkd = _ud.normalize("NFKD", ch)
            out.append("".join(c for c in nfkd
                               if not _ud.combining(c) and c in allowed_set))
        return "".join(out)
    except Exception:
        return text
