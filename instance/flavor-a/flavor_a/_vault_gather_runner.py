"""Vault-gather runner — executed UNDER THE BRAIN INTERPRETER (python3.12) via
subprocess from ``flavor_a.screenpipe_source._subprocess_vault_gather`` (the
Flavor-A source adapter's vault-search sidecar; re-homed here with the adapter in
the SRC-3 source-adapter split — it IS the adapter's py3.9/3.12 search boundary).

WHY this exists: the fidelity harness runs in-process under system Python 3.9.6,
whose sqlite3 was built without loadable-extension support
(`enable_load_extension` absent). The embeddings vector extension cannot load
there, so context_lib._fetch_vault silently returns 0 hits. The brain runs
embeddings under python3.12 (extension support present). This tiny script runs
the SAME context_lib.gather(handle, sources=["vault"], topic=...) under 3.12 and
prints the result as JSON to stdout — reusing all of context_lib's logic
(person-anchoring, topic fusion, recency, rerank, per-chunk content_ts).

LEAK-SAFETY: this returns LIVE (current) vault hits. The harness parent applies
the content_ts fence (officer_runner._content_ts + leakguard.filter_mcp_result)
to these hits and drops anything at/after the case cutoff. This script bypasses
NO fence — it only makes the search succeed so the fence has real hits to
filter. It is scoped to sources=["vault"] EXACTLY (Tier-1 only; never the live
Tier-2 "now" fetchers).

CONTRACT: argv = [handle, topic]; stdout = a single JSON object
{"hits": [...], "topic_terms": [...]} on success, or {"hits": [], "error": str}
on any failure (always exit 0 so the parent degrades gracefully, never crashes).
Base dir is resolved from CABINET_RETRO_PIPE_DIR (the brain pipes location) —
the same env the retro shim uses — never from the untrusted handle.
"""

import datetime as _dt
import json
import os
import sys
from pathlib import Path


def _json_default(o):
    if isinstance(o, (_dt.datetime, _dt.date)):
        return o.isoformat()
    return str(o)


def _safe_handle(handle: str) -> str:
    """Reject a handle that could be used to escape the vault (defense in depth
    — context_lib resolves the handle to a person folder). Forward/back slashes,
    parent-traversal, and null bytes are refused."""
    h = (handle or "").strip()
    if not h or "\x00" in h or "/" in h or "\\" in h or ".." in h:
        raise ValueError(f"unsafe handle: {handle!r}")
    return h


def main(argv: list) -> int:
    try:
        handle = _safe_handle(argv[1] if len(argv) > 1 else "")
        topic = (argv[2] if len(argv) > 2 else "") or None

        # Base dir = the brain pipes root, from the controlled env var (same
        # source the retro shim uses), NEVER from the handle.
        pipe_dir = Path(
            os.environ.get(
                "CABINET_RETRO_PIPE_DIR",
                str(Path.home() / ".screenpipe" / "pipes" / "retrodiction"),
            )
        ).expanduser()
        pipes_root = pipe_dir.parent
        for p in (str(pipes_root / "_shared"), str(pipes_root / "embeddings")):
            if p not in sys.path and Path(p).exists():
                sys.path.insert(0, p)

        import context_lib
        res = context_lib.gather(handle, sources=["vault"], topic=topic) or {}
        out = {"hits": res.get("hits", []) or [],
               "topic_terms": res.get("topic_terms")}
        sys.stdout.write(json.dumps(out, default=_json_default))
        return 0
    except Exception as e:  # never crash the parent — emit empty + the reason
        sys.stdout.write(json.dumps({"hits": [], "error": str(e)}))
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
