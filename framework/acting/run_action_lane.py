#!/usr/bin/env python3.12
"""Capture→action lane runner — the live shell around action_lane's pure core.

Pivot of run_draft_lane.py per the 2026-07-03 Captain ruling: same singleton
lock, same ·pid· card + cabinet:action:<pid> store + consequence-ledger
proposal, ACTION payloads instead of reply drafts. Propose-only: every card
awaits Nate's approve/edit:/skip: through the (fixed) binder; approves execute
via framework.frontdoor.action_exec.

Signals v1 (read-only over the Plan-A vault, newest-first, fenced to a recency
window): open commitments (6-Commitments), fresh meeting notes (2-Meetings),
fresh decisions (5-Reflections/Decisions). The gather step is `as_of`-shaped so
the retrodiction harness can drive the same path with a historical clock.

No attention quota (Captain ruling 2026-07-03): every genuinely-needed action
is sent. MAX_PER_RUN is a technical anti-runaway bound only. The quality bar
lives in the proposer prompt (genuine need + SOLVE-shaped chains).

Run: python3.12 framework/acting/run_action_lane.py [--dry-run]
  --dry-run: gather + propose + print the would-be cards; no Telegram, no
  ledger, no Redis writes. The eyeball gate before the scheduled lane.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from framework.acting import action_lane, screenpipe_adapter as sa  # noqa: E402
from framework.acting.loop import proposal_event, proposal_id, pending_proposals  # noqa: E402
from framework.fidelity.consequence import emit_consequence, read_ledger  # noqa: E402
from framework.frontdoor import actfirst_canary  # noqa: E402  # cid-echo suppression (TI-7)


def covered_evidence_refs() -> frozenset:
    """Evidence refs carried by ANY prior action card (open or decided) — the
    stable dedup identity across runs (LLM subject slugs drift; refs don't)."""
    refs: set = set()
    try:
        for ev in read_ledger():
            if ev.get("action") == "action-card":
                refs.update(r for r in (ev.get("refs") or []) if isinstance(r, str))
    except Exception:
        pass   # fail-open here is safe: slug dedup still applies
    return frozenset(refs)

VAULT = Path.home() / "Obsidian" / "screenpipe-brain"
# Captain-ratified directions.yml (mission/instruments/bets/not_goals per lane) —
# injected into the proposer prompt + used to validate every card's direction_fit.
DIRECTIONS_PATH = Path(__file__).resolve().parents[2] / "instance" / "config" / "directions.yml"
LOCK_PATH = "/tmp/cabinet-action-lane.lock"
# Captain ruling 2026-07-03: NO attention quota — send every genuinely-needed
# action. MAX_PER_RUN is a technical anti-runaway bound only (a berserk LLM
# must not flood 20 cards in one tick), not a budget.
MAX_PER_RUN = 8
WINDOW_H = 72
LLM_MODEL = "claude-sonnet-4-6"
_lock_fh = None


def _acquire_lock() -> bool:
    global _lock_fh
    _lock_fh = open(LOCK_PATH, "w")
    try:
        fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _load_env() -> None:
    for env in (Path(__file__).resolve().parents[2] / "cabinet" / ".env",
                Path.home() / ".screenpipe" / "pipes" / "_shared" / ".env"):
        try:
            for line in env.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    v = v.strip().strip('"').strip("'")
                    # an EMPTY value never claims the key — cabinet/.env ships
                    # ANTHROPIC_API_KEY= blank (officers run on subscription)
                    # and must not shadow the real key in _shared/.env
                    if v:
                        os.environ.setdefault(k.strip(), v)
        except OSError:
            pass


def _redis(*args: str) -> str:
    host = os.environ.get("REDIS_HOST", "localhost")
    out = subprocess.run(["redis-cli", "-h", host, *args],
                         capture_output=True, text=True, timeout=10).stdout.strip()
    return "" if out in ("", "(nil)") else out


def load_directions() -> "dict | None":
    """Parse the Captain-ratified directions.yml (yaml.safe_load only) for
    injection into the proposer prompt + direction_fit validation. A missing or
    broken file degrades to None — the proposer then skips direction_fit
    enforcement rather than dropping every card (graceful degradation)."""
    try:
        import yaml
        data = yaml.safe_load(DIRECTIONS_PATH.read_text())
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _suppress_log(line: str) -> None:
    """Sink for the proposer's dedup/skip decisions — one line each to the
    launchd log so no drop is silent (SEC-4 RT-A12)."""
    print(line)


def _llm(system: str, user: str) -> str:
    """Raw-text Anthropic call (the core parses its own JSON). Key from env;
    never logged."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""
    body = {"model": LLM_MODEL, "max_tokens": 4096, "system": system,
            "messages": [{"role": "user", "content": user}]}
    r = subprocess.run(
        ["curl", "-s", "--max-time", "180", "https://api.anthropic.com/v1/messages",
         "-H", f"x-api-key: {api_key}",
         "-H", "anthropic-version: 2023-06-01",
         "-H", "content-type: application/json",
         "-d", json.dumps(body)],
        capture_output=True, text=True, timeout=185)
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return ""
    return "".join(c.get("text", "") for c in (d.get("content") or [])
                   if c.get("type") == "text")


# ---------------------------------------------------------------------------
# Signals (read-only vault gather; as_of-shaped for future replay)
#
# PRO-4 (2026-07-04): a PROFILE-driven section table. OPERATIONAL is the live
# lane's perception (commitments / meetings / decisions + product health / people
# radar / code) — it sees the field instead of ~3% of it. STRATEGIC is the
# grander-lane view (opportunities + all health + code + retro + directions),
# consumed by the weekly strategic lane (a later wave). FILE-ONLY BY CONTRACT:
# gather reads vault .md files (+ the directions config) and NEVER calls a live
# API — so the retrodiction/sim harness can replay the exact same gather at a
# historical as_of deterministically (the fencing the whole learning plane rests
# on). New sections (health.md, 3-People/_radar, 7-Opportunities) may be ABSENT
# until their scout/snapshot lanes land — every section degrades to empty, never
# an error. Excerpts are provenance-fenced (SEC-4 discipline: signal text is
# world-description, never instructions).
# ---------------------------------------------------------------------------

# (label, subpath, filenames, window_h, cap, chars, ff_filter, group_by_product)
#   filenames=None        → rglob every *.md under subpath (recency-windowed)
#   filenames=[...]        → only those basenames under subpath/*/ (per-product dirs)
#   window_h=None          → UNWINDOWED (all ages, still <= as_of — never leak future)
#   ff_filter={k: pred}    → keep a file only if its YAML head[k] satisfies pred(v)
#   group_by_product=True  → cap counts PRODUCTS (all their named files), not files
_Section = namedtuple(
    "_Section",
    "label subpath filenames window_h cap chars ff_filter group_by_product")


def _sec(label: str, subpath: str, *, filenames=None, window_h: "int | None" = WINDOW_H,
         cap: int = 5, chars: int = 700, ff_filter=None,
         group_by_product: bool = False) -> "_Section":
    return _Section(label, subpath, filenames, window_h, cap, chars, ff_filter,
                    group_by_product)


def _ff_truthy(v: Any) -> bool:
    return v is True or str(v).strip().lower() == "true"


def _ff_new_or_investigating(v: Any) -> bool:
    return str(v).strip().lower() in ("new", "investigating")


# Profiles are independent tables (so e.g. health carries the alert:true filter
# under OPERATIONAL but is unfiltered — "all health" — under STRATEGIC).
PROFILES = {
    "operational": [
        _sec("OPEN COMMITMENT", "6-Commitments", cap=8, chars=700),
        _sec("MEETING", "2-Meetings", cap=5, chars=1200),
        _sec("DECISION", "5-Reflections/Decisions", cap=4, chars=700),
        _sec("PRODUCT HEALTH", "9-Codebases", filenames=["health.md"],
             cap=3, chars=600, ff_filter={"alert": _ff_truthy}),
        _sec("PEOPLE", "3-People/_radar", cap=3, chars=500),
        _sec("CODE", "9-Codebases", filenames=["commits.md", "deployment.md"],
             cap=2, chars=800, group_by_product=True),
    ],
    "strategic": [
        _sec("OPPORTUNITY", "7-Opportunities", window_h=None, cap=6, chars=700,
             ff_filter={"status": _ff_new_or_investigating}),
        _sec("PRODUCT HEALTH", "9-Codebases", filenames=["health.md"],
             window_h=None, cap=8, chars=600),
        _sec("CODE", "9-Codebases", filenames=["commits.md", "deployment.md"],
             cap=2, chars=800, group_by_product=True),
        _sec("RETRO", "5-Reflections/Weekly-Trends", window_h=None, cap=1, chars=900),
    ],
}


def _read_frontmatter(text: str) -> dict:
    """Parse ONLY the leading `---`..`---` YAML head (yaml.safe_load, minimal
    line-parse fallback). Never executes anything — the head is data."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text or "", re.DOTALL)
    if not m:
        return {}
    block = m.group(1)
    try:
        import yaml
        d = yaml.safe_load(block)
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    out: dict = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _ff_match(p: Path, ff_filter: "dict | None") -> bool:
    if not ff_filter:
        return True
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    fm = _read_frontmatter(text)
    return all(pred(fm.get(key)) for key, pred in ff_filter.items())


def _mtime(p: Path) -> "dt.datetime | None":
    try:
        return dt.datetime.fromtimestamp(p.stat().st_mtime, tz=dt.timezone.utc)
    except OSError:
        return None


def _recent_files(folder: Path, *, as_of: dt.datetime, window_h: "int | None",
                  cap: int, ff_filter: "dict | None" = None) -> list:
    """Newest-first *.md under folder, fenced to (as_of - window_h, as_of].
    window_h=None drops the lower bound (unwindowed) but keeps the as_of ceiling
    so a replay never leaks a file newer than its clock. ff_filter (if any) is
    applied newest-first, reading only until `cap` matches are found."""
    if not folder.exists():
        return []
    lo = (as_of - dt.timedelta(hours=window_h)) if window_h is not None else None
    cands = []
    for p in folder.rglob("*.md"):
        if "_noise" in p.parts:
            continue
        m = _mtime(p)
        if m is None or m > as_of or (lo is not None and m < lo):
            continue
        cands.append((m, p))
    cands.sort(reverse=True)
    out = []
    for _, p in cands:
        if not _ff_match(p, ff_filter):
            continue
        out.append(p)
        if len(out) >= cap:
            break
    return out


def _named_files(root: Path, names: list, *, as_of: dt.datetime,
                 window_h: "int | None", cap: int, ff_filter: "dict | None" = None,
                 group_by_product: bool = False) -> list:
    """The named files (e.g. health.md, commits.md) under each product dir
    root/*/. group_by_product ⇒ cap counts PRODUCTS (newest-first by their newest
    matching file), each contributing all its named files; else cap counts files.
    Same as_of/window fencing + ff_filter as _recent_files."""
    if not root.exists():
        return []
    lo = (as_of - dt.timedelta(hours=window_h)) if window_h is not None else None
    found = []
    for prod in sorted(root.iterdir()):
        if not prod.is_dir():
            continue
        for name in names:
            p = prod / name
            if not p.exists():
                continue
            m = _mtime(p)
            if m is None or m > as_of or (lo is not None and m < lo):
                continue
            if not _ff_match(p, ff_filter):
                continue
            found.append((m, prod.name, p))
    found.sort(reverse=True)                      # newest first
    if not group_by_product:
        return [p for _, _, p in found[:cap]]
    accepted: list = []
    out = []
    for _, prodname, p in found:
        if prodname not in accepted:
            if len(accepted) >= cap:
                continue
            accepted.append(prodname)
        out.append(p)
    return out


def _excerpt(p: Path, chars: int) -> str:
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    # drop our own graph block + fences; the LLM needs prose, not plumbing
    text = re.sub(r"<!-- graph:links -->.*?<!-- /graph:links -->", "", text,
                  flags=re.DOTALL)
    return text.strip()[:chars]


def _relpath(p: Path, vault: Path) -> str:
    try:
        return str(p.relative_to(vault))
    except ValueError:
        return p.name


def _directions_block() -> str:
    """The Captain-ratified directions.yml, verbatim (STRATEGIC only) — read from
    the instance config, still file-only, no API."""
    try:
        txt = DIRECTIONS_PATH.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return ""
    return f"--- DIRECTIONS ref={DIRECTIONS_PATH.name} ---\n{txt[:2000]}" if txt else ""


def gather_signals(as_of: dt.datetime, *, window_h: int = WINDOW_H,
                   profile: str = "operational", vault: "Path | None" = None,
                   suppress_cids=frozenset()) -> str:
    """The fenced evidence bundle for a profile. FILE-ONLY (no API) so the sim
    harness replays it deterministically; v1 fencing = file-recency window ending
    at as_of (replay-grade content_ts fencing lands with the sim harness). New
    folders may be absent → their section is simply empty.

    ``suppress_cids`` drops any excerpt carrying one of OUR OWN acted correlation
    ids (an act→capture→act echo — TI-7); empty (the default) is a no-op, so the
    pre-flip lane and the sim harness are unchanged. The live lane passes
    ``actfirst_canary.own_acted_cids()`` once acting begins (wired at TI-3)."""
    vault = vault if vault is not None else VAULT
    sections = PROFILES.get(profile, PROFILES["operational"])
    parts = []                                    # (path, fenced-text) — path for logging
    for sec in sections:
        root = vault / sec.subpath
        # a section using the module default window honors the caller's override;
        # a section with its own window (incl. None = unwindowed) keeps it.
        eff_window = window_h if sec.window_h == WINDOW_H else sec.window_h
        if sec.filenames:
            files = _named_files(root, sec.filenames, as_of=as_of,
                                 window_h=eff_window, cap=sec.cap,
                                 ff_filter=sec.ff_filter,
                                 group_by_product=sec.group_by_product)
        else:
            files = _recent_files(root, as_of=as_of, window_h=eff_window,
                                  cap=sec.cap, ff_filter=sec.ff_filter)
        for p in files:
            body = _excerpt(p, sec.chars)
            if body:
                parts.append((p, f"--- {sec.label} ref={_relpath(p, vault)} ---\n{body}"))
    # TI-7 cid-echo suppression: never re-feed our own re-captured acts to the
    # proposer. No-op when suppress_cids is empty (pre-flip / sim replay).
    kept = actfirst_canary.filter_cid_echoes(
        parts, suppress_cids, text_of=lambda t: t[1], log=_suppress_log)
    blocks = [fenced for _, fenced in kept]
    if profile == "strategic":
        dirs = _directions_block()
        if dirs:
            blocks.append(dirs)
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Present
# ---------------------------------------------------------------------------

def _tg(text: str) -> None:
    # HQ CHAIR channel ONLY (Captain ruling 2026-07-03: cabinet cards go to the
    # HQ Chair bot, never the Screenpipe bot). TELEGRAM_COS_TOKEN is the Chair's
    # bot — the same one the cos-inbound poller polls, so replies BIND. There is
    # deliberately NO fallback to TELEGRAM_BOT_TOKEN: that is the Screenpipe
    # bot, whose updates never reach the binder (the first 5 live cards landed
    # there and could not be verdicted).
    token = os.environ.get("TELEGRAM_COS_TOKEN", "")
    chat = os.environ.get("CAPTAIN_TELEGRAM_ID", "")
    if not token or not chat:
        raise RuntimeError("telegram env missing (TELEGRAM_COS_TOKEN / CAPTAIN_TELEGRAM_ID)")
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    urllib.request.urlopen(
        urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                               data=data), timeout=20)


def _store_action(pid: str, prop: action_lane.ActionProposal, cid: str = "") -> None:
    rec = {"cid": cid, "lane": prop.lane, "subject": prop.subject,
           "situation": prop.situation,
           "steps": [{"kind": s.kind, "title": s.title, "payload": s.payload}
                     for s in prop.steps],
           "evidence": list(prop.evidence),
           "confidence": prop.confidence, "urgency": prop.urgency}
    _redis("SET", f"cabinet:action:{pid}", json.dumps(rec), "EX", "604800")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not _acquire_lock():
        print("done: another action-lane run holds the lock")
        return 0
    _load_env()

    now = dt.datetime.now(dt.timezone.utc)
    budget = MAX_PER_RUN

    signals = gather_signals(now)
    if not signals.strip():
        print("done: no fresh signals in window")
        return 0

    decided = set(sa.decided_subjects().keys())
    open_subjects = {  # any pending proposal's subject, action or draft
        (p.get("subject") or "") for p in pending_proposals() if isinstance(p, dict)}

    proposals = action_lane.propose_actions(
        signals, as_of=now.strftime("%Y-%m-%dT%H:%M:%SZ"), llm=_llm,
        decided_subjects=decided, open_subjects=open_subjects,
        budget_left=budget, covered_evidence=covered_evidence_refs(),
        directions=load_directions(), suppress_log=_suppress_log)

    if args.dry_run:
        print(f"DRY RUN — {len(proposals)} card(s) would present:\n")
        for p in proposals:
            prop_ev = proposal_event(actor={"kind": "officer", "id": "officer:cos"},
                                     lane=p.lane, subject=p.subject,
                                     ts=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                     action="action-card")
            print(action_lane.render_card(p, proposal_id(prop_ev)))
            print("\n" + "=" * 60 + "\n")
        return 0

    presented = 0
    actor = {"kind": "officer", "id": "officer:cos"}
    for p in proposals:
        ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # B2.1 cid (strategy-report corrected rec 2, 2026-07-03): without a
        # minted correlation id every card is unjoinable to probe outcomes and
        # lands unattributable — the wire the graduation engine starves without.
        from framework.probes import correlation
        cid = correlation.mint()
        prop_ev = proposal_event(actor=actor, lane=p.lane, subject=p.subject,
                                 ts=ts, action="action-card",
                                 refs=[correlation.ref_for(cid)] + list(p.evidence))
        # action_type stamping (graduation wire). Guarded by the shared enum:
        # only a mapping whose target EXISTS in classifier.ACTION_TYPES is
        # stamped, so no invalid type is ever emitted. task_create activates
        # automatically when the Captain applies the germline amendment
        # (docs/proposals/germline-amendment-task-create-2026-07-03.md);
        # until then creates stay unstamped exactly as before. Chains stamp
        # only when ALL steps agree on one type (honest cell accounting).
        at = action_lane.chain_action_type(p)
        if at:
            prop_ev["action_type"] = at
        pid = proposal_id(prop_ev)
        card = action_lane.render_card(p, pid)   # marker-stripped inside
        emit_consequence(**prop_ev)              # ledger FIRST (fail-closed order)
        _store_action(pid, p, cid=cid)
        _tg(card)
        presented += 1
        print(f"presented action card -> {p.subject} ({p.lane}, conf={p.confidence:.2f})")
    print(f"done: presented {presented} action card(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
