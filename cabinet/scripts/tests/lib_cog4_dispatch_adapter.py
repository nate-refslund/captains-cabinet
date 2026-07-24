"""lib_cog4_dispatch_adapter.py — the REAL-CLI adapter for the W2 T2 dispatch
sims (COG-4 §7.3/W5; contract §12 rows 3/5/6/9/10/11/12/14/15 + the six-limb
order battery). Helper, not a test (pytest collects test_*.py only).

PURPOSE — the retirement vehicle: the T2 corpus (`test_cog4_sim_dispatch.py`)
pins the dispatcher spec against a fixture store + a pure reference function;
its 10 vacuity arms retire onto "a subprocess adapter over the real CLI's
shadow-record output" the moment `cabinet/scripts/cog4-dispatch-shadow.py`
lands. THIS is that adapter: it (a) builds REAL kernel-shaped schedule stores
(the framework.scheduler.model algebra — legal here: the boundary rows
allowlist `lib_cog4_*` for framework.scheduler) seeded with the same scenario
content the corpus seeds, (b) runs the landed CLI as a subprocess, and (c)
parses its stdout outcome into an Outcome-shaped object carrying the same
mode/reason/records vocabulary the corpus asserts. `test_cog4_dispatch_cli.py`
runs the corpus properties through it OUT-OF-BAND now (pre-proving the
post-surgery state green, §13 — the corpus stays untouched; the integrator
performs the actual arm retirement).

TWO STORE BUILDERS:
  * `build_real_store(cache_dir, snapshot, rows)` — the RAW writer: canonical
    bytes + the model.schedule_rows_hash chain + the full manifest envelope
    (epoch/counts/conflicts/schedule_rows_hash) + the snapshot-record binding,
    WITHOUT model.validate_snapshot. This is what lets the corpus's
    invalid-by-construction seeds (a recorded-null wake-input hash, an in-run
    duplicate row — §12 sims 14/order) exist as SERVABLE stores: serve
    verifies integrity, not builder-side schema, and the dispatcher must
    refuse from its OWN limbs.
  * `fold_real_store(snapshot_path, cache_dir)` — the real fold
    (framework.scheduler.fold.build_schedule) for valid snapshots.

FIXTURE-POLICY TRANSLATION: the corpus's fixture verdict policy
({risk_verdicts, undo_required}) maps onto the CLI's matrix_policy-shaped
JSON via wildcard verdict rows — `fixture_policy()`:
  fixture_low -> {"*": "auto"}; fixture_propose -> {"*": "propose_only"};
  fixture_gated -> {"*": "always_gated"}; fixture_mutating ->
  {"*": "act_with_undo"} (the undo_required semantics: an act_with_undo
  verdict over a descriptor declaring undo_contract "none" is the
  dispatcher's declared undo gap). A ceiling refusal needs no policy row —
  the declared `ceiling` member short-circuits (§5.2).

SELF-CONTAINED BY LAW (L1111): mirrors the corpus seed vocabulary in ITS OWN
constants; imports nothing from `test_cog4_sim_dispatch.py`. (Authored
imported by no W2 corpus file; since the W5 landing 2026-07-24 the corpus's
RETIRED TestRealDispatchCliArms import this adapter as their real-CLI binding
— the L1111 concern, shared constants between parallel W2 units, stays
intact: this is a W5 lib, not a sibling W2 corpus.)

S0: python3.12, no DB, no network (subprocess runs the in-repo CLI only).
Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; COG-4 W5 x1.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from framework.scheduler import model as _model  # noqa: E402
from framework.scheduler.fold import build_schedule as _fold_build  # noqa: E402

DISPATCH_CLI = _REPO / "cabinet" / "scripts" / "cog4-dispatch-shadow.py"

CUTOFF = "2026-07-20T00:00:00Z"

# the seven §7.1 wake-input keys (mirrored constant — corpus vocabulary).
WAKE_INPUT_KEYS = (
    "cortex_belief_store_hash",
    "objectives_graph_rows_hash",
    "organ_registry_hash",
    "services_manifest_hash",
    "organ_health_hash",
    "failure_history_hash",
    "capability_availability_hash",
)


# ---------------------------------------------------------------------------
# scenario seeds (the corpus make_* shapes, emitted onto the REAL store)
# ---------------------------------------------------------------------------
def make_snapshot(**overrides) -> dict:
    """A serve-shaped snapshot record: the seven wake-input hashes + scope +
    canonical cutoff (what the serve limbs bind). Extra members ride along
    canonically. Overrides merge `wake_input_hashes` member-wise (the corpus
    idiom) — a None value stays None (the sim-14 recorded-null seed)."""
    snap = {
        "schema_version": _model.SNAPSHOT_SCHEMA_VERSION,
        "scope": "fixture",
        "cutoff": CUTOFF,
        "wake_input_hashes": {
            "cortex_belief_store_hash": "cortexhash-aaa",
            "objectives_graph_rows_hash": "objgraphhash-bbb",
            "organ_registry_hash": "registryhash-ccc",
            "services_manifest_hash": "serviceshash-ddd",
            "organ_health_hash": "healthhash-eee",
            "failure_history_hash": "failhash-fff",
            "capability_availability_hash": "capshash-ggg",
        },
    }
    for key, value in overrides.items():
        if key == "wake_input_hashes":
            snap["wake_input_hashes"] = dict(snap["wake_input_hashes"],
                                             **value)
        else:
            snap[key] = value
    return snap


def make_row(organ: str, operation: str, *, risk="fixture_low", ceiling=(),
             undo="none", budget_units=1, deps=(), decision="select",
             reason="selected", subject=None, action_type=None,
             **extra) -> dict:
    """A REAL §7.2 decision row (the full ROW_FIELDS tuple) carrying the
    corpus descriptor shape: the three enforcement members + the open
    capability identity (+ an optional compat action_type)."""
    capability = f"{organ}/{operation}" if "/" not in operation else operation
    descriptor = {
        "capability": capability,
        "risk_class": risk,
        "ceiling": sorted(ceiling),
        "undo_contract": undo,
    }
    if action_type is not None:
        descriptor["action_type"] = action_type
    row = {
        "organ": organ,
        "operation": operation,
        "subject": subject,
        "descriptor": descriptor,
        "decision": decision,
        "reason": reason,
        "budget_units": budget_units,
        "deps": deps if isinstance(deps, dict) else sorted(deps),
        "tie_break_key": _model.tie_break_key(organ, operation),
    }
    row.update(extra)
    return row


def make_organ_manifest(name: str, *, max_staleness=3600, fallback="skip",
                        permissions=(), dependencies=(),
                        idem_fields=("organ", "operation", "wake_id")) -> dict:
    """The corpus fixture organ manifest (the PROPOSED §4.2 fields as data)."""
    return {
        "name": name,
        "kind": "organ",
        "freshness_needs": {
            "max_staleness_seconds": max_staleness,
            "expected_output": f"out/{name}.json",
        },
        "fallback": fallback,
        "permissions": sorted(permissions),
        "dependencies": sorted(dependencies),
        "idempotency": {"key_fields": list(idem_fields)},
    }


def make_live(snapshot: dict, manifests: dict, **overrides) -> dict:
    """Declared live state at (hypothetical) dispatch time — the corpus
    shape; every member is data handed to the CLI as a file."""
    live = {
        "wake_input_hashes": dict(snapshot["wake_input_hashes"]),
        "remaining_budget": 100,
        "wake_id": "wake-0001",
        "organ_output_age_seconds": {name: 0 for name in manifests},
        "organ_health": {name: {"probe_ran": True, "exit_code": 0}
                         for name in manifests},
        "organs_available": sorted(manifests),
        "capabilities_available": sorted(
            {p for m in manifests.values()
             for p in m.get("permissions", ())}),
        "services_cadence": [{"service": "fixture-cron-row",
                              "interval_seconds": 1800}],
    }
    live.update(overrides)
    return live


def fixture_policy() -> dict:
    """The corpus fixture verdict policy translated to the CLI's
    matrix_policy document shape (wildcard rows — module docstring)."""
    return {
        "verdicts": {
            "fixture_low": {"*": "auto"},
            "fixture_propose": {"*": "propose_only"},
            "fixture_gated": {"*": "always_gated"},
            "fixture_mutating": {"*": "act_with_undo"},
        },
    }


# ---------------------------------------------------------------------------
# real-store builders
# ---------------------------------------------------------------------------
def build_real_store(cache_dir: Path, snapshot: dict, rows: list) -> dict:
    """The RAW kernel-shaped writer: rows total-ordered by tie_break_key, the
    real chain (model.schedule_rows_hash) + the full manifest envelope +
    snapshot-record binding — NO validate_snapshot (see module docstring).
    Returns the manifest."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda r: r["tie_break_key"])
    record = _model.canonical_bytes(snapshot)
    (cache_dir / _model.SNAPSHOT_RECORD_FILE).write_bytes(record)
    (cache_dir / _model.SCHEDULE_FILE).write_text(
        "".join(_model.canonical_bytes(r).decode("utf-8") + "\n"
                for r in ordered), encoding="utf-8")
    selected = sum(1 for r in ordered if r.get("decision") == "select")
    manifest = {
        "schema_version": _model.MANIFEST_SCHEMA_VERSION,
        "epoch": {
            "scheduler_version": _model.SCHEDULER_VERSION,
            "snapshot_hash": _model.sha256_hex(record),
            "wake_input_hashes": dict(snapshot["wake_input_hashes"]),
            "scope": snapshot["scope"],
            "cutoff": snapshot["cutoff"],
        },
        _model.MANIFEST_ROWS_HASH_KEY: _model.schedule_rows_hash(ordered),
        "counts": {"rows": len(ordered), "selected": selected,
                   "deferred": len(ordered) - selected,
                   "conflicts": 0},
        "conflicts": [],
    }
    (cache_dir / _model.MANIFEST_FILE).write_bytes(
        _model.canonical_bytes(manifest))
    return manifest


def fold_real_store(snapshot_path: Path, cache_dir: Path) -> dict:
    """The real §7.2 fold over a VALID snapshot file (validate_snapshot
    enforced inside)."""
    return _fold_build(snapshot_path, cache_dir)


def crashed_build(snapshot: dict, rows: list, cache_dir: Path) -> None:
    """A mid-fold KILL: only a .tmp lands — a prior valid store (if any)
    stays untouched (the corpus sim-15 seed)."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda r: r["tie_break_key"])
    (cache_dir / (_model.SCHEDULE_FILE + ".tmp")).write_text(
        "".join(_model.canonical_bytes(r).decode("utf-8") + "\n"
                for r in ordered), encoding="utf-8")


# ---------------------------------------------------------------------------
# the subprocess adapter (Outcome over the CLI's shadow-record output)
# ---------------------------------------------------------------------------
class Outcome:
    """The corpus Outcome shape rebuilt from the CLI's stdout record."""

    def __init__(self, payload: dict, returncode: int, stderr: str) -> None:
        self.mode = payload.get("mode")
        self.reason = payload.get("reason")
        self.records = payload.get("records", [])
        self.safe_schedule = payload.get("safe_schedule")
        self.payload = payload
        self.returncode = returncode
        self.stderr = stderr

    def would_dispatch(self) -> list:
        return [r for r in self.records
                if r.get("decision") == "would_dispatch"]


def run_cli(cache_dir: Path, live: dict, manifests: dict, policy: dict,
            workdir: Path, *, shadow_log: Path | None = None,
            shadow_seed_keys: tuple = (), officer: str = "cos",
            lane: str | None = None, posture: str | None = None,
            now: str | None = None, live_joint: bool = False,
            pointer_path: Path | None = None,
            extra_env: dict | None = None) -> Outcome:
    """Materialize the declared inputs as files, run the landed CLI, parse
    the stdout outcome. `shadow_seed_keys` pre-seeds idempotency keys into
    the shadow log (the corpus live["shadow_log"] seam); the pointer default
    is pointed INTO the workdir so a developer machine's real state never
    leaks into a test run."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    live_p = workdir / "live-state.json"
    live_p.write_text(json.dumps(live), encoding="utf-8")
    man_p = workdir / "organ-manifests.json"
    man_p.write_text(json.dumps(manifests), encoding="utf-8")
    pol_p = workdir / "matrix-policy.json"
    pol_p.write_text(json.dumps(policy), encoding="utf-8")
    log_p = Path(shadow_log) if shadow_log else workdir / "shadow-log.jsonl"
    if shadow_seed_keys:
        with log_p.open("a", encoding="utf-8") as fh:
            for key in shadow_seed_keys:
                fh.write(json.dumps({"idempotency_key": key}) + "\n")
    pointer = Path(pointer_path) if pointer_path \
        else workdir / "no-pointer-here"

    cmd = [sys.executable, str(DISPATCH_CLI),
           "--cache-dir", str(cache_dir),
           "--live", str(live_p),
           "--organ-manifests", str(man_p),
           "--matrix-policy", str(pol_p),
           "--shadow-log", str(log_p),
           "--officer", officer,
           "--pointer-path", str(pointer)]
    if lane is not None:
        cmd += ["--lane", lane]
    if posture is not None:
        cmd += ["--posture", posture]
    if now is not None:
        cmd += ["--now", now]
    if live_joint:
        cmd += ["--live-joint"]
    env = None
    if extra_env is not None:
        import os as _os
        env = dict(_os.environ, **extra_env)
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          cwd=str(_REPO), env=env)
    payload: dict = {}
    for line in proc.stdout.strip().splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                payload = json.loads(line)
            except ValueError:
                continue
    assert payload or proc.returncode == 3, (
        f"CLI emitted no outcome record (rc={proc.returncode})\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}")
    return Outcome(payload, proc.returncode, proc.stderr)


def derive_idempotency_key(organ: str, operation: str, wake_id: str,
                           key_fields=("organ", "operation",
                                       "wake_id")) -> str:
    """The corpus/CLI key derivation (sha256 over canonical ensure_ascii
    False JSON of the declared fields) — for seeding replay scenarios."""
    import hashlib
    context = {"organ": organ, "operation": operation, "wake_id": wake_id}
    payload = {f: context[f] for f in key_fields}
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def by_organ(outcome: Outcome, organ: str) -> dict:
    matches = [r for r in outcome.records if r.get("organ") == organ]
    assert matches, f"no record for organ {organ!r}: {outcome.records}"
    return matches[0]
