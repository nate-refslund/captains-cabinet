#!/usr/bin/env python3.12
"""cog4-organ-runner — the composed wake vehicle (COG-4 §9.5, MF-AC2).

The ONE services.yml row this CLI serves (`cog4-organ-runner`, kind cron)
composes N projection/measurement rows into one fixed wake: launchd fires this
CLI on the row's fixed interval; it loads EXACTLY the organ manifests the row
NAMES (the §9.5 wake-row semantics — the row→manifest association is DECLARED
in the row's `organs:` list, never discovered by globbing a directory) and
runs each organ per its OWN manifest (trigger_policy / health_proof / fallback
/ state_ownership discipline), writing each organ's declared outputs.

SCHEDULER-BLIND BY CONSTRUCTION (§9.5): this file never reads, lists, or
writes the shadow scheduler's store, and never imports framework.scheduler —
enforced statically by DELIBERATE ABSENCE from the boundary manifest's
scheduler-token and schedule-store allowlists (cabinet/config/
boundary-manifest.yml rows 4/7, the cog2-import-gate.py:265-268 idiom) and
behaviorally by the §12 runner-invariance battery (test_cog4_organ_runner.py:
with and without a schedule artifact injected into the cache, behavior is
byte-identical). The shadow scheduler's decisions influence NOTHING here —
cutover remains a future pointer/adapter amendment (§7.3 tripwire).

WHAT "run each organ" MEANS:
  * entrypoint mode — the manifest declares `entrypoints.run` (the absorbed
    services.yml row's command, a fixed tracked string): executed via
    /bin/bash -c from the run root, environment inherited from this process
    (launchd's wrapper already cd'd to CABINET_ROOT and sourced cabinet/.env,
    exactly as it did for the absorbed rows). The exit code is classified per
    the manifest's `health_proof.exit_codes`: `ok` (default [0]) and
    `honest_failure` (e.g. judge-calibration's exit 1 = bar honestly NOT met,
    the fail-closed floor WORKING — the absorbed row's documented contract)
    both count as HEALTHY; anything else applies the manifest `fallback`.
  * fixture mode — a manifest WITHOUT entrypoints (the W2 corpus fixture
    shape) gets the deterministic reference projection: the canonical JSON
    body {organ, payload, wake_id} written to its first declared output — the
    exact test_cog4_organ_runner.py reference_runner semantic, so the
    invariance battery binds to this CLI unchanged.

PER-ORGAN RECEIPT (the §9.2 probe law's artifact): after every HEALTHY organ
completion (ok or honest_failure) the runner atomically rewrites
<run-root>/cabinet/cache/organs/<name>/last-run.json (deterministic content —
no clock), which is the `freshness_needs.expected_output` the watchdog's
per-organ derived floors probe (framework/watchdog/registry.py
_parse_organ_manifests). A persistently failing organ inside a live runner
stops stamping its receipt and trips ITS OWN floor while the shared runner
log stays fresh — floors are conserved per organ, never pooled (§9.2
COUNT+TUPLE).

FALLBACK SEMANTICS (manifest `fallback`, §4.2): skip | safe_noop → record the
failure on stderr and continue with the remaining organs (quiet degrade — the
per-organ floor is the pager); escalate → print a FATAL marker line (the
watchdog JOB_ERROR_MARKERS tail scan pages on it) and exit 1 at the end.
Structural refusals (row/manifest unreadable, state_ownership collision,
non-periodic trigger_policy) exit 2 — a mis-deployment, never a quiet skip.

Behavior JSON (stdout, deterministic): {"organs_selected", "outputs",
"results", "exit_status"} — log lines go to stderr so stdout stays parseable
(the invariance battery's adapter reads it).

Modes:
  default        — --services-yml cabinet/services.yml --service
                   cog4-organ-runner (the launchd invocation)
  --row-json     — a row fixture {"organs": [...], "wake_id": ...} +"
                   --manifest-dir (bare organ names resolve to
                   <manifest-dir>/<name>.manifest.json — the corpus harness
                   shape)
  --plan         — load + validate + print the behavior JSON with nothing
                   executed and nothing written (doctor/test smoke)

Boundary (§8.3): imports framework.organs ONLY (an allowlisted organs reader:
read_manifest_file + state_ownership_collisions); no framework.scheduler, no
authority/acting/frontdoor imports, no network, no credentials.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; fleet composition rides the 2026-07-21
ownership-on-GO (COG-4 W6 unit e2, Fable-for-execution per the 2026-07-23
calibration).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from framework.organs.registry import (  # noqa: E402  (allowlisted organs reader, §8.3 row 5)
    MANIFEST_SUFFIXES,
    OrganRegistryError,
    read_manifest_file,
    state_ownership_collisions,
)

RUNNER_SERVICE_DEFAULT = "cog4-organ-runner"
RECEIPT_REL_DIR = Path("cabinet") / "cache" / "organs"


class RunnerRefusal(ValueError):
    """A structural mis-deployment — the runner refuses (exit 2), never a
    quiet partial wake."""


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# row loading — the DECLARED row→manifest association (§9.5)
# ---------------------------------------------------------------------------

def load_row_from_services(services_yml: Path, service: str) -> dict:
    """The runner row from cabinet/services.yml: name + the `organs:` list of
    manifest paths. PyYAML is fine cabinet-side (the stdlib-only survival
    contract binds the watchdog registry, not this CLI)."""
    import yaml  # deferred: fixture mode must not require it

    try:
        doc = yaml.safe_load(services_yml.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RunnerRefusal(f"services manifest unreadable: {exc}") from None
    rows = (doc or {}).get("services")
    if not isinstance(rows, list):
        raise RunnerRefusal(f"{services_yml}: no services list")
    matches = [r for r in rows
               if isinstance(r, dict) and r.get("name") == service]
    if len(matches) != 1:
        raise RunnerRefusal(
            f"{services_yml}: expected exactly one {service!r} row, "
            f"found {len(matches)}")
    row = matches[0]
    organs = row.get("organs")
    if not isinstance(organs, list) or not organs or \
            not all(isinstance(o, str) and o.strip() for o in organs):
        raise RunnerRefusal(
            f"{service}: the runner row must EXPLICITLY name its composed "
            "organ manifests in a non-empty `organs:` list (§9.5 declared "
            "association — never discovery)")
    return {"service": service, "wake_id": "wake-fixed",
            "organs": [o.strip() for o in organs]}


def load_row_from_json(row_json: Path) -> dict:
    try:
        row = json.loads(row_json.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RunnerRefusal(f"row fixture unreadable: {exc}") from None
    if not isinstance(row, dict) or not isinstance(row.get("organs"), list):
        raise RunnerRefusal("row fixture must be a mapping with an organs list")
    row.setdefault("wake_id", "wake-fixed")
    return row


def resolve_manifest_ref(ref: str, *, manifest_base: Path,
                         manifest_dir: Path | None) -> Path:
    """One declared organ ref → one manifest file path. A ref carrying a
    manifest suffix is a path (absolute, or relative to `manifest_base` — the
    root the DECLARING manifest's refs are written against: the services.yml
    repo root in services mode, the run root in fixture mode); a bare name is
    the corpus-harness shape <manifest-dir>/<name>.manifest.json. Resolution
    is DECLARATIVE — no globbing, no discovery (§9.5)."""
    if any(ref.endswith(sfx) for sfx in MANIFEST_SUFFIXES):
        p = Path(os.path.expanduser(ref))
        if not p.is_absolute():
            p = manifest_base / p
        return p
    if manifest_dir is None:
        raise RunnerRefusal(
            f"organ ref {ref!r} is a bare name but no --manifest-dir was "
            "given (bare names are the fixture-harness shape)")
    return manifest_dir / f"{ref}.manifest.json"


def load_declared_manifests(row: dict, *, manifest_base: Path,
                            manifest_dir: Path | None) -> list[dict]:
    """Load EXACTLY the manifests the row names — a structurally unreadable
    manifest refuses the whole wake (fail-closed; a partial fleet is a lie).
    Structural checks mirror the organs registry (kind == organ, non-empty
    unique name); §4.2 schema validation stays parked (CG-33 window)."""
    manifests: list[dict] = []
    seen: dict[str, str] = {}
    for ref in row["organs"]:
        path = resolve_manifest_ref(ref, manifest_base=manifest_base,
                                    manifest_dir=manifest_dir)
        try:
            manifest = read_manifest_file(path)
        except OrganRegistryError as exc:
            raise RunnerRefusal(f"declared manifest {ref!r}: {exc}") from None
        if manifest.get("kind") != "organ":
            raise RunnerRefusal(
                f"{path.name}: kind is {manifest.get('kind')!r}, not 'organ'")
        name = manifest.get("name")
        if not isinstance(name, str) or not name:
            raise RunnerRefusal(f"{path.name}: no non-empty organ name")
        if name in seen:
            raise RunnerRefusal(
                f"{path.name}: duplicate organ name {name!r} "
                f"(already declared by {seen[name]})")
        seen[name] = path.name
        manifests.append(manifest)
    collisions = state_ownership_collisions(manifests)
    if collisions:
        raise RunnerRefusal(
            "state_ownership discipline violated (§4.2/§9.5): "
            + "; ".join(collisions))
    for manifest in manifests:
        policy = manifest.get("trigger_policy")
        mode = policy.get("mode") if isinstance(policy, dict) else policy
        if mode not in (None, "periodic"):
            raise RunnerRefusal(
                f"{manifest['name']}: trigger_policy mode {mode!r} is not "
                "runnable by the fixed-wake vehicle (v1 runs periodic organs "
                "on every wake; event/on_demand organs need the future "
                "dispatch amendment)")
    return manifests


# ---------------------------------------------------------------------------
# running one organ
# ---------------------------------------------------------------------------

def _exit_class(manifest: dict, rc: int) -> str:
    """Classify an entrypoint exit code per the manifest health_proof:
    ok (default [0]) | honest_failure (declared, e.g. judge-calibration's
    exit-1-by-design) | failed."""
    hp = manifest.get("health_proof")
    codes = hp.get("exit_codes") if isinstance(hp, dict) else None
    ok = codes.get("ok") if isinstance(codes, dict) else None
    honest = codes.get("honest_failure") if isinstance(codes, dict) else None
    ok_list = ok if isinstance(ok, list) else [0]
    honest_list = honest if isinstance(honest, list) else []
    if rc in ok_list:
        return "ok"
    if rc in honest_list:
        return "honest_failure"
    return "failed"


def _atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-receipt-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _stamp_receipt(run_root: Path, name: str, wake_id: str, status: str) -> None:
    """The per-organ liveness receipt the watchdog's derived floor probes
    (freshness = mtime; content deterministic — no clock reads here)."""
    receipt = run_root / RECEIPT_REL_DIR / name / "last-run.json"
    _atomic_write(receipt, _canon({"organ": name, "wake_id": wake_id,
                                   "status": status}) + b"\n")


def run_organ(manifest: dict, *, run_root: Path, wake_id: str) -> dict:
    """Run ONE organ per its manifest. Returns {status, rc, fallback}."""
    name = manifest["name"]
    entry = manifest.get("entrypoints")
    command = entry.get("run") if isinstance(entry, dict) else None
    if command:
        proc = subprocess.run(["/bin/bash", "-c", command], cwd=str(run_root),
                              stdout=sys.stderr, stderr=sys.stderr,
                              check=False)
        status = _exit_class(manifest, proc.returncode)
        rc = proc.returncode
    else:
        # fixture projection — the corpus reference semantic (module docstring)
        outputs = manifest.get("outputs") or []
        if not outputs:
            raise RunnerRefusal(f"{name}: no entrypoint and no declared output")
        out_path = run_root / str(outputs[0])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        body = _canon({"organ": name, "payload": manifest.get("payload"),
                       "wake_id": wake_id}).decode("utf-8") + "\n"
        out_path.write_text(body, encoding="utf-8")
        status, rc = "ok", 0
    if status in ("ok", "honest_failure"):
        _stamp_receipt(run_root, name, wake_id, status)
    return {"status": status, "rc": rc,
            "fallback": str(manifest.get("fallback") or "skip")}


def _output_digests(manifest: dict, run_root: Path, *, ran: bool) -> dict:
    """Declared-output digests for the behavior record: sha256 of each output
    that exists under the run root (relative outputs only — absolute/external
    surfaces are reported as null, they are the organ script's own artifacts),
    null otherwise. Deterministic; --plan never reads (all null)."""
    digests: dict[str, str | None] = {}
    for rel in manifest.get("outputs") or []:
        rel = str(rel)
        digests[rel] = None
        if not ran or os.path.isabs(os.path.expanduser(rel)):
            continue
        p = run_root / rel
        if p.is_file():
            digests[rel] = _digest(p.read_bytes())
    return digests


# ---------------------------------------------------------------------------
# the wake
# ---------------------------------------------------------------------------

def run_wake(row: dict, *, run_root: Path, manifest_base: Path,
             manifest_dir: Path | None, plan_only: bool) -> dict:
    manifests = load_declared_manifests(row, manifest_base=manifest_base,
                                        manifest_dir=manifest_dir)
    wake_id = str(row.get("wake_id") or "wake-fixed")
    selected: list[str] = []
    outputs: dict[str, str | None] = {}
    results: dict[str, dict] = {}
    escalated = False
    for manifest in manifests:
        name = manifest["name"]
        selected.append(name)
        if plan_only:
            results[name] = {"status": "planned", "rc": None,
                             "fallback": str(manifest.get("fallback") or "skip")}
            outputs.update(_output_digests(manifest, run_root, ran=False))
            continue
        result = run_organ(manifest, run_root=run_root, wake_id=wake_id)
        results[name] = result
        outputs.update(_output_digests(manifest, run_root, ran=True))
        if result["status"] == "failed":
            fallback = result["fallback"]
            if fallback == "escalate":
                # the marker the watchdog tail scan pages on (JOB_ERROR_MARKERS)
                _log(f"FATAL: organ {name} failed rc={result['rc']} "
                     f"(fallback=escalate)")
                escalated = True
            else:
                # quiet degrade: the per-organ receipt floor is the pager
                _log(f"organ {name} failed rc={result['rc']} — "
                     f"fallback={fallback}; continuing (its derived floor "
                     "pages on persistence)")
        else:
            _log(f"organ {name}: {result['status']} (rc={result['rc']})")
    exit_status = 1 if escalated else 0
    return {"organs_selected": selected, "outputs": outputs,
            "results": results, "exit_status": exit_status}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--services-yml", type=Path, default=None,
                    help="fleet manifest (default <run-root>/cabinet/services.yml)")
    ap.add_argument("--service", default=RUNNER_SERVICE_DEFAULT,
                    help=f"runner row name (default {RUNNER_SERVICE_DEFAULT})")
    ap.add_argument("--row-json", type=Path, default=None,
                    help="row fixture JSON (the invariance-battery shape)")
    ap.add_argument("--manifest-dir", type=Path, default=None,
                    help="resolution root for BARE organ names (fixture mode)")
    ap.add_argument("--run-root", type=Path, default=None,
                    help="root for outputs/receipts + entrypoint cwd "
                         "(default $CABINET_ROOT, else the repo root)")
    ap.add_argument("--plan", action="store_true",
                    help="load + validate + print the behavior JSON; execute "
                         "nothing, write nothing")
    args = ap.parse_args(argv)

    run_root = (args.run_root
                or Path(os.environ.get("CABINET_ROOT") or _REPO)).resolve()
    try:
        if args.row_json is not None:
            row = load_row_from_json(args.row_json)
            manifest_base = run_root
        else:
            services_yml = (args.services_yml
                            or (run_root / "cabinet" / "services.yml")).resolve()
            row = load_row_from_services(services_yml, args.service)
            # the row's refs are written against ITS repo root (services.yml
            # lives at <root>/cabinet/services.yml) — never the write root.
            manifest_base = (services_yml.parents[1]
                             if services_yml.parent.name == "cabinet"
                             else services_yml.parent)
        behavior = run_wake(row, run_root=run_root,
                            manifest_base=manifest_base,
                            manifest_dir=args.manifest_dir,
                            plan_only=args.plan)
    except RunnerRefusal as exc:
        _log(f"cog4-organ-runner: REFUSED — {exc}")
        return 2
    print(json.dumps(behavior, sort_keys=True))
    return int(behavior["exit_status"])


if __name__ == "__main__":
    raise SystemExit(main())
