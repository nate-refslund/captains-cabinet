"""Typed envelope v1 for the cabinet Redis-Streams bus — VALIDATE + ENFORCE.

Ledger context (docs/plans/operative-egg-ledger-2026-07-07.yml): row A6 ships
the envelope schema + validator over the EXISTING untyped bus; row A12 is the
bus-hardening gate that makes it BINDING. Two side-effectful surfaces now
exist: report_only() (A6 warn-only census — counts, never blocks) and
enforce() (A12 "flip to block", Captain ruling 2026-07-14 — a TYPED envelope
that fails validate() is REFUSED at the producer). enforce() enforces ONLY the
checks validate() already performs; SCOPE ADDITIONS beyond that
(division-blocking, the taint-join LAW) remain Captain-gated (HANDBACK #14 /
CG-9(d)). The untyped LEGACY path stays grandfathered — enforce() never blocks
it — until a separate Captain scope decision condemns it.

Choke points (followed from the code, not the plan row — the plan named
framework/triggers/registry.py, but that file is the durable at-time/interval
reminder registry and never touches Redis; the actual bus producers are):
  * cabinet/scripts/lib/triggers.sh  trigger_send() XADD (:172-176) — every
    officer/cron sender incl. run-status-sweep.sh rides it   [wiring BLOCKED
    this wave: multi-writer guard — file owned by feat/fidelity-harness-design]
  * cabinet/mcp-server/server.py XADD sites: cross-cabinet self-delivery
    (→ cabinet:triggers:<role>), send_message (→ cabinet:inbox:<peer>),
    request_handoff (→ cabinet:inbox:<peer>)
    [wired, ENFORCED per Captain ruling 2026-07-14 "flip to block" — each site
     calls _envelope_enforce() and REFUSES the XADD on a typed-invalid envelope;
     legacy/untyped entries stay open (grandfathered). Line numbers omitted — they drift]
Consumers: officers via XREADGROUP group officer-<name>
(cabinet/scripts/start-officer-mac.sh:485-505) and
cabinet/scripts/exhaust-archive.py (STREAM_PATTERN cabinet:triggers:*).

FAIL DIRECTIONS (two surfaces, two directions):
  * report_only() is FAIL-OPEN — in warn-only census the bus must be unaffected
    even if this module is buggy: it swallows every exception into a counter,
    and validate() never raises on any input. Producers call it BESIDE — never
    around — their XADD; a validator crash costs one counter tick, not a message.
  * enforce() is FAIL-CLOSED for TYPED envelopes — a typed envelope it cannot
    cleanly judge is BLOCKED (the Captain's safer direction: never silently
    send a suspect typed envelope). Producers call it as a GATE before the XADD
    and refuse the send when it returns blocked. Legacy/untyped entries are
    exempt via a leading presence check taken BEFORE any fallible work, so an
    enforcement bug can never break the grandfathered bus. enforce() never
    raises into the producer.

Names-not-values logging: violation lines carry field NAMES, byte sizes and a
short whitelist of bounded identity fields only. Bus messages can echo env
vars, errors and personal content (see exhaust-archive.py's scrub list); the
violations file must never become a second copy of that content.

Size bound: MAX_ENVELOPE_BYTES = 16384. Measured 2026-07-11 (read-only XRANGE
over live cabinet:triggers:{cos,<lane>-ceo,...,comms-officer} across every
officer stream on the deployment):
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

    FOUR-WAY since COG-1 (§4.1 — VERSION DISPATCH happens here, BEFORE the
    v1 closed-set check, which would otherwise refuse every v2 envelope):

    * no "envelope" field → ("legacy_untyped", []) — grandfathered until the
      A12 gate per the A6 row rollback note; counted, never condemned.
    * envelope JSON WITHOUT "schema_version" → v1: the FROZEN validate() →
      ("ok", []) or ("invalid", reasons). No v1 semantic change.
    * envelope JSON WITH "schema_version" → v2: validate_v2() →
      ("ok", []) or ("invalid", reasons).
    * non-str / non-JSON envelope field → ("invalid", reasons).
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
    ok, reasons = validate_any(payload)
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


# --------------------------------------------------------------------------
# Enforcement wiring (A12 "flip to block" — Captain ruling 2026-07-14)
# --------------------------------------------------------------------------
# report_only() above COUNTS a non-conforming envelope but the producer still
# SENDS it (fail-open census). enforce() is the BINDING gate the A12 row makes
# authoritative: under ENFORCED, a TYPED envelope that fails validate() is
# BLOCKED — the producer refuses the send (no XADD). It enforces EXACTLY the
# checks validate()/classify_fields() already perform; it adds NO new
# validation scope (division-blocking, the taint-join law → Captain-gated).
#
# GRANDFATHER (the bus-breakage guard): a legacy untyped entry (no "envelope"
# field) is the A6-grandfathered path and, as measured 2026-07-11, 100% of
# current live bus traffic. It is NEVER blocked — condemning the legacy path is
# a separate Captain scope decision, not this flip. The typed/legacy split is a
# single near-unbreakable presence check taken BEFORE any fallible work, so an
# enforcement bug cannot become a bus-wide outage of grandfathered traffic.
#
# FAIL-DIRECTION (deliberate): enforce() fails CLOSED (BLOCK) for a TYPED
# envelope it cannot cleanly judge — the safer direction the Captain intends.
# classify_fields()/validate() never raise on a dict, so that path is only
# reachable under a truly pathological failure; it still fails closed there and
# NEVER raises into the producer. Legacy/untyped stays open.
#
# SWITCH: ENFORCED (module constant, default True per the 2026-07-14 ruling) is
# the greppable, reversible mode flag; env CABINET_ENVELOPE_ENFORCE=0 drops the
# gate to warn-only (report_only() still logs; nothing is blocked). This knob is
# INDEPENDENT of the report kill-knob (CABINET_ENVELOPE_REPORT) — census and
# enforcement are separate concerns; set both to 0 to disable envelopes wholly.

ENFORCE_ENV = "CABINET_ENVELOPE_ENFORCE"     # "0" = warn-only knob (default: ENFORCED)
ENFORCED = True                              # Captain ruling 2026-07-14 "flip to block"

# Count of sends refused by enforce() this process (audit/observability sibling
# to REPORT_ERRORS / REPORT_SUPPRESSED).
ENFORCE_BLOCKED = 0


def enforcement_enabled() -> bool:
    """True when enforce() may BLOCK a send. Default follows ENFORCED (True per
    the 2026-07-14 Captain ruling); CABINET_ENVELOPE_ENFORCE=0 reverts to
    warn-only (no blocking — report_only() still records the violation)."""
    return os.environ.get(ENFORCE_ENV, "1" if ENFORCED else "0") != "0"


def enforce_blocked() -> int:
    """Number of sends enforce() has refused this process (observability)."""
    return ENFORCE_BLOCKED


def enforce(fields: Any) -> tuple[bool, str, list[str]]:
    """Enforcement decision for one outbound bus entry (the flat field/value
    dict as it would be XADDed). Returns (blocked, verdict, reasons):

      * blocked=True  → the producer MUST refuse the send (do NOT XADD);
                        ``reasons`` carries the validate() failure reasons.
      * blocked=False → the send proceeds unchanged.

    Semantics — enforces ONLY what validate() already checks (via
    classify_fields), NO new scope:
      * legacy_untyped (no "envelope" field, or a non-dict entry) → NOT blocked
        (A6-grandfathered; the bus-breakage guard — see the module comment).
      * ok      (typed + validate() passed)                       → NOT blocked.
      * invalid (typed + validate() failed, or a non-str / non-JSON envelope
                 field)  → BLOCKED when enforcement_enabled(); returned
                 not-blocked (verdict still "invalid") in warn-only mode.

    NOTE — replay (A12 class 2) is intentionally NOT enforced here: validate()
    accepts the same id twice by design (at-least-once bus; dedupe is the
    consumer's job via ReplayWindow), so blocking a replayed id at the producer
    would be a NEW scope AND would break correct redelivery. Its defense stays
    consumer-side.

    NEVER raises. Fail-direction = BLOCK for a TYPED envelope on an unexpected
    error (fail-closed); the leading typed/legacy split keeps grandfathered
    traffic exempt from both enforcement and that fail-closed path.
    """
    global ENFORCE_BLOCKED
    # Leading typed/legacy split BEFORE any heavier work. A non-dict entry cannot
    # be a typed envelope → legacy (open). The `in` test can only misbehave on a
    # pathological dict SUBCLASS (poisoned __contains__/__eq__), which no real
    # producer builds; if it raises we treat the entry as suspect-typed and let
    # the fail-closed judge below block it — enforce() itself still NEVER raises.
    try:
        is_typed = isinstance(fields, dict) and "envelope" in fields
    except Exception:  # pragma: no cover — pathological dict-like only
        is_typed = True
    if not is_typed:
        return (False, "legacy_untyped", [])
    try:
        verdict, reasons = classify_fields(fields)
    except Exception as e:  # pragma: no cover — classify_fields never raises on a dict
        # Typed envelope we could not judge → FAIL-CLOSED (Captain's direction).
        verdict, reasons = "invalid", [f"enforce internal error: {type(e).__name__}"]
    if verdict == "invalid" and enforcement_enabled():
        ENFORCE_BLOCKED += 1
        return (True, verdict, reasons[:MAX_REASONS])
    return (False, verdict, reasons[:MAX_REASONS])


# --------------------------------------------------------------------------
# Envelope v2 (COG-1 §4 — cognitive-core-phase-1-contract-2026-07-20.md)
# --------------------------------------------------------------------------
# The module docstring above describes the v1 plane and is deliberately left
# untouched (together with the whole v1 body — validate() is BYTE-FROZEN per
# the COG-1 plan §4.1; the v2 red-team suite pins the region's exact bytes).
# v2 doc lives here.
#
# v2 is the outbox-relay envelope for domain-namespaced events (pilot:
# tasks.*). Version dispatch happens in classify_fields()/validate_any():
# an envelope carrying "schema_version" is judged by validate_v2(); one
# without it stays on the frozen v1 branch — so v1 traffic, its bounds and
# its red-team suite are untouched, and a v2 envelope can never be refused
# by v1's closed key set (§4.1).
#
# Field set (§4.2 — all fields, no sentinels): schema_version (exact
# literal), event_id ULID (v1 ULID_RE, \Z anchor), event_type
# <domain>.<name> resolved through the DOMAIN registry and NEVER a member of
# the central VALID_EVENT_TYPES (the M4 vocabulary fence), occurred_at /
# recorded_at in the single Phase-0 §3.3 UTC-second spelling (ordering
# between them is DESCRIPTIVE — two clocks, skew never quarantines),
# cabinet_id, scope_kind cabinet|lane|project with conditional
# lane_id/project_id (missing levels ABSENT — never null, never inferred,
# never sentinel: the Phase-0 SENTINEL_IDS vocabulary is refused on
# cabinet_id/lane_id/project_id), producer, correlation_id uuid4-hex (B2.1,
# framework/probes/correlation.py — adopted, not superseded), causation_id
# ULID or absent, idempotency_key (the outbox row's SQL-unique key),
# classification AS DATA ONLY (v1 TAINT_TIERS vocabulary; no join law —
# CG-9(d) stays Captain-gated), payload_schema <domain>/<name>@<version>
# resolved in the registry, and exactly one of payload / payload_ref
# (payload_ref is validated-shape-reserved for later phases).
#
# Size bound: MAX_V2_ENVELOPE_BYTES below is v2-only and PROVISIONAL per
# §4.3 — ratified by measurement before any enforce flip; the v2 suite
# asserts measured max fixture size ×5 ≤ bound (v1's 16384 is untouched).
# An over-bound envelope short-circuits registry/payload work (§6.1 poison
# ordering: "payload over bound" and "unresolvable payload_schema" are
# separate terminal classes).
#
# Fail directions (same two surfaces as v1): report_only() stays fail-open
# census; validate_v2() never raises and fails CLOSED (invalid) on any
# internal error — including a broken schema_registry import, which is LAZY
# (house precedent: etl-common.py:20-23, intake.py:229) so a registry defect
# can never break the v1 plane at import time. enforce()'s knobs
# (CABINET_ENVELOPE_ENFORCE / CABINET_ENVELOPE_REPORT) govern v2 through
# classify_fields() with no new switch — the §4.3 joint-knob blast radius is
# accepted and stated in the plan.

V2_SCHEMA_VERSION = "cabinet-envelope/v2"

V2_REQUIRED_KEYS = ("schema_version", "event_id", "event_type", "occurred_at",
                    "recorded_at", "cabinet_id", "scope_kind", "producer",
                    "correlation_id", "idempotency_key", "classification",
                    "payload_schema")
V2_CONDITIONAL_KEYS = ("lane_id", "project_id", "payload", "payload_ref")
V2_OPTIONAL_KEYS = ("causation_id",)
V2_ENVELOPE_KEYS = (frozenset(V2_REQUIRED_KEYS)
                    | frozenset(V2_CONDITIONAL_KEYS)
                    | frozenset(V2_OPTIONAL_KEYS))

# One scope dialect (foundry.md:52 = phase-0 contract §3.2 verbatim):
# cabinet → no levels; lane → lane_id; project → lane_id + project_id.
SCOPE_KINDS = ("cabinet", "lane", "project")
_SCOPE_LEVELS = {"cabinet": frozenset(),
                 "lane": frozenset({"lane_id"}),
                 "project": frozenset({"lane_id", "project_id"})}

# The Phase-0 sentinel vocabulary (framework/evolution/contracts.py
# SENTINEL_IDS — duplicated as a literal to keep this module import-light;
# the v2 suite pins equality so the two sets cannot drift).
V2_SENTINEL_IDS = frozenset({"*", "default", "global", "none", "null",
                             "unknown"})

MAX_V2_ENVELOPE_BYTES = 32768   # provisional per §4.3 — see section comment
MAX_PAYLOAD_REF_CHARS = 1024    # reserved reference locator bound

# Single UTC-second spelling (Phase-0 §3.3; regex per contracts.py:344-355).
_UTC_SECOND_RE = re.compile(
    r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
# uuid4-hex (B2.1 standard, framework/probes/correlation.py _CID_RE).
_CORRELATION_ID_RE = re.compile(r"\A[0-9a-f]{32}\Z")
# Domain-namespaced event type: <domain>.<name>, exactly one dot.
_EVENT_TYPE_RE = re.compile(
    r"\A[a-z][a-z0-9_-]{0,63}\.[a-z][a-z0-9_]{0,63}\Z")

# Lazily-cached central enum (M4 fence). Populated on first v2 validation;
# an import failure lands in validate_v2's belt → invalid (fail-closed for
# typed v2 traffic; the v1 plane never touches this).
_CENTRAL_EVENT_TYPES: Optional[frozenset] = None


def _central_event_types() -> frozenset:
    global _CENTRAL_EVENT_TYPES
    if _CENTRAL_EVENT_TYPES is None:
        from framework.events.emitter import VALID_EVENT_TYPES  # lazy import
        _CENTRAL_EVENT_TYPES = frozenset(VALID_EVENT_TYPES)
    return _CENTRAL_EVENT_TYPES


def _check_ulid(reasons: list[str], payload: dict, key: str, *,
                required: bool) -> None:
    if key not in payload:
        if required:
            reasons.append(f"missing required key: {key}")
        return
    v = payload[key]
    if not isinstance(v, str):
        reasons.append(f"{key}: expected str, got {type(v).__name__}")
    elif not ULID_RE.match(v):
        reasons.append(f"{key}: not ulid-shaped (26-char Crockford base32)")


def _check_utc_second(reasons: list[str], payload: dict, key: str) -> None:
    if key not in payload:
        reasons.append(f"missing required key: {key}")
        return
    v = payload[key]
    if not isinstance(v, str):
        reasons.append(f"{key}: expected str, got {type(v).__name__}")
        return
    if not _UTC_SECOND_RE.match(v):
        reasons.append(f"{key}: not the canonical UTC-second spelling "
                       f"(YYYY-MM-DDTHH:MM:SSZ)")
        return
    from datetime import datetime  # lazy: keeps the v1 import surface frozen
    try:
        datetime.fromisoformat(v[:-1] + "+00:00")
    except ValueError:
        reasons.append(f"{key}: not a real UTC datetime")


def _check_vocabulary(reasons: list[str], payload: dict) -> None:
    """event_type + payload_schema discipline via the domain registry (§4.4).
    Only called under the size bound (§6.1 poison ordering)."""
    et = payload.get("event_type")
    et_wellformed = False
    if "event_type" not in payload:
        reasons.append("missing required key: event_type")
    elif not isinstance(et, str):
        reasons.append(f"event_type: expected str, got {type(et).__name__}")
    elif not _EVENT_TYPE_RE.match(et):
        reasons.append("event_type: not <domain>.<name> shaped")
    elif et in _central_event_types():
        # domain vocabulary NEVER rides the central enum (M4 fence)
        reasons.append(f"event_type: {et[:64]!r} is a central "
                       f"VALID_EVENT_TYPES member — domain events resolve "
                       f"through the domain registry, never the central enum")
    else:
        et_wellformed = True

    ps = payload.get("payload_schema")
    if "payload_schema" not in payload:
        reasons.append("missing required key: payload_schema")
        return
    if not isinstance(ps, str):
        reasons.append(f"payload_schema: expected str, got {type(ps).__name__}")
        return
    from framework.triggers import schema_registry  # lazy import (see section comment)
    try:
        domain, name, version = schema_registry.parse_schema_id(ps)
    except schema_registry.SchemaIdError:
        reasons.append("payload_schema: not <domain>/<name>@<version> shaped")
        return
    try:
        schema = schema_registry.resolve(domain, name, version)
    except schema_registry.SchemaRegistryError:
        reasons.append("payload_schema: does not resolve in the domain "
                       "registry")
        return
    if et_wellformed and et not in schema.get(
            schema_registry.EVENT_TYPES_KEY, []):
        reasons.append("event_type: not declared by the resolved "
                       "payload_schema")
    inline = payload.get("payload")
    if isinstance(inline, dict):
        for issue in schema_registry.structural_issues(inline, schema)[:8]:
            at = "payload" + issue.path[1:] if issue.path.startswith("$") \
                else "payload"
            reasons.append(f"{at}: {issue.message}")


def validate_v2(payload: Any) -> tuple[bool, list[str]]:
    """Validate a v2 envelope (COG-1 §4.2). Returns (ok, reasons).
    NEVER raises.

    Same discipline as v1: STRICT closed key set (any key outside
    V2_ENVELOPE_KEYS is a violation); names-not-values reasons (key names,
    type names, lengths, bounds, and truncated closed-enum candidates only —
    never free-text values, never payload content). Fail direction: a v2
    envelope this validator cannot cleanly judge is INVALID (fail-closed for
    typed traffic — the belt below), while census reporting stays fail-open
    in report_only() exactly as for v1.
    """
    reasons: list[str] = []
    try:
        if not isinstance(payload, dict):
            return False, [f"envelope: expected dict, got {type(payload).__name__}"]

        unknown = sorted(str(k) for k in set(payload) - V2_ENVELOPE_KEYS)
        if unknown:
            reasons.append(f"unknown keys: {', '.join(k[:24] for k in unknown[:8])}")

        # schema_version — the exact literal, nothing else
        sv = payload.get("schema_version")
        if sv != V2_SCHEMA_VERSION:
            shown = sv[:32] if isinstance(sv, str) else type(sv).__name__
            reasons.append(f"schema_version: {shown!r} is not "
                           f"{V2_SCHEMA_VERSION!r}")

        # id discipline (§4.2 table — no third vocabulary)
        _check_ulid(reasons, payload, "event_id", required=True)
        _check_ulid(reasons, payload, "causation_id", required=False)
        if "correlation_id" not in payload:
            reasons.append("missing required key: correlation_id")
        else:
            cid = payload["correlation_id"]
            if not isinstance(cid, str):
                reasons.append(f"correlation_id: expected str, got "
                               f"{type(cid).__name__}")
            elif not _CORRELATION_ID_RE.match(cid):
                reasons.append("correlation_id: not uuid4-hex "
                               "(32 lowercase hex — B2.1 standard)")

        # timestamps — canonical spelling only; occurred_at ≤ recorded_at is
        # DESCRIPTIVE, never validated (two clocks — §4.2)
        _check_utc_second(reasons, payload, "occurred_at")
        _check_utc_second(reasons, payload, "recorded_at")

        # bounded identity strings
        _check_str(reasons, payload, "cabinet_id")
        _check_str(reasons, payload, "producer")
        _check_str(reasons, payload, "idempotency_key")

        # sentinel refusal on identity/scope ids (closed known set — safe to
        # echo; missing levels are ABSENT, never placeholders)
        for key in ("cabinet_id", "lane_id", "project_id"):
            v = payload.get(key)
            if isinstance(v, str) and v in V2_SENTINEL_IDS:
                reasons.append(f"{key}: sentinel id {v!r} refused "
                               f"(missing levels are absent, never sentinels)")

        # scope invariant (one scope dialect — §4.2)
        scope = payload.get("scope_kind")
        if "scope_kind" not in payload:
            reasons.append("missing required key: scope_kind")
        elif not isinstance(scope, str):
            reasons.append(f"scope_kind: expected str, got {type(scope).__name__}")
        elif scope not in SCOPE_KINDS:
            reasons.append(f"scope_kind: {scope[:32]!r} not in {list(SCOPE_KINDS)}")
        else:
            required_levels = _SCOPE_LEVELS[scope]
            for key in ("lane_id", "project_id"):
                if key in required_levels:
                    _check_str(reasons, payload, key)
                elif key in payload:
                    reasons.append(f"{key}: must be absent for scope_kind "
                                   f"{scope!r} (missing levels absent, "
                                   f"never inferred)")

        # classification — DATA ONLY, the v1 taint-tier vocabulary (§4.2;
        # no join law, no enforcement — CG-9(d) stays Captain-gated)
        cls = payload.get("classification")
        if "classification" not in payload:
            reasons.append("missing required key: classification")
        elif not isinstance(cls, str):
            reasons.append(f"classification: expected str, got "
                           f"{type(cls).__name__}")
        elif cls not in TAINT_TIERS:
            reasons.append(f"classification: {cls[:32]!r} not in "
                           f"{list(TAINT_TIERS)}")

        # payload xor payload_ref (exactly one — §4.2)
        has_payload = "payload" in payload
        has_ref = "payload_ref" in payload
        if has_payload and has_ref:
            reasons.append("payload/payload_ref: exactly one must be "
                           "present, both found")
        elif not has_payload and not has_ref:
            reasons.append("payload/payload_ref: exactly one must be "
                           "present, neither found")
        if has_ref:
            _check_str(reasons, payload, "payload_ref",
                       max_chars=MAX_PAYLOAD_REF_CHARS)
        if has_payload and not isinstance(payload.get("payload"), dict):
            reasons.append(f"payload: expected object, got "
                           f"{type(payload.get('payload')).__name__}")

        # v2 size bound FIRST, then registry/payload work (§6.1 poison
        # ordering: an over-bound envelope never burns registry cycles)
        size = envelope_bytes(payload)
        if size > MAX_V2_ENVELOPE_BYTES:
            reasons.append(f"envelope: {size} bytes exceeds "
                           f"{MAX_V2_ENVELOPE_BYTES}")
        else:
            _check_vocabulary(reasons, payload)

        reasons = reasons[:MAX_REASONS]
        return (len(reasons) == 0), reasons
    except Exception as e:  # belt: validate_v2() NEVER raises (fail-closed)
        return False, [f"validator internal error: {type(e).__name__}"][:MAX_REASONS]


def validate_any(payload: Any) -> tuple[bool, list[str]]:
    """The §4.1 VERSION-DISPATCHING doorway — producers and consumers judge
    an envelope here. NEVER raises.

    * dict carrying "schema_version" → validate_v2() (v2 branch)
    * anything else → the FROZEN v1 validate() (v1 branch; non-dict inputs
      keep v1's rejection semantics byte-for-byte)

    This is the entry task-events-watch.py's _valid_envelope re-points at
    (§3 disposition / §12.2 item 9 — the consumer wave): a consumer stuck on
    raw validate() would poison-ACK 100% of v2 entries at cutover.
    """
    try:
        is_v2 = isinstance(payload, dict) and "schema_version" in payload
    except Exception:  # pragma: no cover — pathological dict subclass only
        is_v2 = True   # suspect-typed → the stricter v2 judge (fail-closed)
    if is_v2:
        return validate_v2(payload)
    return validate(payload)
