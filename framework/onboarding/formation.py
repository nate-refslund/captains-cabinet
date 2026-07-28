"""framework.onboarding.formation — the deep Formation stage machine.

Formation is the post-First-Dividend, propose-only deep self-setup run
(``docs/plans/onboarding-v2-design-of-record-2026-07-14.md``): discover →
consent → ingest/organize → strategy map → the T+24h
strategic briefing. Most of it is still the SKELETON — run-id + journal
helpers, resume logic, undo, and stage entry-point STUBS that write an honest
IOU artifact ("not yet built — Phase 3 increment N"); those stages do no fake
work, call no LLM, touch no network and read no Captain data. The production
First Window + hash-bound Charter live in ``framework.onboarding.journey``;
this module MUST NOT duplicate that state or be presented as though deep
orientation is implemented.

ONE STAGE IS REAL: ``DISCOVERY_DONE`` (the ordering inversion, Captain ruling
2026-07-26). It STRUCTURES what the ratified First Window already read into
``framework.onboarding.estate``'s derived-estate document and derives
``instance/config/lanes-proposed.yml`` beside it, so ``lanes`` stop being
something the operator must declare before the cabinet has looked at anything.
It performs NO NEW READ — no folder is opened, no connector is called; every
fact is re-derived from artifacts the journey wrote after the Captain ratified
a hash-bound charter. The stages after it stay honest IOUs precisely because
real ingest is gated on the employee-slice experiment (direction gate D9:
"the sweep and its consumer land as ONE unit or not at all").

Safety model (structural, not conventional):
* PROPOSE-ONLY / NOTHING ACTIVATES — every artifact lands under
  ``instance/onboarding/formation/<run-id>/``, a surface the mission compiler
  structurally never reads (its filename gate reads only
  ``instance/config/outcomes.yml``; pinned by test_formation.py's invariant).
  The two DISCOVERY_DONE outputs sit one level up
  (``instance/onboarding/formation/derived-estate.yml`` and
  ``instance/config/lanes-proposed.yml``) so consumers have ONE stable path
  instead of guessing a run id — and both are equally inert: the compiler's
  filename gate does not read them, and ``generate-instance.py`` takes lanes
  ONLY from the answers file, so a proposed lane cannot hire anyone.
* REVERSIBLE — ``undo_run`` supersede-archives the whole run dir into
  ``instance/onboarding/formation/_pre-adopt-<UTC-stamp>/<run-id>/`` (the
  generate-instance --adopt idiom: nothing deleted, ever), and takes the two
  DISCOVERY_DONE outputs with it when they carry THIS run's id — otherwise
  undoing a run would leave its derived estate behind, still feeding the
  generator and the briefing.
* HONEST IOU — the C1 consent gate is NOT built yet, so the READ_SCOPE
  stub's artifact states plainly that no consent was requested and no data
  was read; downstream stubs read nothing either.
* NO append-interface.sh — formation is not granted the Captain-law ledgers
  (closes the self-persuasion channel; formation.sh never references it).
* Budgeted — the per-run LLM call cap rides ``CABINET_FORMATION_CALL_CAP``
  (malformed values fall back, never crash — the genesis knob pattern) and is
  recorded in the run's FORMATION_START journal row. The scaffold itself
  makes 0 calls; future increments enforce the recorded cap.

Journal contract: ``<run-dir>/journal.jsonl`` is APPEND-ONLY — one JSON line
per stamp, never rewritten. Resume = skip any stamp that already has a row.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

FORMATION_DIR_REL = "instance/onboarding/formation"
JOURNAL_NAME = "journal.jsonl"
GENERATED_MARKER = "generated-by: framework.onboarding.formation"
IOU_PREFIX = "not yet built — Phase 3 increment"

START_STAMP = "FORMATION_START"
# The stages that DO REAL WORK. Everything else is an honest IOU stub, and
# this set is what keeps the two apart in one place instead of by prose:
# estimate_lines, the artifact writer and the tests all read it.
REAL_STAMPS = frozenset({"DISCOVERY_DONE"})
# (stamp, artifact slug, phase-3 increment number, design-stage label)
STAGES: tuple[tuple[str, str, int, str], ...] = (
    ("DISCOVERY_DONE", "discovery", 1, "F1 estate discovery"),
    ("READ_SCOPE_RATIFIED", "read-scope", 2, "C1 itemized read-scope consent gate"),
    ("INGEST_DONE", "ingest", 3, "F2 ingest + organize"),
    ("STRATEGY_DONE", "strategy", 4, "F3 strategy map"),
    ("BRIEFING_DONE", "briefing", 5, "F5 T+24h strategic briefing"),
)
STAGE_STAMPS = tuple(s[0] for s in STAGES)
ALL_STAMPS = (START_STAMP,) + STAGE_STAMPS

_DEFAULT_CALL_CAP = 25
# A run id is a bare dir name, NEVER a path: safe charset, no leading
# '_'/'.' (protects the _pre-adopt area and dotfiles), no separators.
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def cabinet_root() -> Path:
    """Deployment root: ``CABINET_ROOT`` env else this checkout (the
    genesis.cabinet_root semantics — kept local, import-light)."""
    env_root = os.environ.get("CABINET_ROOT")
    return Path(env_root) if env_root else Path(__file__).resolve().parents[2]


def _utc_now_iso(now: str | None = None) -> str:
    return now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def call_cap() -> int:
    """The CABINET_FORMATION_CALL_CAP env knob. Malformed or non-positive
    values fall back to the default — a bad knob must never crash a run."""
    raw = os.environ.get("CABINET_FORMATION_CALL_CAP")
    if raw is None:
        return _DEFAULT_CALL_CAP
    try:
        val = int(raw)
    except ValueError:
        return _DEFAULT_CALL_CAP
    return val if val > 0 else _DEFAULT_CALL_CAP


def new_run_id(now: str | None = None) -> str:
    """``formation-YYYYMMDD-HHMMSS-xxxx`` — sortable, collision-suffixed."""
    ts = _utc_now_iso(now).replace("-", "").replace(":", "")
    ts = ts[:8] + "-" + ts[9:15]  # YYYYMMDDTHHMMSSZ → YYYYMMDD-HHMMSS
    return f"formation-{ts}-{os.urandom(2).hex()}"


def formation_dir(root: Path | None = None) -> Path:
    base = Path(root) if root else cabinet_root()
    return base / FORMATION_DIR_REL


def run_dir(root: Path | None, run_id: str) -> Path:
    """The run dir, PATH-CONTAINED: the id must be a bare name (safe charset,
    no separators, no leading '_'/'.') and resolve under the formation dir —
    'formation-..-x', '../x', '_pre-adopt-x/y' all refuse loudly."""
    if not _RUN_ID_RE.match(run_id) or run_id.startswith("_pre-adopt"):
        raise ValueError(f"invalid run id: {run_id!r}")
    fdir = formation_dir(root)
    path = fdir / run_id
    # belt-and-braces: resolve() and re-check containment (Corridor rule)
    if path.resolve().parent != fdir.resolve():
        raise ValueError(f"run id escapes the formation dir: {run_id!r}")
    return path


def journal_path(root: Path | None, run_id: str) -> Path:
    return run_dir(root, run_id) / JOURNAL_NAME


def append_journal(root: Path | None, run_id: str, stamp: str, *,
                   status: str, note: str = "", now: str | None = None) -> dict:
    """APPEND one JSON line — the journal is never rewritten (append-only is
    the resume contract). Returns the appended row."""
    if stamp not in ALL_STAMPS:
        raise ValueError(f"unknown formation stamp: {stamp!r}")
    row = {"ts": _utc_now_iso(now), "run_id": run_id, "stage": stamp,
           "status": status, "note": note}
    path = journal_path(root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def read_journal(root: Path | None, run_id: str) -> list[dict]:
    """All parseable rows, in order. Malformed lines are skipped (an honest
    partial read beats a crash over one bad byte in a crash-interrupted
    append) — but never rewritten."""
    path = journal_path(root, run_id)
    if not path.is_file():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def journaled_stamps(root: Path | None, run_id: str) -> set[str]:
    return {str(r.get("stage")) for r in read_journal(root, run_id)}


def next_stage(root: Path | None, run_id: str) -> str | None:
    """First stage stamp with no journal row — the resume pointer. None when
    the run is complete."""
    done = journaled_stamps(root, run_id)
    for stamp in STAGE_STAMPS:
        if stamp not in done:
            return stamp
    return None


def open_run(root: Path | None = None, run_id: str | None = None, *,
             now: str | None = None) -> dict:
    """Create (or re-open for RESUME) a run: mkdir + the FORMATION_START row
    (written once — a resumed run keeps its original START row and cap)."""
    rid = run_id or new_run_id(now)
    rdir = run_dir(root, rid)
    resumed = rdir.exists() and START_STAMP in journaled_stamps(root, rid)
    rdir.mkdir(parents=True, exist_ok=True)
    cap = call_cap()
    if not resumed:
        append_journal(root, rid, START_STAMP, status="open",
                       note=f"call_cap={cap} (CABINET_FORMATION_CALL_CAP); "
                            "scaffold — every stage is an honest IOU stub",
                       now=now)
    return {"run_id": rid, "run_dir": str(rdir), "resumed": resumed,
            "call_cap": cap, "next_stage": next_stage(root, rid)}


def run_call_cap(root: Path | None, run_id: str) -> int:
    """The cap RECORDED at open (rides the run across resumes, so a changed
    env knob can't silently raise a running budget). Fallback: current knob."""
    for row in read_journal(root, run_id):
        if row.get("stage") == START_STAMP:
            m = re.search(r"call_cap=(\d+)", str(row.get("note") or ""))
            if m:
                return int(m.group(1))
    return call_cap()


def estimate_lines(root: Path | None, run_id: str) -> list[str]:
    """The printed cost estimate — honest: zero LLM calls, and honest about
    which stages actually do something (a blanket "every stage is a stub" line
    became false the moment DISCOVERY_DONE started deriving the estate)."""
    cap = run_call_cap(root, run_id)
    remaining = [s for s in STAGE_STAMPS
                 if s not in journaled_stamps(root, run_id)]
    return [
        f"Cost estimate — run {run_id}:",
        f"  LLM CLI calls this run: 0 of a per-run cap of {cap} "
        "(CABINET_FORMATION_CALL_CAP)",
        "  DISCOVERY_DONE structures the ALREADY-RATIFIED First Window into "
        "the derived estate",
        "  (no new read: no folder opened, no connector, no network, no LLM). "
        "Every other",
        "  stage is an honest IOU stub and reads nothing. Future increments "
        "spend against the",
        "  recorded cap only.",
        f"  Stages remaining: {len(remaining)} of {len(STAGE_STAMPS)}"
        + (f" (resume — next: {remaining[0]})" if remaining
           and len(remaining) < len(STAGE_STAMPS) else ""),
    ]


def _stage_artifact_text(stamp: str, slug: str, increment: int, label: str, *,
                         run_id: str, now: str) -> str:
    lines = [
        "---",
        "schema: cabinet.formation-stage-iou/v1",
        f"stage: {stamp}",
        f"run_id: {run_id}",
        f"{GENERATED_MARKER} (Phase 3 scaffold)",
        f"generated_at: {now}",
        "status: iou",
        "---",
        "",
        f"# Formation stage IOU — {label}",
        "",
        f"{IOU_PREFIX} {increment} ({label}).",
        "",
        "This stage stamped its checkpoint but did NO work: no LLM call, no",
        "network, no Captain data read, nothing proposed, nothing activated.",
        "The mission compiler structurally never reads this surface.",
    ]
    if stamp == "READ_SCOPE_RATIFIED":
        lines += [
            "",
            "HONESTY NOTE: the C1 consent gate is not built — no read-scope was",
            "presented to the Captain and NO consent was requested or recorded.",
            "This stamp marks only the checkpoint's place in the stage machine;",
            "until increment 2 lands, formation reads nothing of the Captain's.",
        ]
    return "\n".join(lines) + "\n"


def _run_discovery(root: Path | None, run_id: str, rdir: Path, ts: str) -> dict:
    """DISCOVERY_DONE, for real: ratified First Window → derived estate →
    lanes-proposed. Reads only artifacts the journey already wrote; the
    run-local copy under the run dir is what ``undo_run`` archives, and the
    two stable-path files are what the generator and genesis consume."""
    from framework.onboarding import estate as _estate  # local: import-light

    answers = {}
    base = Path(root) if root else cabinet_root()
    apath = base / "instance/config/cabinet-init.answers.yml"
    if apath.is_file():
        try:
            import yaml
            loaded = yaml.safe_load(apath.read_text(encoding="utf-8"))
            answers = loaded if isinstance(loaded, dict) else {}
        except Exception:
            answers = {}
    doc = _estate.derive_estate(base, answers=answers, run_id=run_id, now=ts)
    written = _estate.write_estate(doc, base)
    lanes = _estate.write_lanes_proposed(doc, base, now=ts)
    import yaml
    copy = rdir / "discovery.yml"
    tmp = copy.with_name(copy.name + ".tmp")
    tmp.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True,
                                  width=100), encoding="utf-8")
    os.replace(tmp, copy)
    return {"status": "derived", "stamp": "DISCOVERY_DONE", "artifact": str(copy),
            "sources": written["sources"], "entities": written["entities"],
            "lanes_proposed": lanes["lanes"]}


def run_stage(root: Path | None, run_id: str, stamp: str, *,
              now: str | None = None) -> dict:
    """Execute one stage: DISCOVERY_DONE derives the estate for real, every
    other stamp writes its honest-IOU artifact. Both journal the stamp.
    Idempotent — an already-journaled stamp is skipped (RESUME), its artifact
    untouched."""
    matches = [s for s in STAGES if s[0] == stamp]
    if not matches:
        raise ValueError(f"unknown formation stage stamp: {stamp!r}")
    _, slug, increment, label = matches[0]
    if stamp in journaled_stamps(root, run_id):
        return {"status": "already-done", "stamp": stamp, "artifact": None}

    ts = _utc_now_iso(now)
    rdir = run_dir(root, run_id)
    rdir.mkdir(parents=True, exist_ok=True)
    if stamp in REAL_STAMPS:
        res = _run_discovery(root, run_id, rdir, ts)
        append_journal(root, run_id, stamp, status=res["status"],
                       note=(f"{label}: {res['sources']} source(s), "
                             f"{res['entities']} entity(ies), "
                             f"{res['lanes_proposed']} lane(s) proposed; "
                             f"no new read (ratified First Window only)"),
                       now=ts)
        return res
    artifact = rdir / f"{slug}-IOU.md"
    text = _stage_artifact_text(stamp, slug, increment, label,
                                run_id=run_id, now=ts)
    tmp = artifact.with_name(artifact.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, artifact)  # atomic (the genesis _atomic_write pattern)
    append_journal(root, run_id, stamp, status="stub-iou",
                   note=f"{IOU_PREFIX} {increment} ({label}); "
                        f"artifact: {artifact.name}",
                   now=ts)
    return {"status": "stub-iou", "stamp": stamp, "artifact": str(artifact)}


def _archive_discovery_outputs(root: Path | None, run_id: str, dest: Path) -> list:
    """Take DISCOVERY_DONE's two stable-path outputs with the run they belong
    to. They live OUTSIDE the run dir (one stable path beats a run-id guess
    for consumers), so archiving only the run dir would leave the derived
    estate still feeding the generator's ``lanes: []`` gate and the briefing's
    cards after the run that produced it was undone — an undo that leaves its
    effect in place is not an undo. Only outputs stamped with THIS run id
    move, so a later run's estate is never dragged away by an older undo."""
    from framework.onboarding import estate as _estate  # local: import-light
    base = Path(root) if root else cabinet_root()
    doc = _estate.load_estate(base)
    if str(doc.get("run_id") or "") != run_id:
        return []
    moved = []
    for rel in (_estate.ESTATE_REL, _estate.LANES_PROPOSED_REL):
        path = base / rel
        if not path.is_file():
            continue
        target = dest / "superseded" / Path(rel).name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
        moved.append(rel)
    return moved


def undo_run(root: Path | None, run_id: str, *, now: str | None = None) -> dict:
    """Supersede-archive the run dir in the ``_pre-adopt`` idiom: MOVE it to
    ``instance/onboarding/formation/_pre-adopt-<UTC-stamp>/<run-id>/`` —
    nothing deleted, path-contained, honest refusal when the run is absent.
    DISCOVERY_DONE's derived estate + lanes-proposed ride along when they carry
    this run's id (see ``_archive_discovery_outputs``). (When formation grows
    DB writes — F2 ingest — undo also supersedes those rows; it has none.)"""
    rdir = run_dir(root, run_id)  # validates the id + containment
    if not rdir.is_dir():
        return {"status": "no-such-run", "run_id": run_id, "archived_to": None}
    stamp = _utc_now_iso(now).replace(":", "").replace("-", "")
    dest_dir = formation_dir(root) / f"_pre-adopt-{stamp}"
    dest = dest_dir / run_id
    n = 2
    while dest.exists():  # never clobber an earlier archive
        dest = dest_dir / f"{run_id}.{n}"
        n += 1
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(rdir), str(dest))
    superseded = _archive_discovery_outputs(root, run_id, dest)
    receipt = dest / "undo-receipt.md"
    with open(receipt, "a", encoding="utf-8") as fh:
        fh.write(f"{GENERATED_MARKER} (undo)\n"
                 f"superseded_at: {_utc_now_iso(now)}\n"
                 f"undone_run: {run_id}\n"
                 f"superseded_outputs: {', '.join(superseded) or 'none'}\n"
                 "note: supersede-archive — nothing deleted; restore by "
                 "moving this dir back.\n")
    return {"status": "archived", "run_id": run_id, "archived_to": str(dest),
            "superseded_outputs": superseded}


def main(argv: list[str] | None = None) -> int:  # pragma: no cover — thin CLI
    """Fixed-argv CLI for formation.sh (the stage machine's python half).

        python3.12 -m framework.onboarding.formation open [--run-id ID] [--id-only]
        python3.12 -m framework.onboarding.formation estimate --run-id ID
        python3.12 -m framework.onboarding.formation stage --run-id ID --stamp S
        python3.12 -m framework.onboarding.formation undo --run-id ID
        python3.12 -m framework.onboarding.formation journal --run-id ID

    `stage` prints ``<status> <artifact-or-->`` on one line (bash parses the
    first word). Exit 3 on refusals (bad id, unknown stamp, no such run).
    """
    import argparse
    import sys

    ap = argparse.ArgumentParser(prog="framework.onboarding.formation")
    ap.add_argument("cmd", choices=["open", "estimate", "stage", "undo", "journal"])
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--stamp", default=None)
    ap.add_argument("--id-only", action="store_true")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "open":
            res = open_run(run_id=args.run_id)
            if args.id_only:
                print(res["run_id"])
            else:
                print(json.dumps(res, indent=2))
            return 0
        if not args.run_id:
            print("formation: --run-id is required", file=sys.stderr)
            return 3
        if args.cmd == "estimate":
            print("\n".join(estimate_lines(None, args.run_id)))
            return 0
        if args.cmd == "stage":
            if not args.stamp:
                print("formation: --stamp is required", file=sys.stderr)
                return 3
            res = run_stage(None, args.run_id, args.stamp)
            print(f"{res['status']} {res['artifact'] or '-'}")
            return 0
        if args.cmd == "undo":
            res = undo_run(None, args.run_id)
            print(json.dumps(res, indent=2))
            return 0 if res["status"] == "archived" else 3
        if args.cmd == "journal":
            for row in read_journal(None, args.run_id):
                print(json.dumps(row, ensure_ascii=False))
            return 0
    except ValueError as e:
        print(f"formation: {e}", file=sys.stderr)
        return 3
    return 2


if __name__ == "__main__":  # pragma: no cover
    import sys
    sys.exit(main())
