"""framework.frontdoor.charter_amend — the one-sentence Comms-Charter amend
path behind the binder's ``charter:`` verb (attention-gateway spec §4.7; the
promise in framework/attention/charter-default.yml's header).

PROPOSE-ONLY by construction (autonomy law): ``request()`` turns the Captain's
one sentence into a machine-derived yaml override, validates the WHOLE merged
result against the charter schema (fail-closed: invalid ⇒ CharterError with
the schema error, nothing written), and files a pending card — it never
touches the charter file. ``grant()`` applies a pending amendment through
``framework.attention.charter.amend`` (which re-validates and writes
atomically), with §4.10.4 disturbance-asymmetry provenance:

  * QUIETEN-only amendments (provably quieter: floor shrink, route demotion,
    longer quiet window, terse, silent-fyi, lower caps) auto-apply on grant
    under chair trust (reversible, act-first-with-undo ladder rung).
  * Anything LOUDER applies ONLY with the Captain's grant receipt — the
    citable inbound Telegram message id of the grant reply itself. The grant
    IS the provenance: it rides the amendment ledger row as
    ``{trust: captain, receipt_message_id: <grant reply id>}``. No receipt ⇒
    refuse, nothing written. Neutral/ambiguous classifies as louder
    (conservative — only provably-quieter skips attestation).

Free text NEVER becomes a yaml value: the sentence grammar maps onto fixed
enums, HH:MM-validated times, bounded ints, and class slugs that must already
exist in the active charter. Unparseable ⇒ refuse listing the supported
forms. The pending store is an append-only last-write-wins jsonl sidecar of
the charter path (deployment-local, gitignored, like the amendments ledger).
No network, no subprocess; yaml.safe_load/safe_dump only.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from framework.attention import charter
from framework.attention.charter import CharterError

_ID_RE = re.compile(r"^CHM-[0-9a-f]{8}$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_TIME = r"(?:[01][0-9]|2[0-3]):[0-5][0-9]"

# Loudness ranking of routes — higher disturbs the Captain more. Used ONLY to
# classify a route change as quieten (rank drops) vs louder (anything else).
_ROUTE_RANK = {"mute": 0, "weekly-rollup": 1, "next-briefing": 2,
               "standing-card": 3, "direct-now": 4}
_ROUTES = set(_ROUTE_RANK)

# --- the one-sentence grammar (whole-sentence anchored, case-insensitive) ----
# Every form maps to a bounded intent; anything else is refused with this
# menu. Kept deterministic on purpose (loop.py's v1-heuristic house rule):
# the Chair LLM may still call charter.amend() natively for richer sentences.
SUPPORTED_FORMS = (
    "quiet hours <HH:MM> to <HH:MM>",
    "verbose | terse",
    "ack confirm-line | ack silent-fyi",
    "decisions cap <N> | show at most <N> decisions",
    "wake me for <class>",
    "stop waking me for <class> | don't wake me for <class>",
    "route <class> <direct-now|standing-card|next-briefing|weekly-rollup|mute>",
    "mute <class>",
)

_TAIL = r"\s*[.!]?\s*$"
_WINDOW_RE = re.compile(
    rf"^\s*quiet\s+hours\s+({_TIME})\s*(?:to|until|[-–—])\s*({_TIME}){_TAIL}",
    re.IGNORECASE)
_VERBOSITY_RE = re.compile(rf"^\s*(?:be\s+)?(verbose|terse){_TAIL}", re.IGNORECASE)
_ACK_RE = re.compile(rf"^\s*ack\s+(confirm-line|silent-fyi){_TAIL}", re.IGNORECASE)
_CAP_RE = re.compile(
    rf"^\s*(?:decisions\s+cap\s+(\d{{1,2}})|show\s+at\s+most\s+(\d{{1,2}})\s+decisions){_TAIL}",
    re.IGNORECASE)
_FLOOR_ADD_RE = re.compile(
    rf"^\s*wake\s+me\s+for\s+([a-z0-9][a-z0-9-]*){_TAIL}", re.IGNORECASE)
_FLOOR_REMOVE_RE = re.compile(
    rf"^\s*(?:stop\s+waking\s+me\s+for|do\s*n[o']t\s+wake\s+me\s+for)\s+"
    rf"([a-z0-9][a-z0-9-]*){_TAIL}", re.IGNORECASE)
_ROUTE_RE = re.compile(
    rf"^\s*route\s+([a-z0-9][a-z0-9-]*)\s+(?:to\s+)?"
    rf"(direct-now|standing-card|next-briefing|weekly-rollup|mute){_TAIL}",
    re.IGNORECASE)
_MUTE_RE = re.compile(rf"^\s*mute\s+([a-z0-9][a-z0-9-]*){_TAIL}", re.IGNORECASE)


def parse_sentence(sentence: str) -> dict:
    """The Captain's one sentence → a bounded intent dict, or CharterError.

    Intent shapes (nothing else exists):
      {"op": "quiet_window", "start": HH:MM, "end": HH:MM}
      {"op": "set", "key": "verbosity"|"ack_style", "value": <schema enum>}
      {"op": "decisions_cap", "value": int 1..99}
      {"op": "floor_add"|"floor_remove", "class_id": <slug>}
      {"op": "route", "class_id": <slug>, "route": <schema route enum>}
    """
    t = " ".join(str(sentence or "").split())
    if not t:
        raise CharterError("empty amendment sentence — refused, nothing written")
    m = _WINDOW_RE.match(t)
    if m:
        start, end = m.group(1), m.group(2)
        if start == end:
            raise CharterError(
                "start == end is the zero-length (disabled) window — disabling "
                "quiet hours is the interview's explicit verb, not a one-line "
                "amendment; refused, nothing written")
        return {"op": "quiet_window", "start": start, "end": end}
    m = _VERBOSITY_RE.match(t)
    if m:
        return {"op": "set", "key": "verbosity", "value": m.group(1).lower()}
    m = _ACK_RE.match(t)
    if m:
        return {"op": "set", "key": "ack_style", "value": m.group(1).lower()}
    m = _CAP_RE.match(t)
    if m:
        n = int(m.group(1) or m.group(2))
        if n < 1:
            raise CharterError("decisions cap must be >= 1 — refused")
        return {"op": "decisions_cap", "value": n}
    m = _FLOOR_REMOVE_RE.match(t)   # before floor_add: both mention "wake me"
    if m:
        return {"op": "floor_remove", "class_id": m.group(1).lower()}
    m = _FLOOR_ADD_RE.match(t)
    if m:
        return {"op": "floor_add", "class_id": m.group(1).lower()}
    m = _ROUTE_RE.match(t)
    if m:
        return {"op": "route", "class_id": m.group(1).lower(),
                "route": m.group(2).lower()}
    m = _MUTE_RE.match(t)
    if m:
        return {"op": "route", "class_id": m.group(1).lower(), "route": "mute"}
    raise CharterError(
        "could not parse the amendment sentence — supported forms: "
        + "; ".join(SUPPORTED_FORMS)
        + ". (Full control: edit the deployment charter override by hand — "
          "see comms-charter.yml.example next to it.)")


# ---------------------------------------------------------------------------
# Base + derive + classify
# ---------------------------------------------------------------------------

def _read_mapping(path: Path) -> dict:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise CharterError(f"charter at {path} is not a mapping")
    return doc


def _amend_base(path: Path) -> dict:
    """The charter body an amendment applies over — EXACTLY charter.amend()'s
    own base resolution (deployment override if present+valid, else the
    framework default), so preview and apply can never disagree."""
    if path.exists():
        try:
            base = _read_mapping(path)
            charter.validate_charter(base)
            return {k: v for k, v in base.items() if k != "_source"}
        except (CharterError, OSError, yaml.YAMLError):
            pass
    return {k: v for k, v in charter.load_default().items() if k != "_source"}


def _quiet_hours_of(base: dict) -> dict:
    qh = base.get("quiet_hours") or {}
    return {"start": str(qh.get("start", "21:00")),
            "end": str(qh.get("end", "07:00")),
            "floor_classes": [str(c) for c in (qh.get("floor_classes") or [])]}


def _class_ids(base: dict) -> list[str]:
    return [str(c.get("id")) for c in (base.get("classes") or [])
            if isinstance(c, dict)]


def derive(base: dict, intent: dict) -> dict:
    """intent → the top-level ``changes`` mapping charter.amend applies
    (full quiet_hours / classes objects with ONLY the one dial moved — every
    other field carried unchanged, the quiet_hours.py house rule). Returns {}
    when the intent already rules (honest no-op); raises CharterError when the
    intent no longer applies (unknown class — free text never mints one)."""
    op = intent.get("op")
    if op == "set":
        key, value = intent["key"], intent["value"]
        if base.get(key) == value:
            return {}
        return {key: value}
    if op == "decisions_cap":
        aq = dict(base.get("attention_queue") or {})
        if aq.get("decisions_render_cap") == intent["value"]:
            return {}
        aq["decisions_render_cap"] = int(intent["value"])
        return {"attention_queue": aq}
    if op == "quiet_window":
        qh = _quiet_hours_of(base)
        if (qh["start"], qh["end"]) == (intent["start"], intent["end"]):
            return {}
        qh["start"], qh["end"] = intent["start"], intent["end"]
        return {"quiet_hours": qh}
    if op in ("floor_add", "floor_remove"):
        cid = intent["class_id"]
        qh = _quiet_hours_of(base)
        floor = list(qh["floor_classes"])
        if op == "floor_add":
            if cid not in _class_ids(base):
                raise CharterError(
                    f"unknown class {cid!r} — a floor entry must name an "
                    f"existing charter class (have: "
                    f"{', '.join(_class_ids(base))}); refused, nothing written")
            if cid in floor:
                return {}
            floor.append(cid)
        else:
            if cid not in floor:
                return {}
            floor = [c for c in floor if c != cid]
        qh["floor_classes"] = floor
        return {"quiet_hours": qh}
    if op == "route":
        cid, route = intent["class_id"], intent["route"]
        classes = [dict(c) for c in (base.get("classes") or [])
                   if isinstance(c, dict)]
        target = next((c for c in classes if c.get("id") == cid), None)
        if target is None:
            raise CharterError(
                f"unknown class {cid!r} — a route change must name an "
                f"existing charter class (have: "
                f"{', '.join(_class_ids(base))}); refused, nothing written")
        if target.get("route") == route:
            return {}
        target["route"] = route
        return {"classes": classes}
    raise CharterError(f"unknown amendment op {op!r} — refused")


def _quiet_minutes(start: str, end: str) -> int:
    """Length of the quiet window in minutes; start == end ⇒ 0 (disabled —
    the LOUDEST window, per the gate's structural never-match)."""
    def _m(t: str) -> int:
        h, mn = t.split(":")
        return int(h) * 60 + int(mn)
    return (_m(end) - _m(start)) % (24 * 60)


def classify(base: dict, intent: dict) -> str:
    """'quieten' | 'louder' — the §4.10.4 disturbance classification.

    CONSERVATIVE: only a provably-quieter move classifies as quieten; every
    other move (louder, neutral, ambiguous — e.g. an equal-length shifted
    window) is 'louder' and keeps explicit Captain provenance on grant."""
    op = intent.get("op")
    if op == "floor_add":
        return "louder"
    if op == "floor_remove":
        return "quieten"
    if op == "set":
        if intent["key"] == "verbosity":
            return "quieten" if intent["value"] == "terse" else "louder"
        return "quieten" if intent["value"] == "silent-fyi" else "louder"
    if op == "decisions_cap":
        cur = (base.get("attention_queue") or {}).get("decisions_render_cap", 7)
        return "quieten" if int(intent["value"]) < int(cur) else "louder"
    if op == "quiet_window":
        qh = _quiet_hours_of(base)
        cur = _quiet_minutes(qh["start"], qh["end"])
        new = _quiet_minutes(intent["start"], intent["end"])
        return "quieten" if new > cur else "louder"
    if op == "route":
        classes = base.get("classes") or []
        target = next((c for c in classes
                       if isinstance(c, dict) and c.get("id") == intent["class_id"]),
                      {})
        cur = _ROUTE_RANK.get(str(target.get("route")), _ROUTE_RANK["direct-now"])
        new = _ROUTE_RANK[intent["route"]]
        return "quieten" if new < cur else "louder"
    return "louder"


# ---------------------------------------------------------------------------
# Rendered yaml diff (the card body)
# ---------------------------------------------------------------------------

def _dump(obj: dict) -> list[str]:
    return yaml.safe_dump(obj, sort_keys=False,
                          allow_unicode=True).rstrip().splitlines()


def render_yaml_diff(base: dict, changes: dict) -> str:
    """Old→new yaml for exactly the changed subtrees (-/+ lines). For a
    classes change only the affected class mapping is rendered, never the
    whole taxonomy."""
    lines: list[str] = []
    for key, new_val in changes.items():
        old_val = base.get(key)
        if key == "classes":
            old_by = {c.get("id"): c for c in (old_val or [])
                      if isinstance(c, dict)}
            for c in new_val:
                oc = old_by.get(c.get("id"))
                if oc == c:
                    continue
                label = f"classes[{c.get('id')}]"
                if oc is not None:
                    lines += ["- " + l for l in _dump({label: dict(oc)})]
                lines += ["+ " + l for l in _dump({label: dict(c)})]
        else:
            if old_val is not None:
                lines += ["- " + l for l in _dump({key: old_val})]
            lines += ["+ " + l for l in _dump({key: new_val})]
    out = "\n".join(lines)
    return out if len(out) <= 1600 else out[:1600] + "\n…"


def render_card(row: dict) -> str:
    """The propose-only card. LOUDER cards document the provenance law: the
    grant reply itself is the citable Captain provenance that applies them."""
    if row.get("classification") == "quieten":
        cls_line = ("quieten — auto-applies on grant (chair provenance, "
                    "§4.10.4 quieter-is-free)")
    else:
        cls_line = ("LOUDER — applies only with YOUR grant as Captain "
                    "provenance (the grant reply's receipt id is recorded, "
                    "§4.10.4)")
    return (f"📜 Charter amendment {row['id']} proposed — nothing applied yet.\n"
            f"“{row.get('sentence', '')}”\n"
            f"Class: {cls_line}\n"
            f"{row.get('preview', '')}\n"
            f"Reply `charter grant {row['id']}` to apply, "
            f"`charter drop {row['id']}` to discard.")


# ---------------------------------------------------------------------------
# Pending store — append-only last-write-wins jsonl sidecar
# ---------------------------------------------------------------------------

def proposals_path(charter_path: "Path | None" = None) -> Path:
    p = Path(charter_path) if charter_path else charter.instance_path()
    return p.parent / "comms-charter-proposals.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_row(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _merged(path: Path) -> dict:
    rows: dict = {}
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            rows[row["id"]] = {**rows.get(row["id"], {}), **row}
    return rows


def _fingerprint(intent: dict) -> str:
    digest = hashlib.sha256(
        json.dumps(intent, sort_keys=True).encode("utf-8")).hexdigest()
    return "CHM-" + digest[:8]


def _check_id(amend_id: str) -> str:
    if not (isinstance(amend_id, str) and _ID_RE.match(amend_id)):
        raise CharterError(f"malformed charter-amend id {amend_id!r}")
    return amend_id


# ---------------------------------------------------------------------------
# The three verbs
# ---------------------------------------------------------------------------

def request(sentence: str, *, charter_path: "Path | None" = None) -> dict:
    """File the Captain's one-sentence amendment PROPOSE-ONLY.

    Parse → derive the machine changes against the live base → validate the
    ENTIRE merged result against the charter schema (fail-closed: any
    CharterError refuses with the schema error and NOTHING is written — not
    even a pending row) → append the pending row → return the card. The
    charter file itself is never touched here."""
    path = Path(charter_path) if charter_path else charter.instance_path()
    intent = parse_sentence(sentence)
    base = _amend_base(path)
    changes = derive(base, intent)
    if not changes:
        raise CharterError(
            "the charter already rules exactly that — nothing to amend")
    merged = {k: v for k, v in base.items()}
    merged.update(changes)
    merged["version"] = int(base.get("version", 1)) + 1
    charter.validate_charter(merged)   # refuse BEFORE any write
    classification = classify(base, intent)
    row = {
        "id": _fingerprint(intent),
        "ts": _utc_now(),
        "status": "proposed",
        # ``·`` is the binder's proposal-marker delimiter — never allow the
        # sentence to smuggle one onto a card (same strip as _grant_receipt).
        "sentence": " ".join(str(sentence).split()).replace("·", "")[:280],
        "intent": intent,
        "classification": classification,
        "preview": render_yaml_diff(base, changes),
    }
    _append_row(proposals_path(path), row)
    return {"amend_id": row["id"], "classification": classification,
            "card": render_card(row), "changes": changes, "row": row}


def grant(amend_id: str, *, receipt_message_id: "int | None" = None,
          charter_path: "Path | None" = None) -> dict:
    """Apply a pending amendment — the Captain's grant.

    Re-derives against the LIVE base (the charter may have moved since the
    card) and re-classifies; the APPLY-TIME classification picks the §4.10.4
    provenance: quieten ⇒ chair trust (auto-apply on grant), louder ⇒ requires
    ``receipt_message_id`` (the grant reply's own inbound Telegram id — the
    grant IS the provenance) else refuses with nothing written. The write
    itself rides charter.amend (schema re-validated, atomic, ledger row)."""
    _check_id(amend_id)
    path = Path(charter_path) if charter_path else charter.instance_path()
    pp = proposals_path(path)
    row = _merged(pp).get(amend_id)
    if row is None:
        raise CharterError(
            f"unknown charter-amend id {amend_id} — nothing granted")
    if row.get("status") != "proposed":
        raise CharterError(
            f"{amend_id} is {row.get('status')!r} — nothing to grant")
    intent = row.get("intent") or {}
    base = _amend_base(path)
    changes = derive(base, intent)     # may refuse: intent no longer applies
    if not changes:
        _append_row(pp, {"id": amend_id, "ts": _utc_now(),
                         "status": "applied-noop"})
        return {"applied": False, "amend_id": amend_id,
                "note": "already rules — honest no-op, nothing written"}
    classification = classify(base, intent)
    provenance: dict = {"via": "charter-amend-verb", "amend_id": amend_id}
    if classification == "quieten":
        provenance["trust"] = "chair"
        if isinstance(receipt_message_id, int) and receipt_message_id > 0:
            provenance["receipt_message_id"] = receipt_message_id
    else:
        if not (isinstance(receipt_message_id, int) and receipt_message_id > 0):
            raise CharterError(
                "a LOUDER amendment applies only with the Captain's citable "
                "grant receipt (§4.10.4 upgrade-is-attested): the grant "
                "reply's inbound message id was not available — refused, "
                "nothing written")
        provenance["trust"] = "captain"
        provenance["receipt_message_id"] = receipt_message_id
    why = f"charter-amend {amend_id} ({classification}): {row.get('sentence', '')}"
    version = charter.amend(changes, why, provenance, charter_path=path)
    _append_row(pp, {"id": amend_id, "ts": _utc_now(), "status": "applied",
                     "version": version, "classification": classification})
    return {"applied": True, "amend_id": amend_id, "version": version,
            "classification": classification}


def drop(amend_id: str, why: str = "", *,
         charter_path: "Path | None" = None) -> dict:
    """Discard a pending amendment. Nothing is ever written to the charter."""
    _check_id(amend_id)
    path = Path(charter_path) if charter_path else charter.instance_path()
    pp = proposals_path(path)
    row = _merged(pp).get(amend_id)
    if row is None:
        raise CharterError(
            f"unknown charter-amend id {amend_id} — nothing dropped")
    if row.get("status") != "proposed":
        raise CharterError(
            f"{amend_id} is {row.get('status')!r} — nothing to drop")
    _append_row(pp, {"id": amend_id, "ts": _utc_now(), "status": "dropped",
                     "why": " ".join(str(why or "").split())[:200]})
    return {"dropped": True, "amend_id": amend_id}
