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
                "boards": ["1234567890"],
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
        assert "1234567890" in text
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
            ("integrations", {"telegram": {"ceo_bot": "8273645123:AAH8f2kQp9zYx-W7vNqLm3RtUv5sJcDbE21"}}),
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
# Universality — the framework carries no deployment specifics
# ---------------------------------------------------------------------------

class TestUniversality:
    FORBIDDEN = [
        r"\bpolads\b", r"\bstephie\b", r"\bstepnetwork\b", r"\bnate\b",
        r"\bhq-macbook\b", r"8631324091", r"\bjfm\b",
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
