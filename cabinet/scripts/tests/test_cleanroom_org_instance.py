"""Clean-room day-1 org recall locks — the generate-instance.py memory chain.

Wave-1 (2026-07-07) made a FRESH org-flavor instance recall-capable on day 1:
`cabinet/scripts/generate-instance.py` emits `instance/config/sources.yml`
binding `framework.sources.org:OrgSource` (the cabinet_memory-backed
PersonalSource) and stamps platform.yml with the `org_vault_dir` corpus
key (vault wave 2026-07-17; formerly `product_brain_dir`). These tests lock
that emission chain through the REAL CLI (subprocess,
argv list — never a shell string) so any future change that breaks day-1 org
recall fails HERE, loudly:

  * sources.yml exists, binds ``ORG_SOURCE_ADAPTER``, carries the
    "generated-by: cabinet-init" marker (regenerability), and deliberately
    has NO ``dispatch:`` binding (an org box has no personal actuator estate
    — get_dispatch() must fail-close to NullPersonalDispatch);
  * platform.yml carries the ``org_vault_dir`` key (the org corpus dir
    surfaced by ``framework.env.org_vault_dir()``);
  * NO secret-shaped string appears anywhere under the generated root —
    scanned with the generator's OWN ``SECRET_PATTERNS`` so this lock can
    never drift from the refusal list;
  * a path-escape slug makes the CLI exit non-zero and nothing escapes
    ``--root``;
  * ``autonomy.flavor: personal`` emits NOTHING — a Flavor-A captain's box
    must never be silently rebound to OrgSource.

Fictional "Ada"/Acme fixtures throughout (universality: no deployment data).
Run: python3 -m pytest cabinet/scripts/tests/test_cleanroom_org_instance.py -q
"""

from __future__ import annotations

import importlib.util as _ilu
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# Captured at import (collection) time, BEFORE any test runs:
# test_library_mcp_client patches the global subprocess.Popen and the patch
# can leak across modules in a whole-repo run — restore the real one around
# our spawns so a leaked FakePopen can't fail these tests.
_REAL_POPEN = subprocess.Popen

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_GENERATOR = _SCRIPTS_DIR / "generate-instance.py"

# generate-instance.py is hyphenated — load it via importlib (same pattern as
# test_generate_instance.py; distinct module name, no sys.modules collision).
spec = _ilu.spec_from_file_location("generate_instance_cleanroom_lock", _GENERATOR)
gi = _ilu.module_from_spec(spec)
spec.loader.exec_module(gi)


# ---------------------------------------------------------------------------
# Fixtures — fictional Ada/Acme captain, ONE lane, ORG flavor
# ---------------------------------------------------------------------------

PLATFORM_FIXTURE = """\
# =============================================================
# Test platform configuration (fictional captain)
# =============================================================
captain_name: Placeholder            # Default: "Captain" if not set
captain_timezone: UTC                # IANA identifier
captain_telegram_chat_id: "0000"

communication:
  briefing_frequency: daily
"""


def org_answers() -> dict:
    """Minimal org-flavor answers: one fictional lane, no secrets anywhere."""
    return {
        "version": 1,
        "captain": {
            "name": "Ada",
            "timezone": "Europe/Madrid",
            "telegram_chat_id": "12345678",
        },
        "cabinet": {
            "id": "acme-hq",
            "mode": "single",
            "org_shape": "portfolio",
            "officer_model": "claude-fable-5",
        },
        "lanes": [
            {
                "name": "Acme Storefront",
                "slug": "acme-store",
                "repos": ["acme/storefront"],
                "task_system": "plugin:dev-tasks",
                "boards": ["42424242"],
            },
        ],
        # flavor "org" is also the DEFAULT — declared explicitly here because
        # this suite locks the org-flavor emission contract by name.
        "autonomy": {"posture": "propose_first", "flavor": "org"},
        "integrations": {
            "telegram": {"ceo_bot": "", "bot_token_env": "TELEGRAM_BOT_TOKEN_COS"},
            "mcp_env_names": ["NEON_API_KEY"],
        },
    }


@pytest.fixture()
def cab_root(tmp_path: Path) -> Path:
    """A minimal fake CABINET_ROOT with the REAL lane-CEO template."""
    root = tmp_path / "cab"
    (root / "instance/config/contexts").mkdir(parents=True)
    (root / "instance/config/projects").mkdir(parents=True)
    (root / "instance/agents").mkdir(parents=True)
    (root / "presets/portfolio/agents").mkdir(parents=True)
    shutil.copy(
        _REPO_ROOT / "presets/portfolio/agents/_lane-ceo.md.template",
        root / "presets/portfolio/agents/_lane-ceo.md.template",
    )
    (root / "instance/config/platform.yml").write_text(PLATFORM_FIXTURE)
    return root


def write_answers(root: Path, answers: dict) -> Path:
    path = root / "instance/config/cabinet-init.answers.yml"
    path.write_text(yaml.safe_dump(answers, sort_keys=False))
    return path


def run_cli(root: Path, answers_path: Path) -> "subprocess.CompletedProcess":
    """Run the REAL generator CLI — argv list, shell=False, Popen restored."""
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        return subprocess.run(
            [sys.executable, str(_GENERATOR),
             "--root", str(root), "--answers", str(answers_path)],
            capture_output=True, text=True, timeout=120,
        )
    finally:
        subprocess.Popen = patched


def run_cli_ok(root: Path, answers: dict) -> "subprocess.CompletedProcess":
    result = run_cli(root, write_answers(root, answers))
    assert result.returncode == 0, (
        f"generate-instance CLI failed rc={result.returncode}:\n"
        f"{result.stdout}\n{result.stderr}"
    )
    return result


# ---------------------------------------------------------------------------
# The org emission contract — sources.yml + org_vault_dir
# ---------------------------------------------------------------------------

class TestOrgSourcesEmission:
    def test_adapter_constant_is_the_framework_org_source(self):
        """Pin the binding target itself: a renamed module/class must fail
        here (and be migrated deliberately), not drift silently."""
        assert gi.ORG_SOURCE_ADAPTER == "framework.sources.org:OrgSource"

    def test_cli_emits_sources_yml_binding_orgsource(self, cab_root):
        run_cli_ok(cab_root, org_answers())
        sources = cab_root / "instance/config/sources.yml"
        assert sources.is_file(), "org-flavor run must emit instance/config/sources.yml"
        text = sources.read_text()
        # generated-by marker → the file is regenerable, never hand-authored
        assert gi.MARKER in text
        parsed = yaml.safe_load(text)
        assert parsed["adapter"] == "framework.sources.org:OrgSource"
        # deliberately NO write/actuator binding — get_dispatch() must
        # fail-close to NullPersonalDispatch on an org box
        assert parsed.get("dispatch") is None
        assert not re.search(r"^dispatch:", text, re.M)

    def test_platform_carries_org_vault_dir(self, cab_root):
        run_cli_ok(cab_root, org_answers())
        text = (cab_root / "instance/config/platform.yml").read_text()
        assert re.search(r"^org_vault_dir:", text, re.M), (
            "platform.yml must carry a top-level org_vault_dir key"
        )
        platform = yaml.safe_load(text)
        # RELATIVE to the deployment root (⇒ <root>/vault), never an
        # absolute machine path: generated config must stay relocatable and
        # launcher-free (an absolute tmp/live path would carry the machine's
        # username and trip the universality ratchet).
        assert platform["org_vault_dir"] == "vault"

    def test_rerun_is_idempotent_on_the_emitted_binding(self, cab_root):
        """The marker convention must keep the emitted files regenerable:
        a second identical run succeeds and rewrites byte-identically."""
        run_cli_ok(cab_root, org_answers())
        sources_before = (cab_root / "instance/config/sources.yml").read_bytes()
        platform_before = (cab_root / "instance/config/platform.yml").read_bytes()
        run_cli_ok(cab_root, org_answers())
        assert (cab_root / "instance/config/sources.yml").read_bytes() == sources_before
        assert (cab_root / "instance/config/platform.yml").read_bytes() == platform_before

    def test_personal_flavor_emits_a_live_local_binding(self, cab_root):
        """INVERTED 2026-07-27. This arm used to assert the generator emits NO
        sources.yml for flavor: personal. That assertion was literally correct
        and was the reason the personal preset shipped inert: with no binding
        the deployment fail-closes to NullPersonalSource (available() False,
        search() -> no hits), so the ONE flavor shaped for an operator who does
        not run a company had zero recall out of the box. It now binds the
        read-only local-folder adapter, and still emits no dispatch.

        INVERTED AGAIN 2026-07-28 on the local_root arm, which asserted
        ``"vault"``. That value was hardcoded with no answers-file override,
        and ``<root>/vault`` is the cabinet's OWN shipped documentation — so a
        clean-room personal hatch resolved live recall over the framework's
        docs and reported ``available() True``. Undeclared is now UNSET."""
        answers = org_answers()
        answers["autonomy"]["flavor"] = "personal"
        run_cli_ok(cab_root, answers)
        src_path = cab_root / "instance/config/sources.yml"
        assert src_path.is_file()
        src = yaml.safe_load(src_path.read_text(encoding="utf-8"))
        assert src["adapter"] == "framework.sources.local:LocalNotesSource"
        assert src.get("local_root") is None
        assert "dispatch" not in src

    def test_personal_flavor_binds_a_declared_notes_root(self, cab_root):
        """A clean-room personal hatch that DOES declare a folder binds it."""
        answers = org_answers()
        answers["autonomy"]["flavor"] = "personal"
        answers["sources"] = {"notes_root": "~/notes"}
        run_cli_ok(cab_root, answers)
        src = yaml.safe_load(
            (cab_root / "instance/config/sources.yml").read_text(encoding="utf-8"))
        assert src["local_root"] == "~/notes"


# ---------------------------------------------------------------------------
# Secret hygiene — nothing secret-shaped anywhere in the generated tree
# ---------------------------------------------------------------------------

class TestSecretHygiene:
    def test_no_secret_shaped_strings_in_generated_output(self, cab_root):
        """Scan EVERY file under the generated root with the generator's own
        SECRET_PATTERNS — config carries env-var NAMES only, and this lock
        cannot drift from the generator's refusal list because it IS it."""
        run_cli_ok(cab_root, org_answers())
        assert gi.SECRET_PATTERNS, "generator lost its SECRET_PATTERNS list"
        for path in sorted(cab_root.rglob("*")):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for pat in gi.SECRET_PATTERNS:
                assert not pat.search(text), (
                    f"secret-shaped string in generated output: {path} "
                    f"matches {pat.pattern!r}"
                )


# ---------------------------------------------------------------------------
# Containment — path-escape slugs are refused by the CLI (rc != 0)
# ---------------------------------------------------------------------------

class TestPathEscapeRefused:
    def test_path_escape_slug_cli_refuses_and_nothing_escapes(self, cab_root):
        answers = org_answers()
        answers["lanes"][0]["slug"] = "../evil"
        result = run_cli(cab_root, write_answers(cab_root, answers))
        assert result.returncode != 0, (
            f"path-escape slug must fail the CLI, got rc=0:\n{result.stdout}"
        )
        assert "ERROR" in result.stderr
        # nothing escaped --root, and the aborted run emitted no binding
        assert not (cab_root.parent / "evil").exists()
        assert not (cab_root / "instance/config/sources.yml").exists()
        assert not list((cab_root / "instance/config/contexts").glob("*.yml"))
