"""B2.1 — the correlation-id propagation standard (the join is the evidence plane).

An OUTCOME probe (B2.3-B2.7) observes an external artifact — a Vercel deploy, a
Sentry release, a git commit, a support thread — and must join it back to the
Cabinet PROPOSAL that caused it, WITHOUT inferring from time/author heuristics
[RT#3]. The join key is a uuid4 minted at proposal time (``loop.propose``),
carried on the proposal event's ``refs`` as ``cabinet-proposal-id:<uuid>`` and
STAMPED into each artifact in a format-specific way. This module is the SINGLE
SOURCE OF TRUTH for those formats — mint, stamp, and read-back. It is PURE: no
IO, no state, stdlib only, so any probe or hook can import it freely.

Internal correlation (binding a reply to its pending proposal) already uses
``loop.proposal_id`` — the identity tuple. THIS is the separate EXTERNAL key for
artifacts produced by downstream execution, where the identity tuple isn't
visible. Unattributable artifacts (human merges, external pushes) carry no id
and MUST record ``outcome.status=unknown`` crediting no officer [RT#3].
"""
from __future__ import annotations

import re
import uuid

# --- the canonical format strings (single source of truth) ---
REF_PREFIX = "cabinet-proposal-id:"           # the refs[] convention on the event
GIT_TRAILER_KEY = "Cabinet-Proposal-Id"       # git commit message / PR body trailer
RESEND_HEADER_KEY = "X-Cabinet-Proposal-Id"   # outbound support email header
VERCEL_META_KEY = "cabinetProposalId"         # `vercel deploy --meta <k>=<cid>`
MONDAY_FOOTER_PREFIX = "cabinet-proposal-id:"  # Monday update body footer

_CID = r"[0-9a-f]{32}"                         # uuid4().hex
_CID_RE = re.compile(rf"\A{_CID}\Z")


def mint() -> str:
    """A fresh correlation id — uuid4 hex (32 chars)."""
    return uuid.uuid4().hex


def is_cid(value: str) -> bool:
    return bool(isinstance(value, str) and _CID_RE.match(value))


def short(cid: str) -> str:
    """The 8-char human tag used in subject lines ([CAB-xxxxxxxx])."""
    return (cid or "")[:8]


# --- refs[] convention: how the proposal EVENT carries the id -----------------

def ref_for(cid: str) -> str:
    return f"{REF_PREFIX}{cid}"


def cid_from_refs(refs) -> str | None:
    """The first well-formed cabinet-proposal-id in a refs list, else None."""
    for r in refs or []:
        if isinstance(r, str) and r.startswith(REF_PREFIX):
            v = r[len(REF_PREFIX):].strip()
            if is_cid(v):
                return v
    return None


# --- artifact stampers: the OUTBOUND formats downstream execution emits -------

def git_trailer(cid: str) -> str:
    """Trailer line for a commit message's final paragraph / PR body footer."""
    return f"{GIT_TRAILER_KEY}: {cid}"


def resend_header(cid: str) -> tuple[str, str]:
    """(header-name, value) for an outbound support email."""
    return (RESEND_HEADER_KEY, cid)


def vercel_meta(cid: str) -> tuple[str, str]:
    """(meta-key, value) for `vercel deploy --meta <k>=<v>`."""
    return (VERCEL_META_KEY, cid)


def subject_tag(cid: str) -> str:
    """Human-visible short tag for an email subject line."""
    return f"[CAB-{short(cid)}]"


def monday_footer(cid: str) -> str:
    """Footer line for a Monday update body."""
    return f"{MONDAY_FOOTER_PREFIX} {cid}"


# --- extractors / read-back: how a probe RECOVERS the id from an artifact -----
# Strict, prefix-anchored patterns (never a loose scan) so untrusted artifact
# text can't smuggle a false id past the join.
# `(?![0-9a-f])` after the 32-hex group rejects a 32-char PREFIX of a longer hex
# run (e.g. a 40-char blob) — a malformed/untrusted artifact must not join.
_TRAILER_RE = re.compile(rf"^{re.escape(GIT_TRAILER_KEY)}:[ \t]*({_CID})(?![0-9a-f])[ \t]*$",
                         re.IGNORECASE | re.MULTILINE)
_FOOTER_RE = re.compile(rf"{re.escape(MONDAY_FOOTER_PREFIX)}[ \t]*({_CID})(?![0-9a-f])",
                        re.IGNORECASE)
_SUBJECT_RE = re.compile(r"\[CAB-([0-9a-f]{8})\]", re.IGNORECASE)


def from_git_trailer(text: str) -> str | None:
    m = _TRAILER_RE.search(text or "")
    return m.group(1).lower() if m else None


def from_subject_tag(text: str) -> str | None:
    """The 8-char SHORT form from a subject tag (never a full cid) — a probe
    disambiguates it against the known open proposals' short ids."""
    m = _SUBJECT_RE.search(text or "")
    return m.group(1).lower() if m else None


def extract(text: str) -> str | None:
    """Best-effort recovery of a FULL cid from arbitrary artifact body text —
    tries the git trailer then the Monday-footer form. The Resend header and the
    subject tag are read via their own accessors (a header dict / from_subject_tag)
    because they don't live in body text."""
    for rx in (_TRAILER_RE, _FOOTER_RE):
        m = rx.search(text or "")
        if m:
            return m.group(1).lower()
    return None
