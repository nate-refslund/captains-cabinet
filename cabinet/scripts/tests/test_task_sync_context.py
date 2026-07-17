"""Config-split fix (2026-07-17) — task_sync_runner resolves its project
config through the shared preset-aware context chain (framework.env.
active_context), not a bare active-project.txt read.

The runner is deployment-scoped (no officer identity), so its live rungs are
env > active-project.txt > single-declared-lane > declared lane_default; a
miss must be LOUD with the remedy naming those rungs — never the old
misleading "set active project first" (writing active-project.txt on a
preset deployment would flip every other consumer).

Synthetic Testburg vocabulary; no network, no adapters exercised beyond
config parsing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cabinet.scripts.task_sync_runner import _active_project_config  # noqa: E402


def _seed(tmp_path: Path, *, contexts: "dict[str, str]",
          projects: "dict[str, str]", platform_yml: "str | None" = None,
          active_project: "str | None" = None) -> Path:
    cfg = tmp_path / "instance" / "config"
    (cfg / "contexts").mkdir(parents=True)
    (cfg / "projects").mkdir(parents=True)
    for name, body in contexts.items():
        (cfg / "contexts" / name).write_text(body, encoding="utf-8")
    for name, body in projects.items():
        (cfg / "projects" / name).write_text(body, encoding="utf-8")
    if platform_yml is not None:
        (cfg / "platform.yml").write_text(platform_yml, encoding="utf-8")
    if active_project is not None:
        (cfg / "active-project.txt").write_text(active_project, encoding="utf-8")
    return tmp_path


def test_env_context_selects_project_config(monkeypatch, tmp_path):
    root = _seed(tmp_path,
                 contexts={"bakery.yml": "slug: bakery\n",
                           "newsletter.yml": "slug: newsletter\n"},
                 projects={"bakery.yml": "tasks:\n  system: none\n"})
    monkeypatch.setenv("CABINET_CONTEXT", "bakery")
    cfg = _active_project_config(str(root))
    assert cfg == {"tasks": {"system": "none"}}


def test_active_project_txt_still_works(monkeypatch, tmp_path):
    root = _seed(tmp_path,
                 contexts={"bakery.yml": "slug: bakery\n"},
                 projects={"bakery.yml": "tasks:\n  system: none\n"},
                 active_project="bakery\n")
    monkeypatch.delenv("CABINET_CONTEXT", raising=False)
    assert _active_project_config(str(root))["tasks"]["system"] == "none"


def test_lane_default_covers_portfolio_runner(monkeypatch, tmp_path):
    """Portfolio shape (no active-project.txt): the runner follows the
    Captain-ruled lane_default."""
    root = _seed(tmp_path,
                 contexts={"bakery.yml": "slug: bakery\n",
                           "newsletter.yml": "slug: newsletter\n"},
                 projects={"newsletter.yml": "tasks:\n  system: none\n"},
                 platform_yml="lane_default: newsletter\n")
    monkeypatch.delenv("CABINET_CONTEXT", raising=False)
    assert _active_project_config(str(root)) == {"tasks": {"system": "none"}}


def test_unresolved_context_raises_with_full_remedy(monkeypatch, tmp_path):
    """Multi-lane, no env, no file, no default → LOUD, remedy names the
    rungs (negative control: the old 'set active project first' advice must
    be gone — it is WRONG on a preset deployment)."""
    root = _seed(tmp_path,
                 contexts={"bakery.yml": "slug: bakery\n",
                           "newsletter.yml": "slug: newsletter\n"},
                 projects={})
    monkeypatch.delenv("CABINET_CONTEXT", raising=False)
    with pytest.raises(FileNotFoundError) as exc:
        _active_project_config(str(root))
    msg = str(exc.value)
    for needle in ("CABINET_CONTEXT", "active-project.txt", "lane_default"):
        assert needle in msg
    assert "set active project first" not in msg


def test_resolved_context_without_project_yaml_names_the_path(monkeypatch, tmp_path):
    root = _seed(tmp_path,
                 contexts={"bakery.yml": "slug: bakery\n"},
                 projects={})
    monkeypatch.delenv("CABINET_CONTEXT", raising=False)
    with pytest.raises(FileNotFoundError) as exc:
        _active_project_config(str(root))  # single lane resolves 'bakery'
    assert "bakery.yml" in str(exc.value)


def test_malformed_env_context_is_not_a_path_segment(monkeypatch, tmp_path):
    """Injection control: a traversal-shaped CABINET_CONTEXT is refused by
    the resolver's shape gate, so it can never reach the projects/ join."""
    root = _seed(tmp_path,
                 contexts={"bakery.yml": "slug: bakery\n"},
                 projects={"bakery.yml": "tasks:\n  system: none\n"})
    monkeypatch.setenv("CABINET_CONTEXT", "../../../etc/passwd")
    # rung skipped → single declared lane resolves instead
    assert _active_project_config(str(root)) == {"tasks": {"system": "none"}}
