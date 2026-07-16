"""Tests for cabinet/scripts/generate-instance.py (cabinet-init generator).

Uses a FICTIONAL "Acme" captain with two fake lanes throughout — the
fixture doubles as the universality proof: the generator must work for any
captain, and neither the generator nor the cabinet-init skill may carry
this repo's own deployment specifics (see test_universality).

Run: cd cabinet/scripts && python3 -m pytest tests/ -v
(or from the repo root: python3 -m pytest cabinet/scripts/tests/ -v)
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

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent

# generate-instance.py is hyphenated — load it via importlib (same pattern
# as cabinet/scripts/lib/tests/test_run_etl.py).
spec = _ilu.spec_from_file_location("generate_instance_under_test",
                                    _SCRIPTS_DIR / "generate-instance.py")
gi = _ilu.module_from_spec(spec)
spec.loader.exec_module(gi)


# ---------------------------------------------------------------------------
# Fixtures — fictional Acme captain, two fake lanes
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

# officers:
#   cos: { type: fulltime }
"""


def acme_answers() -> dict:
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
                "neon_project": "acme-store-db",
                "vercel_project": "storefront",
            },
            {
                "name": "Acme Labs",
                "slug": "acme-labs",
                "repos": ["acme/labs", "acme/labs-site"],
                "task_system": "linear",
                "linear_team_key": "labs",
                "linear_workspace_url": "https://linear.app/acme-labs",
                "boards": ["labs"],
            },
        ],
        "autonomy": {"posture": "propose_first"},
        "integrations": {
            "telegram": {"ceo_bot": "", "bot_token_env": "TELEGRAM_BOT_TOKEN_COS"},
            "mcp_env_names": ["NEON_API_KEY", "VERCEL_API_KEY"],
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


def run_gen(root: Path, answers: dict, **kwargs) -> list:
    return gi.generate(root, write_answers(root, answers), **kwargs)


def run_cli(cab_root: Path, *extra: str) -> subprocess.CompletedProcess:
    """Run the generator CLI with stdin CLOSED — any prompt would hit EOF
    and fail loud, so exit 0 doubles as the zero-prompts proof."""
    return subprocess.run(
        [sys.executable, str(_SCRIPTS_DIR / "generate-instance.py"),
         "--root", str(cab_root), *extra],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120,
    )


# ---------------------------------------------------------------------------
# Happy path — portfolio shape
# ---------------------------------------------------------------------------

class TestPortfolioGeneration:
    def test_generates_expected_files(self, cab_root):
        run_gen(cab_root, acme_answers())
        for rel in [
            "instance/config/contexts/acme-store.yml",
            "instance/config/contexts/acme-labs.yml",
            "instance/config/projects/acme-store.yml",
            "instance/config/projects/acme-labs.yml",
            "instance/agents/acme-store-ceo.md",
            "instance/agents/acme-labs-ceo.md",
            "instance/config/roster.yml",
            "instance/config/platform.yml",
        ]:
            assert (cab_root / rel).is_file(), f"missing {rel}"

    def test_context_matches_existing_schema(self, cab_root):
        run_gen(cab_root, acme_answers())
        ctx = yaml.safe_load((cab_root / "instance/config/contexts/acme-store.yml").read_text())
        # exact key set of the existing context files
        assert set(ctx.keys()) == {"slug", "name", "capacity", "description", "active"}
        assert ctx["slug"] == "acme-store"
        assert ctx["name"] == "Acme Storefront"
        assert ctx["capacity"] == "work"
        assert ctx["active"] is False
        assert "Acme Storefront" in ctx["description"]

    def test_project_matches_template_shape(self, cab_root):
        run_gen(cab_root, acme_answers())
        text = (cab_root / "instance/config/projects/acme-store.yml").read_text()
        proj = yaml.safe_load(text)
        assert set(proj.keys()) == {"product", "activation", "notion", "linear", "neon", "telegram"}
        assert proj["product"]["name"] == "Acme Storefront"
        assert proj["product"]["repo"] == "acme/storefront"
        assert proj["activation"]["status"] == "pending"
        assert proj["neon"]["project"] == "acme-store-db"
        assert proj["telegram"]["bot_mode"] == "single_ceo"
        assert proj["telegram"]["ceo_officer"] == "cos"
        assert proj["telegram"]["officers"] == {}
        # plugin task route → tasks block deliberately absent, with the comment
        assert "tasks" not in proj
        assert not re.search(r"^tasks:", text, re.M)
        assert "DELIBERATELY ABSENT" in text
        assert "dev-tasks" in text
        # infra identifiers are NAMES only
        assert "storefront" in text  # vercel project name in comment

    def test_project_linear_lane(self, cab_root):
        run_gen(cab_root, acme_answers())
        text = (cab_root / "instance/config/projects/acme-labs.yml").read_text()
        proj = yaml.safe_load(text)
        assert proj["linear"]["team_key"] == "labs"
        assert proj["linear"]["workspace_url"] == "https://linear.app/acme-labs"
        assert "DELIBERATELY ABSENT" not in text
        # multi-repo lane: first repo is product.repo, rest noted
        assert proj["product"]["repo"] == "acme/labs"
        assert "acme/labs-site" in text

    def test_agent_rendered_from_real_template(self, cab_root):
        run_gen(cab_root, acme_answers())
        text = (cab_root / "instance/agents/acme-store-ceo.md").read_text()
        # all placeholders substituted, none invented
        assert "{{" not in text and "}}" not in text
        assert "Acme Storefront" in text
        assert "acme/storefront" in text
        assert "42424242" in text
        # frontmatter parses and carries the generated role id
        fm = yaml.safe_load(text.split("---", 2)[1])
        assert fm["name"] == "acme-store-ceo"
        assert "Acme Storefront" in fm["description"]
        # default officer_model lands in the frontmatter (the {{MODEL}} seam)
        assert fm["model"] == "claude-fable-5"
        # ownership marker present; template-contract explanation stripped
        assert gi.MARKER in text
        assert "NOT a loadable role definition" not in text

    def test_officer_model_lands_in_agent_and_roster(self, cab_root):
        """A non-default officer_model must reach BOTH artifacts.

        Before the {{MODEL}} placeholder, the template hardcoded
        claude-fable-5 while render_roster honored officer_model — a
        non-default model produced a roster disagreeing with the agent
        frontmatter."""
        answers = acme_answers()
        answers["cabinet"]["officer_model"] = "claude-sonnet-4-6"
        run_gen(cab_root, answers)

        for slug in ("acme-store", "acme-labs"):
            text = (cab_root / f"instance/agents/{slug}-ceo.md").read_text()
            fm = yaml.safe_load(text.split("---", 2)[1])
            assert fm["model"] == "claude-sonnet-4-6"
            assert "claude-fable-5" not in text

        roster = yaml.safe_load((cab_root / "instance/config/roster.yml").read_text())
        assert roster["roster"]["cos"]["model"] == "claude-sonnet-4-6"
        assert roster["roster"]["acme-store-ceo"]["model"] == "claude-sonnet-4-6"

    def test_platform_officers_block_supervisor_compatible(self, cab_root):
        run_gen(cab_root, acme_answers())
        text = (cab_root / "instance/config/platform.yml").read_text()
        # officer-supervisor.sh greps '^  <slug>:.*type:' — single-line inline format
        assert re.search(r"^  cos: \{ type: fulltime \}", text, re.M)
        assert re.search(r"^  acme-store-ceo: \{ type: consultant \}", text, re.M)
        assert re.search(r"^  acme-labs-ceo: \{ type: consultant \}", text, re.M)
        assert gi.PLATFORM_BEGIN in text and gi.PLATFORM_END in text
        platform = yaml.safe_load(text)
        assert platform["officers"] == {
            "cos": {"type": "fulltime"},
            "acme-store-ceo": {"type": "consultant"},
            "acme-labs-ceo": {"type": "consultant"},
        }

    def test_platform_captain_keys_updated_comment_preserved(self, cab_root):
        run_gen(cab_root, acme_answers())
        text = (cab_root / "instance/config/platform.yml").read_text()
        platform = yaml.safe_load(text)
        assert platform["captain_name"] == "Ada"
        assert platform["captain_timezone"] == "Europe/Madrid"
        assert str(platform["captain_telegram_chat_id"]) == "12345678"
        # inline comment on the replaced line survives
        assert re.search(r"^captain_name: Ada\s+# Default", text, re.M)
        # untouched sections survive verbatim
        assert "briefing_frequency: daily" in text

    def test_idempotent_rerun_byte_identical(self, cab_root):
        written = run_gen(cab_root, acme_answers())
        snapshot = {p: p.read_bytes() for p in written}
        run_gen(cab_root, acme_answers())
        for p, before in snapshot.items():
            assert p.read_bytes() == before, f"{p} changed on idempotent re-run"

    def test_dry_run_writes_nothing(self, cab_root):
        before = sorted(str(p) for p in cab_root.rglob("*") if p.is_file())
        platform_before = (cab_root / "instance/config/platform.yml").read_bytes()
        run_gen(cab_root, acme_answers(), dry_run=True)
        after = sorted(str(p) for p in cab_root.rglob("*") if p.is_file())
        # only the answers file itself was added by the test helper
        new = set(after) - set(before)
        assert new == {str(cab_root / "instance/config/cabinet-init.answers.yml")}
        assert (cab_root / "instance/config/platform.yml").read_bytes() == platform_before


# ---------------------------------------------------------------------------
# Roster — must be parseable by the REAL bootstrap-roles.sh --roster parser
# ---------------------------------------------------------------------------

class TestRosterBootstrapCompat:
    def test_roster_seeds_via_real_bootstrap_script(self, cab_root):
        run_gen(cab_root, acme_answers())
        roster = cab_root / "instance/config/roster.yml"
        assert yaml.safe_load(roster.read_text())["roster"]["cos"]["title"] == "Chair"

        # Stub org-runtime.py so seed_role's CLI calls are side-effect free.
        stub_dir = cab_root / "cabinet/scripts"
        stub_dir.mkdir(parents=True, exist_ok=True)
        (stub_dir / "org-runtime.py").write_text("import sys\nsys.exit(0)\n")

        result = subprocess.run(
            ["bash", str(_SCRIPTS_DIR / "bootstrap-roles.sh"),
             "--roster", str(roster), "--product-slug", "acme"],
            env={"PATH": "/usr/bin:/bin:/usr/local/bin",
                 "CABINET_ROOT": str(cab_root), "HOME": str(cab_root)},
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, f"bootstrap-roles failed:\n{result.stdout}\n{result.stderr}"

        active = cab_root / "instance/roles/active"
        seeded = sorted(p.name for p in active.glob("*.yml"))
        assert seeded == ["acme-labs-ceo.yml", "acme-store-ceo.yml", "cos.yml"]

        chair = yaml.safe_load((active / "cos.yml").read_text())
        assert chair["title"] == "Chair"
        assert chair["model"] == "claude-fable-5"
        assert chair["authority_level"] == "captain_proxy"
        assert "validates_deployments" in chair["capabilities"]

        ceo = yaml.safe_load((active / "acme-store-ceo.yml").read_text())
        assert ceo["title"] == "Acme Storefront CEO"
        assert ceo["authority_level"] == "mission_executor"
        assert ceo["capabilities"] == ["deploys_code", "logs_captain_decisions"]


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------

class TestGuardrails:
    def test_path_escape_slug_refused(self, cab_root):
        for evil in ["../evil", "../../etc", "/abs/path", "a/b", "a.b", "UPPER", "..", "x x"]:
            answers = acme_answers()
            answers["lanes"][0]["slug"] = evil
            with pytest.raises(gi.GenerationError, match="slug|refused|match"):
                run_gen(cab_root, answers)
        # nothing escaped or was written outside instance/
        assert not (cab_root.parent / "evil").exists()
        assert not list((cab_root / "instance/config/contexts").glob("*.yml"))

    def test_instance_path_containment_helper(self, cab_root):
        with pytest.raises(gi.GenerationError, match="PATH REFUSED"):
            gi._instance_path(cab_root, "config", "..", "..", "presets", "x.yml")

    def test_secret_values_refused(self, cab_root):
        secrets = [
            ("integrations", {"telegram": {"ceo_bot": "82736451:AAH8f2kQp9zYx-W7vNqLm3RtUv5sJcDbE21"}}),
            ("lanes_desc", "-----BEGIN RSA PRIVATE KEY-----"),
            ("lanes_desc", "sk-ant-api03-aaaaaaaaaaaaaaaaaaaa"),
            ("lanes_desc", "postgres://user:hunter2pass@db.example.com/x"),
            ("lanes_desc", "ghp_abcdefghij0123456789ABCDEFGHIJ01"),
        ]
        for kind, payload in secrets:
            answers = acme_answers()
            if kind == "integrations":
                answers["integrations"] = payload
            else:
                answers["lanes"][0]["description"] = payload
            with pytest.raises(gi.GenerationError, match="SECRET REFUSED"):
                run_gen(cab_root, answers)
        assert not list((cab_root / "instance/config/contexts").glob("*.yml"))

    def test_env_var_fields_must_be_names(self, cab_root):
        answers = acme_answers()
        answers["integrations"]["telegram"]["bot_token_env"] = "lowercase value"
        with pytest.raises(gi.GenerationError, match="ENV VAR NAME"):
            run_gen(cab_root, answers)

    def test_never_clobbers_hand_authored_files(self, cab_root):
        hand = cab_root / "instance/config/contexts/acme-store.yml"
        hand.write_text("slug: acme-store\nname: Hand Authored\nactive: true\n")
        with pytest.raises(gi.GenerationError, match="REFUSING to overwrite"):
            run_gen(cab_root, acme_answers())
        assert "Hand Authored" in hand.read_text()
        # --force overwrites explicitly
        run_gen(cab_root, acme_answers(), force=True)
        assert "Hand Authored" not in hand.read_text()
        assert gi.MARKER in hand.read_text()

    def test_unmanaged_officers_block_refused(self, cab_root):
        platform = cab_root / "instance/config/platform.yml"
        platform.write_text(PLATFORM_FIXTURE + "\nofficers:\n  legacy: { type: fulltime }\n")
        with pytest.raises(gi.GenerationError, match="unmanaged top-level 'officers:'"):
            run_gen(cab_root, acme_answers())

    def test_template_missing_clear_error(self, cab_root):
        (cab_root / "presets/portfolio/agents/_lane-ceo.md.template").unlink()
        with pytest.raises(gi.GenerationError, match="lane-CEO template missing"):
            run_gen(cab_root, acme_answers())

    def test_reserved_and_duplicate_slugs_refused(self, cab_root):
        answers = acme_answers()
        answers["lanes"][0]["slug"] = "cos"
        with pytest.raises(gi.GenerationError, match="reserved"):
            run_gen(cab_root, answers)
        answers = acme_answers()
        answers["lanes"][1]["slug"] = answers["lanes"][0]["slug"]
        with pytest.raises(gi.GenerationError, match="duplicate"):
            run_gen(cab_root, answers)

    def test_cli_exit_code_2_on_guardrail(self, cab_root):
        answers = acme_answers()
        answers["lanes"][0]["slug"] = "../evil"
        path = write_answers(cab_root, answers)
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "generate-instance.py"),
             "--root", str(cab_root), "--answers", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 2
        assert "ERROR" in result.stderr


# ---------------------------------------------------------------------------
# Other org shapes + example answers
# ---------------------------------------------------------------------------

class TestShapesAndExample:
    def test_functional_shape_skips_portfolio_artifacts(self, cab_root):
        answers = acme_answers()
        answers["cabinet"]["org_shape"] = "functional"
        run_gen(cab_root, answers)
        assert (cab_root / "instance/config/contexts/acme-store.yml").is_file()
        assert (cab_root / "instance/config/projects/acme-store.yml").is_file()
        assert not list((cab_root / "instance/agents").glob("*-ceo.md"))
        assert not (cab_root / "instance/config/roster.yml").exists()
        text = (cab_root / "instance/config/platform.yml").read_text()
        assert gi.PLATFORM_BEGIN not in text
        assert yaml.safe_load(text)["captain_name"] == "Ada"

    def test_example_answers_are_valid(self, cab_root):
        path = cab_root / "instance/config/cabinet-init.answers.yml"
        path.write_text(gi.EXAMPLE_ANSWERS)
        gi.generate(cab_root, path)  # full pass on the documented example
        assert (cab_root / "instance/config/roster.yml").is_file()


# ---------------------------------------------------------------------------
# sources.yml emission (org flavor → OrgSource) + org_vault_dir stamping
# ---------------------------------------------------------------------------

class TestSourcesAndOrgVault:
    def test_org_flavor_emits_orgsource_binding(self, cab_root):
        """org flavor (explicit) → marked sources.yml binding OrgSource; the
        platform gains org_vault_dir (relative to the deployment root)."""
        answers = acme_answers()
        answers["autonomy"] = {"posture": "propose_first", "flavor": "org"}
        run_gen(cab_root, answers)

        src_path = cab_root / "instance/config/sources.yml"
        assert src_path.is_file()
        text = src_path.read_text()
        assert gi.MARKER in text
        src = yaml.safe_load(text)
        assert src["adapter"] == "framework.sources.org:OrgSource"
        # deliberately NO dispatch binding — get_dispatch() fail-closes to
        # NullPersonalDispatch (draft-capture-only)
        assert "dispatch" not in src

        platform = yaml.safe_load((cab_root / "instance/config/platform.yml").read_text())
        assert platform["org_vault_dir"] == "vault"

    def test_default_flavor_is_org_and_emits(self, cab_root):
        """No autonomy.flavor key at all (the acme fixture) → defaults to org
        → sources.yml still emitted (fresh org instances must not fail-close
        to NullPersonalSource = zero recall)."""
        assert "flavor" not in acme_answers()["autonomy"]
        run_gen(cab_root, acme_answers())
        src = yaml.safe_load((cab_root / "instance/config/sources.yml").read_text())
        assert src["adapter"] == "framework.sources.org:OrgSource"

    def test_functional_org_shape_also_emits(self, cab_root):
        """The signal is FLAVOR, not org_shape — a functional org box gets
        the binding too."""
        answers = acme_answers()
        answers["cabinet"]["org_shape"] = "functional"
        run_gen(cab_root, answers)
        assert (cab_root / "instance/config/sources.yml").is_file()

    def test_personal_flavor_emits_nothing(self, cab_root):
        """flavor: personal (Flavor-A) → NO sources.yml — the captain binds
        their own personal adapter by hand; today's behavior preserved."""
        answers = acme_answers()
        answers["autonomy"] = {"posture": "propose_first", "flavor": "personal"}
        run_gen(cab_root, answers)
        assert not (cab_root / "instance/config/sources.yml").exists()

    def test_hand_authored_sources_never_clobbered(self, cab_root):
        """An existing sources.yml WITHOUT the marker (e.g. a live Flavor-A
        screenpipe binding) refuses the run and survives byte-identical."""
        hand = cab_root / "instance/config/sources.yml"
        hand.write_text("# hand-authored live binding\nadapter: flavor_a.x:HandAuthored\n")
        before = hand.read_bytes()
        with pytest.raises(gi.GenerationError, match="REFUSING to overwrite"):
            run_gen(cab_root, acme_answers())
        assert hand.read_bytes() == before
        # personal flavor: no emission attempted, hand file untouched, run OK
        answers = acme_answers()
        answers["autonomy"] = {"posture": "propose_first", "flavor": "personal"}
        run_gen(cab_root, answers)
        assert hand.read_bytes() == before

    def test_generated_sources_rerun_idempotent(self, cab_root):
        run_gen(cab_root, acme_answers())
        src_path = cab_root / "instance/config/sources.yml"
        before = src_path.read_bytes()
        run_gen(cab_root, acme_answers())
        assert src_path.read_bytes() == before

    def test_hand_edited_org_vault_dir_survives(self, cab_root):
        """org_vault_dir is set-if-absent: a captain's hand-edited value
        must survive every re-run (there is no answers source for it)."""
        platform = cab_root / "instance/config/platform.yml"
        platform.write_text(PLATFORM_FIXTURE + 'org_vault_dir: "custom/corpus"\n')
        run_gen(cab_root, acme_answers())
        parsed = yaml.safe_load(platform.read_text())
        assert parsed["org_vault_dir"] == "custom/corpus"
        assert platform.read_text().count("org_vault_dir") == 1

    def test_hand_edited_legacy_product_brain_dir_suppresses_stamping(self, cab_root):
        """Vault-rename back-compat: a pre-rename platform.yml carrying a
        hand-edited product_brain_dir must NOT gain an org_vault_dir stamp —
        the resolver reads the new key FIRST, so stamping it would silently
        override the captain's legacy curation."""
        platform = cab_root / "instance/config/platform.yml"
        platform.write_text(PLATFORM_FIXTURE + 'product_brain_dir: "custom/corpus"\n')
        run_gen(cab_root, acme_answers())
        text = platform.read_text()
        assert "org_vault_dir" not in text, (
            "generator stamped org_vault_dir over a hand-edited legacy "
            "product_brain_dir — the legacy value would stop winning"
        )
        parsed = yaml.safe_load(text)
        assert parsed["product_brain_dir"] == "custom/corpus"

    def test_dry_run_emits_no_sources(self, cab_root):
        run_gen(cab_root, acme_answers(), dry_run=True)
        assert not (cab_root / "instance/config/sources.yml").exists()

    def test_invalid_flavor_refused(self, cab_root):
        answers = acme_answers()
        answers["autonomy"] = {"flavor": "corporate"}
        with pytest.raises(gi.GenerationError, match="autonomy.flavor"):
            run_gen(cab_root, answers)
        assert not (cab_root / "instance/config/sources.yml").exists()


# ---------------------------------------------------------------------------
# active-project.txt emission + --adopt (fresh-captain hatch, 2026-07-07)
# ---------------------------------------------------------------------------

class TestActiveProjectAndAdopt:
    def test_active_project_written_from_first_lane(self, cab_root):
        """Fresh hatch: the generator writes active-project.txt with the first
        lane slug — without it bootstrap-roles.sh exits 1 (hatch stall)."""
        run_gen(cab_root, acme_answers())
        ap = cab_root / "instance/config/active-project.txt"
        assert ap.is_file()
        assert ap.read_text() == "acme-store\n"

    def test_existing_active_project_never_touched(self, cab_root):
        """Operator state: an existing active project survives every re-run."""
        ap = cab_root / "instance/config/active-project.txt"
        ap.parent.mkdir(parents=True, exist_ok=True)
        ap.write_text("other-lane\n")
        run_gen(cab_root, acme_answers())
        assert ap.read_text() == "other-lane\n"

    def test_active_project_emitted_for_functional_shape(self, cab_root):
        answers = acme_answers()
        answers["cabinet"]["org_shape"] = "functional"
        run_gen(cab_root, answers)
        assert (cab_root / "instance/config/active-project.txt").read_text() == "acme-store\n"

    def test_dry_run_writes_no_active_project(self, cab_root):
        run_gen(cab_root, acme_answers(), dry_run=True)
        assert not (cab_root / "instance/config/active-project.txt").exists()

    def test_adopt_archives_hand_authored_files(self, cab_root):
        """A clone shipping a previous deployment's hand-authored files:
        --adopt archives them under instance/_pre-adopt-*/ (never deletes)
        and generates fresh marked files."""
        hand_ctx = cab_root / "instance/config/contexts/acme-store.yml"
        hand_ctx.write_text("slug: acme-store\nname: Previous Captain Lane\nactive: true\n")
        hand_src = cab_root / "instance/config/sources.yml"
        hand_src.write_text("# hand-authored live binding\nadapter: flavor_a.x:HandAuthored\n")

        run_gen(cab_root, acme_answers(), adopt=True)

        # fresh marked files in place
        assert gi.MARKER in hand_ctx.read_text()
        assert "Previous Captain Lane" not in hand_ctx.read_text()
        assert gi.MARKER in hand_src.read_text()

        # originals preserved byte-for-byte in the adopt archive
        archives = list((cab_root / "instance").glob("_pre-adopt-*"))
        assert len(archives) == 1
        arch = archives[0]
        assert (arch / "config/contexts/acme-store.yml").read_text() == \
            "slug: acme-store\nname: Previous Captain Lane\nactive: true\n"
        assert "HandAuthored" in (arch / "config/sources.yml").read_text()

    def test_adopt_archives_unmanaged_officers_platform(self, cab_root):
        """The rehearsal stall: platform.yml with another deployment's
        unmanaged officers: block hard-refused generation. --adopt archives
        the whole file and renders fresh captain keys + managed block."""
        platform = cab_root / "instance/config/platform.yml"
        prev = PLATFORM_FIXTURE + "\nofficers:\n  legacy-ceo: { type: consultant }\n"
        platform.write_text(prev)

        run_gen(cab_root, acme_answers(), adopt=True)

        text = platform.read_text()
        assert gi.PLATFORM_BEGIN in text
        assert "legacy-ceo" not in text
        parsed = yaml.safe_load(text)
        assert parsed["captain_name"] == "Ada"
        assert parsed["officers"]["cos"] == {"type": "fulltime"}

        archives = list((cab_root / "instance").glob("_pre-adopt-*"))
        assert len(archives) == 1
        assert (archives[0] / "config/platform.yml").read_text() == prev

    def test_adopt_never_touches_existing_posture(self, cab_root):
        """posture.yml is a Captain ruling — --adopt must not archive or
        regenerate it."""
        posture = cab_root / "instance/config/posture.yml"
        posture.write_text("version: 1\nstatus: ruled\nposture: guardian\n")
        run_gen(cab_root, acme_answers(), adopt=True)
        assert posture.read_text() == "version: 1\nstatus: ruled\nposture: guardian\n"

    def test_adopt_dry_run_moves_nothing(self, cab_root):
        hand = cab_root / "instance/config/sources.yml"
        hand.write_text("# hand-authored\nadapter: flavor_a.x:HandAuthored\n")
        before = hand.read_bytes()
        run_gen(cab_root, acme_answers(), adopt=True, dry_run=True)
        assert hand.read_bytes() == before
        assert not list((cab_root / "instance").glob("_pre-adopt-*"))

    def test_without_adopt_refusal_unchanged(self, cab_root):
        """--adopt is opt-in: the plain run still refuses hand-authored files."""
        hand = cab_root / "instance/config/contexts/acme-store.yml"
        hand.write_text("slug: acme-store\nname: Hand Authored\nactive: true\n")
        with pytest.raises(gi.GenerationError, match="REFUSING to overwrite"):
            run_gen(cab_root, acme_answers())


# ---------------------------------------------------------------------------
# --defaults fast lane (init-fastlane 2026-07-09) — one confirm, zero questions
# ---------------------------------------------------------------------------

class TestDefaultsFastLane:
    def test_defaults_happy_path_zero_prompts(self, cab_root):
        """python3.12 generate-instance.py --defaults [--captain-name NAME]:
        exit 0, instance generated, no prompts (stdin is DEVNULL)."""
        res = run_cli(cab_root, "--defaults", "--captain-name", "Dana Prime")
        assert res.returncode == 0, res.stderr

        # the defaults answers file: marker-stamped, consent-safe values
        answers_path = cab_root / "instance/config/cabinet-init.answers.yml"
        text = answers_path.read_text()
        assert gi.MARKER in text
        answers = yaml.safe_load(text)
        assert answers["captain"]["name"] == "Dana Prime"
        assert answers["captain"]["timezone"] == "UTC"
        assert answers["captain"]["telegram_chat_id"] == "0000"
        assert answers["cabinet"] == {
            "id": "main", "mode": "single", "org_shape": "portfolio",
            "officer_model": gi.DEFAULT_MODEL,
        }
        assert answers["autonomy"] == {
            "posture": "propose_first", "flavor": "org",
            "target_posture": "guardian",
        }
        assert [lane["slug"] for lane in answers["lanes"]] == ["first-lane"]
        assert answers["integrations"]["telegram"]["bot_token_env"] == "TELEGRAM_COS_TOKEN"

        # the full instance generated through the EXISTING path
        for rel in [
            "instance/config/contexts/first-lane.yml",
            "instance/config/projects/first-lane.yml",
            "instance/agents/first-lane-ceo.md",
            "instance/config/roster.yml",
            "instance/config/sources.yml",
            "instance/config/posture.yml",
            "instance/config/active-project.txt",
        ]:
            assert (cab_root / rel).is_file(), f"missing {rel}"
        platform = yaml.safe_load((cab_root / "instance/config/platform.yml").read_text())
        assert platform["captain_name"] == "Dana Prime"
        posture = yaml.safe_load((cab_root / "instance/config/posture.yml").read_text())
        assert posture["posture"] == "guardian"      # consent-safe, explicit
        assert posture["flavor"] == "org"
        src = yaml.safe_load((cab_root / "instance/config/sources.yml").read_text())
        assert src["adapter"] == "framework.sources.org:OrgSource"
        ctx = yaml.safe_load((cab_root / "instance/config/contexts/first-lane.yml").read_text())
        assert ctx["active"] is False                # nothing activates
        assert (cab_root / "instance/config/active-project.txt").read_text() == "first-lane\n"

    def test_default_captain_name_resolution(self, monkeypatch):
        """--captain-name wins; else $USER (if NAME_RE-valid); else 'Captain'.
        An INVALID explicit name refuses loud; an unusable ambient $USER
        falls back silently (it was never asked for)."""
        assert gi.default_captain_name("Ada") == "Ada"
        assert gi.default_captain_name("  Ada  ") == "Ada"
        for bad in ("bad:name", "   ", "a\nb"):
            with pytest.raises(gi.GenerationError, match="captain-name"):
                gi.default_captain_name(bad)
        monkeypatch.setenv("USER", "zoe")
        assert gi.default_captain_name(None) == "zoe"
        monkeypatch.setenv("USER", "bad:user")
        assert gi.default_captain_name(None) == "Captain"
        monkeypatch.delenv("USER", raising=False)
        assert gi.default_captain_name(None) == "Captain"
        # NAME_RE-valid but YAML-reserved/typed-scalar names must round-trip
        # as the EXACT string — an unquoted `name: yes` loads back as True
        # (silent substitute = invented data). _yaml_str quotes exactly these
        # and leaves plain names bare (byte-stable for shell greppers).
        assert gi._yaml_str("Ada") == "Ada"
        assert gi._yaml_str("Dana Prime") == "Dana Prime"
        for reserved in ("yes", "Null", "true", "OFF", "0000", "2026-01-01"):
            assert gi.default_captain_name(reserved) == reserved
            assert gi._yaml_str(reserved) == f'"{reserved}"'
            loaded = yaml.safe_load(gi.render_default_answers(reserved))
            assert loaded["captain"]["name"] == reserved

    def test_defaults_idempotent_rerun_byte_identical(self, cab_root):
        assert run_cli(cab_root, "--defaults", "--captain-name", "Dana").returncode == 0
        snapshot = {p: p.read_bytes()
                    for p in (cab_root / "instance").rglob("*") if p.is_file()}
        assert run_cli(cab_root, "--defaults", "--captain-name", "Dana").returncode == 0
        for p, before in snapshot.items():
            assert p.read_bytes() == before, f"{p} changed on --defaults re-run"
        after = {p for p in (cab_root / "instance").rglob("*") if p.is_file()}
        assert after == set(snapshot), "re-run created unexpected files"

    def test_defaults_then_plain_run_parity(self, cab_root):
        """--defaults rides the EXACT existing generation path: a plain run
        (no --defaults) over the defaults-written answers file is
        byte-identical."""
        assert run_cli(cab_root, "--defaults", "--captain-name", "Dana").returncode == 0
        snapshot = {p: p.read_bytes()
                    for p in (cab_root / "instance").rglob("*") if p.is_file()}
        assert run_cli(cab_root).returncode == 0     # plain lane, same answers
        for p, before in snapshot.items():
            assert p.read_bytes() == before

    def test_defaults_inherited_instance_suggests_adopt(self, cab_root):
        """Inherited clone (platform.yml captain differs + a marker-less
        file): the refusal names the previous captain and teaches --adopt;
        --defaults --adopt then completes with exit 0, archiving (never
        deleting) the previous deployment's file."""
        platform = cab_root / "instance/config/platform.yml"
        platform.write_text(PLATFORM_FIXTURE.replace(
            "captain_name: Placeholder", "captain_name: Prev Captain"))
        hand_src = cab_root / "instance/config/sources.yml"
        hand_src.write_text("# hand-authored live binding\nadapter: flavor_a.x:HandAuthored\n")

        res = run_cli(cab_root, "--defaults", "--captain-name", "Dana")
        assert res.returncode == 2
        assert "REFUSING to overwrite" in res.stderr
        assert "'Prev Captain'" in res.stderr        # the inherited signal, named
        assert "--adopt" in res.stderr               # the taught fix
        assert not list((cab_root / "instance/config/contexts").glob("*.yml"))

        res2 = run_cli(cab_root, "--defaults", "--captain-name", "Dana", "--adopt")
        assert res2.returncode == 0, res2.stderr
        assert yaml.safe_load(platform.read_text())["captain_name"] == "Dana"
        assert gi.MARKER in hand_src.read_text()
        archived = list((cab_root / "instance").glob("_pre-adopt-*/config/sources.yml"))
        assert len(archived) == 1
        assert "HandAuthored" in archived[0].read_text()

    def test_plain_run_hint_only_when_captain_differs(self, cab_root):
        """The inherited teach rides every refusal (not just --defaults) and
        fires ONLY when the existing platform captain actually differs."""
        hand = cab_root / "instance/config/contexts/acme-store.yml"
        hand.write_text("slug: acme-store\nname: Hand Authored\nactive: true\n")
        with pytest.raises(gi.GenerationError) as exc:
            run_gen(cab_root, acme_answers())        # fixture captain 'Placeholder' != 'Ada'
        assert "--adopt" in str(exc.value)
        assert "'Placeholder'" in str(exc.value)

        platform = cab_root / "instance/config/platform.yml"
        platform.write_text(PLATFORM_FIXTURE.replace(
            "captain_name: Placeholder", "captain_name: Ada"))
        with pytest.raises(gi.GenerationError) as exc2:
            run_gen(cab_root, acme_answers())        # same captain — a rename/own-file case
        assert "REFUSING to overwrite" in str(exc2.value)
        assert "looks inherited" not in str(exc2.value)

    def test_defaults_refuses_interview_answers_without_adopt(self, cab_root):
        """An existing answers file WITHOUT the marker is an interview record:
        --defaults refuses (file untouched) and teaches both fixes;
        --defaults --adopt archives it and starts from defaults."""
        answers_path = write_answers(cab_root, acme_answers())
        before = answers_path.read_bytes()

        res = run_cli(cab_root, "--defaults", "--captain-name", "Dana")
        assert res.returncode == 2
        assert "--defaults --adopt" in res.stderr
        assert "WITHOUT --defaults" in res.stderr
        # inherited-clone signal: platform.yml carries 'Placeholder' and the
        # defaults captain would be 'Dana' — the refusal names the previous
        # captain (same teach as the generation-pass refusals)
        assert "looks inherited" in res.stderr
        assert "'Placeholder'" in res.stderr
        # refused run shows no happy-path banner above the error
        assert "defaults fast lane:" not in res.stdout
        assert answers_path.read_bytes() == before   # never clobbered

        res2 = run_cli(cab_root, "--defaults", "--captain-name", "Dana", "--adopt")
        assert res2.returncode == 0, res2.stderr
        assert gi.MARKER in answers_path.read_text()
        assert yaml.safe_load(answers_path.read_text())["captain"]["name"] == "Dana"
        archived = list((cab_root / "instance").glob(
            "_pre-adopt-*/config/cabinet-init.answers.yml"))
        assert len(archived) == 1
        assert archived[0].read_bytes() == before    # archived, never deleted

    def test_defaults_answers_refusal_hint_only_when_captain_differs(self, cab_root):
        """The answers-file refusal names the previous captain ONLY on a real
        inherited signal — refusing over one's OWN interview record (same
        platform captain) must not claim the instance looks inherited."""
        platform = cab_root / "instance/config/platform.yml"
        platform.write_text(PLATFORM_FIXTURE.replace(
            "captain_name: Placeholder", "captain_name: Dana"))
        write_answers(cab_root, acme_answers())      # marker-less interview record
        res = run_cli(cab_root, "--defaults", "--captain-name", "Dana")
        assert res.returncode == 2
        assert "REFUSING to overwrite" in res.stderr
        assert "looks inherited" not in res.stderr

    def test_defaults_answers_target_never_a_generator_output(self, cab_root):
        """--defaults WRITES the answers target, so the target must be named
        '*.answers.yml' — the one filename shape no generated instance file
        can occupy. Without the fence, a marker-stamped generator output
        (posture.yml — Captain-ruled never-touched once written) would read
        as 'generator-owned answers file' and be rewritten permanently.
        Unconditional: --force/--adopt do not widen it, and the refusal must
        not carry the 'REFUSING to overwrite' cue (hatch.sh greps that to
        auto-run --adopt, the wrong fix for a mis-aimed --answers)."""
        assert run_cli(cab_root, "--defaults", "--captain-name", "Dana").returncode == 0
        posture = cab_root / "instance/config/posture.yml"
        before = posture.read_bytes()
        assert gi.MARKER in before.decode()          # marker-stamped output...
        for extra in ((), ("--force",), ("--adopt",)):
            res = run_cli(cab_root, "--defaults", "--captain-name", "Dana",
                          "--answers", str(posture), *extra)
            assert res.returncode == 2, res.stdout
            assert ".answers.yml" in res.stderr      # ...refused, fix taught
            assert "REFUSING to overwrite" not in res.stderr
            assert "defaults fast lane:" not in res.stdout   # no banner on refusal
            assert posture.read_bytes() == before    # never touched
        # an ABSENT reserved target is refused too — a squatted
        # active-project.txt would feed YAML answers to bootstrap-roles.sh
        target = cab_root / "instance/config/active-project.txt"
        target.unlink()
        res = run_cli(cab_root, "--defaults", "--captain-name", "Dana",
                      "--answers", str(target))
        assert res.returncode == 2
        assert not target.exists()

    def test_defaults_reserved_captain_name_end_to_end(self, cab_root):
        """--captain-name yes must land as the STRING 'yes' in both the
        answers file and platform.yml (never bool True, never a silent
        'Captain' fallback); plain names stay unquoted in platform.yml."""
        res = run_cli(cab_root, "--defaults", "--captain-name", "yes")
        assert res.returncode == 0, res.stderr
        answers = yaml.safe_load(
            (cab_root / "instance/config/cabinet-init.answers.yml").read_text())
        assert answers["captain"]["name"] == "yes"
        platform_text = (cab_root / "instance/config/platform.yml").read_text()
        assert 'captain_name: "yes"' in platform_text
        assert yaml.safe_load(platform_text)["captain_name"] == "yes"

    def test_defaults_dry_run_writes_nothing(self, cab_root):
        before = {p: p.read_bytes() for p in cab_root.rglob("*") if p.is_file()}
        res = run_cli(cab_root, "--defaults", "--captain-name", "Dana", "--dry-run")
        assert res.returncode == 0, res.stderr
        after = {p: p.read_bytes() for p in cab_root.rglob("*") if p.is_file()}
        assert after == before                       # no new files, no changed BYTES
        assert "[dry-run] would write instance/config/cabinet-init.answers.yml" in res.stdout

    def test_captain_name_requires_defaults(self, cab_root):
        res = run_cli(cab_root, "--captain-name", "Dana")
        assert res.returncode == 2
        assert "--captain-name requires --defaults" in res.stderr

    def test_defaults_answers_write_stays_jailed(self, cab_root, tmp_path):
        """--defaults WRITES the answers file, so the instance/ path jail
        applies to it: an --answers path outside instance/ is refused."""
        outside = tmp_path / "outside-answers.yml"
        res = run_cli(cab_root, "--defaults", "--captain-name", "Dana",
                      "--answers", str(outside))
        assert res.returncode == 2
        assert "PATH REFUSED" in res.stderr
        assert not outside.exists()

    def test_defaults_output_universality(self, cab_root):
        """defaults-generated artifacts carry no deployment-specific tokens."""
        assert run_cli(cab_root, "--defaults", "--captain-name", "Dana").returncode == 0
        for p in (cab_root / "instance").rglob("*"):
            if p.is_file() and p.suffix in {".yml", ".md"}:
                text = p.read_text().lower()
                for pattern in TestUniversality.FORBIDDEN:
                    assert not re.search(pattern, text), f"{p} contains {pattern}"


# ---------------------------------------------------------------------------
# Universality — the framework carries no deployment specifics
# ---------------------------------------------------------------------------

class TestUniversality:
    # DETECTOR PATTERN LIST (never relax/narrow): the launcher deployment's
    # lane/org/name/host tokens, quoted here solely so the universality
    # guard can prove the generated artifacts carry none of them.
    # Chat-id token: the REAL launcher chat id was scrubbed from the public
    # tree (2026-07-12) — the pattern now pins the tracked platform.yml
    # placeholder (10 zeros), so generated artifacts can never echo the
    # launcher's tracked config value either (defaults use "0000", answers
    # carry their own id — neither matches a 10-zero run).
    FORBIDDEN = [
        r"\bpolads\b", r"\bstephie\b", r"\bstepnetwork\b", r"\bnate\b",
        r"\bhq-macbook\b", r"0000000000", r"\bjfm\b",
    ]

    @pytest.mark.parametrize("rel", [
        "cabinet/scripts/generate-instance.py",
        ".claude/skills/cabinet-init/SKILL.md",
        "framework/schemas/consequence-event.schema.json",
    ])
    def test_no_deployment_specific_tokens(self, rel):
        text = (_REPO_ROOT / rel).read_text().lower()
        for pattern in self.FORBIDDEN:
            assert not re.search(pattern, text), f"{rel} contains deployment-specific token {pattern}"

    def test_generated_output_only_reflects_answers(self, cab_root, tmp_path):
        run_gen(cab_root, acme_answers())
        for p in (cab_root / "instance").rglob("*"):
            if p.is_file() and p.suffix in {".yml", ".md"}:
                text = p.read_text().lower()
                for pattern in self.FORBIDDEN:
                    assert not re.search(pattern, text), f"{p} contains {pattern}"


# ---------------------------------------------------------------------------
# Forward-compat pin — an unknown top-level `mission:` key is TOLERATED
# ---------------------------------------------------------------------------
class TestUnknownMissionKeyTolerated:
    """The purpose-first interview (onboarding-vision-2026-07-14 Phase 2) will
    add a machine-readable top-level ``mission:`` block to
    cabinet-init.answers.yml. That upgrade only works if the zero-LLM
    generator IGNORES an unknown top-level key rather than rejecting it. Pin
    that tolerance TODAY so the interview change can never silently trip the
    generator — and so anyone who later adds strict top-level validation is
    forced to reconcile with this contract (Phase 0 zero-risk fix)."""

    def _build_root(self, base: Path) -> Path:
        (base / "instance/config/contexts").mkdir(parents=True)
        (base / "instance/config/projects").mkdir(parents=True)
        (base / "instance/agents").mkdir(parents=True)
        (base / "presets/portfolio/agents").mkdir(parents=True)
        shutil.copy(
            _REPO_ROOT / "presets/portfolio/agents/_lane-ceo.md.template",
            base / "presets/portfolio/agents/_lane-ceo.md.template",
        )
        (base / "instance/config/platform.yml").write_text(PLATFORM_FIXTURE)
        return base

    @staticmethod
    def _generated_tree(root: Path) -> dict:
        """Every GENERATED instance file → text. Excludes the answers file
        itself (it legitimately differs between the two arms — one carries the
        mission block)."""
        out = {}
        for p in sorted((root / "instance").rglob("*")):
            if p.is_file() and p.name != "cabinet-init.answers.yml":
                out[str(p.relative_to(root))] = p.read_text(encoding="utf-8")
        return out

    _MISSION_BLOCK = {
        "purpose": "Make EU political-ad compliance effortless for publishers.",
        "success_90d": "Three publishers live on the transparency flow.",
        "never_touch": ["production deploys without review", "captain PII"],
    }

    def test_generated_tree_identical_with_and_without_mission(self, tmp_path):
        baseline_root = self._build_root(tmp_path / "baseline")
        run_gen(baseline_root, acme_answers())
        baseline = self._generated_tree(baseline_root)

        mission_root = self._build_root(tmp_path / "withmission")
        answers = acme_answers()
        answers["mission"] = dict(self._MISSION_BLOCK)
        run_gen(mission_root, answers)
        with_mission = self._generated_tree(mission_root)

        assert set(baseline) == set(with_mission), (
            "the mission key changed WHICH files were generated")
        for rel in baseline:
            assert baseline[rel] == with_mission[rel], (
                f"the mission key changed generated content of {rel} — the "
                "generator must ignore unknown top-level keys, not consume them")

    def test_cli_exit_zero_with_mission_key(self, tmp_path):
        """End-to-end through the CLI with stdin closed (zero-prompt proof):
        a top-level mission block must not raise or prompt."""
        root = self._build_root(tmp_path / "cli")
        answers = acme_answers()
        answers["mission"] = dict(self._MISSION_BLOCK)
        path = write_answers(root, answers)
        res = run_cli(root, "--answers", str(path))
        assert res.returncode == 0, res.stderr
        assert (root / "instance/config/roster.yml").is_file()


class TestFreeTextYamlEscaping:
    """egg-hatch-engine-5: free-text lane fields (one_liner, linear_workspace_url,
    linear_team_key, ceo_bot) were interpolated RAW into double-quoted YAML — a
    stray quote aborted generation, a backslash silently mutated the stored
    value. Pin that they now round-trip through _yaml_free (json.dumps escaping)."""

    def test_quotes_and_backslashes_round_trip(self, cab_root):
        answers = acme_answers()
        lane = answers["lanes"][0]
        lane["task_system"] = "linear"
        lane["one_liner"] = 'ship "fast" \\ safely'
        lane["linear_team_key"] = 'te"am'
        lane["linear_workspace_url"] = 'https://linear.app/a"b'
        answers["integrations"]["telegram"]["ceo_bot"] = 'bot"x'
        run_gen(cab_root, answers)  # must NOT raise on the quote
        proj = yaml.safe_load(
            (cab_root / "instance/config/projects/acme-store.yml").read_text())
        # exact round-trip — quote survives, backslash NOT mutated
        assert proj["product"]["description"] == 'ship "fast" \\ safely'
        assert proj["linear"]["workspace_url"] == 'https://linear.app/a"b'
        assert proj["linear"]["team_key"] == 'te"am'
        assert proj["telegram"]["ceo_bot"] == 'bot"x'

    def test_plain_one_liner_still_renders(self, cab_root):
        answers = acme_answers()
        answers["lanes"][0]["one_liner"] = "a clean simple tagline"
        run_gen(cab_root, answers)
        proj = yaml.safe_load(
            (cab_root / "instance/config/projects/acme-store.yml").read_text())
        assert proj["product"]["description"] == "a clean simple tagline"
