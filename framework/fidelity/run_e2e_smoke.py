"""T5 — small REAL reversible end-to-end smoke runner (live OAuth judge, NO sends).

The Captain's directive: test the real flow, reversible only. This drives the SAME
chain as the F1 batch (run_f1.run_batch) on a SMALL n of held-out reply cases
with the LIVE seams — real OAuth `claude -p` judge + real gather + real Voyage
STYLE scoring — then closes the loop the F1 batch does not: it emits a
fidelity-case-scored consequence event (the T3 path, carrying the intent axis)
for every scored case and runs graduation.evaluate over the resulting cells, so
graduation actually READS the events. The point is to prove the FLOW works
live; the scores may be low and that is fine.

REVERSIBILITY (the only-thing-allowed posture, Captain asleep / autonomous):
  * reads + scores + LOCAL JSONL ledger writes ONLY.
  * NO queue_draft, NO email/Teams/Graph/Make/SMTP, NO board write, NO deploy,
    NO Captain-facing outbound — none of those code paths are touched.
  * NO pay-as-you-go spend: every LLM call goes through
    ``framework.fidelity.oauth_llm.oauth_raw_llm``, which strips
    ANTHROPIC_API_KEY (Max OAuth pool only) and runs from an isolated temp cwd.
  * the consequence/org-event ledgers honor the operator-set
    CABINET_EVENT_LOG_DIR; tests isolate it to a tmp dir so even the local
    writes land nowhere durable.

If OAuth / Voyage / the retrodiction lib are unavailable, ``preflight`` fails
LOUD (it NAMES each missing dependency) — the runner does not fake a result.
The ``__main__`` block prints a JSON summary (no score bodies) and, given a
path argument, appends a short run note for the morning review. It NEVER raises
out of __main__ on a live error: the error is captured into the result/note and
reported, so a flaky OAuth call does not block the overnight task (per the T5
directive "do NOT block on it if it errors — capture the error and move on").
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Any

from framework.fidelity import graduation
from framework.fidelity.fidelity_events import emit_case_scored
from framework.fidelity.oauth_llm import oauth_raw_llm
from framework.fidelity.retro import retro_available
from framework.fidelity.run_f1 import run_batch
from framework.fidelity.scorer import CaseScore

# Bounded probe for the OAuth `claude -p` AUTH_OK check. Short — it is only a
# liveness ping, not a real judge call.
_AUTH_PROBE_TIMEOUT_S = 90
_AUTH_PROBE_TOKEN = "AUTH_OK"


# ---------------------------------------------------------------------------
# Preflight — the live-availability gate. Fail-loud, never silently fake.
# ---------------------------------------------------------------------------

def _oauth_ok() -> bool:
    """True iff a bounded headless `claude -p` returns the AUTH_OK token.

    Fixed argv (NO shell=True, no user-interpolated command string). HOME is
    left intact (the macOS keychain / OAuth is HOME-anchored); ANTHROPIC_API_KEY
    is stripped so this probe can never bill the pay-as-you-go path. A missing
    CLI / timeout / non-zero exit reads as 'not available' (False), never an
    exception that aborts the run."""
    argv = [
        "claude", "-p",
        "--model", "claude-sonnet-4-6",
        "--setting-sources", "project,local",
        "--output-format", "text",
        "--append-system-prompt",
        f"Reply with exactly the token {_AUTH_PROBE_TOKEN} and nothing else.",
    ]
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    try:
        r = subprocess.run(
            argv, input="ping", capture_output=True, text=True,
            timeout=_AUTH_PROBE_TIMEOUT_S, env=env,
            cwd=tempfile.gettempdir(),  # isolated cwd — no project CLAUDE.md
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
    if r.returncode != 0:
        return False
    return _AUTH_PROBE_TOKEN in (r.stdout or "")


def _voyage_ok() -> bool:
    """True iff the Voyage key resolves through the embeddings lib (it lazily
    loads _shared/.env). No network call — just key resolution, which is what
    gates the real STYLE embedding."""
    try:
        import importlib.util
        from pathlib import Path
        p = Path.home() / ".screenpipe" / "pipes" / "embeddings" / "lib.py"
        if not p.exists():
            return False
        spec = importlib.util.spec_from_file_location("sp_emb_voyage_probe", str(p))
        if spec is None or spec.loader is None:
            return False
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return bool(m._voyage_key())
    except Exception:
        return False


def _retro_ok() -> bool:
    """True iff the retrodiction lib (the case extractor + scoring engine) is
    importable — the gather + score backbone the smoke reuses."""
    try:
        return bool(retro_available())
    except Exception:
        return False


def preflight() -> tuple[bool, list[str]]:
    """Gate the live run. Returns (ok, missing). ``missing`` NAMES each
    unavailable dependency so a skip is loud, never silent. The three checks
    are independent: a partial failure still fails (you cannot run the real
    flow without all three)."""
    missing: list[str] = []
    if not _oauth_ok():
        missing.append("oauth: `claude -p` did not return AUTH_OK "
                       "(no OAuth session / CLAUDE_CODE_OAUTH_TOKEN)")
    if not _voyage_ok():
        missing.append("voyage: VOYAGE_API_KEY did not resolve via the "
                       "embeddings lib (_shared/.env)")
    if not _retro_ok():
        missing.append("retrodiction: lib not importable at CABINET_RETRO_PIPE_DIR")
    return (not missing, missing)


# ---------------------------------------------------------------------------
# run_smoke — the full chain: batch -> emit scored events -> read graduation.
# ---------------------------------------------------------------------------

def _hydrate_score(d: dict[str, Any]) -> CaseScore:
    """Re-hydrate a CaseScore from a run_batch ``scores`` dict (run_batch
    returns ``[s.__dict__ for s in scores]``). Keeps the smoke decoupled from
    run_batch's internal CaseScore objects."""
    return CaseScore(**d)


def _cell_str(officer_role: str, lane: str, action_type: str) -> str:
    """Stable string key for the per-cell graduation map in the result dict."""
    return f"officer:{officer_role}|{lane}|{action_type}"


def run_smoke(officer_role: str = "cos", n_cases: int = 1,
              lane: str = "send-1to1-reply",
              action_type: str = "internal_message",
              people_dir=None) -> dict[str, Any]:
    """Drive the real F1 batch on a small n, emit a scored consequence event
    per case, then read graduation over the resulting cells.

    Returns ``{n_scored, n_leaked, decision_match_rate, beats_baseline,
    baseline, scores, graduation}``. The ``scores`` are the raw run_batch score
    dicts; ``graduation`` maps a per-cell string key to graduation.evaluate's
    {state, evidence}. No side effects beyond the local consequence/org-event
    ledger writes (reversible).
    """
    result = run_batch(officer_role=officer_role, n_cases=n_cases,
                       people_dir=people_dir, emit_events=True)

    # Emit a scored consequence event per scored case (the T3 path) so
    # graduation can read the intent axis + an intent-mapped review verdict.
    # Leaked cases are NOT in result["scores"] (run_batch already excluded +
    # counted them in n_leaked), so they never produce a scored event.
    for sd in result.get("scores", []):
        cs = _hydrate_score(sd)
        emit_case_scored(cs, officer=officer_role, lane=lane,
                         action_type=action_type)

    # Read graduation back over the distinct cells we just scored. On a small
    # smoke this is one cell, but we evaluate every distinct (actor, lane,
    # action_type) the events landed in, so the map is honest.
    grad: dict[str, Any] = {}
    if result.get("scores"):
        cell = (f"officer:{officer_role}", lane, action_type)
        grad[_cell_str(officer_role, lane, action_type)] = graduation.evaluate(cell)

    return {
        "n_scored": result.get("n_scored", 0),
        "n_leaked": result.get("n_leaked", 0),
        "decision_match_rate": result.get("decision_match_rate", 0.0),
        "beats_baseline": result.get("beats_baseline", False),
        "baseline": result.get("baseline"),
        "scores": result.get("scores", []),
        "graduation": grad,
    }


# ---------------------------------------------------------------------------
# CLI — print a JSON summary; optionally append a run note. Never raises on a
# live error (capture + report, per the T5 directive).
# ---------------------------------------------------------------------------

def _summary(result: dict[str, Any]) -> dict[str, Any]:
    """The score-body-free summary (the scores list is large + private)."""
    grad_states = {k: v.get("state") for k, v in (result.get("graduation") or {}).items()}
    return {
        "n_scored": result.get("n_scored"),
        "n_leaked": result.get("n_leaked"),
        "decision_match_rate": result.get("decision_match_rate"),
        "beats_baseline": result.get("beats_baseline"),
        "baseline": result.get("baseline"),
        "graduation_states": grad_states,
    }


def main(argv: list[str] | None = None) -> dict[str, Any]:
    """Run the smoke, print a JSON summary, optionally append a run note.

    argv: [officer_role] [n_cases] [note_path]. Returns the summary dict (also
    used by the live test as a thin driver). Captures any live error into the
    summary + note rather than raising — the overnight task must not block on a
    flaky OAuth call."""
    import json
    import sys
    from datetime import datetime, timezone

    argv = list(sys.argv[1:] if argv is None else argv)
    role = argv[0] if len(argv) > 0 else "cos"
    n = int(argv[1]) if len(argv) > 1 else 1
    note_path = argv[2] if len(argv) > 2 else None

    ok, missing = preflight()
    if not ok:
        summary = {"skipped": True, "missing": missing,
                   "ts": datetime.now(timezone.utc).isoformat()}
        print(json.dumps(summary, indent=2))
        if note_path:
            _append_note(note_path, summary)
        return summary

    try:
        result = run_smoke(officer_role=role, n_cases=n)
        summary = _summary(result)
        summary["ts"] = datetime.now(timezone.utc).isoformat()
    except Exception as e:  # capture + report; do NOT block the overnight task
        summary = {"error": repr(e)[:500],
                   "ts": datetime.now(timezone.utc).isoformat()}

    print(json.dumps(summary, indent=2))
    if note_path:
        _append_note(note_path, summary)
    return summary


def _append_note(path: str, summary: dict[str, Any]) -> None:
    """Append a short, fenced run note (a local docs write only — reversible)."""
    import json
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n```json\n" + json.dumps(summary, indent=2) + "\n```\n")


if __name__ == "__main__":
    main()
