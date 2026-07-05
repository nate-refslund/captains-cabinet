"""Shared fixtures/helpers for the framework.channels [AX-5] suite."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Every test owns its env + a private event-ledger dir, so replay()
    reads only this test's events (same pattern as the authority suites)."""
    for var in ("CABINET_ROOT", "CABINET_ENV", "SLACK_BOT_TOKEN",
                "DATABASE_URL", "CABINET_FRAMEWORK_STORE_MIRROR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))


def write_channels_yml(root: Path, text: "str | None" = None,
                       **overrides) -> Path:
    """Materialize <root>/instance/config/channels.yml (raw `text` wins)."""
    cfg = {"version": 1, "org_domains": ["acme.com"]}
    cfg.update(overrides)
    d = root / "instance/config"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "channels.yml"
    p.write_text(text if text is not None else yaml.safe_dump(cfg))
    return p
