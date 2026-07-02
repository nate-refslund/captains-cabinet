"""framework.frontdoor.morning_synthesis — a front-door INTAKE SOURCE.

Pulls REAL current signals from the screenpipe brain and enqueues them as intake
items, so the Chair's send path weaves them into ONE unified message instead of
N separate pings. This is a "rewire" source per the committed architecture's pipe
disposition (docs/cabinet-architecture-cohesive-2026-06-22.md §5): screenpipe
provides the signal (System 1), the cabinet composes the single voice (System 2).

NOTHING here sends. It only enqueues to the durable intake; the one live send
stays in channel.send (allow_sends-gated). Signal gathering is best-effort — a
brain/capture hiccup yields fewer items, never a crash.
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess

from framework.acting import product_health
from framework.acting import screenpipe_adapter as sa
from framework.frontdoor import intake

# Repo root (…/framework/frontdoor/morning_synthesis.py → up 3). Used to locate
# the dated follow-ups reader without depending on the caller's cwd.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DUE_FOLLOWUPS_SH = os.path.join(_REPO_ROOT, "cabinet", "scripts", "due-followups.sh")

# ---------------------------------------------------------------------------
# OPERATIONAL-vs-CAPTAIN routing (2026-06-26, Nate's standing directive).
# WHY: deploy-health + Sentry error-health are RAW OPERATIONAL/MONITORING signals.
# Per Nate's repeated correction, every operational/error/monitoring alert routes
# to the CHAIR (cos) to triage — escalating to Nate ONLY if genuinely necessary —
# NOT straight onto his phone via the briefing. (This was the live source of the
# "sentry-step-polads: N unresolved errors in 24h" ping Nate kept flagging — it was
# the cabinet's OWN front-door synthesis surfacing Sentry, NOT a Sentry-native rule.)
# So those two sources are delivered as an OFFICER MESSAGE on the Chair's Redis
# trigger stream `cabinet:triggers:cos` (the same path pipe-health uses + the exact
# shape cabinet/scripts/lib/triggers.sh::trigger_send writes), and are NO LONGER
# enqueued into the Nate-bound front-door intake. The genuinely Captain-facing
# sources (awaiting-reply, owed commitments, dated follow-ups) stay in the intake.
# The Chair's post-tool-use hook + redis-trigger-channel MCP surface the trigger on
# its next turn; the Chair triages (gather-then-decide) and escalates only the
# genuinely-actionable. Reversible: flip _OPERATIONAL_SOURCES back into the intake.
_OPERATIONAL_SOURCES = {"sentry-health", "deploy-health"}
_CHAIR_OFFICER = "cos"
_CHAIR_STREAM = f"cabinet:triggers:{_CHAIR_OFFICER}"
_CHAIR_GROUP = f"officer-{_CHAIR_OFFICER}"


def notify_chair(message: str, *, sender: str = "frontdoor-synthesis") -> bool:
    """Deliver an OPERATIONAL alert to the Chair (cos) as an officer-stream message.

    Mirrors cabinet/scripts/lib/triggers.sh::trigger_send byte-for-byte so the
    redis-trigger-channel MCP + the Chair's post-tool-use hook surface it exactly
    like any officer→officer trigger: idempotent consumer-group create (MKSTREAM on
    the officer-cos group, NOT intake's frontdoor group), then XADD with the TWO
    fields trigger_read expects — {sender, message="[<utc>] From <sender>: <msg>"}.

    Implemented as a direct redis-cli subprocess (NOT intake._redis()) for two
    reasons the backend abstraction can't meet: (1) an officer trigger needs TWO
    stream fields, but backend.xadd writes only one; (2) the group is officer-cos,
    not intake's hardcoded 'frontdoor'. This matches pipe-health/check.py::notify_chair
    exactly (the proven sibling). Best-effort: returns True on enqueue, False
    otherwise; NEVER raises into the caller (a failed alert must not crash the
    briefing). REDIS_HOST/REDIS_PORT mirror intake + triggers.sh."""
    host = os.environ.get("REDIS_HOST", "redis")
    port = os.environ.get("REDIS_PORT", "6379")
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    payload = f"[{ts}] From {sender}: {message}"
    try:
        # Idempotent group create (MKSTREAM) — matches trigger_send; harmless if it
        # already exists (BUSYGROUP swallowed by the capture).
        subprocess.run(
            ["redis-cli", "-h", host, "-p", str(port),
             "XGROUP", "CREATE", _CHAIR_STREAM, _CHAIR_GROUP, "0", "MKSTREAM"],
            capture_output=True, text=True, timeout=10)
        r = subprocess.run(
            ["redis-cli", "-h", host, "-p", str(port),
             "XADD", _CHAIR_STREAM, "*", "sender", sender, "message", payload],
            capture_output=True, text=True, timeout=10)
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def _operational_summary(items: list[dict]) -> str:
    """Compose the operational items (sentry/deploy health) into ONE Chair-bound
    message body. Each item's payload.summary is the human line the source already
    built (e.g. 'Sentry — sentry-step-polads: 5 unresolved error(s) in 24h — …').
    A urgency_tier=='ping-now' item is flagged so the Chair can prioritize."""
    lines = ["OPERATIONAL HEALTH (route: triage + escalate to Nate only if needed):"]
    for it in items:
        summary = (it.get("payload") or {}).get("summary") or it.get("source", "?")
        tier = it.get("urgency_tier", "batch")
        flag = " [INCIDENT — ping-now]" if tier == "ping-now" else ""
        lines.append(f"• {summary}{flag}")
    return "\n".join(lines)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


# Cheap, no-LLM noise markers — obvious automated / service-desk / notification
# mail that never warrants a reply. This is a coarse pre-filter so the first
# unified message isn't polluted by bot mail; the ACCURATE filter is the
# should_nate_reply gate (screenpipe_adapter.gather), wired in as a follow-on.
_NOISE_MARKERS = (
    "you don't often get email", "kundeservice", "no-reply", "noreply",
    "do-not-reply", "nulstil din adgangskode", "reset your password",
    "nyhedsbrev", "newsletter", "unsubscribe", "verifikationskode",
    "verification code", "notification@", "notifications@",
)


def _looks_like_noise(person: str, snippet: str) -> bool:
    blob = f"{person} {snippet}".lower()
    return any(m in blob for m in _NOISE_MARKERS)


def awaiting_reply_items(*, hours: int = 72, limit: int = 6) -> list[dict]:
    """Real awaiting-reply threads → intake items (batch tier).

    Each item surfaces (not drafts) a thread that has no reply from Nate yet,
    with provenance. Obvious automated/service-desk mail is pre-filtered out.
    Best-effort: any gather failure → empty list.
    """
    try:
        threads = sa.find_threads(hours=hours) or []
    except Exception:
        threads = []

    items: list[dict] = []
    for t in threads:
        if len(items) >= limit:
            break
        if not isinstance(t, dict):
            continue
        # 1:1 only — Nate rarely replies to group/list threads (the bias the
        # should_nate_reply gate encodes). Restricting to direct threads keeps
        # the synthesis to where a reply is genuinely expected.
        if ((t.get("audience") or {}).get("kind") or "direct") in ("group", "list"):
            continue
        person = t.get("person") or "someone"
        last = ((t.get("last") or {}).get("text") or "").strip().replace("\n", " ")
        if _looks_like_noise(person, last):
            continue
        snippet = (last[:140] + "…") if len(last) > 140 else last
        summary = f"{person} is awaiting your reply"
        if snippet:
            summary += f" — “{snippet}”"
        items.append({
            "source": "awaiting-reply",
            "kind": "thread",
            "ts": _now_iso(),
            "urgency_tier": "batch",
            "payload": {"summary": summary},
            "context": {
                "why": "inbound thread, no reply from you yet",
                "person": person,
                "slug": t.get("slug"),
            },
        })
    return items


def commitment_items(*, commitments: list | None = None, today: str | None = None,
                     limit: int = 5) -> list[dict]:
    """Time-pressing commitments Nate OWES → intake items (batch tier).

    Surfaces only DATED, open, owed-by-Nate commitments whose due date is today
    or past (overdue + due-today) — the briefing is a time-pressing nudge
    surface; undated promises live in the ledger and don't need a daily ping.
    Most-overdue first (due asc), capped at ``limit``. Each item carries
    provenance (person + commitment_id). Best-effort: any gather failure → [].

    ``commitments`` / ``today`` are injectable for tests (no brain, no clock).
    """
    if commitments is None:
        try:
            commitments = sa.open_commitments(direction="owed_by_nate") or []
        except Exception:
            commitments = []
    today = today or _today()

    dated = [
        c for c in commitments
        if isinstance(c, dict)
        and (c.get("due") or "").strip()
        and (c.get("due") or "").strip() <= today
    ]
    # ISO date string sorts chronologically — most overdue first.
    dated.sort(key=lambda c: (c.get("due") or "").strip())

    items: list[dict] = []
    for c in dated:
        if len(items) >= limit:
            break
        text = (c.get("text") or "").strip().replace("\n", " ")
        if not text:
            continue
        due = (c.get("due") or "").strip()
        person = c.get("person") or "someone"
        snippet = (text[:140] + "…") if len(text) > 140 else text
        when = "overdue" if due < today else "due today"
        items.append({
            "source": "commitment",
            "kind": "owed-by-you",
            "ts": _now_iso(),
            "urgency_tier": "batch",
            "payload": {"summary": f"You owe {person}: {snippet} — {when} (was due {due})"},
            "context": {
                "why": "open commitment, no fulfillment detected yet",
                "person": person,
                "slug": c.get("slug"),
                "commitment_id": c.get("commitment_id"),
                "due": due,
            },
        })
    return items


def _deploy_apps() -> list[str]:
    """Monitored Vercel app names from the instance env (CABINET_DEPLOY_HEALTH_APPS,
    comma-separated). Empty/unset → no apps → deploy-health stays silent. Keeping
    the product names in instance env (set by the briefing wrapper) keeps THIS
    framework module product-agnostic."""
    raw = os.environ.get("CABINET_DEPLOY_HEALTH_APPS", "")
    return [a.strip() for a in raw.split(",") if a.strip()]


def deploy_health_items(*, apps: list | None = None) -> list[dict]:
    """Vercel deploy health → intake items, but ONLY when something is wrong.

    For each monitored app: surface an item if its latest deploy is ERROR/CANCELED
    (ping-now — the live build is broken) or there are recent failed/cancelled
    deploys (batch). Quiet when healthy — a briefing that says "all green" every
    night is noise. Apps come from the instance env (``_deploy_apps``); framework
    stays product-agnostic. Best-effort: a per-app failure skips that app, never
    crashes the briefing.

    ``apps`` is injectable for tests (no env, no network).
    """
    if apps is None:
        apps = _deploy_apps()

    items: list[dict] = []
    for app in apps:
        try:
            h = sa.deploy_health(app)
        except Exception:
            continue
        failed = h.get("failed") or []
        latest = h.get("latest_state")
        latest_bad = latest in ("ERROR", "CANCELED")
        if not failed and not latest_bad:
            continue  # healthy → stay silent

        if latest_bad:
            summary = f"Deploy health — {app}: latest deploy is {latest}"
            tier = "ping-now"
        else:
            summary = f"Deploy health — {app}: {len(failed)} recent failed/cancelled deploy(s)"
            tier = "batch"
        items.append({
            "source": "deploy-health",
            "kind": "vercel",
            "ts": _now_iso(),
            "urgency_tier": tier,
            "payload": {"summary": summary},
            "context": {
                "why": "monitored Vercel app",
                "app": app,
                "failed": len(failed),
                "latest_state": latest,
            },
        })
    return items


# A single Sentry issue with >= this many events in the 24h window reads as an
# active incident (prod is actively erroring) → ping-now; otherwise batch.
_INCIDENT_EVENTS = 1000


def _sentry_cfg() -> tuple[str, str]:
    return (os.environ.get("CABINET_SENTRY_ORG", "").strip(),
            os.environ.get("CABINET_SENTRY_PROJECT", "").strip())


def sentry_health_items(*, org: str | None = None, project: str | None = None,
                        health: dict | None = None) -> list[dict]:
    """Sentry error health → intake items, ONLY when there are unresolved errors.

    ping-now if any single issue is an active incident (>= _INCIDENT_EVENTS events
    in 24h — prod is actively erroring), else batch. Quiet when clean. Org/project
    come from the instance env (CABINET_SENTRY_ORG / CABINET_SENTRY_PROJECT) so this
    framework module stays product-agnostic. Best-effort: any failure → [].

    ``health`` is injectable for tests (no network).
    """
    if org is None:
        org = _sentry_cfg()[0]
    if project is None:
        project = _sentry_cfg()[1]
    if not org or not project:
        return []
    if health is None:
        try:
            health = product_health.sentry_health(org, project)
        except Exception:
            return []
    issues = (health or {}).get("issues") or []
    if not issues:
        return []
    top = max((int(i.get("events", 0) or 0) for i in issues), default=0)
    titles = ", ".join(f"{(i.get('title') or '')[:60]} ({i.get('events', 0)})"
                       for i in issues[:3])
    return [{
        "source": "sentry-health",
        "kind": "errors",
        "ts": _now_iso(),
        "urgency_tier": "ping-now" if top >= _INCIDENT_EVENTS else "batch",
        "payload": {"summary": f"Sentry — {project}: {len(issues)} unresolved error(s) in 24h — {titles}"},
        "context": {
            "why": "unresolved product errors (Sentry)",
            "project": project,
            "count": len(issues),
            "top_events": top,
        },
    }]


def _due_followups(script: str | None = None) -> list[dict]:
    """Run the dated follow-ups reader and return the DUE entries as objects.

    Shells out to ``cabinet/scripts/due-followups.sh --json`` (the single source
    of the "which entries are ripe" logic — date + status parsing lives THERE,
    not duplicated here). Returns the parsed JSON array (objects with id /
    check_from / entry). Best-effort: a missing script, non-zero exit, timeout,
    or unparseable output → ``[]`` (never raises into the briefing).

    ``script`` overrides the reader path for tests.
    """
    sh = script or _DUE_FOLLOWUPS_SH
    try:
        out = subprocess.run(
            [sh, "--json"],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except Exception:
        return []
    if out.returncode != 0:
        return []
    try:
        data = json.loads(out.stdout or "[]")
    except (ValueError, TypeError):
        return []
    return data if isinstance(data, list) else []


def followup_items(*, due: list[dict] | None = None) -> list[dict]:
    """Dated follow-ups whose check_from date has arrived → intake items.

    The register (``shared/interfaces/follow-ups.md``) holds dated, gather-then-
    decide follow-ups. When an entry's ``check_from`` is reached and it's still
    ``open``, it surfaces here so the briefing's "📌 Follow-ups due" content puts
    it in front of the Chair. We do NOT decide or nudge: the item carries the
    entry's own ``gather`` (verify-resolved query) + ``nudge_if`` (open
    condition) text so the Chair does gather-then-decide per its rule — verify
    whether it already resolved (brain + email) BEFORE any nudge. A resolved
    item must stay silent; only a genuinely-open one pings Nate.

    Batch tier (rides the next briefing's decision queue), unless the entry text
    itself is flagged time-critical (contains ``ping-now``) → ping-now. Each item
    carries the entry id for provenance and mark-done. Best-effort: reader failure
    → no items (``due`` is injectable for tests).
    """
    if due is None:
        due = _due_followups()

    items: list[dict] = []
    for d in due:
        if not isinstance(d, dict):
            continue
        entry = (d.get("entry") or "").strip()
        if not entry:
            continue
        fid = (d.get("id") or "").strip()

        # Pull the human subject = the 4th pipe field (after id | deadline |
        # check_from). Falls back to the id if the line isn't the expected shape.
        parts = [p.strip() for p in entry.split("|")]
        subject = parts[3] if len(parts) > 3 else (fid or entry)

        # The Chair needs the entry's own gather + nudge_if rule inline so the
        # gather-then-decide is self-contained in the surfaced item. Carry the
        # FULL entry text in the summary (it already reads as an instruction).
        summary = f"📌 Follow-up due — {subject} · {entry}"

        # Default batch (rides the next briefing). If the author marked the entry
        # time-critical, honor it as ping-now.
        tier = "ping-now" if "ping-now" in entry.lower() else "batch"

        items.append({
            "source": "follow-up",
            "kind": "dated-register",
            "ts": _now_iso(),
            "urgency_tier": tier,
            "payload": {"summary": summary},
            "context": {
                "why": "dated follow-up reached its check date — gather-then-decide before nudging",
                "followup_id": fid,
                "subject": subject,
            },
        })
    return items


def gather_items(*, hours: int = 72, limit: int = 6) -> list[dict]:
    """All synthesis items from every real source.

    Sources today: awaiting-reply 1:1 threads + time-pressing commitments Nate owes
    (overdue / due-today) + Vercel deploy-health (failed/broken builds) + Sentry
    error-health (unresolved prod errors) + dated follow-ups whose check_from date
    has arrived (the "📌 Follow-ups due" content — gather-then-decide rule carried
    inline). Each is best-effort + quiet when healthy.

    NOTE on routing (done in enqueue_synthesis, not here): the two OPERATIONAL
    sources (deploy-health, sentry-health — see _OPERATIONAL_SOURCES) are split off
    to the Chair's trigger stream for triage; only the Captain-facing sources are
    woven into the briefing the composer sends to Nate. gather_items itself still
    returns ALL sources (callers/tests that want the raw signal set are unaffected).
    PostHog is intentionally NOT wired as an alert source — the configured analytics
    project carries only pageview traffic, no error signal (see the cos source
    registry). Calendar stays out (no live feed).
    """
    items = awaiting_reply_items(hours=hours, limit=limit)
    items += commitment_items(limit=limit)
    items += deploy_health_items()
    items += sentry_health_items()
    items += followup_items()
    return items


def enqueue_synthesis(*, hours: int = 72, limit: int = 6) -> dict:
    """Gather real signals; route operational ones to the Chair and the rest to the
    Captain-bound intake.

    SPLIT ROUTING (2026-06-26, Nate's standing directive — see _OPERATIONAL_SOURCES):
    operational/monitoring signals (Sentry + deploy health) go to the Chair's trigger
    stream (cabinet:triggers:cos) for triage via notify_chair() — they are NO LONGER
    enqueued into the Nate-bound front-door intake. Everything else (awaiting-reply,
    owed commitments, dated follow-ups) is genuinely Captain-facing and still enqueues
    to the intake for the composed briefing. Still never sends to Nate directly; the
    intake's one live send stays in channel.send (allow_sends-gated).

    Returns {'enqueued': n, 'ids': [...], 'sources': [...], 'chair_routed': m,
    'chair_sources': [...], 'chair_delivered': bool} — 'enqueued' counts ONLY the
    Captain-bound intake items (back-compat: same meaning as before for those).
    """
    items = gather_items(hours=hours, limit=limit)
    operational = [it for it in items if it.get("source") in _OPERATIONAL_SOURCES]
    captain_items = [it for it in items if it.get("source") not in _OPERATIONAL_SOURCES]

    ids = [intake.enqueue(it) for it in captain_items]

    chair_delivered = True
    if operational:
        chair_delivered = notify_chair(_operational_summary(operational))

    return {
        "enqueued": len(ids),
        "ids": ids,
        "sources": sorted({it["source"] for it in captain_items}),
        "chair_routed": len(operational),
        "chair_sources": sorted({it["source"] for it in operational}),
        "chair_delivered": chair_delivered,
    }


if __name__ == "__main__":  # pragma: no cover — manual dev invocation
    import json
    print(json.dumps(enqueue_synthesis(), indent=2, default=str))
