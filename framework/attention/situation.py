"""framework.attention.situation — mechanical situation identity.

WHY (2026-07-08 feed incident): every dedup key in the acting lanes was LLM
prose — subject slugs re-worded per run, evidence refs annotated per run
("path — <fresh paraphrase>") — so 'same evidence = same situation' never
fired and one testament reminder became 6+ cards and 2 duplicate calendar
events. This module extracts the STABLE ids embedded in those strings
(vault paths, commitment ids, correlation ids, event UUIDs, monday ids,
URLs) so identity comparison is deterministic prose-free set overlap.

Pure stdlib, no I/O, no clock — safe inside the replay-deterministic
propose step. Extracted "paths" are opaque identity strings: never opened,
resolved, or joined onto a filesystem. Spec:
docs/plans/cabinet-attention-gateway-spec-2026-07-08.md §4.1.
"""
from __future__ import annotations

import hashlib
import re
from typing import Iterable

# Per-string and per-call hard caps: canonicalization runs on LLM/captured
# text, so a hostile mega-string must cost O(cap), not O(input).
_MAX_STR = 10_000
_MAX_ITEMS = 64

# Vault-relative markdown paths. Deliberately NO spaces in the class: the
# evidence annotation separator (" — ") and OCR artifacts would otherwise
# glue prose into the path. A space-bearing filename loses its prefix here;
# the id patterns below (cmt-/uuid/monday) still carry identity for those.
_MD_PATH = re.compile(r"[\w()&.\-/]+\.md")
_CMT_ID = re.compile(r"\bcmt-[0-9a-f]{6,}\b")
_CORR_ID = re.compile(r"\bcabinet-proposal-id:[0-9a-f]{8,}\b")
_UUID = re.compile(
    r"\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b")
_MONDAY = re.compile(r"\bmonday:(\d{6,})\b")
_URL = re.compile(r"https?://[^\s<>\"'`]+")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _norm_path(p: str) -> str:
    p = re.sub(r"/{2,}", "/", p).lstrip("=")
    while p.startswith("./"):
        p = p[2:]
    return p.strip("/")


def _norm_url(u: str) -> str:
    m = re.match(r"(https?)://([^/]+)(.*)", u, re.IGNORECASE)
    if not m:
        return u
    scheme, host, rest = m.groups()
    return f"{scheme.lower()}://{host.lower()}{rest.rstrip('.,;:)')}"


def canonical_refs(evidence: "Iterable | None") -> frozenset:
    """Extract the stable-id set from raw evidence strings.

    Non-string items and over-cap input are skipped, never raised on: this
    runs on model output inside the propose step and must be total."""
    out: set = set()
    if evidence is None:
        return frozenset(out)
    try:
        items = list(evidence)[:_MAX_ITEMS]
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
        out.update(_norm_url(x) for x in _URL.findall(s))
    return frozenset(out)


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
