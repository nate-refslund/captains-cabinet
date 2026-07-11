"""Typed envelope v1 for the cabinet Redis-Streams bus — REPORT-ONLY (A6).

Ledger context (docs/plans/operative-egg-ledger-2026-07-07.yml): row A6 ships
the envelope schema + validator over the EXISTING untyped bus; row A12 is the
bus-hardening acceptance gate that later makes it binding. THIS MODULE NEVER
ENFORCES: enforcement, division-blocking, and any scope additions are
HANDBACK #14 (Captain-gated). The untyped legacy path is grandfathered until
the A12 gate per the A6 row's own rollback note.

Choke points (followed from the code, not the plan row — the plan named
framework/triggers/registry.py, but that file is the durable at-time/interval
reminder registry and never touches Redis; the actual bus producers are):
  * cabinet/scripts/lib/triggers.sh  trigger_send() XADD (:172-176) — every
    officer/cron sender incl. run-status-sweep.sh rides it   [wiring BLOCKED
    this wave: multi-writer guard — file owned by feat/fidelity-harness-design]
  * cabinet/mcp-server/server.py XADD sites :430 (cross-cabinet self-delivery
    → cabinet:triggers:<role>), :460 (send_message → cabinet:inbox:<peer>),
    :506 (request_handoff → cabinet:inbox:<peer>)             [wired, report-only]
Consumers: officers via XREADGROUP group officer-<name>
(cabinet/scripts/start-officer-mac.sh:485-505) and
cabinet/scripts/exhaust-archive.py (STREAM_PATTERN cabinet:triggers:*).

FAIL-OPEN BY DESIGN: in report-only mode the bus MUST be unaffected even if
this module is buggy. report_only() swallows every exception into a counter;
validate() never raises on any input. Producers call report_only() beside —
never around — their XADD; a validator crash costs one counter tick, not a
message.

Names-not-values logging: violation lines carry field NAMES, byte sizes and a
short whitelist of bounded identity fields only. Bus messages can echo env
vars, errors and personal content (see exhaust-archive.py's scrub list); the
violations file must never become a second copy of that content.

Size bound: MAX_ENVELOPE_BYTES = 16384. Measured 2026-07-11 (read-only XRANGE
over live cabinet:triggers:{cos,polads-ceo,stephie-ceo,comms-officer}):
n=173 entries, min 168 / median 861 / p95 2018 / max 3259 bytes (sum of
key+value byte lengths). Bound = ~5x observed max, generous headroom for
typed-envelope overhead while still catching flood-shaped payloads.

Replay stance: replay detection is a CONSUMER concern, not a validator
concern. The A12 row prose states the delivery semantics itself:
"at-least-once + idempotent consumers". XREADGROUP redelivers un-ACKed
entries carrying the SAME envelope id — a producer-side or stateless
validator that flagged a twice-seen id would flag correct bus behavior.
Dedupe therefore belongs at the consumption edge, keyed on envelope id;
ReplayWindow below is the bounded helper consumers use for exactly that,
and the red-team suite proves it flags a replayed id.

Taint vocabulary: no canonical taint-tier enum exists in the tree (checked
2026-07-11 — framework/attention "taint" is injection-suspect handling;
trust_ladder tiers are urgency tiers). TAINT_TIERS below is a v1 PROVISIONAL
shape vocabulary for validation only, ordered most→least trusted. The
taint-join LAW (worst-of + trust-non-inheritance) lands as germline VALUES
via the CG-9(d) Captain ledger entry — taint_join()/check_taint_join() here
are pure helpers exercised by the red-team suite, enforced nowhere.

Pure stdlib. Import cost is trivial; no I/O at import time.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional

# --------------------------------------------------------------------------
# Schema (closed sets — FI-1 closed-set doctrine: unknown key = violation)
# --------------------------------------------------------------------------

KINDS = ("intent", "evidence", "verdict", "need", "grant_request", "heartbeat")

# v1 provisional, most→least trusted (see module docstring; CG-9(d) owns the law).
TAINT_TIERS = ("captain", "officer", "system", "cross_cabinet", "external")

REQUIRED_KEYS = ("id", "from", "to", "kind", "provenance", "taint", "budget")
OPTIONAL_KEYS = ("reply_to",)
ENVELOPE_KEYS = frozenset(REQUIRED_KEYS) | frozenset(OPTIONAL_KEYS)

TAINT_KEYS = frozenset({"tier", "sources"})

# ulid-shaped: 26 chars, Crockford base32 (no I, L, O, U).
# \Z not $: Python `$` also matches before a trailing newline, which let a
# forged 27-char id ('0'*26 + '\n') pass as ulid-shaped (review finding
# ULID-NEWLINE-BYPASS, 2026-07-11). \Z anchors at the true end of string.
ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}\Z")

MAX_ENVELOPE_BYTES = 16384   # measured: live max 3259 (n=173) — see docstring
MAX_FIELD_CHARS = 256        # from/to/kind/reply_to/tier and each taint source
MAX_PROVENANCE_CHARS = 1024  # provenance may carry a short producer chain
MAX_SOURCES = 64
MAX_BUDGET = 10**9
MAX_REASONS = 32

# Per-kind rules, each derived from the A6/A12/A7 row prose:
#  * verdict   → reply_to REQUIRED: a verdict answers an existing envelope
#                (A7: verify() requests plane-signed verdicts; the A12
#                forged-verdict class needs the answered-what hook).
#  * evidence  → taint.sources NON-EMPTY: evidence must cite where it came
#                from; worst-of taint-join has nothing to join over an empty
#                source set.
#  * heartbeat → reply_to ABSENT: a liveness beacon answers nothing.
#  * intent / need / grant_request → base fields only.
_KIND_NEEDS_REPLY_TO = frozenset({"verdict"})
_KIND_FORBIDS_REPLY_TO = frozenset({"heartbeat"})
_KIND_NEEDS_SOURCES = frozenset({"evidence"})


def _blen(v: Any) -> int:
    """Byte length of a value as it would ride the bus (same accounting as
    the 2026-07-11 measurement: utf-8 length of the string form)."""
    if isinstance(v, str):
        return len(v.encode("utf-8", errors="replace"))
    try:
        return len(json.dumps(v, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        return len(repr(v).encode("utf-8", errors="replace"))


def envelope_bytes(payload: Any) -> int:
    """Total byte size of an envelope dict (sum of key+value byte lengths)."""
    if not isinstance(payload, dict):
        return _blen(payload)
    return sum(_blen(k) + _blen(v) for k, v in payload.items())


def _check_str(reasons: list[str], payload: dict, key: str, *,
               max_chars: int = MAX_FIELD_CHARS, required: bool = True) -> None:
    """Type/bound check for a string field. Reasons carry key names, types and
    lengths — NEVER field values (names-not-values, see module docstring)."""
    if key not in payload:
        if required:
            reasons.append(f"missing required key: {key}")
        return
    v = payload[key]
    if not isinstance(v, str):
        reasons.append(f"{key}: expected str, got {type(v).__name__}")
        return
    if not v.strip():
        reasons.append(f"{key}: empty")
        return
    if len(v) > max_chars:
        reasons.append(f"{key}: length {len(v)} exceeds {max_chars}")


def _validate_taint(reasons: list[str], taint: Any) -> None:
    if not isinstance(taint, dict):
        reasons.append(f"taint: expected dict, got {type(taint).__name__}")
        return
    unknown = sorted(set(taint) - TAINT_KEYS)
    if unknown:
        reasons.append(f"taint: unknown keys: {', '.join(str(k) for k in unknown)}")
    if "tier" not in taint:
        reasons.append("taint: missing required key: tier")
    else:
        tier = taint["tier"]
        if not isinstance(tier, str):
            reasons.append(f"taint.tier: expected str, got {type(tier).__name__}")
        elif tier not in TAINT_TIERS:
            # tier is a closed-enum value — safe to echo (bounded, never free text)
            reasons.append(f"taint.tier: {tier[:32]!r} not in {list(TAINT_TIERS)}")
    if "sources" not in taint:
        reasons.append("taint: missing required key: sources")
    else:
        sources = taint["sources"]
        if not isinstance(sources, list):
            reasons.append(f"taint.sources: expected list, got {type(sources).__name__}")
        else:
            if len(sources) > MAX_SOURCES:
                reasons.append(f"taint.sources: {len(sources)} items exceeds {MAX_SOURCES}")
            for i, s in enumerate(sources[:MAX_SOURCES]):
                if not isinstance(s, str) or not s.strip():
                    reasons.append(f"taint.sources[{i}]: expected non-empty str, "
                                   f"got {type(s).__name__}")
                    break
                if len(s) > MAX_FIELD_CHARS:
                    reasons.append(f"taint.sources[{i}]: length {len(s)} exceeds "
                                   f"{MAX_FIELD_CHARS}")
                    break


def validate(payload: Any) -> tuple[bool, list[str]]:
    """Validate a typed envelope. Returns (ok, reasons). NEVER raises.

    STRICT closed-key semantics (FI-1 closed-set doctrine): any key outside
    ENVELOPE_KEYS is a violation, as is any key outside TAINT_KEYS inside
    taint. Reasons never embed free-text field values — key names, type
    names, lengths, and closed-enum values (kind, tier) only.
    """
    reasons: list[str] = []
    try:
        if not isinstance(payload, dict):
            return False, [f"envelope: expected dict, got {type(payload).__name__}"]

        unknown = sorted(str(k) for k in set(payload) - ENVELOPE_KEYS)
        if unknown:
            reasons.append(f"unknown keys: {', '.join(unknown[:8])}")

        # id — ulid-shaped
        if "id" not in payload:
            reasons.append("missing required key: id")
        else:
            eid = payload["id"]
            if not isinstance(eid, str):
                reasons.append(f"id: expected str, got {type(eid).__name__}")
            elif not ULID_RE.match(eid):
                reasons.append("id: not ulid-shaped (26-char Crockford base32)")

        _check_str(reasons, payload, "from")
        _check_str(reasons, payload, "to")
        _check_str(reasons, payload, "provenance", max_chars=MAX_PROVENANCE_CHARS)
        _check_str(reasons, payload, "reply_to", required=False)

        # kind — closed six-value set (a seventh kind is a violation: A6 gate)
        kind = payload.get("kind")
        if "kind" not in payload:
            reasons.append("missing required key: kind")
        elif not isinstance(kind, str):
            reasons.append(f"kind: expected str, got {type(kind).__name__}")
        elif kind not in KINDS:
            # kind is a closed-enum candidate — safe to echo truncated
            reasons.append(f"kind: {kind[:32]!r} not in {list(KINDS)}")

        # taint {tier, sources}
        if "taint" not in payload:
            reasons.append("missing required key: taint")
        else:
            _validate_taint(reasons, payload["taint"])

        # budget — non-negative int (bool is an int subclass: reject explicitly)
        if "budget" not in payload:
            reasons.append("missing required key: budget")
        else:
            budget = payload["budget"]
            if isinstance(budget, bool) or not isinstance(budget, int):
                reasons.append(f"budget: expected int, got {type(budget).__name__}")
            elif budget < 0 or budget > MAX_BUDGET:
                reasons.append(f"budget: {budget} outside [0, {MAX_BUDGET}]")

        # per-kind rules (derivations in _KIND_* comments above)
        if isinstance(kind, str):
            if kind in _KIND_NEEDS_REPLY_TO and not payload.get("reply_to"):
                reasons.append("verdict: reply_to required (a verdict answers "
                               "an existing envelope — A7 plane-signed verdicts)")
            if kind in _KIND_FORBIDS_REPLY_TO and "reply_to" in payload:
                reasons.append("heartbeat: reply_to must be absent")
            if kind in _KIND_NEEDS_SOURCES:
                taint = payload.get("taint")
                if isinstance(taint, dict) and taint.get("sources") == []:
                    reasons.append("evidence: taint.sources must be non-empty "
                                   "(evidence cites its sources)")

        # size bound (measured — see module docstring)
        size = envelope_bytes(payload)
        if size > MAX_ENVELOPE_BYTES:
            reasons.append(f"envelope: {size} bytes exceeds {MAX_ENVELOPE_BYTES}")

        reasons = reasons[:MAX_REASONS]
        return (len(reasons) == 0), reasons
    except Exception as e:  # pragma: no cover — belt: validate() NEVER raises
        return False, [f"validator internal error: {type(e).__name__}"][:MAX_REASONS]


# --------------------------------------------------------------------------
# Taint-join helpers (pure; the LAW is CG-9(d) Captain-gated — enforced nowhere)
# --------------------------------------------------------------------------

def taint_join(tiers: list[str]) -> str:
    """Worst-of join. Unknown tier or empty input joins to the WORST tier
    (fail-safe: unrecognized provenance never launders upward)."""
    worst = 0
    if not tiers:
        return TAINT_TIERS[-1]
    for t in tiers:
        try:
            idx = TAINT_TIERS.index(t)
        except ValueError:
            return TAINT_TIERS[-1]
        worst = max(worst, idx)
    return TAINT_TIERS[worst]


def check_taint_join(claimed_tier: str, source_tiers: list[str]) -> bool:
    """True iff claimed_tier is no more trusted than worst-of(source_tiers).
    A joined/forwarded envelope claiming a tier ABOVE its sources' worst-of
    is a taint-forgery (A12 class: taint-tier forgery)."""
    if claimed_tier not in TAINT_TIERS:
        return False
    joined = taint_join(source_tiers)
    return TAINT_TIERS.index(claimed_tier) >= TAINT_TIERS.index(joined)


# --------------------------------------------------------------------------
# Consumer-side replay window (see "Replay stance" in the module docstring)
# --------------------------------------------------------------------------

class ReplayWindow:
    """Bounded seen-id window for IDEMPOTENT CONSUMERS (A12 delivery
    semantics: at-least-once + idempotent consumers). seen(id) returns True
    when the id was already recorded — the consumer skips the duplicate.
    Bounded LRU so a flood cannot grow memory without limit."""

    def __init__(self, capacity: int = 4096):
        self.capacity = max(1, int(capacity))
        self._seen: OrderedDict[str, None] = OrderedDict()

    def seen(self, envelope_id: str) -> bool:
        if envelope_id in self._seen:
            self._seen.move_to_end(envelope_id)
            return True
        self._seen[envelope_id] = None
        if len(self._seen) > self.capacity:
            self._seen.popitem(last=False)
        return False


# --------------------------------------------------------------------------
# Report-only wiring (the ONLY side-effectful surface in this module)
# --------------------------------------------------------------------------

REPORT_ENV = "CABINET_ENVELOPE_REPORT"          # "0" = kill-knob (default ON)
_REPO_ROOT = Path(__file__).resolve().parents[2]
VIOLATIONS_PATH = _REPO_ROOT / "shared" / "interfaces" / "envelope-violations.jsonl"

# NOT YET GITIGNORED (known gap, 2026-07-11): the .gitignore line for this
# runtime file is BLOCKED this wave — .gitignore is owned by
# feat/fidelity-harness-design (multi-writer guard) — and is a NAMED handback
# for the merging session: add `shared/interfaces/envelope-violations.jsonl`
# to .gitignore alongside the other enumerated runtime jsonl siblings
# (falsifier-series, charter-shadow-series, golden-eval-scalar, …).
# No rotation/sweep exists yet either (exhaust-archive.py does not cover this
# file); since 100% of current bus traffic classifies legacy_untyped, the file
# grows on every entry. MAX_VIOLATIONS_BYTES below is the interim self-guard:
# report_only() stops appending (fail-open, counted in REPORT_SUPPRESSED) once
# the file reaches the cap. Proper rotation = follow-up with the A12 gate.
MAX_VIOLATIONS_BYTES = 32 * 1024 * 1024   # 32 MiB append cap (interim guard)

# Fail-open counter: every swallowed exception in report_only() ticks this.
REPORT_ERRORS = 0

# Lines NOT written because the violations file hit MAX_VIOLATIONS_BYTES.
REPORT_SUPPRESSED = 0

# Bounded identity fields whose (truncated) VALUES may appear in a violation
# line. Everything else is names+sizes only — bus messages can echo secrets
# and personal content; the violations file must never mirror it.
_SAFE_VALUE_FIELDS = ("sender", "from", "to", "kind", "tier",
                      "source", "from_agent", "from_cabinet")
_SAFE_VALUE_CHARS = 64


def report_errors() -> int:
    return REPORT_ERRORS


def reporting_enabled() -> bool:
    return os.environ.get(REPORT_ENV, "1") != "0"


def classify_fields(fields: dict) -> tuple[str, list[str]]:
    """Classify one outbound bus entry (flat field/value dict as XADDed).

    * carries an "envelope" field → typed: parse JSON + validate() →
      ("ok", []) or ("invalid", reasons)
    * no "envelope" field → ("legacy_untyped", []) — grandfathered until the
      A12 gate per the A6 row rollback note; counted, never condemned.
    """
    if "envelope" not in fields:
        return "legacy_untyped", []
    raw = fields.get("envelope")
    if not isinstance(raw, str):
        return "invalid", [f"envelope field: expected JSON str, got {type(raw).__name__}"]
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return "invalid", ["envelope field: not valid JSON"]
    ok, reasons = validate(payload)
    return ("ok", []) if ok else ("invalid", reasons)


def report_only(site: str, stream: str, fields: dict,
                path: Optional[os.PathLike] = None) -> None:
    """Report-only conformance probe for one outbound bus entry.

    Appends ONE jsonl line for every non-"ok" entry to
    shared/interfaces/envelope-violations.jsonl (or `path`). NEVER drops,
    mutates, tags, or delays the entry — the caller's XADD proceeds
    identically whether this logs, no-ops, or crashes. FAIL-OPEN BY DESIGN:
    every exception is swallowed into REPORT_ERRORS (report-only means the
    bus must be unaffected even if envelope.py is buggy). Kill-knob:
    CABINET_ENVELOPE_REPORT=0 disables entirely.

    Names-not-values: the line carries field keys, byte sizes, verdict,
    reasons, and truncated values for _SAFE_VALUE_FIELDS only.

    Growth bound: once the target file reaches MAX_VIOLATIONS_BYTES the line
    is silently NOT appended (REPORT_SUPPRESSED ticks) — interim self-guard
    until rotation lands; see the MAX_VIOLATIONS_BYTES comment above.
    """
    global REPORT_ERRORS, REPORT_SUPPRESSED
    try:
        if not reporting_enabled():
            return
        if not isinstance(fields, dict):
            fields = {"_nondict_entry": repr(type(fields))}
        verdict, reasons = classify_fields(fields)
        if verdict == "ok":
            return
        safe: dict[str, str] = {}
        for k in _SAFE_VALUE_FIELDS:
            v = fields.get(k)
            if isinstance(v, str) and v:
                safe[k] = v[:_SAFE_VALUE_CHARS]
        line = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "site": str(site)[:128],
            "stream": str(stream)[:128],
            "verdict": verdict,
            "reasons": reasons[:8],
            "field_keys": sorted(str(k) for k in fields)[:32],
            "field_bytes": envelope_bytes(fields),
            "safe_fields": safe,
        }
        out = Path(path) if path is not None else VIOLATIONS_PATH
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            if out.stat().st_size >= MAX_VIOLATIONS_BYTES:
                REPORT_SUPPRESSED += 1
                return
        except OSError:
            pass  # file absent → first write; any other stat oddity: fail open
        with open(out, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        REPORT_ERRORS += 1
