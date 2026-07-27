#!/usr/bin/env python3.12
"""memory-supersede-apply.py — §4.2 belief invalidation, the APPLY organ.

Closes the loop ``memory-contradictions.py`` deliberately left open: the
detector proposes supersession candidates into
``shared/interfaces/memory-supersession-proposals.jsonl`` and nothing ever
consumed them — two contradictory live rows kept feeding recall forever.
This organ consumes that file and lets the store refine itself, behind a
soak gate (per 2026-07-15 Captain ratification of memory Wave 3).

Lifecycle (detect → soak → apply):
  * NEAR-DUP class (reason ``near-duplicate``): the auto-appliable class,
    and only after re-validation against the CURRENT live store view —
    recomputed token-Jaccard >= 0.75 (the detector's own normalization,
    imported from it so the two organs can never drift), SAME
    source_type, both rows still live, timestamp order intact. The newer
    row supersedes the older via one guarded parameterized UPDATE that
    no-ops unless the older row is still live. Reversible by design:
    ``--undo`` re-nulls exactly the pointer this organ set. Within one
    run, a row an apply just touched blocks further applies referencing
    it (``deferred-touched-id``, stays open) — the in-run live view is
    stale for it, and an equal-timestamp reciprocal pair must never
    supersede BOTH rows out of recall.
  * LIVENESS is live-view-first, then a WINDOWLESS by-id probe (one
    constant parameterized SELECT): absence from the detector's 90-day
    window means superseded OR merely aged out — the probe tells them
    apart. Probe shows superseded/absent → terminal refusal
    (``refused-superseded`` / ``refused-gone``); probe unreachable →
    ``blocked-db``, an OPEN decision that re-validates next run. An
    aged-out but live pair is never silently dropped.
  * SOAK GATE (14 days): from the first soak-ledger entry every
    would-apply is RECORDED, never executed. Auto-apply arms only when
    (now - first entry) >= 14d AND the ledger holds ZERO unresolved
    reversals AND ``instance/config/memory-supersession.yml``
    ``auto_apply`` is not ``hold`` (missing config = ``soak``, the
    ratified default; an unrecognized value fails safe to ``hold``).
    One reversal re-blocks arming until the Captain rules; the ruling
    is recorded with ``--resolve-reversals "<note>"``, which appends a
    ``reversal-resolved`` marker — only reversals AFTER the latest
    marker block (never edit the ledger by hand: consumed-but-open
    pairs would be orphaned; they self-heal from their proposals-file
    stamps, but the ruling verb is the supported path).
  * ACTION-SEAM OUTER GATE (Captain law 2026-07-17): even an ARMED soak
    only acts when the autonomy-graded action seam
    (``framework/authority/action_mode.py`` — THE law for
    autonomous-mutation modes) answers an act mode for this organ's
    apply action: ``go`` (sovereign), or ``act_tell`` (a future
    act-then-tell posture rung — lawful here because ``--undo`` is this
    organ's registered undo handle and the soak ledger is the receipt).
    Today's guardian/earn_up postures answer ``propose``, so an armed
    gate reads ``held-by-action-seam`` and every would-apply stays
    RECORDED, never executed — Captain-granted pairs included (the
    grant stays live on the needs ledger and executes once the posture
    allows acting). The seam is an OUTER gate that may only TIGHTEN:
    an act answer never bypasses soak/hold/veto (those still bind in
    full), and ANY seam failure (import, resolve, shape) fail-closes
    to ``propose``. Tests pin both directions: sovereign + unarmed
    soak still refuses; guardian + armed soak still refuses.
  * HALF-SOAK CARD: once per soak window, at >= day 7, ONE Captain
    heads-up card is filed on the needs ledger (would-apply/cue counts
    + the arming date + the ``hold`` escape hatch) so time-based arming
    is never observation-free. The ``soak-halfway-card`` ledger marker
    is written only when the card got a need id — a guardian-dark
    window retries next run. The card's veto BINDS: while its need is
    ``denied`` on the needs ledger the gate reads
    ``held-by-captain-veto`` — arming and every apply (Captain-approved
    pairs included) are impossible, ONE ``captain-veto-hold`` marker
    records the observation in the soak ledger, and the card is never
    re-filed. The AUTHORITY is the live needs row, re-read every run —
    a later binder ``grant`` on the same card lifts the hold with no
    ledger surgery; config ``hold`` still holds regardless.
  * CONTRADICTION-CUE class (reason ``contradiction-cue``): never
    auto-applies on similarity alone. Each pair files ONE Captain
    one-tap decision card on the needs ledger
    (``framework.authority.needs.file_need`` — the attention queue
    renders it; fingerprint dedup makes re-filing a count-bump, never
    spam). Filing is RETRIED every run until a need id lands in the
    ledger entry — guardian posture or a transient needs failure delays
    the card, never drops it. The card is a promise this organ KEEPS:
    a Captain-approved card routes the pair through the SAME guarded
    apply path on a following run. The approval status is
    ``approved_pending_apply`` — that is what the binder ``grant`` verb
    writes for EVERY kind (``binder_wire._NEED_VERB_STATUS``), and for
    these decision-kind cards the binder approval IS the ruling
    (``grant-apply.sh`` refuses kind!=standing_grant, so nothing in
    production ever writes ``granted`` for them from outside). The
    approval waives only the class restriction and the Jaccard bar
    (it IS the semantic judgment); liveness/type/order guards and the
    armed gate still apply, and the ledger entry carries
    ``via: captain-grant``. Once the approved pair APPLIES, this organ
    closes the need — ``needs.mark(<id>, "granted")``, the receipt,
    mirroring grant-apply.sh's own mark phase — so the approved set
    never grows unbounded; a terminally-refused approved pair closes
    its need as ``superseded`` (the ask is moot). A veto simply never
    approves — both rows stay.

State surfaces (both runtime, gitignored):
  * the proposals file — consumption is stamped PER ROW by appending a
    ``{"status": "consumed"}`` line per proposal_id (O_APPEND,
    last-write-wins per id — the needs-ledger pattern; a shared
    append-file is never rewritten, and the detector's skip-known dedup
    keeps working because every stamped id stays present in the file).
  * ``shared/interfaces/memory-supersession-soak.jsonl`` — the decision
    ledger: per-run markers plus would_apply / applied / refused-* /
    blocked-db / cue-card / reversal entries and the reversal-resolved /
    soak-halfway-card / captain-veto-hold markers. Ids, jaccard and a
    sha256 texts-hash only — never content text.

Security shape: proposal/soak/needs-ledger content is UNTRUSTED — it
flows through ``json.loads`` only; row ids are ``int()``-validated
before binding; the store surface is THREE module constants — two
guarded parameterized psycopg2 UPDATEs plus one read-only by-id probe
SELECT (``%s`` placeholders, ids only) — and the organ is structurally
incapable of removing rows (no such SQL verb in this module — pinned by
test). The connection VALUE (env ``NEON_CONNECTION_STRING`` or
``cabinet/.env``, via the detector's own loader) is never printed. Bulk
reads reuse the detector's constant read-only SELECT. psycopg2 is
imported lazily and a missing driver degrades to a loud ``blocked-db``
decision, never a crash (etl-common lazy-driver pattern). The config
flag fails CLOSED: only a genuinely MISSING file is the ratified
default ``soak``; an unreadable existing file, bad yaml or an unknown
value is ``hold``.

Run:  python3.12 cabinet/scripts/memory-supersede-apply.py
          [--dry-run] [--json]            # consume + classify + soak/apply
      ... --report [--json]               # soak summary for the nightly digest
      ... --undo '<applied soak-ledger json line>'   # reverse one apply
      ... --resolve-reversals '<why>'     # Captain ruling: clear the latch

Scheduled via its OWN services.yml row ``memory-supersede-apply``
(Sundays 05:45, after the 05:30 detect pass — one command per row: the
generated-plist wrapper ``exec``s the command, so a ``&&`` chain after
the detector would never run).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util as _ilu
import json
import os
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]

PROPOSALS_PATH = (_REPO_ROOT / "shared" / "interfaces" /
                  "memory-supersession-proposals.jsonl")
SOAK_PATH = (_REPO_ROOT / "shared" / "interfaces" /
             "memory-supersession-soak.jsonl")
CONFIG_PATH = _REPO_ROOT / "instance" / "config" / "memory-supersession.yml"

SOAK_DAYS = 14                # propose-only window from the FIRST ledger entry
MAX_APPLIES_PER_RUN = 50      # blast-radius bound; the rest stays would_apply

# The organ's action_type namespace — ONE constant so the pair cards
# (``memory-supersede:sup-*``), the soak-halfway card and the batched
# same-source cards (``memory-supersede:batch:*``) can never drift apart
# from the readers that look their rulings back up.
_ACTION_NS = "memory-supersede"

# The soak-halfway card's needs fingerprint — ONE constant so the filer
# (file_soak_halfway_card) and the veto reader (halfway_veto) can never
# drift apart: a card the organ files under one action_type but reads the
# ruling for under another would make the promised veto silently unbinding.
_HALFWAY_ACTION = f"{_ACTION_NS}:soak-halfway"

# The organ's ENTIRE write surface against the store — two module-constant
# parameterized statements (ids only; content never reaches SQL). The
# ``superseded_by IS NULL`` guard makes a raced apply a 0-row no-op, and the
# undo guard restores ONLY a pointer this organ set.
_APPLY_SQL = ("UPDATE cabinet_memory SET superseded_by = %s "
              "WHERE id = %s AND superseded_by IS NULL")
_UNDO_SQL = ("UPDATE cabinet_memory SET superseded_by = NULL "
             "WHERE id = %s AND superseded_by = %s")

# The organ's only OTHER store statement: a WINDOWLESS by-id liveness probe
# (read-only). The detector's live view is 90-day-windowed, so "absent from
# it" conflates superseded with merely aged-out — this probe (ids are
# int()-validated before the list binds to the single %s) tells them apart
# so an aged-out live pair is never terminally refused.
_ROWS_BY_ID_SQL = (
    "SELECT id, source_type, officer, left(content, 1200), "
    "to_char(coalesce(source_created_at, created_at) AT TIME ZONE 'UTC', "
    "'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'), superseded_by "
    "FROM cabinet_memory WHERE id = ANY(%s)")


def _load_detector():
    """The sibling detector module (dashed filename → importlib). Reused for
    _tokens/jaccard/NEAR_DUP_JACCARD (normalization single-source), the
    live-row loader and the conn-string loader."""
    mod = sys.modules.get("memory_contradictions")
    if mod is not None:
        return mod
    spec = _ilu.spec_from_file_location(
        "memory_contradictions",
        _REPO_ROOT / "cabinet" / "scripts" / "memory-contradictions.py")
    mod = _ilu.module_from_spec(spec)
    sys.modules["memory_contradictions"] = mod
    spec.loader.exec_module(mod)
    return mod


_mc = _load_detector()


def _load_ask_mint():
    """The shared same-source ask batcher (cabinet/scripts/lib/ask_mint.py).
    Underscore-named, so a plain sys.path insert imports it — the same door
    officer-inbound-poller.py uses for the lib/ modules it depends on."""
    lib_dir = str(_REPO_ROOT / "cabinet" / "scripts" / "lib")
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    import ask_mint  # noqa: PLC0415 — deliberate late import
    return ask_mint


_am = _load_ask_mint()


# ---------------------------------------------------------------------------
# Time + JSONL plumbing (needs-ledger discipline: O_APPEND, last-write-wins)
# ---------------------------------------------------------------------------

def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(ts: dt.datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_dt(v) -> Optional[dt.datetime]:
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=dt.timezone.utc)
    if v is None:
        return None
    try:
        out = dt.datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return out if out.tzinfo else out.replace(tzinfo=dt.timezone.utc)


def read_jsonl(path: Path) -> List[dict]:
    """Tolerant reader: torn/corrupt lines are skipped, never raised."""
    rows: List[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return rows
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def append_jsonl(path: Path, row: dict) -> None:
    """ONE os.write on an O_APPEND fd — safe against the detector appending
    to the same file concurrently (the reason the proposals file is stamped
    by appended rows, never rewritten in place)."""
    line = (json.dumps(row, sort_keys=True, default=str) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# Config flag — instance/config/memory-supersession.yml
# ---------------------------------------------------------------------------

def load_mode(path: Optional[Path] = None) -> str:
    """``auto_apply`` posture: "soak" (arm after a clean 14d soak — the
    default ratified 2026-07-15) or "hold" (propose-only forever). ONLY a
    genuinely MISSING file is "soak"; an EXISTING file that cannot be read
    (permissions, I/O, a directory in its place), bad yaml, a missing yaml
    lib or an UNRECOGNIZED value all fail safe to "hold" — a typo or a
    broken read must never arm auto-apply. (FileNotFoundError is split out
    of OSError deliberately: a Captain-set ``hold`` whose file turns
    unreadable must stay hold, not fall back to the arming default.)"""
    p = path or CONFIG_PATH
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "soak"
    except OSError:
        return "hold"
    try:
        import yaml
        cfg = yaml.safe_load(text) or {}
    except Exception:  # noqa: BLE001 — bad yaml / missing lib never arms
        return "hold"
    if not isinstance(cfg, dict):
        return "hold"
    val = str(cfg.get("auto_apply", "soak")).strip().lower()
    return val if val in ("soak", "hold") else "hold"


# ---------------------------------------------------------------------------
# Ledger views
# ---------------------------------------------------------------------------

def compact_proposals(rows: List[dict]) -> Dict[str, dict]:
    """Last-write-wins per proposal_id: the newest FULL row (one carrying
    old/new) is the base; the newest row's status rides on top (a later
    ``consumed`` stamp overrides ``proposed``)."""
    out: Dict[str, dict] = {}
    for row in rows:
        pid = row.get("proposal_id")
        if not pid or not isinstance(pid, str):
            continue
        cur = out.get(pid)
        if cur is None:
            out[pid] = dict(row)
            continue
        if isinstance(row.get("old"), dict) and isinstance(row.get("new"), dict):
            merged = dict(row)
            merged["status"] = row.get("status") or cur.get("status")
            out[pid] = merged
        else:
            cur = dict(cur)
            if row.get("status"):
                cur["status"] = row["status"]
            for k in ("consumed_at", "decision"):
                if row.get(k) is not None:
                    cur[k] = row[k]
            out[pid] = cur
    return out


def compact_soak(entries: List[dict]) -> Dict[str, dict]:
    """Latest entry per proposal_id (run markers carry no proposal_id and are
    skipped). A later applied/refused-*/reversal entry closes the item."""
    out: Dict[str, dict] = {}
    for e in entries:
        pid = e.get("proposal_id")
        if pid and isinstance(pid, str):
            out[pid] = e
    return out


def soak_stats(entries: List[dict], *, now=None) -> dict:
    """First-entry clock + decision counts over the whole soak ledger.

    ``reversals`` is the UNRESOLVED count: the ledger is append-only, so
    file order is chronological — a ``reversal-resolved`` marker (appended
    by ``--resolve-reversals``, the Captain's ruling) zeroes every reversal
    before it; only reversals AFTER the latest marker keep blocking.
    ``counts`` stays the raw per-decision totals (the report shows both)."""
    nowdt = _to_dt(now) or _now()
    first: Optional[dt.datetime] = None
    counts: Dict[str, int] = {}
    unresolved = 0
    for e in entries:
        ts = _to_dt(e.get("ts"))
        if ts is not None and (first is None or ts < first):
            first = ts
        d = str(e.get("decision") or "")
        counts[d] = counts.get(d, 0) + 1
        if d == "reversal":
            unresolved += 1
        elif d == "reversal-resolved":
            unresolved = 0
    days = ((nowdt - first).total_seconds() / 86400.0) if first else None
    return {"first_entry": _iso(first) if first else None,
            "days_into_soak": days,
            "reversals": unresolved,
            "counts": counts}


def gate_state(entries: List[dict], mode: str, *, now=None,
               vetoed: bool = False) -> str:
    """held-by-captain-veto | hold | soak | armed. Arms ONLY when the
    14-day soak has elapsed from the FIRST ledger entry with ZERO
    unresolved reversals and the config flag allows it (>= — day 14
    exactly arms, 13d23h does not). Any reversal re-blocks until a
    ``reversal-resolved`` ruling follows it. ``vetoed`` (a Captain deny
    on the soak-halfway card — see ``halfway_veto``) is a BINDING hold
    that outranks everything: the card promised "veto = hold", so a deny
    must make arming impossible, not merely decorate a report."""
    if vetoed:
        return "held-by-captain-veto"
    if mode == "hold":
        return "hold"
    st = soak_stats(entries, now=now)
    if st["days_into_soak"] is None or st["reversals"] > 0:
        return "soak"
    return "armed" if st["days_into_soak"] >= SOAK_DAYS else "soak"


# ---------------------------------------------------------------------------
# Autonomy-graded action seam — the OUTER gate (Captain law 2026-07-17)
# ---------------------------------------------------------------------------
# "Every autonomous mutation's mode is a FUNCTION of the posture level."
# The seam (framework/authority/action_mode.py) answers propose|act_tell|go
# for this organ's apply action; anything but an ACT mode holds an armed
# gate at ``held-by-action-seam`` — a state no ``== "armed"`` check
# matches, so the outer gate can only TIGHTEN the existing soak/hold/veto
# law, never bypass it (an act answer changes nothing about those gates).

# The apply action, described once. reversibility is honest: --undo re-nulls
# exactly the pointer this organ set, and a reversal re-blocks arming — that
# same verb is the REGISTERED undo handle act_tell requires. ring 2: the
# runtime organ plane (no Ring-0 category; the seam would card those).
_APPLY_ACTION = {
    "ring": 2,
    "reversibility": "reversible",
    "category": "memory-supersede-apply",
    "undo_handle": ("python3.12 cabinet/scripts/memory-supersede-apply.py "
                    "--undo '<applied soak-ledger json line>'"),
}

# Seam answers that permit the EXISTING arming law to proceed. propose (or
# any failure) holds. act_tell is lawful because _APPLY_ACTION presents the
# registered undo handle; the seam itself refuses act_tell without one.
_SEAM_ACT_MODES = ("go", "act_tell")


def action_seam_disposition(posture: Optional[str] = None) -> dict:
    """``{"mode", "captain_card"}`` for this organ's apply action, via the
    autonomy-graded action seam. ``posture`` is for hermetic tests —
    production passes None (live posture kernel; the seam resolves with
    ``file_needs=False`` so this read never files needs). Fail-closed: ANY
    import/resolve/shape failure is ``propose``. Never raises."""
    try:
        seam_root = str(_REPO_ROOT)
        if seam_root not in sys.path:
            sys.path.insert(0, seam_root)
        from framework.authority.action_mode import MODES, action_decision
        decision = action_decision(dict(_APPLY_ACTION), posture)
        mode = decision.mode if decision.mode in MODES else "propose"
        return {"mode": mode, "captain_card": bool(decision.captain_card)}
    except Exception:  # noqa: BLE001 — a broken seam must hold, not crash
        return {"mode": "propose", "captain_card": False}


def seam_hold(state: str, disposition: dict) -> str:
    """Apply the outer gate to a ``gate_state`` answer: ``armed`` without an
    act-mode seam answer degrades to ``held-by-action-seam``; every other
    state passes through untouched (the seam never widens hold/veto/soak)."""
    if state == "armed" and disposition.get("mode") not in _SEAM_ACT_MODES:
        return "held-by-action-seam"
    return state


def texts_hash(old_text: str, new_text: str) -> str:
    """Order-sensitive sha16 over the NORMALIZED token sets (what jaccard
    saw) — the soak ledger carries this instead of content text."""
    norm = (" ".join(sorted(_mc._tokens(old_text))) + "|" +
            " ".join(sorted(_mc._tokens(new_text))))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Classification — pure re-validation against the live store view
# ---------------------------------------------------------------------------

def classify(prop: dict, live_by_id: Dict[str, dict], *,
             aux_by_id: Optional[Dict[str, dict]] = None,
             granted: bool = False) -> dict:
    """One compacted proposal → decision dict. Conservative by construction:
    any doubt refuses or stays open (a wrong supersession is memory LOSS; a
    missed one is only a lingering duplicate). BOTH classes must survive
    re-validation (both rows live, same source_type, order intact); then
    only the near-duplicate class can reach ``would_apply`` (recomputed
    Jaccard), while contradiction-cue becomes a ``cue-card`` — never an
    apply on similarity alone. ``granted=True`` (the pair's Captain card
    was granted on the needs ledger) waives ONLY the class restriction and
    the Jaccard bar — every liveness/type/order guard still applies and
    the decision carries ``via: captain-grant``.

    Liveness resolves live-view-first, then ``aux_by_id`` (the windowless
    by-id probe): probe shows ``superseded_by`` set → ``refused-superseded``
    (terminal); probe ran and the id is absent → ``refused-gone``
    (terminal); probe unavailable (``aux_by_id is None``) → ``blocked-db``,
    an OPEN decision re-validated next run — "aged out of the detector's
    90-day window" must never be conflated with "superseded"."""
    old_ref = prop.get("old") if isinstance(prop.get("old"), dict) else {}
    new_ref = prop.get("new") if isinstance(prop.get("new"), dict) else {}
    base = {"proposal_id": str(prop.get("proposal_id") or ""),
            "reason": str(prop.get("reason") or ""),
            "old_id": str(old_ref.get("id") or ""),
            "new_id": str(new_ref.get("id") or "")}
    if base["reason"] not in ("near-duplicate", "contradiction-cue"):
        return {**base, "decision": "refused-unknown-reason"}
    try:
        old_id = int(base["old_id"])
        new_id = int(base["new_id"])
    except ValueError:
        return {**base, "decision": "refused-bad-id"}
    if old_id == new_id:
        return {**base, "decision": "refused-bad-id"}

    def _lookup(rid: int):
        row = live_by_id.get(str(rid))
        if row is not None:
            return row, None
        if aux_by_id is None:
            return None, "unknown"          # probe unavailable this run
        row = aux_by_id.get(str(rid))
        if row is None:
            return None, "gone"
        if row.get("superseded_by"):
            return None, "superseded"
        return row, None                    # live, merely aged out

    old_row, old_miss = _lookup(old_id)
    new_row, new_miss = _lookup(new_id)
    # Terminal facts beat indeterminacy: a provably superseded/absent row
    # ends the pair regardless of the sibling's state.
    if "superseded" in (old_miss, new_miss):
        return {**base, "decision": "refused-superseded"}
    if "gone" in (old_miss, new_miss):
        return {**base, "decision": "refused-gone"}
    if "unknown" in (old_miss, new_miss):
        return {**base, "decision": "blocked-db",
                "note": "liveness probe unavailable"}
    if str(old_row.get("source_type") or "") != str(new_row.get("source_type") or ""):
        return {**base, "decision": "refused-source-type"}
    old_ts, new_ts = _to_dt(old_row.get("ts")), _to_dt(new_row.get("ts"))
    if old_ts and new_ts and new_ts < old_ts:
        return {**base, "decision": "refused-order"}
    if base["reason"] == "contradiction-cue" and not granted:
        cues = prop.get("cues") if isinstance(prop.get("cues"), list) else []
        return {**base, "decision": "cue-card",
                "cues": [str(c) for c in cues][:5]}
    old_text = str(old_row.get("content") or "")
    new_text = str(new_row.get("content") or "")
    sim = _mc.jaccard(_mc._tokens(old_text), _mc._tokens(new_text))
    if base["reason"] == "near-duplicate" and sim < _mc.NEAR_DUP_JACCARD:
        return {**base, "decision": "refused-jaccard", "jaccard": round(sim, 3)}
    out = {**base, "decision": "would_apply", "jaccard": round(sim, 3),
           "texts_hash": texts_hash(old_text, new_text),
           "_old_id_int": old_id, "_new_id_int": new_id}
    if granted and base["reason"] == "contradiction-cue":
        out["via"] = "captain-grant"
    return out


# ---------------------------------------------------------------------------
# Store writers (lazy psycopg2; parameterized; ids only)
# ---------------------------------------------------------------------------

def default_conn_factory():
    """psycopg2 connection from the detector's conn-string loader. LAZY
    driver import (etl-common pattern) so soak/report/cards keep working
    where the driver is absent; the caller maps failures to a loud
    ``blocked-db`` decision. The conn VALUE is never printed."""
    conn_str = _mc._neon_conn()
    if not conn_str:
        raise RuntimeError("no connection string")
    import psycopg2  # lazy: keeps the propose/soak path driver-free
    return psycopg2.connect(conn_str)


def apply_pair(conn, old_id: int, new_id: int) -> bool:
    """One guarded parameterized UPDATE; True iff exactly the still-live
    older row was pointed at the newer one (rowcount 1)."""
    with conn.cursor() as cur:
        cur.execute(_APPLY_SQL, (new_id, old_id))
        changed = cur.rowcount == 1
    conn.commit()
    return changed


def undo_pair(conn, old_id: int, new_id: int) -> bool:
    """Reverse ONE apply: re-null the pointer only while it still points at
    the exact newer row this organ set (rowcount-guarded)."""
    with conn.cursor() as cur:
        cur.execute(_UNDO_SQL, (old_id, new_id))
        changed = cur.rowcount == 1
    conn.commit()
    return changed


def fetch_rows_by_id(ids: List[int], *,
                     conn_factory: Optional[Callable] = None
                     ) -> Optional[List[dict]]:
    """Windowless by-id liveness probe (the constant parameterized
    ``_ROWS_BY_ID_SQL``; ids are int()-validated again before binding).
    Returns None when the store is unreachable (lazy driver / conn
    missing / query failed) — the caller must treat missing-row liveness
    as UNKNOWN (open ``blocked-db``), never as a terminal refusal. Row
    dicts mirror the detector's live-view shape plus ``superseded_by``."""
    if not ids:
        return []
    try:
        safe_ids = sorted({int(i) for i in ids})
    except (TypeError, ValueError):
        return None
    try:
        conn = (conn_factory or default_conn_factory)()
    except Exception:  # noqa: BLE001 — driver/conn missing → unmeasurable
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(_ROWS_BY_ID_SQL, (safe_ids,))
            fetched = cur.fetchall()
    except Exception:  # noqa: BLE001 — a failed probe is honest UNKNOWN
        return None
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    rows: List[dict] = []
    for t in fetched or []:
        if not t or t[0] is None:
            continue
        rows.append({"id": str(t[0]),
                     "source_type": str(t[1] or ""),
                     "officer": str(t[2] or ""),
                     "content": str(t[3] or ""),
                     "ts": str(t[4] or ""),
                     "superseded_by": None if t[5] is None else str(t[5])})
    return rows


# ---------------------------------------------------------------------------
# Needs ledger — the granted-card executor's read side
# ---------------------------------------------------------------------------

def _needs_ledger_path() -> Path:
    """The ONE needs ledger, resolved through the needs module (honors
    CABINET_ROOT); its own path as fallback — never raises."""
    try:
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))
        from framework.authority import needs
        return needs.ledger_path()
    except Exception:  # noqa: BLE001 — a broken import must not kill the pass
        return _REPO_ROOT / "shared" / "interfaces" / "needs-ledger.jsonl"


def _merged_needs(path: Path) -> Dict[str, dict]:
    """Last-write-wins merge per need id over UNTRUSTED ledger JSONL (the
    ledger's own append-only contract — ``needs.mark`` appends a full row
    copy with the new status). String keys only; torn lines skipped."""
    merged: Dict[str, dict] = {}
    for row in read_jsonl(path):
        rid = row.get("id")
        if rid and isinstance(rid, str):
            merged[rid] = {**merged.get(rid, {}), **row}
    return merged


def load_granted_pids(path: Optional[Path] = None) -> Dict[str, str]:
    """Proposal ids whose Captain one-tap card is APPROVED on the needs
    ledger, mapped to their need id — the executor half of the cue-card
    promise. The approval status is ``approved_pending_apply``: that is
    what the binder ``grant NEED-<hex>`` verb writes for EVERY kind
    (``binder_wire._NEED_VERB_STATUS``), and for these decision-kind
    cards the binder approval IS the Captain ruling — ``grant-apply.sh``
    refuses kind!=standing_grant, so production never writes ``granted``
    for them from outside. ``granted`` here is this organ's own
    post-apply RECEIPT (``_mark_need``), which is exactly how a pid
    leaves this map instead of accumulating forever. Rows are UNTRUSTED
    JSONL (tolerant read, string compares only) and a pid landing here
    is still re-validated by ``classify`` (int ids, live rows, guarded
    UPDATE) before any SQL. Denied/vetoed/open cards never land here —
    a pair-card veto keeps both rows by simply never approving."""
    out: Dict[str, str] = {}
    for rid, row in _merged_needs(path or _needs_ledger_path()).items():
        if str(row.get("status") or "") != "approved_pending_apply":
            continue
        action = str(row.get("action_type") or "")
        if action.startswith(f"{_ACTION_NS}:sup-"):
            out[action.split(":", 1)[1]] = rid
    return out


def load_batch_rulings(path: Optional[Path] = None) -> Dict[str, dict]:
    """Captain rulings on the BATCHED same-source cards, keyed by need id.

    A batched card is an ordinary decision card, so the ruling verbs are
    the ones he already has: ``grant NEED-<hex8>`` = approve all
    (``approved_pending_apply``), ``deny NEED-<hex8>`` = skip all
    (``denied``). Nothing else counts — an OPEN batch card resolves
    nothing, exactly like the N cards it replaced (constitution D12:
    silence is never agreement).

    Membership comes from ``ask_mint.batch_members`` reading the row's OWN
    body — the member list the Captain SAW. Re-deriving it from today's
    pending set would let one approval reach pairs that were never on the
    card. A body whose membership cannot be read yields no members and the
    ruling reaches nobody (fail-closed). Rows are UNTRUSTED JSONL; every
    member is still re-validated by ``classify`` before any SQL."""
    out: Dict[str, dict] = {}
    for rid, row in _merged_needs(path or _needs_ledger_path()).items():
        action = str(row.get("action_type") or "")
        if not _am.is_batch_action(action, producer=_ACTION_NS):
            continue
        status = str(row.get("status") or "")
        if status not in ("approved_pending_apply", "denied"):
            continue
        members = _am.batch_members(row)
        if not members:
            continue
        out[rid] = {"status": status, "members": members,
                    "source_key": _am.batch_source_key(action) or ""}
    return out


def halfway_veto(path: Optional[Path] = None) -> Optional[str]:
    """The need id of a VETOED soak-halfway card, else None. The card
    promises "veto = hold", so the organ must READ the ruling it asked
    for: a merged needs-ledger row for ``_HALFWAY_ACTION`` whose latest
    status is ``denied`` binds the gate to ``held-by-captain-veto``.
    Re-checked from the ledger every run — the AUTHORITY is the live
    row, so a later binder ``grant`` on the same card lifts the hold
    with no ledger surgery. Pair cue-cards (action_type
    ``memory-supersede:sup-*``) never reach here: a pair veto keeps two
    rows, only the halfway veto holds the whole gate."""
    for rid, row in _merged_needs(path or _needs_ledger_path()).items():
        if (str(row.get("action_type") or "") == _HALFWAY_ACTION
                and str(row.get("status") or "") == "denied"):
            return rid
    return None


def _mark_need(nid: str, status: str, reason: str,
               mark_need_fn: Optional[Callable] = None) -> Optional[dict]:
    """Close out an approved card's need row — the receipt half of the
    promise, mirroring ``grant-apply.sh``'s mark phase (which does
    ``needs.mark(id, "granted")`` after applying a standing grant):
    ``granted`` once the pair APPLIED, ``superseded`` when the pair
    closed terminally without the apply (the ask is moot). Never raises;
    an unknown id is a ``needs.mark`` no-op (fail closed), and a failed
    receipt leaves the need approved — retried implicitly because the
    pair only closes in the soak ledger when the apply really landed."""
    try:
        if mark_need_fn is not None:
            return mark_need_fn(nid, status, reason)
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))
        from framework.authority import needs
        return needs.mark(nid, status, by="system:memory-supersession",
                          reason=reason)
    except Exception:  # noqa: BLE001 — a receipt must never break the pass
        return None


# ---------------------------------------------------------------------------
# Cue-class Captain cards (needs ledger — the attention queue renders them)
# ---------------------------------------------------------------------------

def file_cue_card(decision: dict,
                  *, file_need_fn: Optional[Callable] = None) -> Optional[str]:
    """ONE Captain one-tap decision card per contradiction pair, on the SAME
    surface every other org ask rides (needs ledger → attention queue →
    pinned card/briefing; approve/veto are the one-taps). action_type
    carries the proposal id so each pair gets its own fingerprint-deduped
    need. Dark under guardian posture by design (file_need no-ops) — the
    soak ledger still records the pair. Never raises. The card text states
    EXACTLY what this organ delivers: a grant is executed by a following
    weekly pass once the auto-apply gate arms — approve is never described
    as an action that already happened."""
    pid = str(decision.get("proposal_id") or "")
    cues = decision.get("cues") or []
    why = (f"memory contradiction {pid}: row {decision.get('new_id')} cues "
           f"supersession of row {decision.get('old_id')}"
           + (f" (cues: {', '.join(cues[:3])})" if cues else "")
           + " — approve = supersede the older row (this organ executes the"
             " grant on a following weekly pass, once the auto-apply gate"
             " arms; guarded, reversible via --undo), veto = keep both rows."
             " Nothing changes until the grant lands.")
    try:
        if file_need_fn is None:
            if str(_REPO_ROOT) not in sys.path:
                sys.path.insert(0, str(_REPO_ROOT))
            from framework.authority import needs
            file_need_fn = needs.file_need
        return file_need_fn(
            "decision",
            action_type=f"{_ACTION_NS}:{pid}",
            why=why,
            unblocks="cabinet_memory recall hygiene",
            cost_of_delay="low",
            filed_by="system:memory-supersession",
            cid=pid)
    except Exception:  # noqa: BLE001 — a card must never break the pass
        return None


def cue_source_key(decision: dict) -> str:
    """The row that CUED a cue-card ask — the batching group key.

    The detector walks pairs newest-first inside one source_type bucket
    (``memory-contradictions.propose``), so ONE new row can cue supersession
    of every older row it contradicts: N asks, one cue. That is exactly the
    shape that produced eleven cards for one decision, so the group key is
    the cueing row — the same row the card text already names ("row X cues
    supersession of row Y")."""
    return str(decision.get("new_id") or "")


def file_cue_batch_card(source_key: str, members: List[str],
                        *, file_need_fn: Optional[Callable] = None) -> dict:
    """ONE Captain card for every cue-card ask the SAME row cued.

    Paid 2026-07-26: eleven near-identical supersession asks arrived as
    eleven cards and collected zero answers. Same surface, same verbs, same
    dedup as ``file_cue_card`` — only the grouping differs, and the body
    lists every member id so approve-all can never reach a pair he did not
    see. Two members is the floor: a single ask stays an ordinary per-pair
    card (the caller's degenerate end). Returns the ``ask_mint`` result
    dict; ``need_id`` None means the ledger no-opped (guardian-dark) and the
    caller retries next run, exactly as for a per-pair card."""
    n = len(members)
    detail = (f"approve all = supersede the older row of all {n} pairs "
              "(this organ executes each grant on a following weekly pass, "
              "once the auto-apply gate arms; guarded, each reversible on "
              "its own via --undo), skip all = keep both rows in every "
              "pair. Nothing changes until the grants land. One decision, "
              f"{n} pairs — every pair is still re-validated and recorded "
              "individually.")
    return _am.group_pending_asks(
        source_key, members,
        producer=_ACTION_NS,
        noun="memory supersessions",
        detail=detail,
        unblocks="cabinet_memory recall hygiene",
        cost_of_delay="low",
        filed_by="system:memory-supersession",
        file_need_fn=file_need_fn)


def file_soak_halfway_card(stats: dict, *, state: str,
                           file_need_fn: Optional[Callable] = None
                           ) -> Optional[str]:
    """ONE Captain heads-up card per soak window (>= day 7) so the gate
    never arms with zero human observation: counts recorded so far, the
    arming date, and the ``hold`` escape hatch. Same needs surface + dedup
    as the cue cards (``_HALFWAY_ACTION`` is the fingerprint). The card's
    one-taps BIND: approve (binder grant) lets the soak arm, veto (binder
    deny) holds the gate — ``halfway_veto`` reads the ruling every run.
    Never raises; None under guardian posture — the caller writes the
    ledger marker only on a real need id, so filing retries next run."""
    counts = stats.get("counts") or {}
    days = stats.get("days_into_soak")
    day_str = f"{days:.0f}" if isinstance(days, (int, float)) else "?"
    first = _to_dt(stats.get("first_entry"))
    arm_date = (_iso(first + dt.timedelta(days=SOAK_DAYS))[:10]
                if first else "unknown")
    posture = ("auto-apply is ARMED as of" if state == "armed"
               else "auto-apply (near-duplicate class only) arms")
    why = (f"memory-supersession soak day {day_str}/{SOAK_DAYS}: "
           f"{counts.get('would_apply', 0)} would-apply and "
           f"{counts.get('cue-card', 0)} cue-card decisions recorded; "
           f"{posture} ~{arm_date} unless "
           "instance/config/memory-supersession.yml is set to "
           "auto_apply: hold — approve = let the soak arm, veto = hold. "
           "Review: python3.12 cabinet/scripts/memory-supersede-apply.py "
           "--report")
    try:
        if file_need_fn is None:
            if str(_REPO_ROOT) not in sys.path:
                sys.path.insert(0, str(_REPO_ROOT))
            from framework.authority import needs
            file_need_fn = needs.file_need
        return file_need_fn(
            "decision",
            action_type=_HALFWAY_ACTION,
            why=why,
            unblocks="observed (not time-only) arming of memory supersession",
            cost_of_delay="low",
            filed_by="system:memory-supersession",
            cid="soak-halfway")
    except Exception:  # noqa: BLE001 — a card must never break the pass
        return None


# ---------------------------------------------------------------------------
# The pass
# ---------------------------------------------------------------------------

def _ledger_entry(decision: dict, *, ts: str, mode: str) -> dict:
    entry = {"ts": ts, "mode": mode}
    for k in ("proposal_id", "reason", "decision", "old_id", "new_id",
              "jaccard", "texts_hash", "cues", "need_id", "note", "via",
              "batch"):
        if decision.get(k) is not None:
            entry[k] = decision[k]
    return entry


def _mint_cue_cards(results: List[tuple], summary: dict, *,
                    ruled_sources: set,
                    file_need_fn: Optional[Callable] = None) -> None:
    """Mint this pass's cue-class Captain cards — ONE per cueing row.

    The grouping decision needs the whole pass, so it happens here rather
    than per-ask inside the classify loop. Three shapes, all deliberate:
    a source with two or more asks becomes ONE batched card listing every
    member; a source with exactly ONE ask stays an ordinary per-pair card
    (a "batch of one" would be a second wording for the same decision);
    and a source whose batched card the Captain has ALREADY ruled on mints
    nothing — re-filing would rewrite the body his ruling was given on, so
    a late member waits for the next window instead of joining an approval
    it was never listed in. Members past the per-card cap are left
    uncarded and retried, never folded silently into a body that does not
    list them. A card that no-ops (guardian-dark) leaves need_id None and
    the existing retry path re-files next run."""
    by_key: Dict[str, List[dict]] = {}
    for _origin, _pid, d in results:
        if str(d.get("decision") or "") == "cue-card":
            by_key.setdefault(cue_source_key(d), []).append(d)

    for key in sorted(by_key):
        group = by_key[key]
        if key and key in ruled_sources:
            continue
        out = ({} if len(group) < 2 else file_cue_batch_card(
            key, sorted(str(d.get("proposal_id") or "") for d in group),
            file_need_fn=file_need_fn))
        if not out.get("batched"):
            for d in group:                       # degenerate end / no key
                d["need_id"] = file_cue_card(d, file_need_fn=file_need_fn)
            continue
        summary["cue_batches"] += 1
        covered = set(out["members"])
        for d in group:
            if str(d.get("proposal_id") or "") not in covered:
                continue
            d["need_id"] = out["need_id"]
            d["batch"] = out["action_type"]


def _close_batch_needs(results: List[tuple], batch_rulings: Dict[str, dict],
                       latest: Dict[str, dict], *,
                       mark_need_fn: Optional[Callable] = None) -> None:
    """ONE receipt per APPROVED batched card — and only once EVERY member
    it listed has reached a terminal state (applied or terminally refused).

    Closing on the first member's outcome would evict the rest from
    ``load_granted_pids`` and silently un-approve them, so a batch whose
    members are still queued under soak/hold/blocked keeps its approval
    live and retries next run — the same "the executor retries" contract a
    per-pair approval has. ``granted`` when the approval actually executed
    for at least one pair, ``superseded`` when every pair turned out moot.
    A DENIED batch needs no receipt: deny is already terminal on the
    ledger, and each member recorded its own skip."""
    if not batch_rulings:
        return
    outcome = {pid: str(d.get("decision") or "") for _o, pid, d in results}
    for nid in sorted(batch_rulings):
        ruling = batch_rulings[nid]
        if ruling["status"] != "approved_pending_apply":
            continue
        finals = [outcome.get(pid)
                  or str((latest.get(pid) or {}).get("decision") or "")
                  for pid in ruling["members"]]
        if not all(f == "applied" or f.startswith("refused-") for f in finals):
            continue
        applied = sum(1 for f in finals if f == "applied")
        total = len(finals)
        key = ruling["source_key"]
        if applied:
            _mark_need(nid, "granted",
                       f"batch {key}: {applied}/{total} pairs applied "
                       "(superseded_by set; each reversible via --undo)",
                       mark_need_fn)
        else:
            _mark_need(nid, "superseded",
                       f"batch {key}: all {total} pairs closed without "
                       "applying — the approval is moot", mark_need_fn)


def run_apply_pass(*, proposals_path: Optional[Path] = None,
                   soak_path: Optional[Path] = None,
                   config_path: Optional[Path] = None,
                   needs_path: Optional[Path] = None,
                   now=None,
                   live_rows: Optional[List[dict]] = None,
                   conn_factory: Optional[Callable] = None,
                   fetch_rows_fn: Optional[Callable] = None,
                   file_need_fn: Optional[Callable] = None,
                   mark_need_fn: Optional[Callable] = None,
                   dry_run: bool = False,
                   posture: Optional[str] = None) -> dict:
    """Consume new proposals + re-validate open items; soak or apply.

    ``posture`` is hermetic test injection for the action-seam OUTER gate
    (module docstring): production passes None and the seam resolves the
    live posture itself. An armed gate additionally requires the seam to
    answer an act mode (``go``/``act_tell``) or it reads
    ``held-by-action-seam`` — recorded, never executed.

    Every processed proposal gets (a) a decision entry in the soak ledger
    (deduped: an identical repeat decision for the same pair appends
    nothing) and (b) a per-row ``consumed`` stamp in the proposals file on
    first consumption. would_apply/blocked-db items stay OPEN and are
    re-validated every run until applied, refused, or reverted; a cue-card
    entry missing its need_id stays open too and re-files the Captain card
    each run until one lands (guardian-dark delays, never drops); a
    cue-card whose need the Captain APPROVED (binder ``grant`` →
    ``approved_pending_apply``) reopens and routes through the guarded
    apply path (``via: captain-grant`` — the executor half of the card's
    promise); once it applies, the need is closed with the ``granted``
    receipt (``_mark_need`` / ``mark_need_fn``), and a terminal refusal
    closes it as ``superseded``. A Captain VETO on the soak-halfway card
    binds the whole gate: state ``held-by-captain-veto`` (no arming, no
    applies), one ``captain-veto-hold`` marker in the soak ledger, no
    card re-filing — the live needs row stays the authority, so a later
    grant lifts the hold. Rows absent from the windowed live view are
    settled by the windowless by-id probe (``fetch_rows_fn``, default the
    real ``fetch_rows_by_id``); an unreachable probe leaves those pairs
    OPEN as ``blocked-db``. Within one run an applied row's ids are
    TOUCHED: later would_apply pairs referencing them defer open (the
    in-run view is stale — a reciprocal equal-ts pair must never
    supersede both rows). Consumed proposals the soak ledger has NO entry
    for (hand-surgery recovery) reopen from their stamps. Unmeasurable
    store (no psql/conn) consumes NOTHING — honest degrade, mirror of the
    detector. dry_run computes everything and writes nothing.

    SAME-SOURCE BATCHING (2026-07-26): cue-card asks are grouped by the row
    that cued them (``cue_source_key``) and minted at the END of the pass,
    once the whole group is known — N asks cued by ONE row become ONE card
    listing all N (``file_cue_batch_card``); distinct sources stay distinct
    cards; a group of one stays an ordinary per-pair card. His ruling on a
    batched card fans out MECHANICALLY, never as new authority: approve-all
    puts every listed member through the SAME per-item apply path (same
    liveness/type/order guards, same per-member soak-ledger entry, same
    armed-gate requirement), and skip-all records one ``cue-card-skipped``
    entry per member. The batch need is closed with ONE receipt only after
    every member reached a terminal state — closing it on the first apply
    would silently un-approve the rest. While a batch card is ruled, no new
    card is minted for that source: a re-file would rewrite the body the
    ruling was given on, and an approval must never grow members after the
    fact."""
    ppath = proposals_path or PROPOSALS_PATH
    spath = soak_path or SOAK_PATH
    nowdt = _to_dt(now) or _now()
    now_iso = _iso(nowdt)

    mode = load_mode(config_path)
    entries = read_jsonl(spath)
    veto_nid = halfway_veto(needs_path)
    disposition = action_seam_disposition(posture)
    state = seam_hold(
        gate_state(entries, mode, now=nowdt, vetoed=bool(veto_nid)),
        disposition)

    measurable = True
    if live_rows is None:
        live_rows = _mc.load_live_rows()
        if live_rows is None:
            measurable = False
            live_rows = []
    live_by_id = {str(r.get("id")): r for r in live_rows}

    proposals = compact_proposals(read_jsonl(ppath))
    pending = {pid: p for pid, p in proposals.items()
               if str(p.get("status") or "") == "proposed"}
    latest = compact_soak(entries)
    granted_pids = load_granted_pids(needs_path)

    # Batched same-source cards: ONE ruling, N members. Approve-all joins
    # the SAME granted map the per-pair grants use, so every member walks
    # the identical guarded path — the fan-out adds no authority, only
    # fewer cards. Skip-all is recorded per member (below). Membership is
    # read from the card BODY (what he saw), never re-derived.
    batch_rulings = load_batch_rulings(needs_path)
    skipped_pids: Dict[str, str] = {}
    for _nid, _r in sorted(batch_rulings.items()):
        target = (granted_pids if _r["status"] == "approved_pending_apply"
                  else skipped_pids)
        for _pid in _r["members"]:
            target.setdefault(_pid, _nid)
    batch_need_ids = set(batch_rulings)
    ruled_sources = {_r["source_key"] for _r in batch_rulings.values()
                     if _r["source_key"]}

    summary = {"mode": mode, "state": state, "pending": len(pending),
               "consumed": 0, "would_apply": 0, "applied": 0, "cue_cards": 0,
               "cue_batches": 0, "skipped": 0,
               "refused": 0, "blocked": 0, "measurable": measurable,
               "dry_run": dry_run, "halfway_card": None,
               "veto_need": veto_nid,
               "action_mode": disposition["mode"]}
    if not measurable:
        return summary  # nothing classifiable — no stamps, no clock start

    # The Captain's halfway veto BINDS (posture already held above): record
    # ONE observation marker per soak window. The marker is the RECORD; the
    # authority stays the live needs row, re-read every run — so a later
    # binder grant on the card lifts the hold with no ledger surgery. Only
    # written once entries exist (an empty ledger must never get its 14-day
    # clock started by a marker) and never on dry-run.
    if (veto_nid and not dry_run and entries
            and not any(str(e.get("decision") or "") == "captain-veto-hold"
                        for e in entries)):
        append_jsonl(spath, {"ts": now_iso, "decision": "captain-veto-hold",
                             "need_id": veto_nid})

    # Work queue: fresh proposals first, then still-open prior decisions
    # (would_apply/blocked-db re-validate until closed; a cue-card entry
    # missing its need_id re-files the Captain card until one lands; a
    # cue-card the Captain APPROVED — binder grant, status
    # approved_pending_apply — reopens into the apply path; a cue-card he
    # SKIPPED on a batched card reopens once, only to record its own skip),
    # then
    # consumed proposals the soak ledger holds NO entry for — hand-surgery
    # on the ledger must not orphan pairs; their stamps carry enough to
    # re-validate, and already-superseded rows close as refused-superseded.
    open_decisions = ("would_apply", "blocked-db")
    work: List[tuple] = [("proposal", pid, pending[pid])
                         for pid in sorted(pending)]
    for pid, e in sorted(latest.items()):
        if pid in pending:
            continue
        dec_prev = str(e.get("decision") or "")
        if dec_prev in open_decisions or (
                dec_prev == "cue-card" and (not e.get("need_id")
                                            or pid in granted_pids
                                            or pid in skipped_pids)):
            work.append(("reopen", pid, {
                "proposal_id": pid,
                "reason": str(e.get("reason") or "near-duplicate"),
                "cues": e.get("cues") or [],
                "old": {"id": e.get("old_id")},
                "new": {"id": e.get("new_id")},
            }))
    for pid, p in sorted(proposals.items()):
        if pid in pending or pid in latest:
            continue
        if str(p.get("status") or "") != "consumed":
            continue
        if str(p.get("decision") or "") in open_decisions + ("cue-card",):
            work.append(("reopen", pid, p))

    # Windowless liveness probe for rows absent from the detector's 90-day
    # view: absence there means superseded OR merely aged out — the by-id
    # probe (one constant parameterized SELECT, int-validated ids only)
    # tells them apart. Probe unreachable → those pairs stay OPEN as
    # blocked-db, never terminally refused.
    missing: set = set()
    for _origin, _pid, p in work:
        for ref in ("old", "new"):
            ref_d = p.get(ref) if isinstance(p.get(ref), dict) else {}
            try:
                rid_int = int(str((ref_d or {}).get("id")))
            except (TypeError, ValueError):
                continue
            if str(rid_int) not in live_by_id:
                missing.add(rid_int)
    aux_by_id: Optional[Dict[str, dict]] = {}
    if missing:
        fetch = fetch_rows_fn or (
            lambda ids: fetch_rows_by_id(ids, conn_factory=conn_factory))
        fetched = fetch(sorted(missing))
        aux_by_id = (None if fetched is None
                     else {str(r.get("id")): r for r in fetched})

    conn = None
    applies = 0
    touched: set = set()
    results: List[tuple] = []       # (origin, pid, decision) in work order
    try:
        for origin, pid, prop in work:
            d = classify(prop, live_by_id, aux_by_id=aux_by_id,
                         granted=pid in granted_pids)
            old_id_int = d.pop("_old_id_int", None)
            new_id_int = d.pop("_new_id_int", None)
            dec = d["decision"]

            if dec == "cue-card" and pid in skipped_pids:
                # Skip-all: HIS ruling on the batched card, recorded per
                # member so the record is per-pair even though the decision
                # was one. Closes the pair (kept, not superseded) — no card
                # re-file, no reopen next run.
                dec = d["decision"] = "cue-card-skipped"
                d["need_id"] = skipped_pids[pid]
                d["via"] = "captain-skip-all"
                summary["skipped"] += 1
            elif dec == "cue-card":
                # Minted AFTER the loop: the batching decision needs the
                # whole group, and one source's asks must arrive as ONE
                # card. Fingerprint dedup (action_type carries the pid, or
                # the source key for a batch) makes a re-file a count-bump,
                # never spam.
                summary["cue_cards"] += 1
            elif dec == "blocked-db":
                # classify-level indeterminacy (liveness probe unreachable)
                # — open, re-validated next run.
                summary["blocked"] += 1
            elif dec == "would_apply":
                do_apply = state == "armed" and not dry_run
                if do_apply and {old_id_int, new_id_int} & touched:
                    # a row of this pair was already mutated THIS run — the
                    # in-run live view is stale for it. Defer open; next run
                    # re-validates against fresh liveness (the reciprocal of
                    # an applied equal-ts pair then closes refused-*).
                    d["note"] = "deferred-touched-id"
                    do_apply = False
                if do_apply and applies >= MAX_APPLIES_PER_RUN:
                    d["note"] = "deferred-apply-cap"
                    do_apply = False
                if do_apply:
                    if conn is None:
                        try:
                            conn = (conn_factory or default_conn_factory)()
                        except Exception:  # noqa: BLE001 — driver/conn missing
                            conn = None
                    if conn is None:
                        d["decision"] = "blocked-db"
                        d["note"] = "store writer unavailable"
                        summary["blocked"] += 1
                    else:
                        try:
                            ok = apply_pair(conn, old_id_int, new_id_int)
                        except Exception:  # noqa: BLE001
                            d["decision"] = "blocked-db"
                            d["note"] = "update failed"
                            summary["blocked"] += 1
                        else:
                            if ok:
                                d["decision"] = "applied"
                                applies += 1
                                summary["applied"] += 1
                                touched.update((old_id_int, new_id_int))
                            else:
                                # raced: someone superseded it since the read
                                d["decision"] = "refused-raced"
                                summary["refused"] += 1
                else:
                    summary["would_apply"] += 1
            elif dec.startswith("refused-"):
                summary["refused"] += 1

            # Receipt half of the approved-card promise: an approval that
            # EXECUTED closes its need as ``granted`` (grant-apply.sh's
            # mark phase, mirrored — how a pid leaves load_granted_pids);
            # one that turned out MOOT (terminal refusal: row gone/already
            # superseded/raced/order/type) closes as ``superseded``. Open
            # outcomes (would_apply under soak/hold, blocked-db, deferred)
            # leave the need approved — the executor retries next run. A
            # BATCH need is exempt here and closed once below: marking it on
            # the first member's outcome would evict the remaining members
            # out of load_granted_pids and silently un-approve them.
            if (pid in granted_pids and not dry_run
                    and granted_pids[pid] not in batch_need_ids):
                final = d["decision"]
                if final == "applied" or final.startswith("refused-"):
                    d["need_id"] = granted_pids[pid]
                    if final == "applied":
                        _mark_need(granted_pids[pid], "granted",
                                   f"pair {pid} applied (superseded_by "
                                   "set; reversible via --undo)",
                                   mark_need_fn)
                    else:
                        _mark_need(granted_pids[pid], "superseded",
                                   f"pair {pid} closed {final} — the "
                                   "approval is moot", mark_need_fn)
            elif pid in granted_pids and granted_pids[pid] in batch_need_ids:
                # the member rode a batched card — record WHICH one
                d["need_id"] = granted_pids[pid]

            results.append((origin, pid, d))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    # ---- ONE card per source ------------------------------------------
    # Minted here, not in the loop: batching is a decision about the whole
    # group, and the group is only known once every ask is classified.
    if not dry_run:
        _mint_cue_cards(results, summary, ruled_sources=ruled_sources,
                        file_need_fn=file_need_fn)

    # ---- record ---------------------------------------------------------
    if not dry_run:
        for origin, pid, d in results:
            prev = latest.get(pid) or {}
            entry = _ledger_entry(d, ts=now_iso, mode=state)
            changed = str(prev.get("decision") or "") != entry["decision"]
            if not changed and entry["decision"] == "cue-card":
                # same decision, but the card finally got its need id —
                # record it so the reopen loop stops re-filing; while
                # it stays None nothing is appended (no ledger growth,
                # retried next run)
                changed = (bool(entry.get("need_id"))
                           and not prev.get("need_id"))
            if changed:
                append_jsonl(spath, entry)
            if origin == "proposal":
                append_jsonl(ppath, {"proposal_id": pid,
                                     "status": "consumed",
                                     "consumed_at": now_iso,
                                     "decision": entry["decision"]})
                summary["consumed"] += 1

    # ---- ONE receipt per batched card, only once every member closed ----
    if not dry_run:
        _close_batch_needs(results, batch_rulings, latest,
                           mark_need_fn=mark_need_fn)

    # Half-soak Captain heads-up (ONE per soak window): the gate otherwise
    # arms on elapsed time alone. The ledger marker is written only when
    # the card got a need id — a guardian-dark window retries next run.
    # Never re-filed while the Captain's veto stands (the ruling landed;
    # needs-side deny-suppression would no-op the re-file anyway).
    if not dry_run and mode == "soak" and not veto_nid:
        st = soak_stats(entries, now=nowdt)
        already = any(str(e.get("decision") or "") == "soak-halfway-card"
                      for e in entries)
        if (not already and st["days_into_soak"] is not None
                and st["days_into_soak"] >= SOAK_DAYS / 2):
            nid = file_soak_halfway_card(st, state=state,
                                         file_need_fn=file_need_fn)
            if nid:
                append_jsonl(spath, {"ts": now_iso,
                                     "decision": "soak-halfway-card",
                                     "need_id": nid})
                summary["halfway_card"] = nid

    if not dry_run:
        append_jsonl(spath, {"ts": now_iso, "decision": "run", "mode": state,
                             **{k: summary[k] for k in
                                ("pending", "consumed", "would_apply",
                                 "applied", "cue_cards", "refused",
                                 "blocked")}})
    return summary


# ---------------------------------------------------------------------------
# Undo — reverse ONE recorded apply; a reversal re-blocks arming
# ---------------------------------------------------------------------------

def run_undo(line: str, *, soak_path: Optional[Path] = None,
             conn_factory: Optional[Callable] = None,
             now=None, dry_run: bool = False) -> dict:
    """``--undo '<applied soak-ledger json line>'``. Parses the pasted
    ledger line (json.loads — untrusted input never touches SQL text),
    verifies it records an apply, re-nulls the pointer with the guarded
    parameterized statement, and appends a ``reversal`` entry — which
    blocks arming until the Captain rules (a reversal IS the precision
    signal the soak exists to catch; the ruling is recorded with
    ``--resolve-reversals``, never by editing the ledger). An undo
    ATTEMPT latches even when the guarded UPDATE finds nothing to undo
    (``undone: false``) — distrust is the signal, fail-safe."""
    spath = soak_path or SOAK_PATH
    nowdt = _to_dt(now) or _now()
    try:
        rec = json.loads(line)
    except json.JSONDecodeError:
        return {"undone": False, "error": "not a json ledger line"}
    if not isinstance(rec, dict) or rec.get("decision") != "applied":
        return {"undone": False, "error": "not an applied ledger line"}
    try:
        old_id = int(str(rec.get("old_id")))
        new_id = int(str(rec.get("new_id")))
    except ValueError:
        return {"undone": False, "error": "bad ids"}
    if dry_run:
        return {"undone": False, "dry_run": True,
                "old_id": str(old_id), "new_id": str(new_id)}
    try:
        conn = (conn_factory or default_conn_factory)()
    except Exception:  # noqa: BLE001
        return {"undone": False, "error": "store writer unavailable"}
    try:
        ok = undo_pair(conn, old_id, new_id)
    except Exception:  # noqa: BLE001
        return {"undone": False, "error": "update failed"}
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    entry = {"ts": _iso(nowdt), "decision": "reversal",
             "proposal_id": str(rec.get("proposal_id") or ""),
             "old_id": str(old_id), "new_id": str(new_id),
             "undone": bool(ok)}
    append_jsonl(spath, entry)
    return {"undone": ok, "proposal_id": entry["proposal_id"],
            "old_id": entry["old_id"], "new_id": entry["new_id"]}


def run_resolve_reversals(note: str, *, soak_path: Optional[Path] = None,
                          now=None) -> dict:
    """``--resolve-reversals '<why>'`` — the Captain ruling that re-arms a
    reversal-latched gate. Appends ONE ``reversal-resolved`` marker (the
    note is untrusted text: it rides through json.dumps into the ledger
    and nowhere else); ``soak_stats`` counts only reversals AFTER the
    latest marker, so the 14-day clock and every open pair stay intact —
    the supported recovery, never ledger surgery. A non-empty note is
    required: a ruling without a why is not a ruling."""
    spath = soak_path or SOAK_PATH
    if not str(note or "").strip():
        return {"resolved": False,
                "error": "a non-empty ruling note is required"}
    entries = read_jsonl(spath)
    unresolved = soak_stats(entries, now=now)["reversals"]
    if unresolved == 0:
        return {"resolved": False, "error": "no unresolved reversals",
                "reversals_cleared": 0}
    append_jsonl(spath, {"ts": _iso(_to_dt(now) or _now()),
                         "decision": "reversal-resolved",
                         "note": str(note).strip(),
                         "resolved_by": "captain"})
    return {"resolved": True, "reversals_cleared": unresolved}


# ---------------------------------------------------------------------------
# Report — one summary block for the nightly digest
# ---------------------------------------------------------------------------

def build_report(*, proposals_path: Optional[Path] = None,
                 soak_path: Optional[Path] = None,
                 config_path: Optional[Path] = None,
                 needs_path: Optional[Path] = None, now=None,
                 posture: Optional[str] = None) -> dict:
    nowdt = _to_dt(now) or _now()
    mode = load_mode(config_path)
    entries = read_jsonl(soak_path or SOAK_PATH)
    st = soak_stats(entries, now=nowdt)
    veto_nid = halfway_veto(needs_path)
    disposition = action_seam_disposition(posture)
    state = seam_hold(
        gate_state(entries, mode, now=nowdt, vetoed=bool(veto_nid)),
        disposition)
    props = compact_proposals(read_jsonl(proposals_path or PROPOSALS_PATH))
    latest = compact_soak(entries)
    counts = st["counts"]
    return {
        "mode": mode, "state": state, "veto_need": veto_nid,
        "action_mode": disposition["mode"],
        "days_into_soak": (round(st["days_into_soak"], 2)
                           if st["days_into_soak"] is not None else None),
        "first_entry": st["first_entry"],
        "proposals_total": len(props),
        "proposals_consumed": sum(1 for p in props.values()
                                  if p.get("status") == "consumed"),
        "proposals_pending": sum(1 for p in props.values()
                                 if p.get("status") == "proposed"),
        "open_would_apply": sum(
            1 for e in latest.values()
            if str(e.get("decision")) in ("would_apply", "blocked-db")),
        "proposed": counts.get("would_apply", 0),
        "applied": counts.get("applied", 0),
        "reverted": counts.get("reversal", 0),
        "reversals_unresolved": st["reversals"],
        "cue_cards": counts.get("cue-card", 0),
        "refused": sum(v for k, v in counts.items()
                       if k.startswith("refused-")),
        "blocked": counts.get("blocked-db", 0),
    }


def render_report(rep: dict) -> str:
    days = rep["days_into_soak"]
    day_str = f"{days:.1f}" if isinstance(days, (int, float)) else "-"
    veto = (f", captain-veto={rep['veto_need']}"
            if rep.get("veto_need") else "")
    seam = (f", action-mode={rep['action_mode']}"
            if rep.get("action_mode") else "")
    return "\n".join([
        "memory-supersession soak report",
        f"  posture: {rep['state']} (auto_apply={rep['mode']}, "
        f"soak day {day_str}/{SOAK_DAYS}, reverted={rep['reverted']}, "
        f"unresolved-reversals={rep['reversals_unresolved']}{veto}{seam})",
        f"  proposals: {rep['proposals_total']} total / "
        f"{rep['proposals_consumed']} consumed / "
        f"{rep['proposals_pending']} pending",
        f"  decisions: would-apply={rep['proposed']} "
        f"(open {rep['open_would_apply']}) applied={rep['applied']} "
        f"reverted={rep['reverted']} cue-cards={rep['cue_cards']} "
        f"refused={rep['refused']} blocked={rep['blocked']}",
    ])


def main(argv: Optional[List[str]] = None) -> int:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(
        description="Apply organ for cabinet_memory supersession — consume "
                    "detector proposals; soak, then (near-dup class only, "
                    "post-soak) apply; cue class files Captain cards.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--report", action="store_true",
                        help="print the soak summary block and exit")
    parser.add_argument("--undo", metavar="LEDGER_LINE",
                        help="reverse one apply: paste its soak-ledger line")
    parser.add_argument("--resolve-reversals", metavar="NOTE",
                        help="Captain ruling: clear the reversal latch "
                             "(appends a reversal-resolved marker; a "
                             "non-empty why is required)")
    args = parser.parse_args(argv)
    if args.report:
        rep = build_report()
        print(json.dumps(rep, sort_keys=True) if args.json
              else render_report(rep))
        return 0
    if args.undo:
        res = run_undo(args.undo, dry_run=args.dry_run)
        print(json.dumps(res, sort_keys=True))
        return 0 if (res.get("undone") or res.get("dry_run")) else 1
    if args.resolve_reversals is not None:
        res = run_resolve_reversals(args.resolve_reversals)
        print(json.dumps(res, sort_keys=True))
        return 0 if res.get("resolved") else 1
    summary = run_apply_pass(dry_run=args.dry_run)
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        note = "" if summary["measurable"] else \
            " ALERT: cabinet_memory unmeasurable (psql/conn unavailable)"
        print(f"memory-supersede-apply: state={summary['state']} "
              f"pending={summary['pending']} consumed={summary['consumed']} "
              f"would_apply={summary['would_apply']} "
              f"applied={summary['applied']} cue_cards={summary['cue_cards']} "
              f"refused={summary['refused']} blocked={summary['blocked']}"
              + (" (dry-run)" if summary["dry_run"] else "") + note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
