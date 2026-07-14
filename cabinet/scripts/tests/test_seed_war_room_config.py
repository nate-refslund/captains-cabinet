"""seed-war-room.py's load_c7_items() — product/captain-agnostic foundation
(2026-07-14). Pins: absent/empty instance file -> [] (never invented data,
never a hard error); present file -> parsed items list; malformed 'items:'
raises loudly rather than silently coercing."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "seed-war-room.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("seed_war_room", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def seeder():
    return _load_module()


def test_absent_instance_file_yields_no_items(tmp_path, seeder):
    assert seeder.load_c7_items(tmp_path) == []


def test_empty_items_key_yields_no_items(tmp_path, seeder):
    cfg = tmp_path / "instance" / "config"
    cfg.mkdir(parents=True)
    (cfg / "war-room-seed.yml").write_text("items:\n", encoding="utf-8")
    assert seeder.load_c7_items(tmp_path) == []


def test_present_file_parses_items(tmp_path, seeder):
    cfg = tmp_path / "instance" / "config"
    cfg.mkdir(parents=True)
    (cfg / "war-room-seed.yml").write_text("""
items:
  - slug: example-item
    lane: null
    subject: "An example census item"
    kind: founder-action
    keywords: [example]
""", encoding="utf-8")
    items = seeder.load_c7_items(tmp_path)
    assert len(items) == 1
    assert items[0]["slug"] == "example-item"


def test_malformed_items_value_raises(tmp_path, seeder):
    cfg = tmp_path / "instance" / "config"
    cfg.mkdir(parents=True)
    (cfg / "war-room-seed.yml").write_text("items: not-a-list\n", encoding="utf-8")
    with pytest.raises(ValueError):
        seeder.load_c7_items(tmp_path)


def test_item_missing_required_field_raises_loudly(tmp_path, seeder):
    # A malformed operator-authored entry (missing 'kind') must fail here,
    # with the offending index/slug named -- not as a bare KeyError deep
    # inside plan()/item_refs().
    cfg = tmp_path / "instance" / "config"
    cfg.mkdir(parents=True)
    (cfg / "war-room-seed.yml").write_text("""
items:
  - slug: incomplete-item
    subject: "Missing its kind field"
    keywords: [example]
""", encoding="utf-8")
    with pytest.raises(ValueError, match="incomplete-item"):
        seeder.load_c7_items(tmp_path)


def test_item_not_a_mapping_raises(tmp_path, seeder):
    cfg = tmp_path / "instance" / "config"
    cfg.mkdir(parents=True)
    (cfg / "war-room-seed.yml").write_text("items:\n  - just-a-string\n",
                                          encoding="utf-8")
    with pytest.raises(ValueError):
        seeder.load_c7_items(tmp_path)
