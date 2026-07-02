"""Component 1 — MCP/plugin self-proposal (prepare + surface, NEVER self-grant).

The Chair, having evaluated + tested a new MCP/plugin, surfaces a ONE-TAP
approval to Nate carrying:

  * the EXACT `cabinet/mcp-scope.yml` diff (the line(s) to add) — computed as a
    STRING for review, NEVER written;
  * any account step (handed to Nate — see Component 2);
  * the test evidence the Chair gathered (the "prove" for a *capability*);
  * a hard-ceiling flag (Captain-required, never auto, if it touches one).

It does this by enqueuing a canonical front-door intake card
(`framework.frontdoor.intake.enqueue`) and emitting a `self_proposal_prepared`
audit event. See docs/prove-to-earn-expansion-2026-06-25.md §2.

HARD LINE (docs §0 + shared/interfaces/captain-patterns.md
autonomy-boundary-accounts-and-self-guards): this module **PREPARES + SURFACES**
only. It has NO write path to `cabinet/mcp-scope.yml` or any germline file, and
NO auto-grant. Nate applies the one scope line himself. The germline guard in
`cabinet/scripts/hooks/pre-tool-use.sh` (exit 2) blocks any self-edit attempt
regardless — this module simply never attempts one (it reads the file to
*compute* the diff text, then stops).

System Python is 3.9.6; stdlib + yaml + in-repo modules only. Fail-closed:
ceiling touches force Captain-required; a missing scope file degrades to a
generic "add <server> to the requesting officer(s)" instruction rather than a
silent pass.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_FRAMEWORK_ROOT = str(Path(__file__).resolve().parents[2])
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from framework.events.emitter import emit  # noqa: E402
from framework.learning.capability_gaps import (  # noqa: E402
    HARD_CEILING_TOUCHES,
    infer_touches,
)

try:
    from yaml import safe_load as _yaml_load
except ImportError:  # pragma: no cover - yaml present in the cabinet runtime
    _yaml_load = None


# The file Nate edits to grant an MCP. We READ it to compute the diff; we NEVER
# write it (hard line). Resolved from CABINET_ROOT so the path is controlled.
_MCP_SCOPE_REL = "cabinet/mcp-scope.yml"


def _cabinet_root(cabinet_root: str | Path | None) -> Path:
    return Path(cabinet_root or os.environ.get("CABINET_ROOT") or _FRAMEWORK_ROOT)


def _mcp_scope_path(cabinet_root: str | Path | None) -> Path:
    return _cabinet_root(cabinet_root) / _MCP_SCOPE_REL


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Scope diff — READ-ONLY over mcp-scope.yml. Returns the line(s) to ADD.
# ---------------------------------------------------------------------------

def _agent_scopes(scope_path: Path) -> dict[str, list[str]]:
    """Return {officer: [mcp, ...]} from mcp-scope.yml `agents:`, or {} on any
    trouble. Read-only; degrades to {} so the caller surfaces a generic grant.
    """
    if _yaml_load is None or not scope_path.exists():
        return {}
    try:
        data = _yaml_load(scope_path.read_text()) or {}
    except Exception:
        return {}
    agents = data.get("agents")
    if not isinstance(agents, dict):
        return {}
    out: dict[str, list[str]] = {}
    for officer, spec in agents.items():
        if isinstance(spec, dict) and isinstance(spec.get("mcps"), list):
            out[str(officer)] = [str(m) for m in spec["mcps"]]
    return out


def compute_scope_diff(
    server: str,
    officers: list[str],
    *,
    cabinet_root: str | Path | None = None,
) -> dict[str, Any]:
    """Compute the EXACT `cabinet/mcp-scope.yml` change to grant `server` to
    `officers` — as text for Nate to apply. NEVER writes the file.

    Returns:
        {
          "needed": bool,                # False if already in scope everywhere
          "server": str,
          "officers_missing": [str],     # officers that don't have it yet
          "diff_text": str,              # the human-readable line(s) to add
          "scope_path": str,             # the file Nate edits
          "scope_readable": bool,        # False if the file couldn't be parsed
        }

    If the scope file is unreadable, `scope_readable=False` and `diff_text`
    degrades to a generic "add `<server>` to each officer's `mcps:`" instruction
    — never a silent "no change needed".
    """
    server = (server or "").strip()
    officers = [str(o).strip() for o in (officers or []) if str(o).strip()]
    scope_path = _mcp_scope_path(cabinet_root)
    scopes = _agent_scopes(scope_path)
    scope_readable = bool(scopes)

    if not scope_readable:
        missing = officers or ["<requesting-officer>"]
        lines = "\n".join(
            f"  {o}:\n    mcps: [..., {server}]   # add '{server}'" for o in missing
        )
        return {
            "needed": True,
            "server": server,
            "officers_missing": missing,
            "diff_text": (
                f"# In {_MCP_SCOPE_REL} under `agents:`, add '{server}' to each "
                f"officer's `mcps:` list:\n{lines}"
            ),
            "scope_path": str(scope_path),
            "scope_readable": False,
        }

    missing = [o for o in officers if server not in scopes.get(o, [])]
    if not missing:
        return {
            "needed": False,
            "server": server,
            "officers_missing": [],
            "diff_text": f"'{server}' is already in scope for {officers} — no edit needed.",
            "scope_path": str(scope_path),
            "scope_readable": True,
        }

    blocks = []
    for o in missing:
        current = scopes.get(o, [])
        proposed = current + [server]
        blocks.append(
            f"  {o}:\n"
            f"    # was:  mcps: [{', '.join(current)}]\n"
            f"    mcps: [{', '.join(proposed)}]"
        )
    diff = (
        f"# In {_MCP_SCOPE_REL}, under `agents:`, add '{server}' "
        f"to: {', '.join(missing)}\n" + "\n".join(blocks)
    )
    return {
        "needed": True,
        "server": server,
        "officers_missing": missing,
        "diff_text": diff,
        "scope_path": str(scope_path),
        "scope_readable": True,
    }


# ---------------------------------------------------------------------------
# Ceiling flag — reuse the code-level backstop.
# ---------------------------------------------------------------------------

def _ceiling_touches(
    server: str,
    why: str,
    evidence: str,
    declared: Optional[list[str]],
) -> list[str]:
    """Which hard-ceiling categories this MCP/plugin touches (sorted).

    Union of declared + keyword-inferred over (server + why + evidence). A hit
    forces Captain-required (defense in depth — matches `can_install`).
    """
    text = f"{server} {why} {evidence}"
    touches = infer_touches(text, "", declared) & HARD_CEILING_TOUCHES
    # honor any explicitly-declared ceiling category even if not a keyword
    for d in declared or []:
        if d in HARD_CEILING_TOUCHES:
            touches.add(d)
    return sorted(touches)


# ---------------------------------------------------------------------------
# Card body — the one-tap proposal text.
# ---------------------------------------------------------------------------

def render_proposal(
    *,
    server: str,
    why: str,
    scope_diff: dict[str, Any],
    test_evidence: str,
    account_step: Optional[str],
    ceiling: list[str],
    kind: str = "mcp",
) -> str:
    """Render the one-tap proposal body (the intake card summary).

    Ordered: What → Scope line → Account step → Test evidence → Ceiling → Apply.
    Pure formatting; contains no secret (it only names fields, never values).
    """
    label = "plugin" if kind == "plugin" else "MCP"
    parts = [f"🔌 New {label} proposal: `{server}` — {why.strip()}"]

    if scope_diff.get("needed"):
        parts.append("Scope line to add (you apply this):\n```\n"
                     + scope_diff["diff_text"].strip() + "\n```")
    else:
        parts.append(scope_diff.get("diff_text", "already in scope."))

    if account_step:
        parts.append(f"Account step (yours): {account_step.strip()}")
    else:
        parts.append("Account step: none.")

    parts.append(f"Test evidence: {test_evidence.strip() or '(none supplied)'}")

    if ceiling:
        parts.append(
            f"⚠ Hard-ceiling: touches {ceiling} — Captain-required, never auto. "
            "Approving grants scope only; any code/credential/spend stays gated."
        )
    else:
        parts.append("Ceiling: none.")

    parts.append(
        "Apply: add the scope line above to `cabinet/mcp-scope.yml` and reload. "
        "The Chair does not self-edit this file."
    )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# prepare_mcp_proposal — compute + surface (the public entry point).
# ---------------------------------------------------------------------------

def prepare_mcp_proposal(
    server: str,
    *,
    officers: list[str],
    why: str,
    test_evidence: str,
    account_step: Optional[str] = None,
    touches: Optional[list[str]] = None,
    kind: str = "mcp",
    gap_id: Optional[str] = None,
    urgency_tier: str = "batch",
    actor: str = "cos",
    cabinet_root: str | Path | None = None,
    enqueue_fn=None,
    emit_fn=None,
) -> dict[str, Any]:
    """Prepare + surface a one-tap MCP/plugin self-proposal. NEVER self-grants.

    Computes the exact mcp-scope.yml diff (read-only), flags ceiling touches,
    builds a canonical intake card, enqueues it (durable Redis-Streams), and
    emits `self_proposal_prepared` for audit. Returns the prepared proposal
    dict (also useful for tests / dry inspection).

    Args:
        server: MCP/plugin token as it appears in mcp-scope.yml (e.g. 'make').
        officers: officer ids to grant (e.g. ['cos']).
        why: one-line rationale.
        test_evidence: what the Chair verified works (the capability proof).
        account_step: credential/account step handed to Nate, or None.
        touches: explicitly-declared hard-ceiling categories, if known.
        kind: 'mcp' | 'plugin'.
        gap_id: link to a capability_gap so can_install still gates a build step.
        urgency_tier: 'batch' (default — rides the next briefing) | 'ping-now'.
        enqueue_fn/emit_fn: test seams (default to intake.enqueue / events.emit).

    Surfacing degrades gracefully: if enqueue fails, the proposal dict + the
    audit event are still returned/emitted (never raises on a transport error).
    """
    server = (server or "").strip()
    if not server:
        raise ValueError("prepare_mcp_proposal: server is required")
    if urgency_tier not in ("ping-now", "batch", "fyi"):
        urgency_tier = "batch"

    scope_diff = compute_scope_diff(server, officers, cabinet_root=cabinet_root)
    ceiling = _ceiling_touches(server, why, test_evidence, touches)
    summary = render_proposal(
        server=server, why=why, scope_diff=scope_diff,
        test_evidence=test_evidence, account_step=account_step,
        ceiling=ceiling, kind=kind,
    )

    proposal = {
        "server": server,
        "kind": kind,
        "officers": officers,
        "why": why,
        "scope_diff": scope_diff,
        "ceiling": ceiling,
        "captain_required": True,  # ALWAYS — a scope grant is always Nate's.
        "account_step": account_step,
        "test_evidence": test_evidence,
        "gap_id": gap_id,
        "urgency_tier": urgency_tier,
        "summary": summary,
    }

    item = {
        "source": "self-proposal",
        "kind": f"{kind}-proposal",
        "ts": _now_iso(),
        "urgency_tier": urgency_tier,
        "payload": {
            "summary": summary,
            "why": why,
            "server": server,
            "ceiling": ceiling,
            "gap_id": gap_id,
        },
    }

    # Surface (durable intake) — best-effort; never raise on transport error.
    enqueue = enqueue_fn
    if enqueue is None:
        try:
            from framework.frontdoor import intake
            enqueue = intake.enqueue
        except Exception:
            enqueue = None
    enqueued_id = None
    if enqueue is not None:
        try:
            enqueued_id = enqueue(item)
        except Exception:
            enqueued_id = None
    proposal["enqueued_id"] = enqueued_id

    # Audit — always emit (the proposal is a fact even if the DM transport hiccups).
    _emit = emit_fn or emit
    try:
        _emit("self_proposal_prepared", actor=actor, payload={
            "server": server, "kind": kind, "officers": officers,
            "ceiling": ceiling, "gap_id": gap_id,
            "scope_needed": scope_diff.get("needed"),
            "urgency_tier": urgency_tier,
        })
    except Exception:
        pass

    return proposal


if __name__ == "__main__":  # tiny manual smoke
    import json
    demo = prepare_mcp_proposal(
        "make",
        officers=["cos"],
        why="Chair needs Make scenario access for the Teams→Outlook flow",
        test_evidence="Listed scenarios via mcp__make; the read modules return rows.",
        account_step=None,
        urgency_tier="batch",
        enqueue_fn=lambda item: "(dry) not-enqueued",
        emit_fn=lambda *a, **k: None,
    )
    print(json.dumps({k: v for k, v in demo.items() if k != "summary"}, indent=2, default=str))
    print("\n--- card ---\n" + demo["summary"])
