"""B2.7 — Support outcome probe (replicates the B2.3 GitHub reference).

A read-only observer of the SUPPORT surface: it reads inbound support threads,
joins each back to the Cabinet PROPOSAL whose approved outbound started it (via
the B2.1 correlation-id), and records the RESULT — resolved / reopened — as a
schema-valid consequence outcome. It writes nothing to the mailbox/provider.
Same structure the fleet copies from ``probe_github``:

  - a PURE ``classify`` (deterministic status mapping — trivially testable),
  - an INJECTABLE client (real impl reads the provider over urllib; tests inject
    fixtures — a probe must NEVER hit the live API in a test),
  - ``run_probe`` orchestrating enabled-gate → join → freshness guard → emit
    through the B2.2 lib, ending with a healthcheck liveness ping.

The JOIN is the evidence plane (B2.1): an inbound reply is matched to its
proposal by the Resend header ``X-Cabinet-Proposal-Id`` (a full cid, preferred)
or — when the customer's client strips the custom header on reply — by the
``[CAB-<short8>]`` subject tag, whose 8-char SHORT is disambiguated against the
open proposals' short ids (a short shared by ≥2 proposals is AMBIGUOUS and does
NOT join — fail closed).

Resolution is Intercom-conservative: silence is success. No customer reply
within ``RESOLUTION_HOURS`` after the approved outbound → the thread resolved; a
customer reply landing AFTER that outbound reopened it; still inside the window →
not yet final (``unknown``, re-emitted next cycle). Confidence is ``medium`` —
thread-resolution is a softer signal than a deterministic deploy/merge read.

RT#3 and the silent-source guard are inherited from ``lib`` — an unattributable
thread emits nothing and credits no officer, and an empty inbox read while
outbound went out (or the provider still reports messages) becomes an honest
page, never a false clean zero.
"""
from __future__ import annotations

import os
import re
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

from framework.probes import correlation
from framework.probes import lib

SLUG = "probe-support"
CADENCE_S = 1800                # 30 min
RESOLUTION_HOURS = 72           # Intercom-conservative quiet window → resolved
ENABLED_ENV = "CABINET_PROBE_SUPPORT_ENABLED"

# ── SHIPS DISABLED ────────────────────────────────────────────────────────────
# This module is INERT until deliberately turned on. ``run_probe`` no-ops (emits
# nothing, touches no client, pings no healthcheck) unless it is told it is
# enabled — either the injected ``enabled=True`` (tests) or the env flag
# CABINET_PROBE_SUPPORT_ENABLED being truthy at runtime (deploy). Importing or
# even scheduling this file does nothing observable while the flag is unset; a
# disabled probe is NOT a failed probe, so it must never page.

# ── DEPLOY TEMPLATE (Nate-gated — NOT installed by building this file) ────────
# Built + tested now; going live is a deliberate deploy step (reads Nate's live
# support inbox) that needs THREE things, none done here:
#   1. a __main__ entry that builds the real ResendSupportClient, reads the
#      support mailbox(es) from config, and calls run_probe per mailbox — guarded
#      by BOTH CABINET_PROBES_ENABLED (fleet-wide) AND the ships-disabled flag
#      CABINET_PROBE_SUPPORT_ENABLED (this probe). It stays dark until the second
#      flag is explicitly set, even after the __main__ + plist land.
#   2. a services.yml row (promote kind → watchdog so generate-plists renders it):
#        - name: probe-support
#          label: com.cabinet.probe-support
#          kind: watchdog
#          command: python3.12 -m framework.probes.probe_support
#          schedule: { interval_s: 1800 }
#          expected: "healthchecks 'probe-support' pinged 30-min; /fail on silent inbox"
#   3. create the healthchecks 'probe-support' check (period 30m, grace) + assign
#      a channel — same as the F0.13 checks.
# Until all three land AND the flag is set, this module is import-only: nothing
# schedules it, nothing touches the live API.


# --- ships-disabled gate -----------------------------------------------------

def _is_enabled() -> bool:
    """True only when CABINET_PROBE_SUPPORT_ENABLED is explicitly truthy.
    Absent/empty/anything-else → disabled (the default)."""
    return os.environ.get(ENABLED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


# --- time parsing (pure) -----------------------------------------------------

_LONG_FRAC_RE = re.compile(r"^(.*\.\d{6})\d+([+-]\d{2}:?\d{2})?$")


def _parse(iso: str) -> datetime:
    """Tolerant ISO-8601 → timezone-aware UTC datetime.

    Handles the two shapes the provider emits: a trailing ``Z`` (→ ``+00:00``)
    and sub-microsecond fractional seconds (truncated to 6 digits, which
    fromisoformat accepts). A naive value is assumed UTC. Raises on an empty /
    unparseable string — the caller skips a thread with no usable timestamp
    rather than guessing."""
    s = (iso or "").strip()
    if not s:
        raise ValueError("empty timestamp")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    m = _LONG_FRAC_RE.match(s)
    if m:                                   # >6 fractional digits (e.g. ns) → µs
        s = m.group(1) + (m.group(2) or "")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# --- pure classification -----------------------------------------------------

def classify(*, outbound_at: str, customer_reply_at: str | None,
             now: datetime) -> tuple[str, str, str]:
    """Map a support thread's observed state to
    (canonical_status, probe_status, evidence).

    ok/resolved = the approved outbound closed it (no customer reply for the
    quiet window); failed/reopened = a customer reply landed AFTER that outbound;
    unknown/pending = still inside the window, not yet final (re-emitted next
    cycle). A reply timestamp that is not strictly after the outbound is the
    customer message we already answered — NOT a reopen."""
    out_dt = _parse(outbound_at)

    if customer_reply_at:
        rep_dt = _parse(customer_reply_at)
        if rep_dt > out_dt:                 # reopen supersedes any quiet window
            return ("failed", "reopened",
                    f"customer replied {customer_reply_at} after outbound {outbound_at}")

    elapsed_h = (now - out_dt).total_seconds() / 3600.0
    if elapsed_h >= RESOLUTION_HOURS:
        return ("ok", "resolved",
                f"no customer reply for {RESOLUTION_HOURS}h after outbound {outbound_at}")
    return ("unknown", "pending",
            f"within {RESOLUTION_HOURS}h resolution window (outbound {outbound_at})")


# --- correlation join (pure) -------------------------------------------------

def _short_index(rows: list | None) -> dict[str, set]:
    """``short8`` → {full cids} over every proposal-carrying row in the ledger.

    Used to expand a subject-tag SHORT (8 hex) back into the full cid the emit
    path needs. A short that maps to ≥2 distinct cids is AMBIGUOUS — the join
    must refuse it (fail closed) rather than credit an arbitrary proposal."""
    idx: dict[str, set] = {}
    for e in rows or []:
        if not isinstance(e, dict):
            continue
        cid = correlation.cid_from_refs(e.get("refs"))
        if cid:
            idx.setdefault(correlation.short(cid), set()).add(cid)
    return idx


def _header_cid(headers: Any) -> str | None:
    """The full cid from the Resend header (case-insensitive name), else None.
    The value MUST pass ``is_cid`` (exact 32-hex) so untrusted header text can't
    smuggle a malformed id past the join."""
    if not isinstance(headers, dict):
        return None
    want = correlation.RESEND_HEADER_KEY.lower()
    for k, v in headers.items():
        if isinstance(k, str) and k.lower() == want and isinstance(v, str):
            val = v.strip().lower()
            if correlation.is_cid(val):
                return val
    return None


def resolve_cid(thread: dict, short_index: dict) -> tuple[str | None, str]:
    """Recover the full cid for a support thread + HOW it was found.

    Header first (a full cid — deterministic), then the subject tag (an 8-char
    short, disambiguated against ``short_index``). Returns (None, reason) when
    unrecoverable: ``no-cid`` (no header, no tag), ``no-open-match`` (tag short
    matches no known proposal), ``ambiguous-short`` (tag short matches ≥2)."""
    cid = _header_cid(thread.get("headers"))
    if cid:
        return cid, "header"
    short = correlation.from_subject_tag(thread.get("subject") or "")
    if not short:
        return None, "no-cid"
    matches = short_index.get(short)
    if not matches:
        return None, "no-open-match"
    if len(matches) > 1:
        return None, "ambiguous-short"
    return next(iter(matches)), "subject-tag"


# --- injectable client (real impl reads the provider; NEVER invoked in tests)-

class ResendSupportClient:
    """Thin READ-ONLY Resend/inbox wrapper. All network lives in ``_get_json``
    (urllib GET, bearer auth, a fixed API host — no shell, no user-controlled
    URL). Tests inject a fake with the same surface; this real client is
    exercised only by a deployed probe, never in the build or the suite."""

    _API_BASE = "https://api.resend.com"

    def __init__(self, api_key_env: str = "RESEND_API_KEY", timeout: int = 20):
        self.api_key_env = api_key_env
        self.timeout = timeout

    def _get_json(self, path: str) -> Any:
        """GET {_API_BASE}{path} with the bearer key from the env. The key is
        read at call time and used only as an Authorization header — never
        logged or echoed. Fixed host + caller-fixed path (no interpolation of
        untrusted input) keeps this off any SSRF surface. Import-safe: any
        failure returns None so a deployed cycle degrades to 'could-not-observe'
        rather than raising."""
        import json
        key = os.environ.get(self.api_key_env, "")
        if not key:
            return None
        req = urllib.request.Request(
            self._API_BASE + path, method="GET",
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 — fixed https host
                body = resp.read()
            return json.loads(body) if body else None
        except Exception:  # noqa: BLE001 — a read failure is a silent source, not a crash
            return None

    def support_threads(self, mailbox: str) -> list[dict]:
        """The Cabinet support threads to classify: each is an approved-outbound
        thread carrying {headers, subject, outbound_at, customer_reply_at}. The
        deploy-side builder normalizes the provider payload into that shape;
        never run here."""
        raise NotImplementedError("deploy-side: normalize the provider payload")

    def outbound_activity(self, mailbox: str) -> bool:
        """Did an approved Cabinet outbound go out in the window — the
        independent 'work happened' signal (analog of local git commits in the
        GitHub probe). Deploy-side."""
        raise NotImplementedError("deploy-side: provider sent-message read")

    def provider_message_count(self, mailbox: str) -> int:
        """The provider's reported inbound message count — the yardstick the
        freshness guard checks the inbox read against. Deploy-side."""
        raise NotImplementedError("deploy-side: provider count read")


# --- orchestration -----------------------------------------------------------

def run_probe(
    *,
    mailbox: str,
    client: Any,
    rows: list | None = None,
    now: str | None = None,
    enabled: bool | None = None,
    emit: Callable[..., Any] = lib.emit_outcome,
    hc: Callable[..., Any] = lib.hc_ping,
) -> dict:
    """One probe cycle. Returns {enabled, fresh, emitted:[...], skipped:[...]}.

    SHIPS DISABLED: with ``enabled`` unset it reads CABINET_PROBE_SUPPORT_ENABLED;
    while disabled it no-ops (no client call, no emit, no ping) — a disabled probe
    is not a failed one. Tests pass ``enabled=True`` to exercise the body."""
    if enabled is None:
        enabled = _is_enabled()
    if not enabled:
        return {"enabled": False, "fresh": None, "emitted": [], "skipped": []}

    # Resolve the ledger ONCE — shared by the short-index and every emit call.
    if rows is None:
        from framework.fidelity.consequence import read_ledger
        rows = read_ledger(since=None)

    threads = client.support_threads(mailbox)
    outbound_went_out = bool(client.outbound_activity(mailbox))
    provider_count = client.provider_message_count(mailbox) or 0
    # Silent-source guard: outbound went out (we EXPECT resolvable threads) or the
    # provider still reports inbound messages, yet the inbox read came back empty
    # → the mailbox/provider read is silently failing. Page, emit nothing.
    activity_expected = outbound_went_out or provider_count > 0
    fresh = lib.freshness_guard(observed=threads, activity_expected=activity_expected,
                                source="support")
    if not fresh["fresh"]:
        hc(SLUG, fail=True)     # silent inbox while outbound went out — page, don't lie
        return {"enabled": True, "fresh": False, "reason": fresh["reason"],
                "emitted": [], "skipped": []}

    now_dt = _parse(now) if now else datetime.now(timezone.utc)
    short_index = _short_index(rows)
    emitted, skipped = [], []
    for th in threads:
        cid, how = resolve_cid(th, short_index)
        if not cid:
            skipped.append({"subject": th.get("subject"), "reason": how})
            continue
        outbound_at = th.get("outbound_at")
        if not outbound_at:
            skipped.append({"cid": cid, "reason": "no-outbound-ts"})
            continue
        status, probe_status, evidence = classify(
            outbound_at=outbound_at, customer_reply_at=th.get("customer_reply_at"),
            now=now_dt)
        ev = evidence if status != "unknown" else None   # unknown carries no evidence
        res = emit(cid=cid, status=status, probe_status=probe_status,
                   source="support", confidence="medium", evidence=ev, rows=rows)
        (emitted if res.get("emitted") else skipped).append(
            {"cid": cid, "status": status, "probe_status": probe_status, "how": how,
             **({} if res.get("emitted") else {"reason": res.get("reason")})})
    hc(SLUG)   # liveness
    return {"enabled": True, "fresh": True, "emitted": emitted, "skipped": skipped}
