"""framework.onboarding.estate — the DERIVED ESTATE: what the cabinet READ.

The ordering inversion (Captain ruling 2026-07-26, adjudicated in the altitude
direction gate): the cabinet must READ the operator's world instead of
interviewing them about it. ``connect -> explore -> structure -> converse``.
Before this module the only description of that world was the cabinet-init
interview, and ``generate-instance.py`` REFUSED to generate without at least
one declared lane — so a developer inside a large company, who owns no lane,
could only invent one or take the ``--defaults`` placeholder. Cards then
derived from that placeholder, which is why the first real briefing scored 1
of 3 with irrelevant cards.

This module is the seam that makes ``lanes`` DERIVABLE. It carries no reader
of its own: it STRUCTURES what the First Window already read under a
Captain-ratified charter (``framework.onboarding.journey``) into one
machine-shaped document three surfaces consume —

  * ``cabinet/scripts/generate-instance.py`` accepts ``lanes: []`` when a
    usable estate exists (discovery RAN), and refuses otherwise;
  * ``framework.onboarding.genesis`` composes proposed outcome cards from the
    estate's entities WITH CITATIONS, instead of from the answers file;
  * ``framework.onboarding.formation`` writes it at DISCOVERY_DONE and derives
    ``instance/config/lanes-proposed.yml`` beside it for Captain ratification.

NO NEW READ HAPPENS HERE. Every fact is re-derived from artifacts the journey
already wrote after the Captain ratified a hash-bound charter; this module
opens no folder, no socket, no connector, and never calls an LLM. That is
deliberate: the direction gate ruled that the sweep and its consumer land as
ONE unit, and that no ingest engine is built before the employee-slice
experiment settles whether cross-system ingest beats single-system reads.
Widening the estate to new source KINDS is a later unit; the schema below
already has the shape for them (``sources[].kind``).

PROVENANCE, PER SOURCE, AND IT SURVIVES THE READ. Each source row carries its
root, its ownership class, the charter hash the read was bound to, the
manifest hash, the entry count, and EVERY refusal with its reason (silent
skips destroy auditability). The journey persists no raw contents, so this
document is paths, hashes and counts — never file bodies.

OWNERSHIP IS ASKED, NEVER INFERRED — and asked exactly once, by somebody
else. The class and its authority basis are declared at the ingest ceiling and
bound INTO the charter hash the Captain approves
(``framework.authority.ownership`` → ``journey._build_charter``), so this
module READS them off the charter rather than asking a second time or keeping
a second vocabulary. ``writes_permitted`` decides whether a derived lane may be
proposed write-capable; a source that is not the operator's own proposes
``task_system: none`` and no repos. ``unclassified`` appears only for a journey
persisted BEFORE that ceiling existed, and it is treated as non-owned. What the
framework CANNOT do — verify the truth of an attestation — is stated rather
than implied.

ALTITUDE. ``mission.altitude`` (the operator's rung: contributor ... company)
is carried onto the document for provenance and read by genesis for card
derivation. It is validated in ``generate-instance.py``, which owns answers
validation; this module reads it tolerantly and treats an unknown value as
absent.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from framework.authority.ownership import (
    OWNERSHIP_CLASSES,
    access_record,
    writes_permitted,
)

SCHEMA = "cabinet.derived-estate/v1"
LANES_PROPOSED_SCHEMA = "cabinet.lanes-proposed/v1"
GENERATED_MARKER = "generated-by: framework.onboarding.estate"

FORMATION_DIR_REL = "instance/onboarding/formation"
ESTATE_REL = FORMATION_DIR_REL + "/derived-estate.yml"
LANES_PROPOSED_REL = "instance/config/lanes-proposed.yml"
JOURNEY_DIR_REL = "instance/onboarding/v2"

ALTITUDES = ("contributor", "project", "team", "function", "company")
# The ownership vocabulary has ONE home (framework.authority.ownership); a
# second copy here would be a second answer to the same question. `unclassified`
# is NOT a class — it is the legacy marker for a journey persisted before the
# ingest ceiling existed, and it is non-owned like everything that is not `self`.
LEGACY_UNCLASSIFIED = "unclassified"

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_RESERVED_SLUGS = frozenset({"cos", "cto", "cpo", "cro", "coo", "main", "_template"})
_MAX_ENTITIES = 12

# A directory is an ENTITY when it carries one of these marker files. Purely
# structural and citable ("I proposed this because THIS file exists at THIS
# path"), never a guess about what the operator's business is: a monorepo
# cannot tell you the business model, and inferring roles or seniority from a
# collaboration graph is fabrication.
ENTITY_MARKERS = (
    "package.json", "pyproject.toml", "setup.py", "cargo.toml", "go.mod",
    "pom.xml", "build.gradle", "gemfile", "composer.json", "requirements.txt",
    "makefile", "dockerfile", "docker-compose.yml", "readme.md", "readme",
    "readme.rst", "readme.txt",
)
#: The subset of ENTITY_MARKERS that declares a project's OWN dependencies. A
#: directory carrying one of these is a project in its own right; a directory
#: carrying only prose or an ops file is a component of the project above it.
#: That distinction is what tells a monorepo apart from a single product with
#: documentation subfolders, and the two want opposite answers about the root.
PROJECT_MANIFESTS = frozenset({
    "package.json", "pyproject.toml", "setup.py", "cargo.toml", "go.mod",
    "pom.xml", "build.gradle", "gemfile", "composer.json", "requirements.txt",
})
_ENTITY_DEPTH = 2


def cabinet_root() -> Path:
    """Deployment root: ``CABINET_ROOT`` env else this checkout (the
    genesis/formation ``cabinet_root`` semantics — kept local, import-light)."""
    env_root = os.environ.get("CABINET_ROOT")
    return Path(env_root) if env_root else Path(__file__).resolve().parents[2]


def _utc_now_iso(now: str | None = None) -> str:
    return now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> dict:
    """Absent/unparseable/wrong-shape → ``{}``. An honest empty beats a crash
    over one bad byte, and every caller treats ``{}`` as "discovery has
    nothing here" rather than inventing a stand-in."""
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def altitude_of(answers: dict | None) -> str | None:
    """The operator's declared rung from ``mission.altitude``, or None.

    Tolerant by design: an absent block, a non-mapping mission, or a verb
    outside ``ALTITUDES`` all read as UNKNOWN. Unknown is a first-class
    answer — nobody was asked — and every consumer keeps its pre-altitude
    behaviour on it. The LOUD refusal for a typo lives in
    ``generate-instance.py``, which owns answers validation; duplicating it
    here would give two answers to one question."""
    mission = (answers or {}).get("mission")
    if not isinstance(mission, dict):
        return None
    verb = str(mission.get("altitude") or "").strip().lower()
    return verb if verb in ALTITUDES else None


def _slugify(name: str, taken: set) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", str(name).strip().lower()).strip("-")[:64]
    base = base or "lane"
    if not _SLUG_RE.match(base):
        base = "lane"
    if base in _RESERVED_SLUGS:
        base = f"{base}-lane"
    slug, n = base, 2
    while slug in taken:
        slug = f"{base[:60]}-{n}"
        n += 1
    taken.add(slug)
    return slug


def _entities_from_manifest(manifest: dict, source_id: str) -> list:
    """Directories under the granted root that carry a project marker.

    Deterministic and citable: the evidence for every entity is the marker
    file's manifest path plus its recorded sha256 — the operator can check the
    claim. The granted root itself counts when a marker sits at depth 0, so a
    single-project folder yields one entity rather than none. Depth is capped
    at ``_ENTITY_DEPTH`` because deeper matches are components, not products,
    and the count is capped so a huge tree cannot flood the proposal file."""
    files = manifest.get("files")
    if not isinstance(files, list):
        return []
    root_label = str(manifest.get("source_label") or "").strip() or "granted-root"
    found: dict = {}
    for row in files:
        if not isinstance(row, dict):
            continue
        rel = str(row.get("path") or "")
        if not rel or rel.startswith("/"):
            continue
        parts = rel.split("/")
        marker = parts[-1].lower()
        if marker not in ENTITY_MARKERS:
            continue
        depth = len(parts) - 1
        if depth > _ENTITY_DEPTH:
            continue
        key = "/".join(parts[:-1])
        name = parts[-2] if depth else root_label
        entry = found.setdefault(
            key, {"name": name, "depth": depth, "evidence": [], "manifest": False})
        entry["manifest"] = entry["manifest"] or marker in PROJECT_MANIFESTS
        if len(entry["evidence"]) < 3:
            entry["evidence"].append({"path": rel, "sha256": str(row.get("sha256") or "")})
    # WHICH ONE IS THE PRODUCT — decided by the marker KIND, not by depth alone.
    # In a monorepo the granted root is a container and the deeper packages are
    # the products, so the root is dropped: a root entity would take a
    # subject-card slot and name the products after the folder the operator
    # happened to point at. But depth alone got this exactly backwards on a
    # single-product repo. Measured 2026-07-28 through the real journey on a
    # live single-product web repo: the root held the ONLY package.json and the
    # deeper markers were a docs README and an internal folder's README, so the
    # cabinet dropped the product and proposed two of its own subdirectories as
    # the lanes. A
    # directory whose only marker is prose or an ops file is a COMPONENT of the
    # project above it, and cannot displace it.
    nested = [row for row in found.values() if row["depth"]]
    if any(row["manifest"] for row in nested):
        found = {k: v for k, v in found.items() if v["depth"]}
    elif nested:
        root_rows = {k: v for k, v in found.items() if not v["depth"]}
        if root_rows:
            found = root_rows
    entities, taken = [], set()
    for key in sorted(found, key=lambda k: (found[k]["depth"], k))[:_MAX_ENTITIES]:
        row = found[key]
        entities.append({
            "id": _slugify(row["name"], taken),
            "kind": "project",
            "name": str(row["name"])[:79],
            "source_id": source_id,
            "relative_path": key or ".",
            "evidence": row["evidence"],
        })
    return entities


def _source_row(charter: dict, manifest: dict, now: str) -> dict:
    """One source row, riding the canonical per-source access record.

    ``access_record`` is the shape that must SURVIVE the read it describes, so
    the estate does not invent a second one: it carries the record verbatim and
    adds only what the estate itself needs (a stable id for entity references,
    the byte total, and whether the scan hit its limits). Ownership and
    authority basis come off the CHARTER — the hash the Captain approved — not
    from a fresh question."""
    payload = charter.get("payload") if isinstance(charter.get("payload"), dict) else {}
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    stats = manifest.get("scan_statistics")
    excluded = stats.get("excluded") if isinstance(stats, dict) else None
    refusals = {k: int(v) for k, v in (excluded or {}).items() if v} \
        if isinstance(excluded, dict) else {}
    declared = str(source.get("ownership") or "")
    ownership = declared if declared in OWNERSHIP_CLASSES else LEGACY_UNCLASSIFIED
    retention = "paths, hashes and counts only; no file contents persisted"
    if ownership in OWNERSHIP_CLASSES:
        record = access_record(
            schema=SCHEMA, source_root=str(source.get("root") or ""),
            ownership=ownership,
            authority_basis=str(source.get("authority_basis") or ""),
            charter_hash=str(charter.get("hash") or ""),
            manifest_hash=str(manifest.get("manifest_hash") or ""),
            entry_count=int(manifest.get("file_count") or 0),
            refusals=refusals, retention=retention, recorded_at=now,
        )
    else:
        # A journey persisted before the ingest ceiling existed. Recorded
        # honestly rather than back-filled with a plausible class, and treated
        # as non-owned everywhere below.
        record = {
            "schema": SCHEMA, "source_root": str(source.get("root") or ""),
            "ownership": LEGACY_UNCLASSIFIED, "authority_basis": "",
            "charter_hash": str(charter.get("hash") or ""),
            "manifest_hash": str(manifest.get("manifest_hash") or ""),
            "entry_count": int(manifest.get("file_count") or 0),
            "refusals": dict(sorted(refusals.items())),
            "refusals_total": sum(refusals.values()),
            "retention": retention, "recorded_at": now, "purge_receipt": None,
        }
    row = {"id": "first-window", "kind": "local_folder",
           "label": str(source.get("label") or manifest.get("source_label") or ""),
           "bytes": int(manifest.get("total_bytes") or 0),
           "truncated_by_limits": bool(manifest.get("truncated_by_limits")),
           "read_only": True, "raw_contents_persisted": False}
    row.update(record)
    return row


def derive_estate(root: Path | None = None, *, answers: dict | None = None,
                  run_id: str | None = None, now: str | None = None) -> dict:
    """Structure the ratified First Window into the derived-estate document.

    A source row is emitted ONLY when the charter is ``ratified`` AND the
    manifest was bound to THAT charter hash — i.e. a read the Captain actually
    approved, matched to the scope it was approved for. Anything else (no
    journey, a pending charter, a manifest from a superseded charter) yields
    ``sources: []`` + ``entities: []``: an HONEST EMPTY that still records
    that discovery ran, which is exactly what the generator's ``lanes: []``
    gate needs to distinguish "found nothing" from "never looked"."""
    base = Path(root) if root else cabinet_root()
    jdir = base / JOURNEY_DIR_REL
    charter = _read_json(jdir / "orientation-charter.json")
    manifest = _read_json(jdir / "first-window-manifest.json")
    dividend = _read_json(jdir / "first-dividend.json")
    ts = _utc_now_iso(now)

    sources, entities, finding = [], [], None
    ratified = str(charter.get("status") or "") == "ratified"
    bound = bool(charter.get("hash")) and manifest.get("charter_hash") == charter.get("hash")
    if ratified and bound:
        row = _source_row(charter, manifest, ts)
        sources.append(row)
        entities = _entities_from_manifest(manifest, row["id"])
        item = dividend.get("finding") if isinstance(dividend.get("finding"), dict) else None
        if item and dividend.get("manifest_hash") == manifest.get("manifest_hash"):
            finding = {
                "kind": str(item.get("kind") or ""),
                "summary": str(item.get("summary") or ""),
                "citations": [c for c in (item.get("citations") or [])
                              if isinstance(c, dict)][:3],
            }
    purpose = ""
    payload = charter.get("payload")
    if isinstance(payload, dict):
        purpose = " ".join(str(payload.get("purpose") or "").split())[:200]

    return {
        "schema": SCHEMA,
        "deployment": str(((answers or {}).get("cabinet") or {}).get("id") or ""),
        "derived_by": "framework.onboarding.formation:DISCOVERY_DONE",
        "derived_at": ts,
        "run_id": run_id or "",
        "altitude": altitude_of(answers) or "",
        "declared_purpose": purpose,
        "sources": sources,
        "entities": entities,
        "first_dividend": finding,
    }


_ESTATE_HEADER = """\
# instance/onboarding/formation/derived-estate.yml — what the cabinet READ.
# {marker}
#
# Structured from the Captain-ratified First Window (no new read happens when
# this file is written). Paths, hashes and counts only — the journey persists
# no raw file contents, and neither does this. `ownership` is ASKED, never
# inferred: until a source is classified `self`, every lane derived from it is
# proposed read-only (task_system: none, no repos).
"""


def write_estate(doc: dict, root: Path | None = None) -> dict:
    """Write the estate document (last write wins — it is a DERIVATION, not a
    ledger: re-deriving from the same artifacts yields the same content, and a
    stale copy of a superseded charter would be worse than an overwrite)."""
    import yaml  # local: keep the module import-light
    base = Path(root) if root else cabinet_root()
    path = base / ESTATE_REL
    body = _ESTATE_HEADER.format(marker=GENERATED_MARKER)
    body += yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)
    _atomic_write(path, body)
    return {"status": "written", "path": str(path),
            "sources": len(doc.get("sources") or []),
            "entities": len(doc.get("entities") or [])}


def load_estate(root: Path | None = None) -> dict:
    """The parsed estate document, read-only. Absent/unparseable → ``{}``."""
    base = Path(root) if root else cabinet_root()
    path = base / ESTATE_REL
    if not path.is_file():
        return {}
    try:
        import yaml  # local: keep the module import-light
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return doc if isinstance(doc, dict) else {}


def estate_is_usable(doc: dict, deployment: str | None = None) -> tuple:
    """``(usable, reason)`` — the gate ``lanes: []`` rides.

    Usable means DISCOVERY RAN for THIS deployment: right schema, a derivation
    timestamp, a source list of the right shape, and a matching deployment id.
    It deliberately does NOT require a non-empty source list — "I looked and
    found nothing" is a legitimate lane-less state, and the cabinet answers it
    with the read-your-world card rather than a fabricated lane. What it
    refuses is a MISSING or FOREIGN artifact, i.e. nobody ever looked here."""
    if not isinstance(doc, dict) or not doc:
        return False, "no derived-estate artifact"
    if doc.get("schema") != SCHEMA:
        return False, f"derived-estate schema is {doc.get('schema')!r}, expected {SCHEMA!r}"
    if not str(doc.get("derived_at") or "").strip():
        return False, "derived-estate carries no derived_at"
    if not isinstance(doc.get("sources"), list) or not isinstance(doc.get("entities"), list):
        return False, "derived-estate sources/entities must be lists"
    if deployment is not None:
        declared = str(doc.get("deployment") or "")
        if declared != str(deployment):
            return False, (f"derived-estate was derived for deployment {declared!r}, "
                           f"not {str(deployment)!r}")
    return True, "ok"


def proposed_lanes(doc: dict) -> list:
    """Estate entities → PROPOSED lane rows (never activated by anything).

    Structural read-only for anything not operator-owned: the decision is
    ``framework.authority.ownership.writes_permitted`` — the same function the
    task adapters route through — so a lane whose source is not the operator's
    is proposed with ``task_system: none`` and no repos, and ratifying it can
    never point a write-capable adapter at an estate they do not own. That is the write-back danger closed at
    the one surface this unit builds — ``task_adapters/base.py``'s "canonical
    wins" pointed at a corporate tracker is an agent overwriting a colleague's
    edits in a system the operator has no authority over."""
    owners = {str(s.get("id")): str(s.get("ownership") or LEGACY_UNCLASSIFIED)
              for s in (doc.get("sources") or []) if isinstance(s, dict)}
    rows = []
    for ent in (doc.get("entities") or []):
        if not isinstance(ent, dict):
            continue
        slug = str(ent.get("id") or "")
        if not _SLUG_RE.match(slug) or slug in _RESERVED_SLUGS:
            continue
        klass = owners.get(str(ent.get("source_id")), LEGACY_UNCLASSIFIED)
        owned = klass in OWNERSHIP_CLASSES and writes_permitted(klass)
        rows.append({
            "name": str(ent.get("name") or slug)[:79],
            "slug": slug,
            "repos": [],
            "task_system": "none",
            "boards": [],
            "derived_from": {
                "source_id": ent.get("source_id"),
                "relative_path": ent.get("relative_path"),
                "evidence": ent.get("evidence") or [],
            },
            "ownership": klass,
            "write_capable_proposal": owned,
        })
    return rows


_LANES_HEADER = """\
# instance/config/lanes-proposed.yml — lanes the cabinet DERIVED from what it
# read. {marker}
#
# PROPOSE-ONLY, and structurally so: no generator, compiler or officer reads
# this filename. `generate-instance.py` takes lanes ONLY from
# instance/config/cabinet-init.answers.yml, so nothing here can activate
# itself or hire anyone.
#
# TO RATIFY a row: copy it (name/slug/repos/task_system/boards) into the
# answers file under `lanes:` — editing freely, it is a proposal — then re-run
#   python3.12 cabinet/scripts/generate-instance.py
# TO REJECT: delete the row (a line in the decisions ledger beats silence).
#
# Every row ships `task_system: none` and no repos until its source is
# classified `ownership: self`: a lane pointed at an estate you do not own
# would let a write-capable adapter overwrite someone else's edits.
"""


def write_lanes_proposed(doc: dict, root: Path | None = None,
                         now: str | None = None) -> dict:
    """Write the lanes-proposed sibling. Rewritten on every discovery run —
    it is a DERIVATION of the current estate, and a row for an entity that no
    longer exists is worse than no row."""
    import yaml  # local: keep the module import-light
    base = Path(root) if root else cabinet_root()
    rows = proposed_lanes(doc)
    body = _LANES_HEADER.format(marker=GENERATED_MARKER)
    body += yaml.safe_dump({
        "schema": LANES_PROPOSED_SCHEMA,
        "deployment": doc.get("deployment") or "",
        "proposed_by": "framework.onboarding.formation",
        "proposed_at": _utc_now_iso(now),
        "derived_from": ESTATE_REL,
        "captain_ratified": False,
        "lanes": rows,
    }, sort_keys=False, allow_unicode=True, width=100)
    _atomic_write(base / LANES_PROPOSED_REL, body)
    return {"status": "written", "path": str(base / LANES_PROPOSED_REL),
            "lanes": len(rows)}
