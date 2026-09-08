"""The claim env cannot reach into the claim suites from the host (A2.9).

WHY THIS EXISTS.  The acceptance drill exports `CABINET_WORKER_ID`,
`CABINET_CLAIM_ID`, `CABINET_CLAIM_LEASE_SECONDS` and (since A2.9)
`CABINET_CLAIM_LEASE_FLOOR_SECONDS`, and an officer session exports the first
of those permanently.  Both claim suites build a subprocess environment by
COPYING os.environ, so a host that carries any of them hands the copy to a
`bash work-graph-complete.sh` child that then asserts a holder nobody claimed
under, or a token nobody minted, or a lease that expired between the claim and
the completion.  Measured on this host before the fixtures were scrubbed: with
CABINET_WORKER_ID exported three arms go red, with CABINET_CLAIM_ID a
DIFFERENT three go red, and the pair together reds six of fifteen.

The suite would fail on the Captain's own box and pass in CI, which is the
worst shape a test can have: an environment-shaped red that looks like a code
regression to whoever runs it next.

Each arm runs the target suite as its OWN pytest process with the whole claim
env exported hostile.  A green rc is the only evidence that counts here — an
in-process assertion about a fixture dict would be a claim about what the code
looks like, not about what the environment does to it.

`CABINET_EVENT_LOG_DIR` is pinned into the child explicitly (A0.4).  The root
conftest overrides it again inside the child, unconditionally and by design;
the pin is here so nothing about this file depends on that.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]

#: Every claim-shaping variable, at the most hostile value each one has.  The
#: two lease vars are the pair that bites: a 1 s floor is what makes a 1 s
#: lease survive resolve_lease instead of being clamped to a minute.
HOSTILE_CLAIM_ENV = {
    "CABINET_WORKER_ID": "hostile-holder",
    "CABINET_CLAIM_ID": "hostile-token",
    "CABINET_CLAIM_LEASE_SECONDS": "1",
    "CABINET_CLAIM_LEASE_FLOOR_SECONDS": "1",
}


@pytest.mark.parametrize("suite", ["test_work_graph_complete.py", "test_claims.py"])
def test_the_suite_is_green_with_the_claim_env_exported_hostile(suite, tmp_path):
    env = dict(os.environ)
    env.update(HOSTILE_CLAIM_ENV)
    env["CABINET_EVENT_LOG_DIR"] = str(tmp_path / "events")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    target = Path("framework") / "missions" / "tests" / suite
    run = subprocess.run(
        [sys.executable, "-m", "pytest", str(target), "-q", "-p", "no:cacheprovider"],
        cwd=str(_ROOT), env=env, capture_output=True, text=True, timeout=600,
    )
    assert run.returncode == 0, "%s reds under the claim env:\n%s\n%s" % (
        suite, run.stdout[-4000:], run.stderr[-2000:],
    )
