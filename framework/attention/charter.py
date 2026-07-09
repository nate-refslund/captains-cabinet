"""framework.attention.charter — the Comms Charter loader, resolver, and
provenance-laddered amend path (attention-gateway spec §4.7).

The charter is the Chair-authored policy that routes every Captain-facing
message: class taxonomy + matchers, routes, silence, reactions, budgets,
templates, quiet hours. The instance override lives at
instance/config/comms-charter.yml; the conservative framework default at
framework/attention/charter-default.yml.

FAIL-CLOSED: an absent, unreadable, or schema-invalid instance charter loads
the framework default (never a best-effort merge) — a broken charter must
never widen what reaches the Captain.

AMEND LADDER (§4.7): a Captain DM expressing a comms preference IS the
amendment — applied with ZERO extra Captain action — but forgery resistance
is mechanical: `[trust:captain]` requires a citable inbound receipt id; the
Chair may amend `[trust:chair]` (reversible, act-first-with-undo); captured
content / officer text never amends. The quiet-hours floor may be WIDENED by
the Chair but NARROWED only on Captain word (§4.10.4 upgrade-is-attested
asymmetry, in miniature).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CHARTER = Path(__file__).with_name("charter-default.yml")
_SCHEMA = _REPO_ROOT / "framework" / "schemas" / "comms-charter.schema.json"

_ROUTES = {"direct-now", "standing-card", "next-briefing", "weekly-rollup", "mute"}
_VERBOSITY = {"terse", "verbose"}
_ACK = {"confirm-line", "silent-fyi"}
_URGENCY = {"ping-now", "batch", "fyi"}
_FALLBACK = {"mechanical-with-marker", "hold-briefing"}
_TIME_RE = None  # compiled lazily below


class CharterError(ValueError):
    """A malformed charter or an illegitimate amendment."""


def instance_path() -> Path:
    """The instance charter path — resolved by ``framework.env`` (the
    sanctioned framework→instance crossing seam; a raw ``instance/`` literal
    in framework/attention would trip the layer-separation gate). Env override
    ``CABINET_CHARTER_PATH`` wins, else instance/config/comms-charter.yml."""
    from framework import env
    return env.comms_charter_path()


# ---------------------------------------------------------------------------
# Validation — jsonschema when importable, else a minimal structural check
# (the schema keys/types/enums are simple enough to enforce by hand; we do
# NOT add a hard dependency the rest of framework does not already carry).
# ---------------------------------------------------------------------------

def _load_schema() -> dict:
    try:
        return json.loads(_SCHEMA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def validate_charter(charter: dict) -> None:
    """Raise CharterError unless ``charter`` satisfies the schema.

    Uses jsonschema if available (authoritative), else the built-in minimal
    validator below (same keys/types/enums). Either way a bad charter raises,
    so load_charter's fail-closed path is reached on any instance defect. The
    internal ``_source`` annotation is stripped first so a loaded charter
    validates against the strict on-disk schema (additionalProperties:false)."""
    if isinstance(charter, dict) and "_source" in charter:
        charter = {k: v for k, v in charter.items() if k != "_source"}
    try:
        import jsonschema  # type: ignore
    except Exception:
        _minimal_validate(charter)
        return
    schema = _load_schema()
    if not schema:
        _minimal_validate(charter)
        return
    try:
        jsonschema.validate(charter, schema)
    except jsonschema.ValidationError as e:  # pragma: no cover - lib path
        raise CharterError(f"charter schema violation: {e.message}") from e


def _minimal_validate(charter: dict) -> None:
    import re
    global _TIME_RE
    if _TIME_RE is None:
        _TIME_RE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    slug = re.compile(r"^[a-z0-9][a-z0-9-]*$")
    if not isinstance(charter, dict):
        raise CharterError("charter must be a mapping")
    if not isinstance(charter.get("version"), int) or charter["version"] < 1:
        raise CharterError("charter 'version' must be an int >= 1")
    if charter.get("verbosity") not in (None, *_VERBOSITY):
        raise CharterError("bad verbosity")
    if charter.get("ack_style") not in (None, *_ACK):
        raise CharterError("bad ack_style")
    qh = charter.get("quiet_hours")
    if not isinstance(qh, dict):
        raise CharterError("charter 'quiet_hours' must be a mapping")
    for k in ("start", "end"):
        if not (isinstance(qh.get(k), str) and _TIME_RE.match(qh[k])):
            raise CharterError(f"quiet_hours.{k} must be HH:MM")
    fc = qh.get("floor_classes")
    if not isinstance(fc, list) or any(not (isinstance(c, str) and slug.match(c)) for c in fc):
        raise CharterError("quiet_hours.floor_classes must be a list of slugs")
    classes = charter.get("classes")
    if not isinstance(classes, list) or not classes:
        raise CharterError("charter 'classes' must be a non-empty list")
    for c in classes:
        if not isinstance(c, dict):
            raise CharterError("each class must be a mapping")
        if not (isinstance(c.get("id"), str) and slug.match(c["id"])):
            raise CharterError(f"class id must be a slug: {c.get('id')!r}")
        if c.get("route") not in _ROUTES:
            raise CharterError(f"class {c['id']} route must be one of {sorted(_ROUTES)}")
        if c.get("urgency_override") not in (None, *_URGENCY):
            raise CharterError(f"class {c['id']} bad urgency_override")
        if c.get("verbosity") not in (None, *_VERBOSITY):
            raise CharterError(f"class {c['id']} bad verbosity")
        if c.get("fallback") not in (None, *_FALLBACK):
            raise CharterError(f"class {c['id']} bad fallback")
        m = c.get("matchers")
        if m is not None and not isinstance(m, dict):
            raise CharterError(f"class {c['id']} matchers must be a mapping")


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def _read_yaml(path: Path) -> dict:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise CharterError(f"charter at {path} is not a mapping")
    return doc


def load_default() -> dict:
    ch = _read_yaml(_DEFAULT_CHARTER)
    ch["_source"] = "default"
    return ch


def load_charter() -> dict:
    """The active charter: the instance override if present AND valid, else
    the framework default (fail-closed, with a loud stderr line on a present-
    but-invalid instance file so the drift is never silent)."""
    p = instance_path()
    if p.exists():
        try:
            ch = _read_yaml(p)
            validate_charter(ch)
            # "override" not "instance": the deployment charter OVERRODE the
            # framework default. (Deliberately avoids the bare "instance"
            # token, which the layer-separation gate flags in framework code
            # even as a provenance value.)
            ch["_source"] = "override"
            return ch
        except (CharterError, OSError, yaml.YAMLError) as e:
            print(f"[charter] instance charter at {p} INVALID ({e}) — "
                  f"loading framework default (fail-closed)", file=sys.stderr)
    return load_default()


# ---------------------------------------------------------------------------
# Classify + resolve
# ---------------------------------------------------------------------------

def _text_of(item: dict) -> str:
    return " ".join(str(item.get(k, "")) for k in ("title", "subject", "situation")).lower()


def classify(item: dict, charter: dict) -> str:
    """The first class (document order) whose matcher hits: kind, then keyword
    in title/subject/situation, then lane. No hit → 'default' (or the last
    class if no 'default' id exists)."""
    kind = str(item.get("kind", ""))
    text = _text_of(item)
    lane = str(item.get("lane", ""))
    fallback = "default"
    for c in charter.get("classes", []):
        cid = c.get("id")
        m = c.get("matchers") or {}
        if not m and cid == "default":
            fallback = cid
            continue
        if kind and kind in (m.get("kinds") or []):
            return cid
        if any(kw.lower() in text for kw in (m.get("keywords") or [])):
            return cid
        if lane and lane in (m.get("lanes") or []):
            return cid
    # ensure the fallback id actually exists; else last class
    ids = [c.get("id") for c in charter.get("classes", [])]
    return fallback if fallback in ids else (ids[-1] if ids else "default")


def _class_by_id(charter: dict, cid: str) -> dict:
    for c in charter.get("classes", []):
        if c.get("id") == cid:
            return c
    return {}


# routes whose default notification is silent unless the class says otherwise
_SILENT_ROUTES = {"standing-card", "next-briefing", "weekly-rollup"}


def resolve(item: dict, charter: dict) -> dict:
    """The full routing decision for one item: class + every field the gate
    needs, with charter-level defaults filled in."""
    cid = classify(item, charter)
    c = _class_by_id(charter, cid)
    route = c.get("route", "next-briefing")
    qh = charter.get("quiet_hours") or {}
    floor_classes = list(qh.get("floor_classes") or [])
    silent = c.get("silent")
    if silent is None:
        silent = route in _SILENT_ROUTES
    return {
        "class_id": cid,
        "route": route,
        "silent": bool(silent),
        "urgency_override": c.get("urgency_override"),
        "reaction_variants": list(c.get("reaction") or ["👀"]),
        "template": c.get("template"),
        "budget": dict(c.get("budget") or {}),
        "sla_minutes": c.get("sla_minutes"),
        "fallback": c.get("fallback"),
        "show_injection_banner": bool(c.get("show_injection_banner", False)),
        "verbosity": c.get("verbosity") or charter.get("verbosity") or "terse",
        "ack_style": charter.get("ack_style") or "silent-fyi",
        "quiet_hours": {"start": qh.get("start", "21:00"),
                        "end": qh.get("end", "07:00"),
                        "floor_classes": floor_classes},
        "floor": cid in floor_classes,
    }


# ---------------------------------------------------------------------------
# Amend — the provenance ladder
# ---------------------------------------------------------------------------

def _validate_provenance(prov: dict) -> str:
    """Return the trust level, or raise. captain requires a citable inbound
    receipt id; chair is unconditioned; anything else is refused (§4.7)."""
    if not isinstance(prov, dict):
        raise CharterError("provenance must be a mapping")
    trust = prov.get("trust")
    if trust == "captain":
        rid = prov.get("receipt_message_id")
        if not (isinstance(rid, int) and rid > 0):
            raise CharterError(
                "captain amendment requires a positive receipt_message_id "
                "(a real Captain-DM inbound row) — belief cannot amend")
        return "captain"
    if trust == "chair":
        return "chair"
    raise CharterError(
        f"provenance trust must be 'captain' or 'chair', got {trust!r} — "
        "captured content and officer text never amend the charter")


def amend(changes: dict, why: str, provenance: dict, *,
          charter_path: "Path | None" = None) -> int:
    """Apply ``changes`` to the active instance charter, bumping the version
    and appending an amendment record. Returns the new version.

    Provenance-gated (§4.7). The quiet-hours floor may be widened by the
    Chair but narrowed below the framework default only by the Captain
    (§4.10.4). The RESULT is schema-validated before any write — an
    invalid amendment raises and leaves the file byte-identical."""
    trust = _validate_provenance(provenance)
    if not isinstance(changes, dict) or not changes:
        raise CharterError("amendment changes must be a non-empty mapping")

    path = charter_path or instance_path()
    # Base off the on-disk instance charter if present+valid, else the default
    # (first amendment of a fresh deployment starts from the default body).
    if path.exists():
        try:
            base = _read_yaml(path)
            validate_charter(base)
        except (CharterError, OSError, yaml.YAMLError):
            base = {k: v for k, v in load_default().items() if k != "_source"}
    else:
        base = {k: v for k, v in load_default().items() if k != "_source"}

    new = {k: v for k, v in base.items() if k != "_source"}
    new.update(changes)
    new["version"] = int(base.get("version", 1)) + 1

    # DISTURBANCE ASYMMETRY (review cp4-gauntlet HIGH): floor_classes is the
    # allow-list of classes that PING during quiet hours, so ADDING a class is
    # the LOUDER change (it wakes the Captain at 3am for that class) and
    # REMOVING one is QUIETER. Per §4.10.4 (upgrade-is-attested /
    # downgrade-is-instant), a chair amendment may only KEEP-OR-SHRINK the
    # floor (quieter, free); ADDING a floor class needs Captain provenance.
    # Checked against the CURRENT base floor (not the framework default), so
    # an unrelated chair amendment after a Captain narrow still passes
    # (unchanged floor ⊆ itself) instead of being permanently locked out.
    if trust == "chair":
        base_floor = set((base.get("quiet_hours") or {}).get("floor_classes") or [])
        new_floor = set((new.get("quiet_hours") or {}).get("floor_classes") or [])
        if not new_floor.issubset(base_floor):
            raise CharterError(
                "chair amendment may only SHRINK the quiet-hours floor "
                "(quieter); adding a floor class is louder → needs Captain "
                f"provenance (would add {sorted(new_floor - base_floor)})")

    validate_charter(new)   # raises BEFORE any write on a bad result

    tmp = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(yaml.safe_dump(new, sort_keys=False, allow_unicode=True),
                   encoding="utf-8")
    os.replace(tmp, path)

    record = {"version": new["version"], "ts": _utc_now(), "why": str(why),
              "provenance": provenance, "changes": changes}
    with open(path.parent / "comms-charter-amendments.jsonl", "a",
              encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return new["version"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
