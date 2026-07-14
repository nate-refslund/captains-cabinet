"""framework.attention.advisor — the "Noticed" lane (onboarding design
2026-07-14 Phase 1): the advisor as an attention-item CLASS, not a subsystem.

One deterministic detector pass, run nightly and once at hatch (right after
genesis, so the first briefing can carry a Noticed section). Findings become
composer-shaped intake items of ``kind: advisory`` — the charter's
``advisory`` class routes them next-briefing ONLY (never ping-now, never a
quiet-hours floor class), so they inherit the gateway's quiet hours, terse
rendering, and feed journaling for free.

V1 DETECTORS — DETERMINISTIC ONLY, NO LLM (the design's own guard):

* ``detect_aging_drafts`` — draft outcome cards sitting unratified in
  ``instance/config/outcomes-proposed.yml`` for more than 7 days (read via
  ``framework.onboarding.genesis``; the file the mission compiler
  structurally never reads).
* ``detect_stack_gaps`` — a lane's repo profile (framework.onboarding.research,
  names only, never .env) names a store (neon / vercel) that the lane-CEO's
  ``cabinet/mcp-scope.yml`` grant lacks → the finding CARRIES the
  ready-to-apply scope-diff TEXT, computed READ-ONLY by
  ``framework.learning.self_proposal.compute_scope_diff`` (a loop can't edit
  its own authorizations — the Captain applies the line).

DEFERRED by design: the plugged-but-unused detector (no per-MCP-server usage
signal exists to diff against) and any LLM phrasing pass.

BUDGETS ARE CHARTER DATA (the advisory class ``budget:`` block —
``max_per_briefing``, ``cooldown_days``, ``max_open``), enforced here per
pass; every suppression is returned with its reason (no silent drops).
Emission state (per-finding-id last_emitted / open-closed) lives beside the
gateway's standing-card map under ``CABINET_ATTENTION_DIR`` (same seam as
framework.attention.gate) — NEVER under instance/config.

PROPOSE-ONLY BY CONSTRUCTION: this module writes exactly one file (its own
state JSON, atomic tmp+os.replace). It never touches outcomes.yml, posture,
launchd, or any germline path; the only activation path for anything it
notices is the Captain acting on the card.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_AGING_DRAFT_DAYS = 7          # detector (b) threshold — design §4 Phase 1
_STACK_STORES = ("neon", "vercel")   # detector (c): stores worth a grant nudge
# Fallbacks when the charter's advisory class carries no budget block —
# identical to charter-default.yml so a stripped charter behaves the same.
_DEFAULT_BUDGET = {"max_per_briefing": 3, "cooldown_days": 14, "max_open": 7}


def _utc_now_iso(now: str | None = None) -> str:
    return now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(ts) -> datetime | None:
    """Tolerant ISO-8601 parse (Z or offset). None on anything else — an
    unparseable timestamp is an honest absence, never a guessed age."""
    if not isinstance(ts, str) or not ts.strip():
        return None
    try:
        dt = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _age_days(ts, now: datetime) -> float | None:
    dt = _parse_iso(ts)
    return (now - dt).total_seconds() / 86400.0 if dt else None


# ---------------------------------------------------------------------------
# State — per-finding-id emission ledger under the attention dir (gate.py's
# CABINET_ATTENTION_DIR seam; never instance/config).
# ---------------------------------------------------------------------------
def _attention_dir() -> Path:
    return Path(os.environ.get("CABINET_ATTENTION_DIR") or
                os.path.expanduser("~/Library/Application Support/cabinet/attention"))


def _state_path() -> Path:
    return _attention_dir() / "advisor-state.json"


def load_state() -> dict:
    """The finding_id → {last_emitted, status, detector} map. Corrupt/absent
    → {} with a loud stderr line (a lost map re-notices sooner — annoyance,
    never silence; same failure posture as gate.load_standing)."""
    p = _state_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as e:
        print(f"[advisor] state at {p} unreadable ({e}) — treating as empty",
              file=sys.stderr)
        return {}


def save_state(state: dict) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(tmp, p)


# ---------------------------------------------------------------------------
# Detector (b) — aging drafts in outcomes-proposed.yml.
# ---------------------------------------------------------------------------
def detect_aging_drafts(root: Path | None = None, *, now: str | None = None,
                        max_age_days: int = _AGING_DRAFT_DAYS) -> list[dict]:
    """Draft cards unratified past ``max_age_days``. Age per row comes from
    the row's own ``proposed_at`` (the merge writer stamps it) else the
    document-level ``proposed_at`` (genesis's write path); rows with neither
    are skipped (honest absence). At most ONE finding — a summary card, not a
    nag per draft."""
    from framework.onboarding import genesis  # config reads live in onboarding

    doc = genesis.load_proposals_doc(root)
    rows = doc.get("outcomes")
    if not isinstance(rows, list):
        return []
    now_dt = _parse_iso(_utc_now_iso(now))
    doc_ts = doc.get("proposed_at")
    aging: list[tuple[str, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("status") != "draft" or row.get("captain_ratified"):
            continue
        age = _age_days(row.get("proposed_at") or doc_ts, now_dt)
        if age is not None and age > max_age_days:
            aging.append((str(row.get("id") or "?"), age))
    if not aging:
        return []
    oldest_id, oldest_age = max(aging, key=lambda t: t[1])
    return [{
        "id": "advisory-aging-drafts",
        "kind": "advisory",
        "detector": "aging-drafts",
        "evidence": (
            f"{len(aging)} draft outcome card(s) in {genesis.PROPOSALS_REL} "
            f"unratified for over {max_age_days}d "
            f"(oldest: {oldest_id}, {int(oldest_age)}d)"
        ),
        "action": (
            "Review each draft: ratify (move the row into "
            "instance/config/outcomes.yml with status: active + "
            "captain_ratified: true), edit it, or reject (delete the row — a "
            "decisions-ledger note beats silence)."
        ),
    }]


# ---------------------------------------------------------------------------
# Detector (c) — stack-gap: repo profile names a store the grant lacks.
# ---------------------------------------------------------------------------
def _local_repo_dir(lane: dict) -> Path | None:
    """The first lane repo entry that resolves to a local directory (URLs and
    absent paths are skipped — profiling is local-filesystem only)."""
    for entry in lane.get("repos") or []:
        text = str(entry).strip()
        if not text or "://" in text or text.startswith("git@"):
            continue
        p = Path(text).expanduser()
        if p.is_dir():
            return p
    return None


def detect_stack_gaps(root: Path | None = None, *, research_fn=None,
                      profiles: dict | None = None) -> list[dict]:
    """For each declared lane with a locally-resolvable repo, profile its
    stack (names only) and flag stores (neon / vercel) whose MCP grant is
    missing from the lane-CEO's ``cabinet/mcp-scope.yml`` entry. The finding
    carries the ready-to-apply scope-diff TEXT — the Captain applies it (a
    loop can't edit its own authorizations).

    Honest skips, never a false-positive nag: lanes without a local repo dir
    are skipped; a profiling error skips that lane; an unreadable/absent
    scope file yields NO findings (grant absence cannot be verified).

    Seams (tests): ``profiles`` maps slug → profile dict (bypasses research);
    ``research_fn(path)`` replaces framework.onboarding.research.research_repo.
    """
    from framework.learning import self_proposal
    from framework.onboarding import genesis, research

    answers = genesis.load_answers(root)
    lanes = [ln for ln in (answers.get("lanes") or []) if isinstance(ln, dict)]
    if not lanes:
        return []
    probe = research_fn or research.research_repo

    findings: list[dict] = []
    for lane in lanes:
        slug = str(lane.get("slug") or "").strip()
        if not slug:
            continue
        if profiles is not None:
            profile = profiles.get(slug)
        else:
            repo_dir = _local_repo_dir(lane)
            if repo_dir is None:
                continue
            try:
                profile = probe(str(repo_dir))
            except Exception:
                continue  # honest skip — a broken repo is not a scope gap
        if not isinstance(profile, dict):
            continue
        stack = profile.get("stack") or []
        needed = [s for s in _STACK_STORES
                  if s in stack or (s == "vercel" and "nextjs" in stack)]
        if not needed:
            continue
        officer = f"{slug}-ceo"
        missing, diffs = [], []
        for store in needed:
            d = self_proposal.compute_scope_diff(store, [officer],
                                                 cabinet_root=root)
            if not d.get("scope_readable"):
                # Scope file unreadable/absent: grant absence is unverifiable
                # — no nag exactly where trust is being earned.
                missing, diffs = [], []
                break
            if d.get("needed"):
                missing.append(store)
                diffs.append(d["diff_text"])
        if not missing:
            continue
        findings.append({
            "id": f"advisory-stack-gap-{slug}",
            "kind": "advisory",
            "detector": "stack-gap",
            "evidence": (
                f"lane '{slug}' repo profile names {', '.join(missing)} but "
                f"cabinet/mcp-scope.yml grants {officer} no such MCP"
            ),
            "action": (
                "If the lane should reach its own stores, apply the scope "
                "diff below to cabinet/mcp-scope.yml (GERMLINE — Captain "
                "applies; nothing here edits it)."
            ),
            "scope_diff": "\n\n".join(diffs),
        })
    return findings


# ---------------------------------------------------------------------------
# The pass — detect → charter budgets → state → intake items.
# ---------------------------------------------------------------------------
def _advisory_budget(charter: dict) -> dict:
    for c in charter.get("classes") or []:
        if isinstance(c, dict) and c.get("id") == "advisory":
            return {**_DEFAULT_BUDGET, **(c.get("budget") or {})}
    return dict(_DEFAULT_BUDGET)


def _item_of(finding: dict, ts: str) -> dict:
    summary = f"👁 Noticed: {finding['evidence']}\nACTION: {finding['action']}"
    if finding.get("scope_diff"):
        summary += f"\n```\n{finding['scope_diff'].rstrip()}\n```"
    return {
        "source": "attention-advisor",
        "kind": "advisory",
        "ts": ts,
        "urgency_tier": "batch",   # never ping-now — briefing-route only
        "payload": {"summary": summary},
        "context": {"why": (
            f"deterministic advisor detector '{finding['detector']}' "
            "(Noticed lane, Phase 1) — propose-only; nothing activates"
        )},
    }


def run_advisor(root: Path | None = None, *, now: str | None = None,
                charter: dict | None = None, findings: list[dict] | None = None,
                state: dict | None = None, save: bool = True) -> dict:
    """One detector pass under charter budgets.

    Returns ``{'items': [...], 'emitted': [ids], 'suppressed':
    [{'id','reason'}], 'closed': [ids], 'budget': {...}}``. Closure hygiene:
    an open advisory whose condition no longer fires is marked closed (the
    detectors are the source of truth; nothing stays open by inertia).

    Seams (tests): ``charter`` / ``findings`` / ``state`` inject the inputs;
    ``save=False`` skips the state write (pure dry pass)."""
    if charter is None:
        from framework.attention import charter as charter_mod
        charter = charter_mod.load_charter()
    budget = _advisory_budget(charter)
    ts = _utc_now_iso(now)
    now_dt = _parse_iso(ts)

    if findings is None:
        findings = detect_aging_drafts(root, now=ts) + detect_stack_gaps(root)
    st = load_state() if state is None else state

    current_ids = {f["id"] for f in findings}
    closed = []
    for fid, rec in st.items():
        if isinstance(rec, dict) and rec.get("status") == "open" \
                and fid not in current_ids:
            rec["status"] = "closed"
            rec["closed_at"] = ts
            closed.append(fid)

    open_count = sum(1 for rec in st.values()
                     if isinstance(rec, dict) and rec.get("status") == "open")
    items, emitted, suppressed = [], [], []
    for finding in findings:
        fid = finding["id"]
        rec = st.get(fid) if isinstance(st.get(fid), dict) else {}
        last = _parse_iso(rec.get("last_emitted"))
        if last is not None and budget["cooldown_days"] > 0 and \
                (now_dt - last).total_seconds() < budget["cooldown_days"] * 86400:
            suppressed.append({"id": fid, "reason":
                               f"cooldown ({budget['cooldown_days']}d)"})
            continue
        if len(emitted) >= budget["max_per_briefing"]:
            suppressed.append({"id": fid, "reason":
                               f"max_per_briefing ({budget['max_per_briefing']})"})
            continue
        is_reopen_or_new = rec.get("status") != "open"
        if is_reopen_or_new and open_count >= budget["max_open"]:
            suppressed.append({"id": fid, "reason":
                               f"max_open ({budget['max_open']})"})
            continue
        st[fid] = {"last_emitted": ts, "status": "open",
                   "detector": finding["detector"]}
        if is_reopen_or_new:
            open_count += 1
        emitted.append(fid)
        items.append(_item_of(finding, ts))

    if save:
        save_state(st)
    return {"items": items, "emitted": emitted, "suppressed": suppressed,
            "closed": closed, "budget": budget}


def main(argv: list[str] | None = None) -> int:  # pragma: no cover — thin CLI
    """CLI: one advisor pass (nightly launchd, or right after genesis at
    hatch — same pass either way, the flag only labels the run).

        python3.12 -m framework.attention.advisor [--at-hatch]

    Always exits 0 — the advisor is a nudge layer and NEVER gates a chain."""
    import argparse

    ap = argparse.ArgumentParser(prog="framework.attention.advisor")
    ap.add_argument("--at-hatch", action="store_true",
                    help="label this as the at-hatch pass (post-genesis); "
                         "the detector pass itself is identical")
    args = ap.parse_args(argv)
    try:
        result = run_advisor()
        result["run"] = "at-hatch" if args.at_hatch else "nightly"
        print(json.dumps(result, indent=2, default=str))
    except Exception as e:
        # Non-gating by contract: a broken advisor is a lost nudge, never a
        # broken hatch or self-wake loop.
        print(f"[advisor] pass failed ({e.__class__.__name__}: {e}) — "
              f"non-gating, exiting 0", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
