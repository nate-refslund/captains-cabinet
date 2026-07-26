"""The rate table, the pricer, the transcript parser and the lane recorder.

Stdlib only (survival contract: this must work on a bare python3 with no site
packages, because it runs inside the Stop hook on every officer turn).

MICRODOLLARS everywhere. $1/MTok is exactly 1 microdollar/token, so a rate
expressed in $/MTok doubles as microdollars-per-token and the arithmetic stays
integer at the boundary.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import subprocess
from typing import Dict, Iterable, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# RATES — list price in $/MTok as (input, output), keyed by a substring of the
# model id. Order matters: the first key found in the model id wins, so put
# more specific families first.
#
# PROVENANCE: Anthropic published list pricing. This table is the SINGLE place
# a rate is written down in this repo; the two shell hooks that used to carry
# their own copies now call price() instead. When a new model ships, add a row
# here — do NOT add a branch anywhere else.
#
# Deliberately NOT in this table: long-context (>200K) premium tiers and any
# batch/priority discount. Both would need the request's actual context size
# and service tier, which the transcript does not reliably carry. Omitting the
# premium means this meter can still UNDER-report a 1M-context turn; that is a
# known, documented residual, recorded in docs/cost-metering.md rather than
# papered over with a guessed multiplier.
# ─────────────────────────────────────────────────────────────────────────────
RATES: Dict[str, Tuple[float, float]] = {
    "fable": (10.0, 50.0),
    "opus": (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku": (1.0, 5.0),
}

# Cache multipliers, applied to the model's INPUT rate. Published Anthropic
# prompt-caching pricing. These three constants are the fix for the shipped
# 5x mispricing — they are asserted by framework/cost/tests/test_meter.py.
MULT_CACHE_WRITE_5M = 1.25   # 5-minute TTL cache write
MULT_CACHE_WRITE_1H = 2.00   # 1-hour TTL cache write
MULT_CACHE_READ = 0.10       # cache hit

# Lanes that spend outside the Claude Code session transcript. Counting only —
# nothing in this module can refuse a call.
#   priced=True  → the lane returns token usage we can price with RATES.
#   priced=False → we count CALLS and vendor UNITS honestly and leave the
#                  dollar figure unset rather than inventing a rate. A lane
#                  showing "1,240 calls (unpriced)" is true; showing "$0.00"
#                  is a lie, and this meter exists because of a lie like that.
LANES: Dict[str, bool] = {
    "advisor": True,       # advisor-crew.ts → api.anthropic.com
    "api_direct": True,    # raw curl → api.anthropic.com (cron + hook callers)
    "subscription": True,  # `claude -p` headless: rides the Max pool, not a card
    "embeddings": False,   # voyage /v1/embeddings
    "rerank": False,       # voyage /v1/rerank
    "tts": False,          # elevenlabs /v1/text-to-speech
    "stt": False,          # elevenlabs /v1/speech-to-text
    "websearch": False,    # metered search MCPs (exa / brave / perplexity)
}

# A principal is an officer slug, or `svc:<service>` for the scheduled lanes
# that have no officer at all. Anything else is refused into "unattributed"
# rather than trusted: this string becomes a Redis FIELD NAME and reaches a
# redis-cli argv, and it arrives from an environment variable.
_PRINCIPAL_RE = re.compile(r"^(svc:)?[a-z0-9][a-z0-9._-]{0,63}$")
UNATTRIBUTED = "unattributed"


def safe_principal(name: Optional[str]) -> str:
    """Normalize an officer/service name into a Redis-field-safe slug.

    Never raises, never propagates an unvetted string. An empty, malformed or
    over-long name becomes ``unattributed`` — spend that we cannot attribute is
    still spend and must still be counted, just not against a wrong officer.
    """
    if not name:
        return UNATTRIBUTED
    slug = str(name).strip().lower()
    if slug in ("", "unknown", "none", "null"):
        return UNATTRIBUTED
    if not _PRINCIPAL_RE.match(slug):
        return UNATTRIBUTED
    return slug


def resolve_rate(model: Optional[str]) -> Tuple[float, float, str]:
    """(input_$/MTok, output_$/MTok, matched_key) for a model id.

    An unrecognized model resolves to the MOST EXPENSIVE known rate with the
    key ``"unknown"``. This is the deliberate direction: the shipped meter
    defaulted unknown models to Sonnet (the cheapest), so every model it failed
    to recognize was billed at a fifth of Opus.
    """
    m = (model or "").lower()
    for key, rate in RATES.items():
        if key in m:
            return rate[0], rate[1], key
    # PER-DIMENSION max, not the max of (input+output). A future row with a high
    # input rate and a low output rate would otherwise leave unknown models
    # resolving to some other family and under-billing input — the one direction
    # this module is not allowed to fail in.
    return (max(r[0] for r in RATES.values()),
            max(r[1] for r in RATES.values()),
            "unknown")


def price(
    model: Optional[str],
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_write_5m: int = 0,
    cache_write_1h: int = 0,
    cache_read: int = 0,
) -> int:
    """Cost of one API response, in microdollars (rounded to nearest micro)."""
    inp, out, _ = resolve_rate(model)
    micro = (
        int(input_tokens or 0) * inp
        + int(output_tokens or 0) * out
        + int(cache_write_5m or 0) * inp * MULT_CACHE_WRITE_5M
        + int(cache_write_1h or 0) * inp * MULT_CACHE_WRITE_1H
        + int(cache_read or 0) * inp * MULT_CACHE_READ
    )
    return int(round(micro))


@dataclasses.dataclass
class TranscriptSlice:
    """What one parse of a transcript slice found."""
    cost_micro: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write: int = 0
    cache_read: int = 0
    lines_read: int = 0          # new watermark: total lines seen in the file
    responses_billed: int = 0    # unique message.id priced
    duplicates_skipped: int = 0  # repeated message.id (one per content block)
    malformed_skipped: int = 0   # entries with unparseable token counts
    watermark_reset: bool = False  # file was shorter than the watermark
    models: Optional[Dict[str, int]] = None   # model -> responses billed
    # The FINAL billed response, kept per-turn rather than summed. The health
    # dashboard, list-officers.sh, org-health-audit.sh and the fw-a14 stop-guard
    # eval all read `cabinet:cost:tokens:<officer>` last_context_pct, which is a
    # property of the latest turn — summing it would report a context window
    # many times over 100%.
    last: Optional[Dict[str, object]] = None

    def __post_init__(self) -> None:
        if self.models is None:
            self.models = {}


def _usage_of(entry: dict) -> Optional[Tuple[str, str, dict]]:
    """(message_id, model, usage) for a billable assistant entry, else None."""
    if entry.get("type") != "assistant":
        return None
    msg = entry.get("message") or {}
    usage = msg.get("usage")
    if not isinstance(usage, dict):
        return None
    model = msg.get("model") or ""
    # `<synthetic>` entries are produced locally by the CLI (e.g. an interrupt
    # notice). They carry a usage block but no API call was made and nothing was
    # billed — pricing them would invent spend.
    if model == "<synthetic>":
        return None
    return msg.get("id") or "", model, usage


def parse_transcript(path: str, from_line: int = 0) -> TranscriptSlice:
    """Price every API response appended to a Claude Code transcript after
    ``from_line``, and return the new watermark.

    Two properties this function exists for, both of them bugs in the meter it
    replaces:

    WATERMARK — the Stop hook fires once per officer response, but a response
    contains one API call per tool round-trip. The old meter priced only the
    LAST assistant entry it could see, so a 30-tool-call turn was billed as
    one. Summing everything instead would double-count on the next Stop, so the
    caller persists ``lines_read`` and passes it back as ``from_line``.

    DEDUPE — the transcript records one assistant entry per CONTENT BLOCK, each
    repeating the same message-level usage. In a real 821-entry transcript only
    352 message ids were distinct; summing entries naively over-counted
    cache_read by 2.3x. Billing is per API response, so we dedupe by
    ``message.id``.
    """
    out = TranscriptSlice()
    try:
        fh = open(path, "r", errors="replace")
    except OSError:
        return out

    # TRUNCATION / REPLACEMENT RECOVERY. The watermark describes a specific
    # file; if the transcript is now SHORTER than the watermark it is not that
    # file any more (rotated, replaced, rebuilt). Without this the meter goes
    # permanently dark for that session: every later turn is skipped because
    # from_line can never be reached again, silently and forever.
    try:
        total_lines = sum(1 for _ in open(path, "r", errors="replace"))
    except OSError:
        total_lines = 0
    if from_line and total_lines < from_line:
        out.watermark_reset = True
        from_line = 0

    seen: set = set()
    with fh:
        for lineno, line in enumerate(fh, start=1):
            out.lines_read = lineno
            if lineno <= from_line:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(entry, dict):
                continue
            got = _usage_of(entry)
            if got is None:
                continue
            mid, model, usage = got
            if mid:
                if mid in seen:
                    out.duplicates_skipped += 1
                    continue
                seen.add(mid)

            # One malformed usage value must not wedge the session. Before this
            # guard a non-numeric token count raised out of the loop, the
            # watermark never advanced, and every subsequent Stop re-read the
            # same poison line — a silent permanent blackout for that officer.
            try:
                i = int(usage.get("input_tokens") or 0)
                o = int(usage.get("output_tokens") or 0)
                cr = int(usage.get("cache_read_input_tokens") or 0)
                cw_total = int(usage.get("cache_creation_input_tokens") or 0)
                cc = usage.get("cache_creation") or {}
                cw1h = int(cc.get("ephemeral_1h_input_tokens") or 0) if isinstance(cc, dict) else 0
                cw5m = int(cc.get("ephemeral_5m_input_tokens") or 0) if isinstance(cc, dict) else 0
            except (TypeError, ValueError):
                out.malformed_skipped += 1
                continue
            if cw1h + cw5m == 0 and cw_total:
                # Older transcripts carry no TTL split. Charge the 5m rate: it
                # is the lower of the two, and inventing 1h spend that may not
                # have happened is the one direction of error this module is
                # allowed to make, since the alternative is fabricating cost.
                cw5m = cw_total

            this_cost = price(model, i, o, cw5m, cw1h, cr)
            out.cost_micro += this_cost
            out.input_tokens += i
            out.output_tokens += o
            out.cache_write += cw5m + cw1h
            out.cache_read += cr
            out.responses_billed += 1
            _, _, key = resolve_rate(model)
            out.models[key] = out.models.get(key, 0) + 1
            out.last = {
                "input": i, "output": o, "cache_write": cw5m + cw1h,
                "cache_read": cr, "cost_micro": this_cost, "model": model or "unknown",
                "context_tokens": i + cr + cw5m + cw1h,
            }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Redis. Best-effort by contract: a metering failure must NEVER break the
# caller. Every call is argv-list (never a shell string) so a principal or lane
# name cannot become a command.
# ─────────────────────────────────────────────────────────────────────────────
def _redis_argv() -> list:
    return [
        "redis-cli",
        "-h", os.environ.get("REDIS_HOST", "127.0.0.1"),
        "-p", str(os.environ.get("REDIS_PORT", "6379")),
    ]


# redis-cli prints error replies on STDOUT and still exits 0. Treating rc as the
# only failure signal is how the spend gate once read a WRONGTYPE ledger as
# "$0 spent" (pre-tool-use.sh carries the same table for the same reason). Here
# it was worse: a failed HINCRBY looked like success, the watermark advanced,
# and the spend was gone with a green log line. A `requirepass` on Redis would
# have zeroed the whole meter fleet-wide while every Stop reported OK.
_ERR_PREFIXES = (
    "NOAUTH ", "NOPERM ", "WRONGTYPE ", "LOADING ", "ERR ", "BUSY ", "MISCONF ",
    "READONLY ", "MASTERDOWN ", "EXECABORT ", "CLUSTERDOWN ", "TRYAGAIN ",
    "CROSSSLOT ", "NOSCRIPT ", "NOREPLICAS ", "(error",
)


def _is_error_reply(s: str) -> bool:
    t = (s or "").lstrip()
    return any(t.startswith(p) for p in _ERR_PREFIXES)


def _redis(*args: str, timeout: float = 5.0) -> Optional[str]:
    try:
        cp = subprocess.run(
            _redis_argv() + [str(a) for a in args],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if cp.returncode != 0:
        return None
    out = (cp.stdout or "").strip()
    if _is_error_reply(out):
        return None
    return out


def _redis_atomic(commands: list, timeout: float = 5.0) -> bool:
    """Run a list of argv-lists inside MULTI/EXEC through ONE redis-cli.

    Three problems solved at once:
      * LATENCY — a metered turn used to spawn 10 redis-cli subprocesses, each
        with its own 5s timeout, so a Redis that accepts connections but never
        answers could stall the Stop hook for ~50s (at or past Claude Code's
        hook timeout). Now it is one subprocess and one budget.
      * ATOMICITY — a partial write (3 of 5 HINCRBYs landing) used to report
        failure, so the whole slice re-billed on the next Stop and
        double-counted the three that had succeeded.
      * ERROR VISIBILITY — every reply is inspected, not just the exit code.

    Values must not contain whitespace or quotes; every field name here is
    slug-validated and every value is an integer or a sanitized token.
    """
    if not commands:
        return True
    script = "MULTI\n" + "\n".join(" ".join(str(a) for a in c) for c in commands) + "\nEXEC\n"
    try:
        cp = subprocess.run(
            _redis_argv(), input=script, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if cp.returncode != 0:
        return False
    out = cp.stdout or ""
    # POSITIVE CONFIRMATION, not absence-of-error. Measured 2026-07-26:
    # `redis-cli` in stdin/pipe mode exits 0 with EMPTY STDOUT when the server
    # is unreachable — it prints "Could not connect" to STDERR for every command
    # and still returns 0. Checking rc and stdout-for-error-prefixes therefore
    # reported a total connection failure as a successful write, which would
    # advance the watermark and drop the spend. So: require MULTI's `OK`, one
    # `QUEUED` per command, and a clean stderr.
    if (cp.stderr or "").strip():
        return False
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if not lines or lines[0] != "OK":
        return False
    if sum(1 for ln in lines if ln == "QUEUED") != len(commands):
        return False
    for line in lines:
        if _is_error_reply(line):
            return False
    return True


def utc_date() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")


def daily_token_key(date: Optional[str] = None) -> str:
    """The officer/session ledger the spend gate reads."""
    return "cabinet:cost:tokens:daily:%s" % (date or utc_date())


def daily_lane_key(date: Optional[str] = None) -> str:
    """The lane ledger — every paid path that is NOT a Claude Code session.

    Deliberately a SEPARATE key from daily_token_key(): the spend gate sums
    ``*_cost_micro`` across the token hash, so folding lanes in there would
    silently change what a per-officer cap means for anyone who still runs one.
    Lanes are counted and reported, never charged against an officer's cap.
    """
    return "cabinet:cost:lanes:daily:%s" % (date or utc_date())


# Both ledgers outlive their day so a late reader still sees yesterday, and so
# the daily snapshot job can pick up a day it missed. 8 days.
_LEDGER_TTL_S = 691200


def record_lane(
    lane: str,
    principal: Optional[str] = None,
    cost_micro: Optional[int] = None,
    units: int = 0,
    calls: int = 1,
    date: Optional[str] = None,
) -> bool:
    """Count one paid non-session call. Returns True if the ledger was written.

    ``cost_micro=None`` means this vendor's price is not in RATES — we still
    record calls and units, and the daily line renders the lane as *unpriced*
    rather than as $0.00.
    """
    if lane not in LANES:
        return False
    who = safe_principal(principal)
    key = daily_lane_key(date)
    pairs = [
        ("%s_calls" % lane, int(calls or 0)),
        ("%s_units" % lane, int(units or 0)),
        ("%s__%s_calls" % (lane, who), int(calls or 0)),
    ]
    if cost_micro is not None:
        c = int(cost_micro)
        pairs.append(("%s_cost_micro" % lane, c))
        pairs.append(("%s__%s_cost_micro" % (lane, who), c))
    cmds = [["HINCRBY", key, field, str(val)] for field, val in pairs
            if not (val == 0 and field.endswith("_units"))]
    cmds.extend(_heartbeat_commands(key))
    cmds.append(["EXPIRE", key, str(_LEDGER_TTL_S)])
    ok = _redis_atomic(cmds)
    if not ok:
        # A metering failure must not break the caller, but it must not be
        # SILENT either. Without this line a week of unreachable Redis records
        # nothing and reads back as a week of zero spend — and with no cap left,
        # nothing else is looking at this ledger. stderr lands in the callers'
        # existing logs; no new surface is involved.
        _warn("cost-meter: lane %r write FAILED (redis unreachable or ledger "
              "unwritable) — %d call(s) NOT counted" % (lane, int(calls or 0)))
    return ok


def _warn(msg: str) -> None:
    try:
        import sys
        print(msg, file=sys.stderr)
    except Exception:
        pass


def _heartbeat_commands(key: str) -> list:
    """Stamp WHEN this ledger was last successfully written.

    The degenerate end of a spend ledger is indistinguishable from its healthy
    end: an empty hash means "nobody spent anything" and ALSO means "the meter
    has been dead for a week". Since the Captain removed the caps (2026-07-26)
    nothing reads this ledger to gate on, so a dead meter had no consequence and
    no symptom. A last-written stamp makes the difference OBSERVABLE to anyone
    who reads the ledger — it decides nothing and interrupts nobody.
    """
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc)
    return [
        ["HSET", key, "meter_last_ok", now.strftime("%Y-%m-%dT%H:%M:%SZ")],
        ["HINCRBY", key, "meter_writes", "1"],
    ]


def record_session_turn(
    principal: Optional[str],
    slice_: TranscriptSlice,
    project: Optional[str] = None,
    date: Optional[str] = None,
) -> bool:
    """Add a parsed transcript slice to the officer ledger the spend gate reads.

    Field shape is unchanged from the hook this replaces (FW-072 pool mode):
    ``<officer>_<dim>``, or ``<officer>_<project>_<dim>`` when a project is set.
    """
    if slice_.responses_billed == 0:
        return True  # nothing new since the last watermark; not a failure
    who = safe_principal(principal)
    if who == UNATTRIBUTED:
        return False
    prefix = who
    if project:
        proj = safe_principal(project)
        if proj != UNATTRIBUTED:
            prefix = "%s_%s" % (who, proj)
    key = daily_token_key(date)
    dims = (
        ("input", slice_.input_tokens),
        ("output", slice_.output_tokens),
        ("cache_write", slice_.cache_write),
        ("cache_read", slice_.cache_read),
        ("cost_micro", slice_.cost_micro),
    )
    cmds = [["HINCRBY", key, "%s_%s" % (prefix, dim), str(int(val))] for dim, val in dims]
    cmds.extend(_heartbeat_commands(key))
    cmds.append(["EXPIRE", key, str(_LEDGER_TTL_S)])
    cmds.extend(_last_turn_commands(who, slice_))
    # One MULTI/EXEC: either the whole turn lands or none of it does, so a
    # partial write can never make the caller re-bill the half that succeeded.
    return _redis_atomic(cmds)


_MODEL_SAFE_RE = re.compile(r"[^A-Za-z0-9._:@-]")


def _last_turn_commands(principal: str, slice_: TranscriptSlice,
                        context_window: Optional[int] = None) -> list:
    """Commands refreshing ``cabinet:cost:tokens:<officer>`` — LATEST-turn snapshot.

    Read by the health dashboard, list-officers.sh, org-health-audit.sh and the
    fw-a14 stop-guard eval. Per-turn, never cumulative (see TranscriptSlice.last).
    """
    last = slice_.last
    if not last:
        return []
    who = safe_principal(principal)
    if who == UNATTRIBUTED:
        return []
    try:
        window = int(context_window or os.environ.get("CONTEXT_WINDOW_SIZE") or 1000000)
    except (TypeError, ValueError):
        window = 1000000
    ctx = int(last.get("context_tokens") or 0)
    pct = (ctx * 100 // window) if window > 0 else 0
    import datetime as _dt
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # A whitespace or newline in the model string would desync every line-pair
    # HGETALL parser downstream, including this module's own hgetall().
    model = _MODEL_SAFE_RE.sub("", str(last.get("model", "unknown")))[:64] or "unknown"
    k = "cabinet:cost:tokens:%s" % who
    return [
        ["HSET", k,
         "last_input", str(last.get("input", 0)),
         "last_output", str(last.get("output", 0)),
         "last_cache_write", str(last.get("cache_write", 0)),
         "last_cache_read", str(last.get("cache_read", 0)),
         "last_cost_micro", str(last.get("cost_micro", 0)),
         "last_model", model,
         "last_context_tokens", str(ctx),
         "last_context_pct", str(pct),
         "last_updated", stamp],
        ["EXPIRE", k, "86400"],
    ]


def watermark_key(session_id: str) -> Optional[str]:
    """Redis key for a session's watermark, or None if the id is unusable.

    A caller that lets the literal ``unknown`` through would collapse EVERY such
    session onto one shared counter, where a long transcript's high watermark
    silently suppresses billing for a short one.
    """
    sid = safe_principal(session_id)
    if sid == UNATTRIBUTED:
        return None
    return "cabinet:cost:wm:%s" % sid


def read_watermark(session_id: str) -> int:
    key = watermark_key(session_id)
    if key is None:
        return 0
    v = _redis("GET", key)
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return 0


def write_watermark(session_id: str, lines: int) -> bool:
    key = watermark_key(session_id)
    if key is None:
        return False
    # TTL matches the ledger (8d), not 48h: an expired watermark re-bills the
    # whole transcript from line 0. That is an OVER-count — the safe direction
    # for a watch — but a needless one.
    return _redis("SET", key, str(int(lines)), "EX", str(_LEDGER_TTL_S)) is not None


def hgetall(key: str) -> Optional[Dict[str, str]]:
    """HGETALL as a dict, or None when Redis is NOT OBSERVABLE.

    None and {} are different answers and callers must keep them apart: {} is
    "the ledger exists and is empty" (an affirmative observation — possibly a
    broken meter), None is "we could not look" (no conclusion available).
    """
    out = _redis("HGETALL", key)
    if out is None:
        return None
    fields: Dict[str, str] = {}
    lines = [ln for ln in out.split("\n") if ln != ""]
    for i in range(0, len(lines) - 1, 2):
        fields[lines[i].strip()] = lines[i + 1].strip()
    return fields


def sum_cost_micro(fields: Iterable[str], hash_: Dict[str, str], suffix: str = "_cost_micro") -> int:
    total = 0
    for f in fields:
        if f.endswith(suffix):
            try:
                total += int(hash_.get(f, "0"))
            except (TypeError, ValueError):
                continue
    return total
