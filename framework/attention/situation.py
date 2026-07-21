"""framework.attention.situation — mechanical situation identity.

WHY (2026-07-08 feed incident): every dedup key in the acting lanes was LLM
prose — subject slugs re-worded per run, evidence refs annotated per run
("path — <fresh paraphrase>") — so 'same evidence = same situation' never
fired and one document-signing reminder became 6+ cards and 2 duplicate calendar
events. This module extracts the STABLE ids embedded in those strings
(vault paths, commitment ids, correlation ids, event UUIDs, monday ids,
scheme'd cabinet ids, URLs) so identity comparison is deterministic
prose-free set overlap.

Pure stdlib, no I/O, no clock — safe inside the replay-deterministic
propose step. Extracted "paths" are opaque identity strings: never opened,
resolved, or joined onto a filesystem. All extracted ids are lowercased —
identity must survive LLM case drift (and macOS's case-insensitive FS
means case-divergent vault spellings are the same file anyway).

Deliberately NOT extracted (false-positive magnets, adversarial-review
2026-07-08): bare hex tokens (git short-shas / case ids glue unrelated
situations), extensionless vault paths (top-dir layout is instance data —
framework must not hardcode one captain's vault shape).

Spec: docs/plans/cabinet-attention-gateway-spec-2026-07-08.md §4.1.
"""
from __future__ import annotations

import hashlib
import re
from typing import Iterable

# Per-STRING hard cap: canonicalization runs on LLM/captured text, so one
# hostile mega-string must cost O(cap), not O(input). There is deliberately
# NO item-count cap: callers pass finite, already-bounded collections (a
# proposal's evidence is caller-capped at 8; the covered set is ledger-
# derived, each row ≤8 refs ≤200 chars) and an item cap silently truncated
# the covered set in hash order — nondeterministic dedup (adversarial
# review 2026-07-08, PYTHONHASHSEED repro).
_MAX_STR = 10_000

# Vault-relative markdown paths. Deliberately NO spaces in the class: the
# evidence annotation separator (" — ") and OCR artifacts would otherwise
# glue prose into the path. A space-bearing filename (2-Meetings/ notes)
# loses its prefix here; the id patterns below still carry identity for
# those. The end-guard rejects `.mdx`, `.md.bak-20260705`, `.md-old`, and
# `.md~` sibling near-misses — extracting the live file's path from a
# sibling's name was a verified false-positive suppression vector.
_MD_PATH = re.compile(r"[\w()&.\-/]+\.md(?![\w~-]|\.\w)")
_CMT_ID = re.compile(r"\bcmt-[0-9a-f]{6,}\b", re.IGNORECASE)
_CORR_ID = re.compile(r"\bcabinet-proposal-id:[0-9a-f]{8,}\b", re.IGNORECASE)
_UUID = re.compile(
    r"\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b")
# monday ids: the canonical "monday:123..." form (colon-space tolerated) and
# the observed prose form "board `<9+ digits>`" (live board/item ids run 10
# digits; the 9-floor keeps compact dates like 20260708 out). Both
# normalize to "monday:<digits>".
_MONDAY = re.compile(r"\bmonday:\s*(\d{6,})\b", re.IGNORECASE)
_BOARD = re.compile(r"\bboard[\s_`'\"-]*(\d{9,})\b", re.IGNORECASE)
# Cabinet scheme'd ids seen in live ledger refs (live-corpus fuzz
# 2026-07-08): veto:<key>, undo-journal:<jid>, thread:<key>. Colon-anchored
# (a space after the colon reads as prose and is excluded); sentence
# punctuation the tail class admits ('.') is stripped at extraction.
# NEED-<hex> is dash-anchored and must contain a DIGIT — hex-alphabet words
# ("need-added", "need-deed") cannot mint ids.
_SCHEME_ID = re.compile(
    r"\b(?:veto|undo-journal|thread):[A-Za-z0-9][\w./@-]{2,64}", re.IGNORECASE)
_NEED_ID = re.compile(r"\bneed-(?=[0-9a-f]*\d)[0-9a-f]{4,}\b", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _norm_path(p: str) -> str:
    p = re.sub(r"/{2,}", "/", p).lstrip("=")
    while p.startswith("./"):
        p = p[2:]
    # A citation like "(9-Codebases/Toolbox/commits.md)" keeps the opening
    # paren (it is in the path class for names like Reflections-&-Research.md);
    # strip leading parens that never close inside the match.
    while p.startswith("(") and p.count("(") > p.count(")"):
        p = p[1:]
    return p.strip("/").lower()


def _norm_url(u: str) -> str:
    # Sentence punctuation binds to the match for pathless URLs too
    # ("see https://newsletter.example."), so strip it from the WHOLE url first.
    u = u.rstrip(".,;:)")
    m = re.match(r"(https?)://([^/]+)(.*)", u, re.IGNORECASE)
    if not m:
        return u
    scheme, host, rest = m.groups()
    # Trailing-slash drift ("…/path/" vs "…/path") is the same identity —
    # mirror _norm_path, which already strips slashes.
    return f"{scheme.lower()}://{host.lower()}{rest.rstrip('/')}"


def canonical_refs(evidence: "Iterable | None") -> frozenset:
    """Extract the stable-id set from raw evidence strings.

    Non-string items and over-cap strings are skipped, never raised on: this
    runs on model output inside the propose step and must be total. Output
    ids are lowercase. Deterministic: a pure function of the input SET
    (iteration order cannot change the result — no truncation)."""
    out: set = set()
    if evidence is None:
        return frozenset(out)
    try:
        items = list(evidence)
    except TypeError:
        return frozenset(out)
    for item in items:
        if not isinstance(item, str):
            continue
        s = item.strip().strip("`\"'")[:_MAX_STR]
        if not s:
            continue
        for m in _MD_PATH.findall(s):
            p = _norm_path(m)
            # a bare filename with no directory carries no vault identity
            if "/" in p:
                out.add(p)
        out.update(x.lower() for x in _CMT_ID.findall(s))
        out.update(x.lower() for x in _CORR_ID.findall(s))
        out.update(x.lower() for x in _UUID.findall(s))
        out.update(f"monday:{x}" for x in _MONDAY.findall(s))
        out.update(f"monday:{x}" for x in _BOARD.findall(s))
        # sentence punctuation binds into the scheme-id tail class — strip it
        out.update(x.lower().rstrip(".,;:") for x in _SCHEME_ID.findall(s))
        out.update(x.lower() for x in _NEED_ID.findall(s))
        out.update(_norm_url(x) for x in _URL.findall(s))
    return frozenset(out)


def path_grade(ref: str) -> bool:
    """True for vault-path canonical refs (the '.md' class) — the weaker
    identity grade: rolling digest files legitimately host many situations
    over time, so consumers treat path-only overlap as the audit-worthy
    suppression class. URLs that happen to end in '.md' are id-grade."""
    return ref.endswith(".md") and "://" not in ref


def situations_overlap(a: "Iterable | None", b: "Iterable | None") -> bool:
    """True when two raw evidence bundles share ANY stable id.

    Empty canonical sets never overlap (prose-only evidence carries no
    identity — fail toward presenting, per the lane dedup doctrine)."""
    ca = canonical_refs(a)
    if not ca:
        return False
    return bool(ca & canonical_refs(b))


def situation_key(evidence: "Iterable | None", subject: str = "") -> str:
    """Stable situation id: hash of the sorted canonical ref-set; slug
    fallback for genuinely ref-less items (matches action_lane.slugify).
    sha1 here is a stable identity digest, not a security boundary."""
    refs = canonical_refs(evidence)
    if refs:
        digest = hashlib.sha1("\n".join(sorted(refs)).encode("utf-8")).hexdigest()
        return f"sit-{digest[:16]}"
    slug = _SLUG_RE.sub("-", (subject or "").lower()).strip("-")[:80]
    return f"slug:{slug}"
