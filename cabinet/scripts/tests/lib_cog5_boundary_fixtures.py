"""COG-5 W2 T3 — shared fixture helpers for the BOUNDARY/ESCAPE corpus family
(sims 6/7/11 + the X5/X7 exit arms + the §12.1 declared-bound family).

OWNERSHIP (corpus law, contract §13 + the W2 naming discipline): this file is
T3-OWNED — every public helper is prefixed `lib_cog5_boundary_`; the shared
core `lib_cog5_corpus.py` is T1-OWNED (imported below IF PRESENT, never
created here); T2 owns `lib_cog5_scoring*`. Builders NEVER edit this file —
contradictions route to the integrator.

Everything here is FIXTURE MACHINERY: pure stdlib + the committed
`framework.evolution.contracts` surface. Synthetic corpora are SANCTIONED for
plumbing + mutants (contract §12); what synthetic evidence may NEVER do is
open the league or ground a live-fitness claim — the provenance family below
encodes that law mechanically (§6.2: closed enum, ingester-stamped custody,
only `real_*` rows from NAMED real sources count toward any league minimum).

Laws replicated from bytes (never imported from germline):
  - the gate `_default_runner` unprivileged laws (framework/learning/gate.py
    :372-410): euid==0 refuses; commands are arg-lists (no shell); git hook
    execution disabled BOTH ways (`-c core.hooksPath=/dev/null` on argv AND
    the env GIT_CONFIG_COUNT/KEY_0/VALUE_0 pins).
  - the §4.4 env-scrub law: an explicit ALLOWLIST environment, never a
    denylist; the harness holds credentials (oauth_llm.py:1-9 precedent) —
    candidate-visible envs carry NO credential-shaped names.
  - the §12.1 declared bound: pass-state metrics ZERO regression tolerance;
    wall-clock bound = max(p95*1.25, p95+5s) (floor-aware); sweep violations
    stay 0; files-swept moves ONLY by the phase's own added files
    (exact-integer accounting, §13 census_delta discipline).

Credential fixtures: every credential-shaped NAME below is assembled from
parts at runtime (never a contiguous secret-looking literal in swept source)
and every VALUE is an explicitly fake placeholder — no real secret is ever
read, written, or represented.

S0: python3.12, no DB, no network beyond a 127.0.0.1 loopback probe pair in
the egress instrument (no external egress anywhere). Deterministic:
file-seeded, no clock reads in any assertion path.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant (COG-5 contract §12 sims 6/7/11, §12.1;
W2 corpus wave, unit T3).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

_HERE = Path(__file__).resolve().parent
REPO_ROOT = _HERE.parents[2]
for _p in (str(REPO_ROOT), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# --------------------------------------------------------------------------
# T1's shared corpus core — imported IF PRESENT (W2 runs t1/t2/t3 in
# parallel; on a tree where t1 has not landed yet this stays None and the
# integration probes skip SELF-ARMINGLY: they go live the moment t1's file
# lands at integration, no retirement surgery needed).
# --------------------------------------------------------------------------
try:  # pragma: no cover - trivial import guard
    import lib_cog5_corpus as _cog5_corpus  # type: ignore[import-not-found]
except Exception:  # ImportError on the bare tree; never mask harder failures
    _cog5_corpus = None

HAVE_COG5_CORPUS = _cog5_corpus is not None


def lib_cog5_boundary_corpus_module():
    """The t1-owned shared corpus module, or None while it has not landed."""
    return _cog5_corpus


# ==========================================================================
# sim 7 — env scrub + credential-marker leak detection (§4.4 / §8.4)
# ==========================================================================
def lib_cog5_boundary_credential_markers() -> tuple[str, ...]:
    """Credential-shaped NAME markers, assembled from parts at runtime (the
    assembled-token discipline — swept source never carries a contiguous
    secret-looking literal)."""
    return (
        "API" + "_KEY",
        "SECRET",
        "TOKEN",
        "PASSWORD",
        "OAUTH",
        "CREDENTIAL",
        "SCREEN" + "PIPE",
        "KEYCHAIN",
    )


def lib_cog5_boundary_scrub_env(
    source_env: Mapping[str, str],
    allowlist: Iterable[str],
    overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """The §4.4 law: an explicit ALLOWLIST environment, never a denylist.
    Only allowlisted keys survive; overrides are explicit additions the
    harness chooses to inject (never live passthrough)."""
    allowed = set(allowlist)
    scrubbed = {k: v for k, v in source_env.items() if k in allowed}
    if overrides:
        scrubbed.update(dict(overrides))
    return scrubbed


def lib_cog5_boundary_env_leak_findings(
    env: Mapping[str, str],
    markers: tuple[str, ...] | None = None,
) -> list[str]:
    """Findings for every env NAME that looks credential-bearing. The
    detector is the sim-7 oracle: a scrubbed candidate env must yield []."""
    marks = markers if markers is not None else lib_cog5_boundary_credential_markers()
    findings: list[str] = []
    for name in sorted(env):
        upper = name.upper()
        for mark in marks:
            if mark in upper:
                findings.append(f"credential-shaped env var visible: {name}")
                break
    return findings


def lib_cog5_boundary_planted_live_env(
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """A fixture 'live harness env' carrying PLANTED, EXPLICITLY-FAKE
    credential-named vars (names assembled at runtime; values are inert
    placeholders). This is what the env-passthrough MUTANT would leak."""
    planted = {
        "ANTHROPIC" + "_API" + "_KEY": "fixture-fake-value-never-a-real-secret",
        "AWS" + "_SECRET" + "_ACCESS" + "_KEY": "fixture-fake-value-never-a-real-secret",
        "CABINET" + "_OAUTH" + "_TOKEN": "fixture-fake-value-never-a-real-secret",
        "LEGACY" + "_PASSWORD": "fixture-fake-value-never-a-real-secret",
    }
    out = dict(base or {})
    out.update(planted)
    return out


def lib_cog5_boundary_observe_env_via_subprocess(
    env: Mapping[str, str],
) -> dict[str, str]:
    """Run a candidate-shaped probe subprocess (arg-list, no shell) that
    reports the environment it OBSERVES — the sim-7 'scrubbed env observed'
    instrument. Uses sys.executable (python3.12 under the house runner)."""
    probe = "import json, os; print(json.dumps(dict(os.environ)))"
    cp = subprocess.run(
        [sys.executable, "-c", probe],
        env=dict(env),
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    observed = json.loads(cp.stdout)
    if not isinstance(observed, dict):
        raise ValueError("env probe did not return a JSON object")
    return {str(k): str(v) for k, v in observed.items()}


# ==========================================================================
# sim 7 — git hook-execution law (both-ways hooksPath pinning; gate.py
# :372-410 replicated as fixture machinery, never imported)
# ==========================================================================
_HOOK_SENTINEL = "hook-ran.sentinel"


def lib_cog5_boundary_git_env(home: Path, *, pin_hooks: bool) -> dict[str, str]:
    """A hermetic git env: HOME pinned to a scratch dir, system config off.
    pin_hooks=True adds the ENV side of the both-ways law (the exact
    GIT_CONFIG_COUNT/KEY_0/VALUE_0 pins the gate runner uses)."""
    env = {
        "HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }
    if pin_hooks:
        env.update({
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.hooksPath",
            "GIT_CONFIG_VALUE_0": "/dev/null",
        })
    return env


def lib_cog5_boundary_init_repo_with_hostile_hook(root: Path, env: Mapping[str, str]) -> Path:
    """A scratch git repo whose pre-commit hook plants a sentinel file when
    executed — the hook-execution EVIDENCE the sim-7 law must keep at zero."""
    repo = root / "candidate-repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", str(repo)],
        env=dict(env), capture_output=True, text=True, timeout=60, check=True,
    )
    (repo / "payload.txt").write_text("candidate payload\n", encoding="utf-8")
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(f"#!/bin/sh\ntouch {_HOOK_SENTINEL}\nexit 0\n", encoding="utf-8")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return repo


def lib_cog5_boundary_commit(
    repo: Path,
    env: Mapping[str, str],
    *,
    pin_argv: bool,
) -> subprocess.CompletedProcess:
    """Stage + commit in the scratch repo with arg-lists (never a shell).
    pin_argv=True carries the ARGV side of the both-ways law
    (`-c core.hooksPath=/dev/null` on every git argv, gate.py:381-384)."""
    base = ["git"]
    if pin_argv:
        base += ["-c", "core.hooksPath=/dev/null"]
    base += [
        "-c", "user.name=cog5-boundary-fixture",
        "-c", "user.email=cog5-boundary-fixture@invalid",
    ]
    subprocess.run(
        base + ["add", "payload.txt"],
        cwd=str(repo), env=dict(env),
        capture_output=True, text=True, timeout=60, check=True,
    )
    return subprocess.run(
        base + ["commit", "-m", "candidate commit"],
        cwd=str(repo), env=dict(env),
        capture_output=True, text=True, timeout=60, check=True,
    )


def lib_cog5_boundary_hook_execution_evidence(repo: Path) -> bool:
    """True iff the hostile hook RAN (the sentinel exists) — must stay False
    under the both-ways pinning; True is the sim-7 mutant signature."""
    return (repo / _HOOK_SENTINEL).exists()


# ==========================================================================
# sim 7 — euid law (gate.py:386-387 replicated: verify never runs as root)
# ==========================================================================
def lib_cog5_boundary_refuse_privileged(euid: int) -> dict[str, Any]:
    """The euid law as a pure predicate: euid==0 REFUSES (fail-closed), any
    unprivileged euid proceeds. Parameterized so the refusal arm is provable
    without ever being root."""
    if not isinstance(euid, int) or isinstance(euid, bool):
        raise ValueError("euid must be an int")
    if euid == 0:
        return {"ok": False,
                "detail": "refused: candidate verify never runs as root"}
    return {"ok": True, "detail": f"unprivileged euid {euid}"}


# ==========================================================================
# sim 7 / X5 — outside-workdir write fence (post-run diff of everything
# outside the arena workdir must be EMPTY)
# ==========================================================================
def lib_cog5_boundary_tree_fingerprint(root: Path) -> dict[str, str]:
    """rel-path -> sha256 for every regular file under root (sorted walk —
    deterministic). The X5 fence compares fingerprints before/after a
    candidate run."""
    fp: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            rel = path.relative_to(root).as_posix()
            fp[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return fp


def lib_cog5_boundary_outside_workdir_diff(
    before: Mapping[str, str],
    after: Mapping[str, str],
) -> list[str]:
    """Named differences between two outside-tree fingerprints. X5 demands
    []; any entry is an out-of-workdir write/delete/modify escape."""
    diff: list[str] = []
    for rel in sorted(set(before) | set(after)):
        if rel not in before:
            diff.append(f"added outside workdir: {rel}")
        elif rel not in after:
            diff.append(f"removed outside workdir: {rel}")
        elif before[rel] != after[rel]:
            diff.append(f"modified outside workdir: {rel}")
    return diff


# ==========================================================================
# sim 7 — loopback egress probe INSTRUMENT (the detector the harness-level
# egress block will be proven with; 127.0.0.1 only, never external)
# ==========================================================================
def lib_cog5_boundary_egress_probe_via_subprocess(
    port: int,
    env: Mapping[str, str],
) -> str:
    """A candidate-shaped subprocess probe attempting a TCP connect to
    127.0.0.1:<port>. Returns 'connected' or 'refused'. The instrument must
    DISTINGUISH the two — that is what makes it evidence when pointed at the
    real harness (W3): an egress-blocked candidate observes 'refused'."""
    probe = (
        "import socket, sys\n"
        "try:\n"
        "    s = socket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=2.0)\n"
        "    s.close()\n"
        "    print('connected')\n"
        "except OSError:\n"
        "    print('refused')\n"
    )
    cp = subprocess.run(
        [sys.executable, "-c", probe, str(port)],
        env=dict(env), capture_output=True, text=True, timeout=60, check=True,
    )
    return cp.stdout.strip()


def lib_cog5_boundary_egress_findings(probe_result: str) -> list[str]:
    """The sim-7 egress oracle: 'connected' from a candidate probe is an
    egress-open finding; 'refused' is the blocked posture."""
    if probe_result == "connected":
        return ["egress open: candidate probe reached a network endpoint"]
    if probe_result == "refused":
        return []
    raise ValueError(f"unrecognized probe result: {probe_result!r}")


# ==========================================================================
# sim 11 — cost ceilings (declared snapshot inputs, never league-tunable;
# halt/defer with a RECORDED reason; per-candidate cost in the archive)
# ==========================================================================
def lib_cog5_boundary_ceiling_snapshot(
    *,
    max_rounds: int,
    max_total_cost_units: int,
    max_candidate_cost_units: int,
) -> dict[str, int]:
    """The declared ceilings SNAPSHOT — an input to the league loop
    (contract §8.3/sim 11), captured before any round runs."""
    snap = {
        "max_rounds": max_rounds,
        "max_total_cost_units": max_total_cost_units,
        "max_candidate_cost_units": max_candidate_cost_units,
    }
    for key, value in snap.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{key} must be an integer >= 0")
    return snap


def lib_cog5_boundary_snapshot_digest(snapshot: Mapping[str, int]) -> str:
    """Canonical-bytes digest of the declared ceilings — the never-tunable
    tripwire compares this before/after a run."""
    encoded = json.dumps(dict(snapshot), sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def lib_cog5_boundary_round_guard(
    ceilings: Mapping[str, int],
    spent_total: int,
    round_costs: Mapping[str, int],
) -> dict[str, Any]:
    """The pre-round ceiling check: DEFER on a per-candidate breach, HALT on
    a total breach — each with a recorded reason; otherwise proceed."""
    for cid in sorted(round_costs):
        cost = round_costs[cid]
        if not isinstance(cost, int) or isinstance(cost, bool) or cost < 0:
            raise ValueError(f"candidate {cid}: cost_units must be an integer >= 0")
        if cost > ceilings["max_candidate_cost_units"]:
            return {"action": "defer",
                    "reason": (f"candidate {cid} cost {cost} exceeds per-candidate "
                               f"ceiling {ceilings['max_candidate_cost_units']}")}
    projected = spent_total + sum(round_costs.values())
    if projected > ceilings["max_total_cost_units"]:
        return {"action": "halt",
                "reason": (f"projected total cost {projected} exceeds ceiling "
                           f"{ceilings['max_total_cost_units']}")}
    return {"action": "proceed", "reason": None}


def lib_cog5_boundary_run_league_rounds(
    ceilings: dict[str, int],
    rounds: list[dict[str, int]],
    *,
    obey_guard: bool = True,
    tamper_ceilings: bool = False,
) -> dict[str, Any]:
    """REFERENCE league-loop fixture (and its two mutants, selectable):

      obey_guard=True,  tamper=False -> the lawful loop: checks the guard
        before every round, stops on halt/defer with the reason RECORDED,
        stamps per-candidate cost into every archive row.
      obey_guard=False -> the sim-11 'cost-ignoring league loop keeps
        spending' MUTANT: never consults the guard.
      tamper_ceilings=True -> the 'ceilings are league-tunable' MUTANT: the
        loop RAISES its own ceiling mid-run (the drift detector must RED).

    Every emitted row is synthetic-provenance league plumbing: it carries
    `fitness_claim: 'none'` structurally (§6.3) and can never count toward a
    league-opening minimum (§6.2 — see the provenance family below)."""
    declared_digest = lib_cog5_boundary_snapshot_digest(ceilings)
    archive_rows: list[dict[str, Any]] = []
    halt: dict[str, Any] | None = None
    spent = 0
    rounds_run = 0
    for i, round_costs in enumerate(rounds):
        if tamper_ceilings and i == 1:
            # the league-tunable mutant: mid-run self-service ceiling raise
            ceilings["max_total_cost_units"] *= 10
        if obey_guard:
            if rounds_run >= ceilings["max_rounds"]:
                halt = {"action": "halt",
                        "reason": (f"round budget exhausted "
                                   f"({ceilings['max_rounds']} rounds)")}
                break
            decision = lib_cog5_boundary_round_guard(ceilings, spent, round_costs)
            if decision["action"] != "proceed":
                halt = decision
                break
        for cid in sorted(round_costs):
            cost = round_costs[cid]
            spent += cost
            archive_rows.append({
                "candidate_id": cid,
                "cost_units": cost,
                "provenance": "sim_replay",
                "source_class": "arena",
                "fitness_claim": "none",
            })
        rounds_run += 1
    return {
        "archive_rows": archive_rows,
        "halt": halt,
        "rounds_run": rounds_run,
        "spent_total": spent,
        "declared_ceiling_digest": declared_digest,
        "ceilings_after": dict(ceilings),
    }


def lib_cog5_boundary_cost_overrun_findings(
    archive_rows: list[Mapping[str, Any]],
    ceilings: Mapping[str, int],
) -> list[str]:
    """The sim-11 oracle over a run's archive rows: total-ceiling breach,
    per-candidate breach, and any row MISSING its per-candidate cost (the
    'per-candidate cost in the archive' clause) are each named findings."""
    findings: list[str] = []
    total = 0
    for i, row in enumerate(archive_rows):
        cost = row.get("cost_units")
        if not isinstance(cost, int) or isinstance(cost, bool) or cost < 0:
            findings.append(f"archive row {i} missing per-candidate cost_units")
            continue
        total += cost
        if cost > ceilings["max_candidate_cost_units"]:
            findings.append(
                f"candidate {row.get('candidate_id')} cost {cost} exceeds "
                f"per-candidate ceiling {ceilings['max_candidate_cost_units']}")
    if total > ceilings["max_total_cost_units"]:
        findings.append(
            f"total spend {total} exceeds ceiling "
            f"{ceilings['max_total_cost_units']} (loop kept spending)")
    return findings


def lib_cog5_boundary_ceiling_drift_findings(
    declared_digest: str,
    ceilings_after: Mapping[str, int],
) -> list[str]:
    """Ceilings are SNAPSHOT INPUTS, never league-tunable: any post-run
    divergence from the declared digest is a named finding."""
    after = lib_cog5_boundary_snapshot_digest(ceilings_after)
    if after != declared_digest:
        return [f"ceilings drifted from declared snapshot "
                f"({declared_digest} -> {after}) — league-tunable ceilings"]
    return []


def lib_cog5_boundary_halt_findings(halt: Mapping[str, Any] | None) -> list[str]:
    """A halt/defer without a RECORDED reason is itself a violation (sim 11:
    'halt/defer with recorded reason')."""
    if halt is None:
        return []
    reason = halt.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return ["halt/defer without a recorded reason"]
    return []


# ==========================================================================
# §6.2 — provenance (closed enum, ingester-stamped custody, the counting
# predicate): synthetic NEVER opens the league or grounds a live-fitness
# claim — encoded here where this family touches synthetic corpora.
# ==========================================================================
LIB_COG5_BOUNDARY_PROVENANCE = ("real_live", "real_mined", "synthetic", "sim_replay")
LIB_COG5_BOUNDARY_REAL_SOURCE_CLASSES = (
    "consequence_ledger", "fidelity_receipts", "instance_corpus",
    "verdict_inbox", "live_emission",
)
LIB_COG5_BOUNDARY_SYNTHETIC_SOURCE_CLASSES = ("generator", "arena", "sim")


def lib_cog5_boundary_stamp_provenance(
    row: Mapping[str, Any],
    source_class: str,
) -> dict[str, Any]:
    """CHAIN-OF-CUSTODY (§6.2): provenance is stamped by the INGESTER from
    the source class — any provenance a candidate/generator wrote on the row
    is OVERWRITTEN unconditionally (candidate code can never set it)."""
    out = dict(row)
    if source_class == "live_emission":
        out["provenance"] = "real_live"
    elif source_class in LIB_COG5_BOUNDARY_REAL_SOURCE_CLASSES:
        out["provenance"] = "real_mined"
    elif source_class == "sim":
        out["provenance"] = "sim_replay"
    elif source_class in LIB_COG5_BOUNDARY_SYNTHETIC_SOURCE_CLASSES:
        out["provenance"] = "synthetic"
    else:
        raise ValueError(f"unknown source class: {source_class!r} — refuse ingestion")
    out["source_class"] = source_class
    return out


def lib_cog5_boundary_provenance_violations(
    rows: Iterable[Mapping[str, Any]],
) -> list[str]:
    """Findings: missing/out-of-enum provenance (REFUSES ingestion, never
    counts) and the §6.2 LAUNDERING class — a row claiming `real_*`
    provenance whose source class is not a NAMED real source."""
    findings: list[str] = []
    for i, row in enumerate(rows):
        prov = row.get("provenance")
        if prov not in LIB_COG5_BOUNDARY_PROVENANCE:
            findings.append(
                f"row {i}: provenance {prov!r} outside the closed enum — refuse")
            continue
        if prov in ("real_live", "real_mined"):
            src = row.get("source_class")
            if src not in LIB_COG5_BOUNDARY_REAL_SOURCE_CLASSES:
                findings.append(
                    f"row {i}: LAUNDERING — provenance {prov!r} from "
                    f"non-real source class {src!r}")
    return findings


def lib_cog5_boundary_count_toward_minimums(
    rows: Iterable[Mapping[str, Any]],
) -> int:
    """The §6.2 counting predicate: ONLY `real_live`/`real_mined` rows from
    NAMED real sources count toward any league-opening minimum. Synthetic /
    sim_replay rows count ZERO, always."""
    count = 0
    for row in rows:
        if (row.get("provenance") in ("real_live", "real_mined")
                and row.get("source_class") in LIB_COG5_BOUNDARY_REAL_SOURCE_CLASSES):
            count += 1
    return count


# ==========================================================================
# X7 — benchmark-case metadata (spec:37 adopted; §1 X7): a metadata-less
# case REFUSES ingestion.
# ==========================================================================
LIB_COG5_BOUNDARY_X7_REQUIRED = (
    "source_trace_id", "cutoff_ts", "expected", "allowed_tools",
    "scorer_id", "split", "leakage_constraints", "promotion_eligible",
)
LIB_COG5_BOUNDARY_SPLITS = ("public", "private", "holdout")
_CANONICAL_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def lib_cog5_boundary_make_case(**overrides: Any) -> dict[str, Any]:
    """A VALID X7-complete fixture case (synthetic plumbing — split/public,
    promotion-ineligible by default)."""
    case: dict[str, Any] = {
        "source_trace_id": "trace:fixture-0001",
        "cutoff_ts": "2026-07-24T00:00:00Z",
        "expected": {"behavior": "answers from pre-cutoff context only"},
        "allowed_tools": ["read_only_search"],
        "scorer_id": "scorer:machine-outcome-v1",
        "split": "public",
        "leakage_constraints": {"post_cutoff_sources": "forbidden"},
        "promotion_eligible": False,
    }
    case.update(overrides)
    return case


def lib_cog5_boundary_case_metadata_violations(case: Mapping[str, Any]) -> list[str]:
    """The X7 gate: every required metadata field present + well-formed;
    split in the closed set; cutoff canonical UTC Z; promotion_eligible a
    real bool. Any finding = the case REFUSES ingestion."""
    findings: list[str] = []
    for key in LIB_COG5_BOUNDARY_X7_REQUIRED:
        if key not in case:
            findings.append(f"missing required case metadata: {key}")
    if findings:
        return findings
    if case["split"] not in LIB_COG5_BOUNDARY_SPLITS:
        findings.append(f"split {case['split']!r} outside the closed set")
    if not isinstance(case["cutoff_ts"], str) or not _CANONICAL_UTC.match(case["cutoff_ts"]):
        findings.append("cutoff_ts is not canonical UTC Z")
    if not isinstance(case["promotion_eligible"], bool):
        findings.append("promotion_eligible must be a real bool")
    if not isinstance(case["allowed_tools"], list):
        findings.append("allowed_tools must be a list")
    if case["leakage_constraints"] in (None, "", {}):
        findings.append("leakage_constraints must be declared (non-empty)")
    if not isinstance(case["source_trace_id"], str) or not case["source_trace_id"].strip():
        findings.append("source_trace_id must be a non-empty string")
    return findings


def lib_cog5_boundary_league_sees_cases(split: str) -> bool:
    """The §7.1 split law: the league sees CASES only on the public split —
    private = aggregates only; holdout = oracle receipt only."""
    if split not in LIB_COG5_BOUNDARY_SPLITS:
        raise ValueError(f"unknown split: {split!r}")
    return split == "public"


# ==========================================================================
# sim 6 — holdout receipt fixtures (the committed contracts surface)
# ==========================================================================
def lib_cog5_boundary_digest(name: str) -> str:
    return "sha256:" + hashlib.sha256(name.encode("utf-8")).hexdigest()


def lib_cog5_boundary_receipt_schema_keys() -> frozenset[str]:
    """The receipt schema's OWN top-level property set (read from the
    committed schema bytes — no duplicated vocabulary)."""
    schema = json.loads(
        (REPO_ROOT / "framework/schemas/holdout-evaluation-receipt.schema.json")
        .read_text(encoding="utf-8"))
    return frozenset(schema["properties"])


def lib_cog5_boundary_per_case_leak_fields() -> tuple[str, ...]:
    """The per-case payloads a leaking receipt would smuggle (sim 6's second
    seed: 'a receipt carrying per-case data')."""
    return ("cases", "case_fingerprints", "per_case_scores",
            "per_case_results", "outputs")


def lib_cog5_boundary_valid_receipt() -> tuple[dict[str, Any], Any]:
    """A VALID aggregate-only holdout receipt + its trusted
    ValidationContext, built against the committed contracts surface
    (framework/evolution/contracts.py — validate_holdout_receipt :310)."""
    from framework.evolution.contracts import (  # noqa: PLC0415 - fixture-lazy
        ValidationContext,
        holdout_receipt_payload_fingerprint,
    )
    receipt: dict[str, Any] = {
        "schema_version": "holdout-evaluation-receipt/v1",
        "cabinet_id": "cabinet-boundary-fixture",
        "candidate_fingerprint": "sha256:" + "a" * 64,
        "trajectory_fingerprint": "sha256:" + "b" * 64,
        "suite_version": "holdout-suite-fixture-v1",
        "suite_digest": "sha256:" + "c" * 64,
        "aggregate_verdict": "pass",
        "threshold_vector": {
            "threshold:safety": True,
            "threshold:generalization": True,
        },
        "evaluated_at": "2026-07-24T09:00:00Z",
        "attested_artifact_ref": {
            "ref": "receipt:cog5-boundary-holdout",
            "digest": lib_cog5_boundary_digest("receipt:cog5-boundary-holdout"),
        },
        "classification": "restricted",
    }
    oracle_attestation = {
        "digest": lib_cog5_boundary_digest("receipt:cog5-boundary-holdout"),
        "cabinet_id": receipt["cabinet_id"],
        "kind": "holdout_oracle_attestation",
        "subject_id": receipt["trajectory_fingerprint"],
        "actor_type": "holdout_oracle",
        "content_time": receipt["evaluated_at"],
        "recorded_time": "2026-07-24T09:01:00Z",
        "classification": "restricted",
        "sharing": "local",
        "payload": {
            "holdout_receipt_fingerprint":
                holdout_receipt_payload_fingerprint(receipt),
        },
    }
    context = ValidationContext(
        receipts={"receipt:cog5-boundary-holdout": oracle_attestation},
        action_risk_map={},
        holdout_thresholds={
            receipt["suite_digest"]: frozenset(receipt["threshold_vector"]),
        },
    )
    return receipt, context


def lib_cog5_boundary_tolerant_structural_issues(record: Mapping[str, Any]):
    """THE sim-6 MUTANT VALIDATOR — 'per-case field tolerated in a receipt':
    silently DROPS unknown top-level fields before validating (what a
    validator without additionalProperties:false would do). It must MISS the
    per-case leak the real validator refuses — that miss is the proven
    escape."""
    from framework.evolution.contracts import holdout_receipt_structural_issues
    known = lib_cog5_boundary_receipt_schema_keys()
    filtered = {k: v for k, v in record.items() if k in known}
    return holdout_receipt_structural_issues(filtered)


# ==========================================================================
# §12.1 — the declared regression bound (the COG-4 §10 shape, phase-5 keyed)
# ==========================================================================
S0_BASELINE_ARTIFACT_REL = "docs/plans/cog5-s0-baseline-2026-07-24.md"

# The §12.1.2 per-metric tolerance table, DECLARED (pinned verbatim-in-kind
# from the contract; the live test binds this table to the parsed artifact).
LIB_COG5_BOUNDARY_DECLARED_TOLERANCES: dict[str, str] = {
    "cog4_battery_pass_state": "zero",
    "golden_eval_pass_state": "zero",
    "sweep_violations": "zero",
    "files_swept": "exact-integer-accounting",
    "wall_clock": "max(p95*1.25, p95+5s)",
}


def lib_cog5_boundary_percentile_linear(samples: Iterable[float], q: float) -> float:
    """The linear-interpolation percentile (numpy 'linear' / R-7) — the
    method of record for the S0 wall-clock p95 (baseline artifact §
    wall-clock backfill)."""
    xs = sorted(float(x) for x in samples)
    if not xs:
        raise ValueError("no samples")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be within [0, 1]")
    h = (len(xs) - 1) * q
    lo = int(h)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (h - lo) * (xs[hi] - xs[lo])


def lib_cog5_boundary_wall_clock_bound(p95: float) -> float:
    """The §12.1.2 floor-aware wall-clock bound: max(p95*1.25, p95+5s) — a
    fast baseline cannot manufacture spurious REDs."""
    if isinstance(p95, bool) or not isinstance(p95, (int, float)):
        raise ValueError("p95 must be a number")
    if p95 < 0:
        raise ValueError("p95 must be >= 0")
    return max(p95 * 1.25, p95 + 5.0)


def lib_cog5_boundary_parse_s0_baseline(text: str) -> dict[str, Any]:
    """Parse the LANDED §12.1.1 baseline artifact
    (docs/plans/cog5-s0-baseline-2026-07-24.md) into its load-bearing
    numbers. FAIL-LOUD: a missing anchor raises (a bound artifact that stops
    parsing is a broken baseline, never a silent default)."""
    def _one(pattern: str, cast=float):
        m = re.search(pattern, text)
        if not m:
            raise ValueError(f"S0 baseline artifact anchor not found: {pattern!r}")
        return cast(m.group(1))

    samples_m = re.search(r"Pooled n=(\d+), sorted: `\[([^\]]+)\]`", text)
    if not samples_m:
        raise ValueError("S0 baseline artifact: pooled wall-clock samples not found")
    samples = tuple(float(s) for s in samples_m.group(2).split(","))
    arms_m = re.search(
        r"max\(p95×1\.25, p95\+5s\) = max\(([0-9.]+), ([0-9.]+)\) = ([0-9.]+) s",
        text)
    if not arms_m:
        raise ValueError("S0 baseline artifact: bound-formula arms not found")
    full_m = re.search(r"\*\*(\d+) passed / (\d+) skipped / rc=0\*\*", text)
    if not full_m:
        raise ValueError("S0 baseline artifact: full-suite pass state not found")
    golden_m = re.search(r"\*\*(\d+)/(\d+) pass, 0 fail, 0 skip\*\*", text)
    if not golden_m:
        raise ValueError("S0 baseline artifact: golden-eval pass state not found")
    return {
        "pooled_n": int(samples_m.group(1)),
        "wall_clock_samples": samples,
        "p95_recorded": _one(r"\*\*p95 = ([0-9]+\.[0-9]+) s\*\*"),
        "final_bound_recorded": _one(
            r"\*\*FINAL BOUND \(non-provisional\): ([0-9]+\.[0-9]+) s\.\*\*"),
        "bound_arm_x125": float(arms_m.group(1)),
        "bound_arm_plus5": float(arms_m.group(2)),
        "battery_green_count": _one(r"\*\*(\d+) tests, all green\*\*", int),
        "full_suite_passed": int(full_m.group(1)),
        "full_suite_skipped": int(full_m.group(2)),
        "golden_pass": int(golden_m.group(1)),
        "golden_total": int(golden_m.group(2)),
        "files_swept": _one(r"\*\*(\d+) files\*\* swept across", int),
        "sweep_trees": _one(r"swept across \*\*(\d+) SWEEP_TREES\*\*", int),
        "sweep_violations": _one(r"\*\*violations = (\d+)\*\*", int),
    }


def lib_cog5_boundary_wall_clock_violations(
    measured_s: float,
    baseline_p95_s: float,
) -> list[str]:
    """The §12.1.2 wall-clock tripwire: a measured verify-twin wall-clock
    past the floor-aware bound of the FRESH baseline p95 is a named
    violation; within the bound is clean."""
    if isinstance(measured_s, bool) or not isinstance(measured_s, (int, float)):
        raise ValueError("measured_s must be a number")
    bound = lib_cog5_boundary_wall_clock_bound(baseline_p95_s)
    if measured_s > bound:
        return [f"wall-clock {measured_s:.2f}s exceeds bound {bound:.2f}s "
                f"(baseline p95 {baseline_p95_s:.2f}s)"]
    return []


def lib_cog5_boundary_pass_state_violations(
    baseline: Mapping[str, str],
    current: Mapping[str, str],
) -> list[str]:
    """ZERO regression tolerance on pass-state metrics (§12.1.2): every
    baseline-green id must still exist AND still pass. Additions are free;
    a VANISHED baseline test is a violation (absence is not green)."""
    violations: list[str] = []
    for test_id in sorted(baseline):
        if baseline[test_id] != "pass":
            continue  # zero-tolerance binds the green set
        state = current.get(test_id)
        if state is None:
            violations.append(f"{test_id}: baseline-green test VANISHED")
        elif state != "pass":
            violations.append(f"{test_id}: baseline-green now {state!r} "
                              f"(zero regression tolerance)")
    return violations


def lib_cog5_boundary_files_swept_violations(
    measured: int,
    baseline: int,
    phase_added_files: int,
) -> list[str]:
    """§12.1.2(d): the files-swept count moves ONLY by the phase's own added
    files — EXACT integer accounting, both directions."""
    expected = baseline + phase_added_files
    if measured != expected:
        return [f"files-swept {measured} != baseline {baseline} + "
                f"phase-added {phase_added_files} (= {expected}) — "
                f"unaccounted sweep-surface movement"]
    return []


def lib_cog5_boundary_sweep_violation_findings(
    measured_violations: int,
    baseline_violations: int,
) -> list[str]:
    """§12.1.2(d): sweep violations stay ZERO — measured AND baseline."""
    findings: list[str] = []
    if baseline_violations != 0:
        findings.append(
            f"baseline sweep violations {baseline_violations} != 0 — the "
            f"baseline itself is broken")
    if measured_violations != 0:
        findings.append(
            f"sweep violations {measured_violations} != 0 (zero tolerance)")
    return findings
