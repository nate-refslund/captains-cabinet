#!/usr/bin/env python3.12
"""A2 mechanical coverage reconciliation — producers vs action-taking surfaces.

Whole-cabinet evidence design (2026-07-16) §2.4 / §3 Phase 2 / R-8: the
coverage gate is the *mechanical* producers-vs-action-surfaces reconciliation,
not a prose report.  This script:

  1. ENUMERATES the action-taking surfaces named by the design (act-first
     lane, learning/gate machinery, watchdog/doctor, officer session
     lifecycle, authority/control-plane verbs, the two telemetry mirror
     chokepoints, plus the already-live producers).
  2. DETECTS which surfaces have a live evidence producer wired (a
     ``framework.evidence`` import seam, the chokepoint mirror seam
     ``from framework import evidence_mirror``, or the mirror allow-list
     registration — producers are code-level import seams only, never a
     generic emit CLI; a shell invocation of the evidence CLI is therefore
     detector-only and never counts as wiring).
  3. EMITS the honest Captain line:
         evidence covers N of M action-taking surfaces; named gaps: ...
     KNOWN-GAP rows are the *expected, honest* Batch-A output — absence of
     evidence is never health, and a gap is reported, not faked green.
  4. FAILS (exit 1) ONLY on an UNENUMERATED surface: a file that trips an
     action-surface detector (an ``emit_consequence`` reference, a
     ``framework.evidence`` import, or a shell evidence-CLI invocation) but
     maps to no enumerated surface.  That is the drift catch — new
     action-taking code must be enumerated here (and reviewed) before it
     can hide.

Exit codes:
  0  reconciled — every detector hit is enumerated (gaps allowed, reported)
  1  DRIFT — at least one unenumerated action-taking surface (A2 violation)
  2  --strict only — an enumerated surface lacks a live producer (the
     Phase-2-end gate: "an enumerated action-taking surface without a live
     producer fails the phase")

Scope and safety:
  * Read-only.  Scans source text under ``framework/`` and
    ``cabinet/scripts/`` only.  NEVER opens the evidence store, never writes,
    never consults environment variables (no env var may bear fuel — A10),
    never touches the network.
  * This is ops/CI tooling, not an officer read surface:
    ``cabinet/scripts/evidence-read.sh`` remains the only officer path to
    evidence content; this script reads no evidence content at all.
  * Test files are excluded from detection: a test exercising a producer is
    not a producer.

Run: ``python3.12 cabinet/scripts/evidence-coverage.py [--json] [--strict]``
(house interpreter only — never bare python3).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA = "cabinet.evidence-coverage/v1"

# Directories under the scan roots that never hold producer code.
SKIP_DIR_NAMES = frozenset({
    ".git", "__pycache__", "node_modules", "officers", "fixtures",
    "worktrees", ".claude", "dashboard", "companion", "evals",
})
# Test files are not producers.
TEST_DIR_NAMES = frozenset({"tests", "test", "hook-regression"})
SOURCE_SUFFIXES = frozenset({".py", ".sh"})

# --- detectors -------------------------------------------------------------
# A file is an "action-taking / evidence-touching" detector hit when it either
# writes consequence rows (the act/outcome ledger) or reaches the evidence
# recorder plane.  Both are deliberately import/call-shaped, matching the law
# that producers are code-level seams only.
# Name-shaped, not call-shaped: consequence writers routinely import the
# function and alias it (``emit = emit_consequence``, keyword defaults), so a
# call-anchored regex misses them.  Any reference to the name marks the file
# as a consequence-writing surface that must be enumerated.
EMIT_CONSEQUENCE_RE = re.compile(r"\bemit_consequence\b")

# A surface counts as WIRED when any of its files carries a producer seam.
# Anchored to real import LINES (not prose): the pre-tool-use enforcement
# hook documents the very import shapes it blocks, and an enforcement guard
# is not a producer.  Python: a module-level or lazy import statement of
# framework.evidence, the chokepoint mirror seam import
# (``from framework import evidence_mirror`` — the org-event + consequence
# chokepoints, Ph2 item 1), or the mirror allow-list registration
# (MIRRORED_ORG_EVENT_TYPES).  Shell is detector-only (see WIRED_SH_RE).
WIRED_PY_RE = re.compile(
    r"(?m)^[ \t]*(?:from[ \t]+framework\.evidence(?:\.[A-Za-z_.]+)?[ \t]+import\b|"
    r"import[ \t]+framework\.evidence\b|"
    r"from[ \t]+\.\.?evidence(?:\.[A-Za-z_.]+)?[ \t]+import\b|"
    r"from[ \t]+framework[ \t]+import[ \t]+evidence_mirror\b)"
    r"|\bMIRRORED_ORG_EVENT_TYPES\b"
)
# Shell CLI invocation (`... -m framework.evidence ...`, interpreter spelling
# free so `$PY -m framework.evidence verify` counts) is a DETECTOR ONLY:
# it marks the file as an evidence-touching surface that must be enumerated
# (the drift catch), but it is never proof of producer wiring — there is no
# emit CLI by law (producers are code-level import seams only), so every
# shell invocation is a read (verify/export/projection) and a read-only
# probe (e.g. the doctor's chain spot-check) must not flip its act surface
# to WIRED.
WIRED_SH_RE = re.compile(
    r"(?m)^[ \t]*[^#\n][^\n]*-m[ \t]+framework\.evidence\b"
)

# --- the enumeration --------------------------------------------------------
# Globs are prefix-style: "dir/**" covers the subtree, otherwise exact
# relative path or fnmatch-style basename pattern within cabinet/scripts.
# ``kind``: act = design-enumerated action-taking surface; mirror = telemetry
# chokepoint (Ph2 item 1); producer = already-live producer; infra =
# evidence-plane tooling (recorder package, doorway, this script, bench) —
# infra rows are enumerated so detector hits map somewhere, but they are not
# counted in the N-of-M action-surface line.
SURFACES: list[dict[str, Any]] = [
    {
        "id": "org-event-mirror",
        "kind": "mirror",
        "design": "Ph2 item 1 — org-event emitter chokepoint",
        "globs": ["framework/events/**"],
    },
    {
        "id": "consequence-mirror",
        "kind": "mirror",
        "design": "Ph2 item 1 — consequence emitter chokepoint",
        "globs": ["framework/fidelity/**"],
    },
    {
        "id": "act-first-lane",
        "kind": "act",
        "design": "Ph2 item 2a — act-first action lane + hourly reconciler",
        "globs": ["framework/frontdoor/**", "framework/acting/**"],
    },
    {
        "id": "learning-gate",
        "kind": "act",
        "design": "Ph2 item 2b — learning/gate machinery recording itself",
        "globs": ["framework/learning/**"],
    },
    {
        "id": "authority-control-plane",
        "kind": "act",
        # Batch B: the kill-switch/germline-lock scripts stay untouched
        # emergency brakes (a tightening is never evidence-gated, §2.6); the
        # live producer is the unlocked authority-transitions state-diff
        # sweep, which imports the mirror allow-list for its signed-classes
        # self-check and emits in-process.  The Captain posture-cap verbs
        # (binder_wire) and the kind-freeze brake (action_undo) emit from
        # framework/frontdoor/** and are enumerated under act-first-lane;
        # need_approved emits from needs.py through the same chokepoint.
        "design": "R-1 — authority/control-plane verbs (needs, posture, "
                  "germline/kill-switch windows)",
        "globs": [
            "framework/authority/**",
            "cabinet/scripts/emit-authority-transitions.py",
        ],
    },
    {
        "id": "attention-hygiene",
        "kind": "act",
        "design": "consequence writers — expiry closures and acted overlays",
        "globs": ["framework/attention/**"],
    },
    {
        "id": "probes-verification",
        "kind": "act",
        "design": "B2.8/B2.9 probe outcomes + fabrication demote rows",
        "globs": ["framework/probes/**"],
    },
    {
        "id": "watchdog-doctor",
        "kind": "act",
        "design": "Ph2 item 2c — watchdog checks and doctor verdicts",
        # Batch B: framework/watchdog/** joined — receipts.py is the typed
        # lens seam (module-exec org emits whose receipts the mirror signs)
        # and honestly carries the surface's producer wiring; check.py stays
        # stdlib-only (subprocess emit, no import seam) by independence law.
        "globs": [
            "cabinet/scripts/cabinet-doctor.sh",
            "cabinet/scripts/*watchdog*",
            "framework/watchdog/**",
        ],
    },
    {
        "id": "officer-session-lifecycle",
        "kind": "act",
        # Batch B: the germline hooks stay enumerated (their generic session
        # classes are pinned exhaust); the live producer is the unlocked
        # state-diff observer, which imports the mirror allow-list for its
        # signed-classes self-check and emits in-process.
        "design": "Ph2 item 2d — session start/end/compaction/handoff hooks",
        "globs": [
            "cabinet/scripts/hooks/**",
            "cabinet/scripts/emit-officer-lifecycle-transitions.py",
        ],
    },
    {
        "id": "roles-missions-lifecycle",
        "kind": "act",
        "design": "R-1 — role authority lifecycle + mission/work-item events",
        "globs": [
            "framework/roles/**", "framework/missions/**",
            "framework/outbox/**", "framework/channels/**",
            "framework/measurement/**", "framework/ovi/**",
        ],
    },
    {
        "id": "onboarding-journey",
        "kind": "producer",
        "design": "Phase 1 — the live production producer (journey.act)",
        "globs": ["framework/onboarding/**"],
    },
    {
        "id": "digest-anchor",
        "kind": "producer",
        "design": "Phase 1 / R-13 — daily digest-anchor trial",
        "globs": [
            "framework/evidence_anchor.py",
            "cabinet/scripts/evidence-anchor.py",
        ],
    },
    {
        "id": "ops-consequence-scripts",
        "kind": "act",
        "design": "consequence writers — ops scripts (seed/expire)",
        "globs": [
            "cabinet/scripts/seed-war-room.py",
            "cabinet/scripts/expire-parked-draft-proposals.py",
        ],
    },
    {
        "id": "governance-review-labels",
        "kind": "producer",
        # Phase 3 item 3 (2026-07-17): the weekly governance-review ritual —
        # Captain-token-gated, TTY-only labeling that lands verdict_human
        # verification/outcome events on the judged trial via the recorder
        # API (the phase's ONE designed write; per-label digests ride the
        # daily external anchor). Never officer-invokable, never scheduled.
        "design": "Ph3 item 3 — Captain governance-review labels (verdict_human)",
        "globs": ["cabinet/scripts/governance-review.py"],
    },
    {
        "id": "shadow-detectors",
        "kind": "infra",
        # Phase 4 item 1 (2026-07-17, SHADOW LAW): read-only detectors over
        # the query plane — clustering + fail-open triage feeding a
        # Captain-facing report file ONLY. Never a producer (zero store
        # writes, zero org events; the first-verify watermark advance is the
        # verifier's own sanctioned side effect, not a producer seam).
        # Enumerated infra so the evidence-import detector maps here instead
        # of tripping drift; deliberately NOT an act surface — nothing
        # downstream may consume its output to gate/block/score/act.
        "design": "Ph4 item 1 — shadow detectors (read-only, report-only)",
        "globs": ["framework/evidence_detectors.py"],
    },
    {
        "id": "evidence-calibration-shadow",
        "kind": "infra",
        # Phase 4 (2026-07-17): SHADOW per-stratum calibration — report-only,
        # ZERO consumers (a repo grep pins that; this enumeration row is the
        # one sanctioned classification-only reference).  It reads the store
        # via the recorder/verifier APIs (hence the evidence_import detector
        # hit) and takes no actions, so kind=infra: never counted in the
        # N-of-M action-surface line, and enumeration grants no power.
        # Exact path on purpose — a future framework/evidence_*.py sibling
        # must still trip the drift catch and be enumerated + reviewed here.
        "design": "Ph4 shadow per-stratum calibration — report-only, zero consumers",
        "globs": ["framework/evidence_calibration.py"],
    },
    {
        "id": "evidence-plane-tooling",
        "kind": "infra",
        "design": "recorder package + bounded doorway + mirror engine + coverage/bench tooling",
        "globs": [
            "framework/evidence/**",
            "framework/evidence_mirror.py",
            # Phase 4 (2026-07-17): the judging-frozen marker module — its
            # Captain-token unfreeze lazily imports the framework.evidence
            # CLI gate (an import seam, not a producer; the marker itself
            # lives outside the store). Enumerated per this gate's own
            # DRIFT remediation.
            "framework/evidence_freeze.py",
            "cabinet/scripts/evidence-*.py",
            "cabinet/scripts/evidence-*.sh",
        ],
    },
    {
        "id": "fuel-integrity-shadow",
        "kind": "infra",
        # Ph4 item 2 (2026-07-17): report-only fuel-integrity shadow checker —
        # reads both planes via the recorder/query/verifier APIs and appends a
        # Captain-facing JSONL OUTSIDE the store (docs/runbooks/
        # fuel-integrity.md).  Nothing consumes its output (shadow law); this
        # census row names the module PATH only so the evidence_import
        # detector hit maps somewhere — enumeration is not consumption.
        "design": "Ph4 item 2 — fuel-integrity shadow check (report-only)",
        "globs": ["framework/evidence_fuel_integrity.py"],
    },
    {
        "id": "signing-broker",
        "kind": "infra",
        # HP-1 (2026-07-17): out-of-process HMAC key custody daemon —
        # imports ONLY the leaf framework/evidence/signing.py formats
        # (hence the evidence_import detector hit); zero store reads or
        # writes, zero org events, zero consumers.  Staged dark
        # (services.yml row disabled:true); armed only by the Captain
        # sudo deploy ceremony (docs/runbooks/evidence-signing-broker.md).
        # Exact path on purpose — the next framework/evidence_*.py sibling
        # must still trip the drift catch and be enumerated + reviewed.
        "design": "HP-1 — signing-key custody broker (staged dark)",
        "globs": ["framework/evidence_signing_broker.py"],
    },
    {
        "id": "evidence-recompute",
        "kind": "producer",
        # HP-2 (whole-cabinet evidence design 2026-07-16 §2.3): independent
        # recompute legs — re-derives fuel-bearing machine outcomes from RAW
        # artifacts (undo-journal bytes, gate pack + patch bytes, the
        # consequence ledger, org-event day files) and appends ONE
        # verification event per checked outcome to its OWN evt-recompute
        # day trials via the public recorder API (hence kind=producer, the
        # governance-review precedent). Report-only shadow otherwise:
        # nothing downstream may gate/score/act on its report or events —
        # the fuel-integrity checker reads them as a report-only third-leg
        # signal. Honest claim: same OS user until HP-1 — corroboration by
        # re-derivation, never a trust-domain boundary.
        "design": "HP-2 — independent recompute legs (own-trial producer, report-only)",
        "globs": ["framework/evidence_recompute.py"],
    },
]


def _is_test_path(rel: Path) -> bool:
    parts = rel.parts
    if any(part in TEST_DIR_NAMES for part in parts):
        return True
    name = rel.name
    return name.startswith("test_") or name == "conftest.py"


def _is_skipped(rel: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in rel.parts)


def _glob_match(rel: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return rel == prefix or rel.startswith(prefix + "/")
    if "*" in pattern:
        import fnmatch

        return fnmatch.fnmatch(rel, pattern)
    return rel == pattern


def _surface_for(rel: str) -> dict[str, Any] | None:
    for surface in SURFACES:
        if any(_glob_match(rel, pattern) for pattern in surface["globs"]):
            return surface
    return None


def _iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for base in ("framework", "cabinet/scripts"):
        base_path = root / base
        if not base_path.is_dir():
            continue
        for path in sorted(base_path.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            if path.suffix not in SOURCE_SUFFIXES:
                continue
            rel = path.relative_to(root)
            if _is_skipped(rel) or _is_test_path(rel):
                continue
            files.append(path)
    return files


def reconcile(root: Path) -> dict[str, Any]:
    """Pure reconciliation: no writes, no env, no store access."""
    root = Path(root).resolve()
    hits: dict[str, list[str]] = {}
    wired_files: dict[str, list[str]] = {surface["id"]: [] for surface in SURFACES}
    unenumerated: list[dict[str, str]] = []

    for path in _iter_source_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if path.suffix == ".sh":
            # Shell can never be producer wiring (no emit CLI exists, by
            # law) — a CLI hit is enumeration-required drift bait only.
            is_wired = False
            touches = bool(WIRED_SH_RE.search(text))
        else:
            is_wired = bool(WIRED_PY_RE.search(text))
            touches = is_wired
        detector_names = []
        if EMIT_CONSEQUENCE_RE.search(text):
            detector_names.append("emit_consequence")
        if touches:
            detector_names.append(
                "evidence_cli" if path.suffix == ".sh" else "evidence_import"
            )
        surface = _surface_for(rel)
        if detector_names:
            hits[rel] = detector_names
            if surface is None:
                unenumerated.append({
                    "file": rel,
                    "detectors": ",".join(detector_names),
                })
        if surface is not None and is_wired:
            wired_files[surface["id"]].append(rel)

    rows: list[dict[str, Any]] = []
    for surface in SURFACES:
        wired = sorted(wired_files[surface["id"]])
        if surface["kind"] == "infra":
            status = "INFRA"
        elif wired:
            status = "WIRED"
        else:
            status = "KNOWN-GAP"
        rows.append({
            "id": surface["id"],
            "kind": surface["kind"],
            "design": surface["design"],
            "status": status,
            "producers": wired,
        })

    action_rows = [row for row in rows if row["kind"] != "infra"]
    covered = [row for row in action_rows if row["status"] == "WIRED"]
    gaps = [row["id"] for row in action_rows if row["status"] == "KNOWN-GAP"]
    line = (
        f"evidence covers {len(covered)} of {len(action_rows)} "
        f"action-taking surfaces; named gaps: {', '.join(gaps) if gaps else 'none'}"
    )
    return {
        "schema": SCHEMA,
        "root": str(root),
        "line": line,
        "covered": len(covered),
        "total": len(action_rows),
        "gaps": gaps,
        "surfaces": rows,
        "unenumerated": sorted(unenumerated, key=lambda item: item["file"]),
        "detector_hits": {rel: hits[rel] for rel in sorted(hits)},
    }


def _default_root() -> Path:
    # cabinet/scripts/evidence-coverage.py -> repo root two levels up.
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evidence-coverage",
        description="A2 mechanical producers-vs-action-surfaces reconciliation.",
    )
    parser.add_argument(
        "--root", type=Path, default=None,
        help="repo root to reconcile (default: this script's repo)",
    )
    parser.add_argument(
        "--json", action="store_true", help="machine-readable report on stdout",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Phase-2-end gate: any KNOWN-GAP action surface exits 2",
    )
    args = parser.parse_args(argv)
    report = reconcile(args.root or _default_root())

    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(report["line"])
        for row in report["surfaces"]:
            producers = ", ".join(row["producers"]) if row["producers"] else "-"
            print(f"  [{row['status']:>9}] {row['id']} ({row['kind']}): {producers}")

    exit_code = 0
    if report["unenumerated"]:
        for item in report["unenumerated"]:
            print(
                "UNENUMERATED action-taking surface: "
                f"{item['file']} (detector: {item['detectors']})",
                file=sys.stderr,
            )
        print(
            "DRIFT: enumerate the surface in cabinet/scripts/evidence-coverage.py "
            "SURFACES (design A2) or remove the rogue producer.",
            file=sys.stderr,
        )
        exit_code = 1
    elif args.strict and report["gaps"]:
        print(
            "STRICT GATE: enumerated action-taking surfaces without a live "
            f"producer: {', '.join(report['gaps'])}",
            file=sys.stderr,
        )
        exit_code = 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
