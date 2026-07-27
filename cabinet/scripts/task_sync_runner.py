"""Task sync runner — orchestrates one sync cycle between Cabinet and external task system.

Phase 5 of the convergence plan. Invoked by `cabinet/cron/task-sync.sh`
every 15 minutes via the cabinet/services.yml `task-sync` row
(interval_s: 900 — the manifest is the cadence truth; the old 5-min header
claim matched nothing and was corrected 2026-07-17).

Pull-only Phase 5 stub: the PUSH half needs the Phase 6 canonical-store
reader (see run_sync body). The nightly task-sync-drift falsifier
(cabinet/scripts/task-sync-drift-falsifier.py) watches the mirror claim.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure framework root is importable
_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from cabinet.scripts.task_adapters.base import (
    CanonicalTask,
    ObserveOnlyTaskAdapter,
    SyncResult,
    get_adapter,
)
from framework.env import active_context
from framework.events.emitter import emit

try:
    from yaml import safe_load as _yaml_load
except ImportError:
    import yaml as _yaml_mod
    _yaml_load = _yaml_mod.safe_load


def _active_project_config(cabinet_root: str | None = None) -> dict[str, Any]:
    """Read instance/config/projects/<slug>.yml for the resolved task context.

    Context resolution is the shared preset-aware chain
    (``framework.env.active_context`` — twin of ``lib/lanes.sh
    cabinet_resolve_context``): ``CABINET_CONTEXT`` env >
    ``instance/config/active-project.txt`` > preset-derived (single declared
    lane, else the declared ``lane_default``). The runner is deployment-scoped
    (no officer identity), so on a multi-lane preset deployment it needs
    ``CABINET_CONTEXT`` in its launchd/cron env (one runner per lane) or a
    declared ``lane_default`` — resolution failure is LOUD with that remedy,
    never a crash-loop on a missing file that the deployment shape simply
    doesn't write. The resolver shape-gates every slug
    (``[a-z0-9][a-z0-9-]{0,31}``), so the path join below is traversal-safe.
    """
    if cabinet_root is None:
        cabinet_root = os.environ.get(
            "CABINET_ROOT",
            str(Path(__file__).parent.parent.parent),
        )
    slug = active_context(root=cabinet_root)
    if not slug:
        raise FileNotFoundError(
            "cannot resolve a task context — set CABINET_CONTEXT in the "
            "runner's env, write instance/config/active-project.txt, or "
            "declare instance/config/contexts/<lane>.yml plus a lane_default "
            "in instance/config/platform.yml"
        )

    proj_file = Path(cabinet_root) / "instance" / "config" / "projects" / f"{slug}.yml"
    if not proj_file.exists():
        raise FileNotFoundError(f"Project config not found: {proj_file}")

    with open(proj_file) as f:
        return _yaml_load(f) or {}


def run_sync(actor: str = "task_sync_runner") -> SyncResult:
    """One sync cycle: pull → push pending canonical changes (stubbed)."""
    project_config = _active_project_config()
    adapter = get_adapter(project_config)
    destination = adapter.destination

    # An observe-only adapter is a DIFFERENT TYPE, so this reads the fact
    # rather than a flag anyone can set (see task_adapters/base.py).
    observe_only = isinstance(adapter, ObserveOnlyTaskAdapter)
    result = SyncResult(
        destination=destination,
        started_at=datetime.now(timezone.utc).isoformat(),
        read_only=observe_only,
        ownership=getattr(adapter, "ownership", None),
    )

    # payload.kind discriminator (COG-1 §7 fence): these three emits SHARE the
    # central outbox_queued/dispatched/failed vocabulary with the relay proper
    # and the channels journal. Stamping kind='task_sync_telemetry' lets parity
    # tooling and the legacy ledger drain fence out this writer family so no
    # metric double-counts (the EVENT TYPES are UNCHANGED — no VALID_EVENT_TYPES
    # edit; renames are Phase-7 compaction work).
    emit("outbox_queued", actor=actor, payload={
        "kind": "task_sync_telemetry",
        "destination": destination,
        "payload": {"event": "task_sync_started", "destination": destination},
        "idempotency_key": f"task_sync_start_{result.started_at}",
    })

    # Health check first; abort early on failure.
    if not adapter.health_check():
        msg = f"adapter health_check failed for {destination}"
        result.errors.append(msg)
        result.finished_at = datetime.now(timezone.utc).isoformat()
        emit("outbox_failed", actor=actor, payload={
            "kind": "task_sync_telemetry",
            "destination": destination,
            "error": msg,
            "terminal": False,
        })
        return result

    # Pull external state. Skeleton adapters return NotImplementedError;
    # treat as zero-tasks-pulled and log a warning.
    try:
        external_tasks = adapter.pull()
    except NotImplementedError as e:
        result.errors.append(f"pull not implemented for {destination}: {e}")
        external_tasks = []
    except Exception as e:  # noqa: BLE001
        result.errors.append(f"pull failed for {destination}: {e}")
        external_tasks = []

    result.pulled = len(external_tasks)

    # Phase 5 MVP: pull only. The PUSH side requires reading Cabinet's
    # canonical task store (officer_tasks Postgres table OR event-replay
    # derivation), which is Phase 6 work (product-bootstrap will populate
    # the canonical store from the explored product).
    # Future: iterate canonical tasks → adapter.push(...) → record SyncResult.pushed

    result.finished_at = datetime.now(timezone.utc).isoformat()
    emit("outbox_dispatched", actor=actor, payload={
        "kind": "task_sync_telemetry",
        "destination": destination,
        "pulled": result.pulled,
        "pushed": result.pushed,
        "errors": result.errors,
        "read_only": result.read_only,
        "ownership": result.ownership,
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a task sync cycle")
    parser.add_argument("--health", action="store_true",
                        help="Health-check the adapter only; exit 0 if healthy, 1 if not")
    parser.add_argument("--json", action="store_true", help="JSON summary on stdout")
    args = parser.parse_args(argv)

    if args.health:
        try:
            project_config = _active_project_config()
            adapter = get_adapter(project_config)
            ok = adapter.health_check()
        except Exception as e:  # noqa: BLE001
            print(f"task-sync: health check failed: {e}", file=sys.stderr)
            return 1
        print(f"task-sync: {adapter.destination} health: {'OK' if ok else 'FAIL'}")
        return 0 if ok else 1

    result = run_sync()
    summary = {
        "destination": result.destination,
        "pulled": result.pulled,
        "pushed": result.pushed,
        "read_only": result.read_only,
        "ownership": result.ownership,
        "errors": result.errors,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"task-sync: {result.destination} — pulled={result.pulled} pushed={result.pushed}")
        if result.errors:
            print(f"  errors: {len(result.errors)}")
            for e in result.errors[:5]:
                print(f"    - {e}")
    return 0 if not result.errors else 1


if __name__ == "__main__":
    sys.exit(main())
