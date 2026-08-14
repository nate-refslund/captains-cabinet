"""The captured Telegram address must survive a regenerate — BOTH ARMS.

WHAT THIS GUARDS. The dashboard's guided Telegram connect
(`cabinet/dashboard/src/actions/telegram-connect.ts`) captures the operator's
chat id with no terminal and records it in three places. Two of them are
obvious: `cabinet/.env CAPTAIN_TELEGRAM_ID`, which the outbound door reads, and
`instance/config/platform.yml captain_telegram_chat_id`, which the inbound
poller's capture seam and the governance label channel read.

The third is the one this file exists for. `captain_telegram_chat_id` is a
GENERATED key: `render_platform` in generate-instance.py re-stamps it from
`captain.telegram_chat_id` in the interview answers on EVERY run. So writing
platform.yml alone would be a hand-edit of a generator output — correct until
the next `python3.12 cabinet/scripts/generate-instance.py`, which would put the
placeholder back and take the cabinet's phone line down with nothing on any
screen to say why. The flow therefore writes the ANSWER too, and a regenerate
re-derives the same value.

WHY BOTH ARMS. `test_survives_when_the_answer_was_written_too` on its own would
pass against a generator that ignored answers entirely, and against a flow that
had never written anything at all. `test_is_clobbered_when_only_platform_was_written`
is the same fixture with the answers write REMOVED, and it asserts the loss —
so the pair proves the generator really does overwrite, and that the answers
write is the thing standing between the operator and a silent revert.
"""

from __future__ import annotations

import importlib.util as _ilu
import shutil
from pathlib import Path

import pytest
import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent

spec = _ilu.spec_from_file_location(
    "generate_instance_for_telegram_test", _SCRIPTS_DIR / "generate-instance.py"
)
gi = _ilu.module_from_spec(spec)
spec.loader.exec_module(gi)

# The placeholder a fresh hatch carries until somebody connects a phone.
PLACEHOLDER = "0000"
# What the guided flow captures. A fictional address; no real account exists.
CAPTURED = "4242424242"

PLATFORM_FIXTURE = f"""\
# =============================================================
# Test platform configuration (fictional captain)
# =============================================================
captain_name: Placeholder
captain_timezone: UTC
captain_telegram_chat_id: "{PLACEHOLDER}"

communication:
  briefing_frequency: daily
"""

OFFICER_CONF = """\
cos:logs_captain_decisions
cos:validates_deployments
acme-store-ceo:deploys_code
acme-store-ceo:logs_captain_decisions
"""

MCP_SCOPE = """\
cabinet: acme-hq
agents:
  cos:
    mcps: [telegram]
  acme-store-ceo:
    mcps: [neon]
"""


def answers(chat_id: str) -> dict:
    return {
        "version": 1,
        "captain": {"name": "Ada", "timezone": "UTC", "telegram_chat_id": chat_id},
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
            }
        ],
    }


@pytest.fixture()
def cab_root(tmp_path: Path) -> Path:
    """A minimal deployment root the generator will accept."""
    root = tmp_path / "cab"
    (root / "instance/config/contexts").mkdir(parents=True)
    (root / "instance/config/projects").mkdir(parents=True)
    (root / "instance/agents").mkdir(parents=True)
    (root / "presets/portfolio/agents").mkdir(parents=True)
    (root / "cabinet").mkdir(parents=True)
    shutil.copy(
        _REPO_ROOT / "presets/portfolio/agents/_lane-ceo.md.template",
        root / "presets/portfolio/agents/_lane-ceo.md.template",
    )
    (root / "cabinet/officer-capabilities.conf").write_text(OFFICER_CONF)
    (root / "cabinet/mcp-scope.yml").write_text(MCP_SCOPE)
    (root / "instance/config/platform.yml").write_text(PLATFORM_FIXTURE)
    return root


def _write_answers(root: Path, chat_id: str) -> Path:
    path = root / "instance/config/cabinet-init.answers.yml"
    path.write_text(yaml.safe_dump(answers(chat_id), sort_keys=False))
    return path


def _stamp_platform(root: Path, chat_id: str) -> None:
    """What the dashboard's YAML line-editor does to platform.yml: change ONE
    line and leave every other byte alone."""
    path = root / "instance/config/platform.yml"
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith("captain_telegram_chat_id:"):
            lines[i] = f'captain_telegram_chat_id: "{chat_id}"'
            break
    else:  # pragma: no cover - the fixture always carries the key
        pytest.fail("fixture lost captain_telegram_chat_id")
    path.write_text("\n".join(lines) + "\n")


def _platform_chat_id(root: Path) -> str:
    doc = yaml.safe_load((root / "instance/config/platform.yml").read_text())
    return str(doc["captain_telegram_chat_id"])


def test_survives_when_the_answer_was_written_too(cab_root: Path) -> None:
    """The flow's real behaviour: both files carry the captured address, so the
    generator re-derives the SAME value and nothing is lost."""
    _write_answers(cab_root, CAPTURED)
    _stamp_platform(cab_root, CAPTURED)
    assert _platform_chat_id(cab_root) == CAPTURED

    gi.generate(cab_root, cab_root / "instance/config/cabinet-init.answers.yml")

    assert _platform_chat_id(cab_root) == CAPTURED, (
        "a regenerate lost the address the operator captured — the guided "
        "Telegram connect must write captain.telegram_chat_id in the answers "
        "file, not only the generated key in platform.yml"
    )


def test_is_clobbered_when_only_platform_was_written(cab_root: Path) -> None:
    """THE ARM THAT PROVES THE ONE ABOVE MEASURES SOMETHING. Same fixture, with
    the answers write removed: the generator stamps the placeholder straight
    back over the captured address. If this ever stops failing, the test above
    has stopped being a guard and `captain_telegram_chat_id` is no longer a
    generated key — which is a change to state in the flow's own comments."""
    _write_answers(cab_root, PLACEHOLDER)  # the answer nobody updated
    _stamp_platform(cab_root, CAPTURED)  # the hand-edit on its own
    assert _platform_chat_id(cab_root) == CAPTURED

    gi.generate(cab_root, cab_root / "instance/config/cabinet-init.answers.yml")

    assert _platform_chat_id(cab_root) == PLACEHOLDER, (
        "the generator no longer re-derives captain_telegram_chat_id from the "
        "answers file — re-read the write path in "
        "cabinet/dashboard/src/actions/telegram-connect.ts, which says it does"
    )


def test_the_generator_refuses_an_address_the_flow_could_not_have_written(
    cab_root: Path,
) -> None:
    """The flow validates the captured id against the same shape the generator
    enforces (`CHAT_ID_RE`), so a value it stores can never be one a later
    regenerate rejects. This pins the two ends of that agreement."""
    assert gi.CHAT_ID_RE.match(CAPTURED)
    assert gi.CHAT_ID_RE.match("-1001234567890")  # a group room is a legal address
    for bad in ("", "abc", "12", "42424242424242424242424242"):
        assert not gi.CHAT_ID_RE.match(bad), f"generator would accept {bad!r}"

    _write_answers(cab_root, "not-an-address")
    with pytest.raises(gi.GenerationError, match="telegram_chat_id"):
        gi.generate(cab_root, cab_root / "instance/config/cabinet-init.answers.yml")
