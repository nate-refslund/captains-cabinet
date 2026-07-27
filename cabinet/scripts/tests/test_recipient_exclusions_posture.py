"""The ruled posture of instance/config/recipient-exclusions.yml.

WHY THIS EXISTS. The file is a Captain-owned safety INPUT that the classifier
reads, and it is agent-writable: it is not in the germline (schg) set and not
in pre-tool-use.sh's protected path lists. Neither is instance/config/
platform.yml, which holds `org_domains` — the ALLOWLIST this file carves back.
So the exposure is plane-wide and pre-existing, not introduced here, and an
agent editing platform.yml can loosen FURTHER than one editing this file (add
a domain and outsiders become internal; the worst available here is restoring
the pre-2026-07-27 subdomain rule). Closing it properly means adding both
paths to the hook, and the hook's germline arms are pinned against
framework/policies/immutable-core.yml by a lockstep meta-test — i.e. a change
to the germline SET, which is a Captain ceremony, not a self-ratification.
Recorded as a handback; see the unit's review artifact.

What IS enforceable here, today, with no ceremony: make the LOOSENING visible.
These arms pin only the knob that can weaken the classifier and deliberately
leave the tightening surface free — the denylist may grow without touching
this file, because adding an exclusion is always safe. A Captain who really
wants `inherit` is making a loosening ruling and should have to edit a test
that says so out loud.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
LIVE = ROOT / "instance/config/recipient-exclusions.yml"
TWIN = ROOT / "instance/config/recipient-exclusions.yml.example"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_the_shipped_twin_is_strict():
    """The twin always ships (the live file is scrubbed from the egg), so a
    stranger's first cabinet inherits bounded subdomain matching. This arm is
    the one that survives into a fresh hatch."""
    assert TWIN.is_file()
    assert _load(TWIN).get("subdomain_matching") == "strict"


def test_the_shipped_twin_denylist_is_empty():
    """Exclusions are Captain rulings, never framework defaults — nobody
    inherits a stranger's list."""
    assert _load(TWIN).get("denylist") == []


@pytest.mark.skipif(not LIVE.is_file(),
                    reason="no live ruled file on this checkout (egg/hatch)")
def test_live_subdomain_matching_is_still_strict():
    """The loosening tripwire. `inherit` restores the unbounded rule in which
    a listed domain claims its entire subdomain namespace — including
    subdomains nobody has checked and subdomains that do not exist yet. It is
    reachable BY DESIGN, but not silently: flipping it turns this red."""
    assert _load(LIVE).get("subdomain_matching") == "strict", (
        "subdomain_matching left `strict` — if this is a deliberate Captain "
        "ruling, change it here in the same commit and say why; if it is not, "
        "someone widened the internal-recipient set without a ruling.")


@pytest.mark.skipif(not LIVE.is_file(),
                    reason="no live ruled file on this checkout (egg/hatch)")
def test_every_live_denylist_row_carries_a_why():
    """The documented obligation, enforced where enforcing it is SAFE. The
    parser deliberately does not gate on `why:` — a forgotten one at runtime
    would turn an urgent Captain exclusion into a deny-all outage. In the
    repo, a missing `why` is just a review defect, so it gates here."""
    rows = _load(LIVE).get("denylist") or []
    missing = [r for r in rows
               if not str((r or {}).get("why", "")).strip()]
    assert not missing, f"denylist rows with no why: {missing}"
