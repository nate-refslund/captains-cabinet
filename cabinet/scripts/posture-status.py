#!/usr/bin/env python3
"""posture-status.py — READ-ONLY posture/axes status as one JSON object [AX-7].

Emits {"level", "flavor", "target", "attested", "narrow_cap"} on stdout via
the posture kernel's own resolution internals (framework/authority/posture.py)
— the ONE resolver chain, never a reimplementation:

  level      resolve_posture()            (env + ruling + narrow caps applied)
  flavor     the ruling's flavor           (null when no schema-valid ruling)
  target     deployment_target()           (ruling value, else inferred)
  attested   the ruling passed the full attestation chain (present + real
             path + schema-valid + deployment-matched + locked)
  narrow_cap the instance/config/posture-narrow cap word (null when absent)

STRICTLY read-only: every read passes file_needs=False so a status probe
never files a need, and nothing is ever written — the dashboard tile renders
this JSON verbatim and offers NO state-changing control (Corridor: authority
changes only via Captain-authenticated surfaces). Never exits non-zero on a
resolvable tree: any unexpected failure emits the guardian fail-closed shape
plus an "error" field, because guardian IS the resolver's answer to every
ambiguity. Runs under the system python3 (3.9-compatible; PyYAML only needed
once a ruling file exists, same as the resolver itself).

Usage: python3 cabinet/scripts/posture-status.py   (root from CABINET_ROOT env)
"""
from __future__ import annotations

import json
import os
import sys

_REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", ".."))


def status() -> dict:
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    from framework.authority import posture

    # file_needs=False everywhere: a status read is side-effect-free.
    ruling, attested = posture._read_ruling(None, file_needs=False)
    return {
        "level": posture.resolve_posture(file_needs=False),
        "flavor": ruling["flavor"] if ruling is not None else None,
        "target": posture.deployment_target(),
        "attested": bool(attested),
        "narrow_cap": posture.narrow_cap(),
    }


def main() -> int:
    try:
        out = status()
    except Exception as exc:  # fail-closed shape, never a crash (render surface)
        out = {"level": "guardian", "flavor": None, "target": None,
               "attested": False, "narrow_cap": None,
               "error": str(exc)[:200]}
    sys.stdout.write(json.dumps(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
