"""framework.attention.situations — the derived per-situation status view.

THE spine of the war-room (attention-gateway spec §4.2, command-center
proposal 2026-07-10 §2): per ``situation_key`` one folded status —

    open → surfaced → pending → acted/decided → verified/resolved → dormant

— built by folding stores that ALL already have tested readers:

  * consequence ledger  (framework.fidelity.consequence.read_ledger)
      proposal rows (open / decided / expired), ``acted:*`` world rows,
      outcome + review enrichment.
  * undo journal        (framework.attention.acted_overlay.load_journal_rows)
      reversal state — a Captain-REVERSED act makes its situation LIVE again.
  * feed journal        (framework.attention.feed.feed_since)
      sends/edits (surfaced state, standing message id, last_surfaced_at)
      and ``closure`` rows (H2 — the closure VERB).
  * standing-card map   (framework.attention.gate.load_standing)
      situation_key → telegram message id.

DERIVED AND REBUILDABLE, never a store of record: delete nothing, write
nothing — every call re-folds the journals. Loaders are injectable so the
replay/sim harness and tests drive the fold deterministically.

H5 EXPIRY RE-TYPE (Captain field-test law, stay-live-until-acted; command
center §5 H5): a ledger ``decision == "expired"`` row is NOT a closure here.
The emitters (germline acting lanes) keep writing expire rows unchanged; this
view RE-TYPES them at fold time into DEMOTIONS — the situation stays live and
descends the presentation ``demote_path`` (queue.py owns the tiers). Only a
Captain VERB (approve / edit / skip via the binder) or WORLD-PROOF (an
``acted:*`` row standing un-reversed, or an explicit ``closure`` feed row)
closes a situation. A situation demoted past the end of the path parks as
``dormant`` — still counted in the census, never deleted.

Ref TAGS (free strings in ledger ``refs``, same pattern as ``lesson:<ref>``):
  deadline:<ISO>       → why_now.deadline_iso (the ONLY thing that can make a
                         Decisions-shelf clock — a real timestamp, never prose)
  kind:<enum>          → decision-card kind override (germline-handback, …)
  harm:<class>         → harm_class override (external_deadline | value_decay)
  leverage:<int>       → blocked work-graph descendants (until world P5 lands)
These carry NO identity (canonical_refs does not extract them) — they are
payload, not keys, and an attacker string in captured content cannot mint one
into an existing situation without already sharing its canonical refs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from framework.attention.situation import canonical_refs, situation_key

# Fold states, in lifecycle order (spec §4.2).
STATES = ("open", "surfaced", "pending", "acted", "decided", "resolved", "dormant")

# States the war-room census counts as LIVE demand on the Captain.
LIVE_STATES = frozenset({"open", "surfaced", "pending"})

# The presentation decay ladder (decision-card contract §1 expiry.demote_path).
# Charter may override per class; this is the framework default.
DEMOTE_PATH = ("ping-now", "standing-card", "briefing", "weekly-rollup",
               "muted+parked")

# Demotions at/past this index park the situation (dormant — census-only).
_PARK_TIER = len(DEMOTE_PATH) - 1

_CAPTAIN_DECISIONS = frozenset({"approve", "edit", "skip"})


# ---------------------------------------------------------------------------
# Ref-tag parsing (payload tags — never identity)
# ---------------------------------------------------------------------------

def _tag(refs: Iterable, prefix: str) -> Optional[str]:
    """Last ``<prefix>:<value>`` tag among refs, or None. Last wins so a
    superseding row can re-stamp a tag."""
    val = None
    for r in refs or ():
        s = str(r)
        if s.startswith(prefix + ":"):
            v = s[len(prefix) + 1:].strip()
            if v:
                val = v
    return val


def parse_iso(s) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def deadline_of(refs: Iterable) -> Optional[str]:
    """A REAL ISO deadline from a ``deadline:`` ref tag, or None. Unparseable
    values are dropped (a prose 'deadline:today' can never mint a clock)."""
    raw = _tag(refs, "deadline")
    return raw if raw and parse_iso(raw) else None


def leverage_of(refs: Iterable) -> int:
    raw = _tag(refs, "leverage")
    try:
        return max(0, int(raw)) if raw else 0
    except ValueError:
        return 0


# ---------------------------------------------------------------------------
# Default loaders (all tested elsewhere; injectable here)
# ---------------------------------------------------------------------------

def _default_ledger(since):
    from framework.fidelity.consequence import read_ledger
    return read_ledger(since=since)


def _default_journal():
    from framework.attention.acted_overlay import load_journal_rows
    return load_journal_rows()


def _default_feed():
    from framework.attention import feed
    rows, _cursor = feed.feed_since(0, max_n=None)
    return rows


def _default_standing():
    from framework.attention.gate import load_standing
    return load_standing()


# ---------------------------------------------------------------------------
# The fold
# ---------------------------------------------------------------------------

def _new_situation(key: str) -> dict:
    return {
        "key": key, "aliases": [key], "refs": [], "subject": "", "lane": None,
        "state": "open", "live": True, "demotions": 0,
        "open_pids": [], "pid": None,
        "created_ts": "", "last_ts": "",
        "last_surfaced_at": None, "standing_message_id": None,
        "class_id": None, "urgency": None,
        "deadline_iso": None, "harm_class": None, "blocked_leverage": 0,
        "kind": None, "filed_by": None, "actions": [],
        "counts": {"proposals": 0, "expiries": 0, "decided": 0,
                   "acted": 0, "sends": 0, "closures": 0},
        # fold scratch (stripped before return)
        "_decided_ts": "", "_acted_ts": "", "_closed_ts": "",
        "_reversed": False, "_open_ts": "",
    }


def _key_of_row(row: dict) -> str:
    refs = [r for r in (row.get("refs") or []) if isinstance(r, str)]
    return situation_key(refs, str(row.get("subject") or ""))


def _fold_ledger_row(sit: dict, row: dict) -> None:
    ts = str(row.get("ts") or "")
    sit["last_ts"] = max(sit["last_ts"], ts)
    sit["created_ts"] = min(filter(None, [sit["created_ts"], ts]), default=ts)
    refs = [r for r in (row.get("refs") or []) if isinstance(r, str)]
    for ref in sorted(canonical_refs(refs)):
        if ref not in sit["refs"]:
            sit["refs"].append(ref)
    if row.get("subject"):
        sit["subject"] = str(row["subject"])
    if row.get("lane"):
        sit["lane"] = str(row["lane"])
    action = str(row.get("action") or "")
    if action and action not in sit["actions"]:
        sit["actions"].append(action)
    actor = row.get("actor") or {}
    if actor.get("id"):
        sit["filed_by"] = f"{actor.get('kind', 'officer')}:{actor['id']}"

    # payload tags (last write wins across rows — folded in ts order)
    dl = deadline_of(refs)
    if dl:
        sit["deadline_iso"] = dl
    harm = _tag(refs, "harm")
    if harm in ("external_deadline", "value_decay", "none"):
        sit["harm_class"] = harm
    lev = leverage_of(refs)
    if lev:
        sit["blocked_leverage"] = max(sit["blocked_leverage"], lev)
    kind_tag = _tag(refs, "kind")
    if kind_tag:
        sit["kind"] = kind_tag

    if action.startswith("acted:"):
        sit["counts"]["acted"] += 1
        sit["_acted_ts"] = max(sit["_acted_ts"], ts)
        return

    prop = row.get("proposal")
    if not isinstance(prop, dict) and "outcome" in row:
        # A proposal-less outcome row is a RECORD (e.g. the H6 estate-triage
        # row, probe receipts) — never live demand on the Captain. Folds as
        # closed unless a real proposal on the same situation says otherwise.
        sit["_closed_ts"] = max(sit["_closed_ts"], ts)
        return
    if isinstance(prop, dict):
        decision = prop.get("decision")
        if decision is None and "outcome" not in row:
            sit["counts"]["proposals"] += 1
            from framework.acting.loop import proposal_id
            pid = proposal_id(row)
            if pid not in sit["open_pids"]:
                sit["open_pids"].append(pid)
            sit["_open_ts"] = max(sit["_open_ts"], ts)
            if not sit["urgency"]:
                sit["urgency"] = None  # urgency is not a ledger field; queue stamps it
        elif decision == "expired":
            # H5 RE-TYPE: expiry is a DEMOTION (routing), never a closure.
            sit["counts"]["expiries"] += 1
            sit["demotions"] += 1
        elif decision in _CAPTAIN_DECISIONS:
            sit["counts"]["decided"] += 1
            sit["_decided_ts"] = max(sit["_decided_ts"],
                                     str(prop.get("decided_at") or ts))


def _fold_feed_row(sit: dict, row: dict) -> None:
    kind = str(row.get("kind") or "")
    ts = str(row.get("ts") or "")
    if row.get("direction") == "out":
        sit["counts"]["sends"] += 1
        if not sit["last_surfaced_at"] or ts > sit["last_surfaced_at"]:
            sit["last_surfaced_at"] = ts
        mid = row.get("telegram_message_id")
        if mid is not None:
            sit["standing_message_id"] = mid
        if kind and sit["class_id"] is None:
            sit["class_id"] = kind
    elif kind == "closure":
        # H2: the closure VERB — a journaled world-proof/Captain resolution.
        sit["counts"]["closures"] += 1
        sit["_closed_ts"] = max(sit["_closed_ts"], ts)


def _finalize(sit: dict, reversed_refs: frozenset) -> dict:
    """Resolve the folded scratch into the ONE lifecycle state."""
    refs = frozenset(sit["refs"])
    reversed_hit = bool(refs & reversed_refs)
    open_pids = sit["open_pids"]
    surfaced = bool(sit["last_surfaced_at"] or sit["standing_message_id"])

    closed_ts = sit["_closed_ts"]
    decided_ts = sit["_decided_ts"]
    acted_ts = sit["_acted_ts"]
    open_ts = sit["_open_ts"]

    if open_pids and (not closed_ts or open_ts > closed_ts):
        # An undecided proposal newer than any closure keeps it live.
        state = "pending" if surfaced else "open"
    elif closed_ts and (not reversed_hit or closed_ts >= sit["last_ts"]):
        state = "resolved"
    elif decided_ts:
        # Captain verb landed (approve/edit/skip). Reversal re-opens.
        state = "open" if reversed_hit else "decided"
    elif acted_ts:
        state = "open" if reversed_hit else "acted"
    elif sit["counts"]["expiries"] and not open_pids:
        # Only expiries: live-but-demoted (stay-live-until-acted), parking at
        # the end of the demote path.
        state = "dormant" if sit["demotions"] >= _PARK_TIER else \
            ("surfaced" if surfaced else "open")
    else:
        state = "surfaced" if surfaced else "open"

    if state in ("open", "surfaced") and sit["demotions"] >= _PARK_TIER:
        state = "dormant"

    sit["state"] = state
    sit["live"] = state in LIVE_STATES
    sit["pid"] = open_pids[-1] if open_pids else None
    if sit["harm_class"] is None:
        sit["harm_class"] = "external_deadline" if sit["deadline_iso"] else "none"
    sit["refs"] = sorted(refs)
    for scratch in ("_decided_ts", "_acted_ts", "_closed_ts", "_reversed",
                    "_open_ts"):
        sit.pop(scratch, None)
    return sit


def _merge_groups(rows: list) -> dict:
    """H1 identity dedup at the fold: group ledger rows by exact situation_key,
    then UNION groups sharing any ID-GRADE canonical ref (paths are the weaker
    grade — a rolling digest .md hosts many situations, so path-only overlap
    never merges; the shipped situation.py doctrine). Returns
    {anchor_key: {"keys": [aliases...], "rows": [...]}} where the anchor is the
    EARLIEST group's key (stable as refs accumulate)."""
    from framework.attention.situation import path_grade

    groups: dict = {}
    order: list = []
    for row in rows:
        key = _key_of_row(row)
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"keys": [key], "rows": [],
                               "ids": set(), "first_ts": str(row.get("ts") or "")}
            order.append(key)
        g["rows"].append(row)
        refs = [r for r in (row.get("refs") or []) if isinstance(r, str)]
        g["ids"].update(r for r in canonical_refs(refs) if not path_grade(r))

    # Union-find over id-grade overlap, deterministic (insertion order).
    parent = {k: k for k in order}

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    by_id: dict = {}
    for k in order:
        for ref in sorted(groups[k]["ids"]):
            if ref in by_id:
                ra, rb = find(by_id[ref]), find(k)
                if ra != rb:
                    # anchor = earliest (first_ts, key) wins
                    a, b = sorted((ra, rb), key=lambda x:
                                  (groups[x]["first_ts"], x))
                    parent[b] = a
            else:
                by_id[ref] = k

    merged: dict = {}
    for k in order:
        root = find(k)
        m = merged.setdefault(root, {"keys": [], "rows": []})
        m["keys"].append(k)
        m["rows"].extend(groups[k]["rows"])
    return merged


def derive(*, ledger_rows: Iterable, journal_rows: Iterable,
           feed_rows: Iterable, standing: "dict | None" = None) -> dict:
    """PURE fold: (ledger, undo journal, feed, standing map) → the situation
    view {situation_key: situation}. Deterministic given its inputs — rows are
    folded in ts order per store; no I/O, no clock. Overlapping ref-sets merge
    on id-grade refs (H1); each situation lists its member keys as
    ``aliases`` so feed/standing rows keyed by ANY revision's key fold in."""
    from framework.attention.acted_overlay import load_acted

    view: dict = {}
    alias_to_anchor: dict = {}

    def sit_for(key: str) -> dict:
        anchor = alias_to_anchor.get(key, key)
        if anchor not in view:
            view[anchor] = _new_situation(anchor)
            alias_to_anchor.setdefault(anchor, anchor)
        return view[anchor]

    ordered = sorted((r for r in ledger_rows if isinstance(r, dict)),
                     key=lambda r: str(r.get("ts") or ""))
    for anchor, group in _merge_groups(ordered).items():
        for alias in group["keys"]:
            alias_to_anchor[alias] = anchor
        sit = sit_for(anchor)
        sit["aliases"] = sorted(set(group["keys"]))
        for row in sorted(group["rows"], key=lambda r: str(r.get("ts") or "")):
            _fold_ledger_row(sit, row)

    # Reversal state via the tested P2 join (status=="reversed" only).
    try:
        acted = load_acted(ledger_rows=ordered, journal_rows=list(journal_rows))
        reversed_refs = acted["reversed_canonical"]
    except Exception:
        reversed_refs = frozenset()   # unknown world: fold without reversals

    for row in sorted((r for r in feed_rows if isinstance(r, dict)),
                      key=lambda r: (r.get("seq") if isinstance(r.get("seq"), int)
                                     else 0)):
        skey = row.get("situation_key")
        if isinstance(skey, str) and skey:
            _fold_feed_row(sit_for(skey), row)

    for skey, card in (standing or {}).items():
        if not isinstance(card, dict):
            continue
        sit = sit_for(str(skey))
        if sit["standing_message_id"] is None:
            sit["standing_message_id"] = card.get("message_id")
        if sit["class_id"] is None:
            sit["class_id"] = card.get("class_id")
        if not sit["last_surfaced_at"]:
            sit["last_surfaced_at"] = card.get("ts")

    return {k: _finalize(s, reversed_refs) for k, s in view.items()}


def build_view(*, since: "str | None" = None,
               ledger_rows=None, journal_rows=None, feed_rows=None,
               standing=None) -> dict:
    """The live situation view with default loaders (each already tested in
    its own module; every one injectable). Read-only: derived, rebuildable."""
    if ledger_rows is None:
        ledger_rows = _default_ledger(since)
    if journal_rows is None:
        try:
            journal_rows = _default_journal()
        except Exception:
            journal_rows = []          # unreadable journal → fold w/o reversals
    if feed_rows is None:
        try:
            feed_rows = _default_feed()
        except Exception:
            feed_rows = []
    if standing is None:
        standing = _default_standing()
    return derive(ledger_rows=ledger_rows, journal_rows=journal_rows,
                  feed_rows=feed_rows, standing=standing)


def live_situations(view: dict) -> list:
    """The LIVE census (open/surfaced/pending), oldest first — the war-room's
    unit of demand. Dormant (parked) situations are censused by callers via
    the full view; they never render on a shelf."""
    rows = [s for s in view.values() if s.get("live")]
    rows.sort(key=lambda s: (str(s.get("created_ts") or ""), s["key"]))
    return rows
