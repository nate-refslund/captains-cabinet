"""Apply-watch [D15, sovereign spec §4 SOV-8] — 72h auto-rollback ledger for
the DARK germline apply lane.

When (and only when) the Captain has armed the DARK apply lane
(`cabinet/scripts/gate-apply.sh` via an explicit `sudo launchctl load` of
`com.cabinet.gate-apply` — never a setup script), every applied evidence pack
is recorded HERE and watched for 72h. This module is pure DECISION logic:
`evaluate()` returns `rollback | close | watch` rows; the ROOT DAEMON is the
only executor (it applies the recorded revert plan) — nothing in this module
mutates the tree, so it is safe to import and run unprivileged anywhere.

Red signals within the window (any one ⇒ rollback):
  * a kind FROZEN after the apply (the brakes fired — action_undo freeze
    mirror rows newer than applied_at),
  * a RED canary receipt after the apply,
  * any injected checker saying red (the daemon wires its own probes).

Ledger IO mirrors framework/authority/needs.py: O_APPEND JSONL at
shared/interfaces/gate-apply-watch.jsonl, ONE os.write per event,
last-write-wins per pack_id — concurrent appenders interleave without
corruption. DATA is runtime state (SKIP-class); this MODULE is Ring-0.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

WATCH_WINDOW_H = 72

_STATUSES = frozenset({"watching", "rollback", "closed"})


def _root(root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(os.environ.get("CABINET_ROOT") or str(_FRAMEWORK_ROOT))


def watch_path(root: str | Path | None = None) -> Path:
    return _root(root) / "shared" / "interfaces" / "gate-apply-watch.jsonl"


def _now(now: str | None = None) -> str:
    if now:
        return now
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(ts: Any) -> datetime | None:
    try:
        return datetime.strptime(str(ts or ""), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _append(path: Path, row: dict[str, Any]) -> None:
    """ONE os.write on an O_APPEND fd — same concurrency posture as needs.py."""
    line = (json.dumps(row, default=str) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


def _merged(path: Path) -> dict[str, dict[str, Any]]:
    """Compacted view: last written row wins per pack_id. Torn lines skipped."""
    state: dict[str, dict[str, Any]] = {}
    try:
        if not path.exists():
            return {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("pack_id"):
                state[str(row["pack_id"])] = row
    except OSError:
        return {}
    return state


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def record_apply(
    pack_id: str,
    *,
    applied_at: str | None = None,
    revert_plan: str,
    sha256: str | None = None,
    applied_by: str = "gate-apply",
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Open a 72h watch on an applied pack. `revert_plan` is the EXACT revert
    the daemon would execute (recorded at apply time from the LOCKED live
    tree, e.g. `git -c core.hooksPath=/dev/null apply -R <variant.patch>`)."""
    row = {
        "pack_id": str(pack_id),
        "status": "watching",
        "applied_at": _now(applied_at),
        "watch_until": (
            (_parse_ts(_now(applied_at)) or datetime.now(timezone.utc))
            + timedelta(hours=WATCH_WINDOW_H)
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "revert_plan": str(revert_plan),
        "sha256": sha256,
        "applied_by": applied_by,
    }
    _append(watch_path(root), row)
    return row


def mark(
    pack_id: str,
    status: str,
    *,
    reason: str | None = None,
    root: str | Path | None = None,
    now: str | None = None,
) -> dict[str, Any] | None:
    """Transition a watch row (the daemon stamps `rollback`/`closed` after it
    acts). Unknown pack_id / bad status ⇒ None, never raises."""
    try:
        if status not in _STATUSES:
            return None
        prev = _merged(watch_path(root)).get(str(pack_id))
        if prev is None:
            return None
        row = dict(prev, status=status, marked_at=_now(now))
        if reason is not None:
            row["reason"] = reason
        _append(watch_path(root), row)
        return row
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Red-signal probes (defaults read the SOV-5 brakes; all injectable)
# ---------------------------------------------------------------------------

def _default_red_signals(applied_at: str, now: str) -> list[str]:
    """Red signals since `applied_at`: new freeze mirror rows or red canary
    receipts. Fail-SAFE toward rollback is wrong here — a broken probe must
    not roll back a healthy apply — so probe errors read as no-signal; the
    daemon layers its own hard probes on top."""
    reds: list[str] = []
    try:
        from framework.frontdoor import action_undo
        for kind, _ in _frozen_since(action_undo, applied_at, now):
            reds.append(f"kind frozen after apply: {kind}")
        for r in action_undo.canary_receipts():
            ts = str(r.get("ts") or "")
            if not r.get("green") and applied_at <= ts <= now:
                reds.append(f"red canary receipt {r.get('kind')}@{ts}")
    except Exception:
        pass
    return reds


def _frozen_since(action_undo: Any, applied_at: str, now: str):
    """(kind, ts) for freeze mirror rows in (applied_at, now] — last-op-wins
    per kind (an unfrozen kind is not a red signal)."""
    try:
        path = action_undo._frozen_mirror()  # noqa: SLF001 — read-only mirror peek
        if not path.exists():
            return
        last: dict[str, dict[str, Any]] = {}
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("kind"):
                last[str(row["kind"])] = row
        for kind, row in last.items():
            ts = str(row.get("ts") or "")
            if row.get("op") != "unfreeze" and applied_at <= ts <= now:
                yield kind, ts
    except Exception:
        return


# ---------------------------------------------------------------------------
# evaluate — decisions only; the (dark) root daemon executes
# ---------------------------------------------------------------------------

def evaluate(
    *,
    now: str | None = None,
    root: str | Path | None = None,
    red_signals_fn: Optional[Callable[[str, str], list[str]]] = None,
) -> list[dict[str, Any]]:
    """One watch pass over every `watching` row. Returns decision rows:

      {pack_id, decision: rollback|close|watch, reason, revert_plan}

    * red signal inside the 72h window ⇒ `rollback` (+ the recorded plan);
    * window elapsed with no red ⇒ `close` (apply survived);
    * otherwise ⇒ `watch` (still inside the window, clean so far).

    Marks `rollback`/`closed` transitions in the ledger so re-runs are
    idempotent, but EXECUTES NOTHING — the dark daemon owns execution.
    Never raises.
    """
    ts = _now(now)
    reds_of = red_signals_fn or _default_red_signals
    decisions: list[dict[str, Any]] = []
    try:
        for pack_id, row in sorted(_merged(watch_path(root)).items()):
            if row.get("status") != "watching":
                continue
            applied_at = str(row.get("applied_at") or "")
            watch_until = str(row.get("watch_until") or "")
            try:
                reds = list(reds_of(applied_at, ts))
            except Exception:
                reds = []
            if reds:
                reason = "; ".join(reds)[:500]
                mark(pack_id, "rollback", reason=reason, root=root, now=ts)
                decisions.append({"pack_id": pack_id, "decision": "rollback",
                                  "reason": reason,
                                  "revert_plan": row.get("revert_plan")})
            elif watch_until and ts >= watch_until:
                mark(pack_id, "closed",
                     reason=f"{WATCH_WINDOW_H}h clean", root=root, now=ts)
                decisions.append({"pack_id": pack_id, "decision": "close",
                                  "reason": f"{WATCH_WINDOW_H}h clean",
                                  "revert_plan": None})
            else:
                decisions.append({"pack_id": pack_id, "decision": "watch",
                                  "reason": "inside window, no red signal",
                                  "revert_plan": None})
    except Exception:
        return decisions
    return decisions


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI
    import argparse
    parser = argparse.ArgumentParser(
        description="Gate apply-watch — 72h rollback DECISIONS (executes nothing).")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    decisions = evaluate()
    if args.json:
        print(json.dumps(decisions, indent=2, default=str))
    else:
        for d in decisions:
            print(f"{d['pack_id']}: {d['decision']} — {d['reason']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
