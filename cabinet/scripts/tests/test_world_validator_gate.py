"""Tests for the Cabinet World E1 law-and-gate scripts:
world-binding-validator.py (allowlisted read-only sandbox), world-legend.py
(Legend Law generator), world-asset-gate.py (conformance gate).
"""
from __future__ import annotations

import hashlib
import importlib.util as _ilu
import json
import struct
import sys
import zlib
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    spec = _ilu.spec_from_file_location(name, _SCRIPTS / filename)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


wbv = _load("world_binding_validator", "world-binding-validator.py")
wag = _load("world_asset_gate", "world-asset-gate.py")


GOOD_ENTRY = {
    "id": "captain_rules",
    "represents": "Courthouse tablets",
    # NB: leading-dash patterns need `-e` or grep eats them as options —
    # morphology v1 bindings follow this shape.
    "source_binding": "grep -c -e '- id:' shared/interfaces/captain-rules-index.yaml",
    "scope": "org-global",
    "tier": "T0",
    "replay": "git",
    "codex": {
        "represents": "Indexed captain rules — one tablet per rule",
        "mechanism_path": "shared/interfaces/captain-rules-index.yaml",
        "day0": "0 tablets",
    },
}


class TestSchema:
    def test_good_entry_clean(self):
        assert wbv.check_schema(GOOD_ENTRY) == []

    def test_untiered_rejected(self):
        e = dict(GOOD_ENTRY)
        del e["tier"]
        assert any("untiered" in p for p in wbv.check_schema(e))

    def test_unreplayed_rejected(self):
        e = dict(GOOD_ENTRY)
        del e["replay"]
        assert any("replay" in p for p in wbv.check_schema(e))

    def test_codex_required(self):
        e = dict(GOOD_ENTRY)
        del e["codex"]
        assert any("codex required" in p for p in wbv.check_schema(e))

    def test_stale_mechanism_path_flagged(self):
        e = json.loads(json.dumps(GOOD_ENTRY))
        e["codex"]["mechanism_path"] = "does/not/exist.py"
        assert any("does not exist" in p for p in wbv.check_schema(e))

    def test_codex_restating_id_rejected(self):
        e = json.loads(json.dumps(GOOD_ENTRY))
        e["codex"]["represents"] = "captain rules"
        assert any("restates" in p for p in wbv.check_schema(e))


class TestSandbox:
    def test_allowlisted_binding_executes(self):
        ok, value = wbv.execute_binding(
            "grep -c -e '- id:' shared/interfaces/captain-rules-index.yaml")
        assert ok, value
        assert int(value) > 0

    def test_binary_outside_allowlist_refused(self):
        ok, reason = wbv.execute_binding("curl https://example.com")
        assert not ok and "allowlist" in reason

    def test_shell_metacharacters_refused(self):
        ok, reason = wbv.execute_binding("wc -l x.txt | tee /tmp/out")
        assert not ok and "metacharacters" in reason
        ok, reason = wbv.execute_binding("ls $(rm -rf /)")
        assert not ok and "metacharacters" in reason

    def test_pipe_inside_quoted_jq_filter_is_inert_and_allowed(self):
        # shell=False: a | INSIDE one quoted argument is data to jq, not a
        # shell pipe — the guard discriminates token-level (standalone |
        # refused above; quoted filter passes).
        series = _SCRIPTS.parents[1] / ".pytest-world-series.jsonl"
        series.write_text('{"memory_rows_total": 619}\n')
        try:
            ok, value = wbv.execute_binding(
                f"jq -r -s 'last | .memory_rows_total' {series.name}")
            assert ok, value
            assert value == "619"
        finally:
            series.unlink(missing_ok=True)

    def test_sqlite_without_readonly_refused(self):
        ok, reason = wbv.execute_binding(
            "sqlite3 cabinet/cache/org-runtime.sqlite3 'SELECT 1'")
        assert not ok and "-readonly" in reason

    def test_path_escape_refused(self):
        ok, reason = wbv.execute_binding("wc -l /etc/passwd")
        assert not ok and "escapes the repo" in reason
        ok, reason = wbv.execute_binding("wc -l ../../etc/passwd")
        assert not ok

    def test_empty_output_is_dead_pixel(self, tmp_path, monkeypatch):
        empty = _SCRIPTS.parents[1] / ".pytest-world-empty.txt"
        empty.write_text("")
        try:
            ok, reason = wbv.execute_binding(f"grep -c ZZZ_NOPE {empty.name}")
            # grep -c with no match exits 1 → FAIL path (exit) — dead pixel.
            assert not ok
        finally:
            empty.unlink(missing_ok=True)


class TestValidateEndToEnd:
    def test_valid_morphology_green(self, tmp_path):
        doc = {"version": 1, "entries": [GOOD_ENTRY]}
        p = tmp_path / "morphology.yml"
        import yaml as _y
        p.write_text(_y.safe_dump(doc))
        findings = wbv.validate(p)
        assert all(f.level == "OK" for f in findings), [f.message for f in findings]

    def test_dark_scope_skips_execution(self, tmp_path):
        e = json.loads(json.dumps(GOOD_ENTRY))
        e["id"] = "dark_thing"
        e["scope"] = "dark"
        e["source_binding"] = "curl evil"  # never executed for dark scope
        import yaml as _y
        p = tmp_path / "morphology.yml"
        p.write_text(_y.safe_dump({"version": 1, "entries": [e]}))
        findings = wbv.validate(p)
        assert findings[0].level == "OK"
        assert "dark" in findings[0].message


def _png_bytes(w: int, h: int) -> bytes:
    """Minimal valid PNG (IHDR + IDAT + IEND)."""
    def chunk(typ: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x00\x00\x00\x00" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class TestAssetGate:
    def _manifest(self, tmp_path, assets):
        (tmp_path / "manifest.json").write_text(json.dumps({"assets": assets}))
        return tmp_path / "manifest.json"

    def test_empty_manifest_green(self, tmp_path):
        m = self._manifest(tmp_path, [])
        assert wag.main([str(m)]) == 0

    def test_conformant_png_green(self, tmp_path):
        data = _png_bytes(32, 48)
        (tmp_path / "officer.png").write_bytes(data)
        m = self._manifest(tmp_path, [{
            "id": "officer", "path": "officer.png", "w": 32, "h": 48,
            "sha256": hashlib.sha256(data).hexdigest()}])
        assert wag.main([str(m)]) == 0

    def test_non_png_refused(self, tmp_path):
        (tmp_path / "evil.png").write_text("<svg onload=alert(1)>")
        m = self._manifest(tmp_path, [{"id": "evil", "path": "evil.png"}])
        assert wag.main([str(m)]) == 1

    def test_containment_escape_refused(self, tmp_path):
        m = self._manifest(tmp_path, [{"id": "esc", "path": "../../.env"}])
        assert wag.main([str(m)]) == 1

    def test_off_grid_refused(self, tmp_path):
        (tmp_path / "odd.png").write_bytes(_png_bytes(30, 48))
        m = self._manifest(tmp_path, [{"id": "odd", "path": "odd.png"}])
        assert wag.main([str(m)]) == 1

    def test_sha_mismatch_refused(self, tmp_path):
        (tmp_path / "a.png").write_bytes(_png_bytes(16, 16))
        m = self._manifest(tmp_path, [{
            "id": "a", "path": "a.png", "sha256": "0" * 64}])
        assert wag.main([str(m)]) == 1

    def test_dimension_mismatch_refused(self, tmp_path):
        (tmp_path / "d.png").write_bytes(_png_bytes(16, 16))
        m = self._manifest(tmp_path, [{
            "id": "d", "path": "d.png", "w": 32, "h": 32}])
        assert wag.main([str(m)]) == 1


class TestLegend:
    def test_legend_generates_from_fixture(self, tmp_path, monkeypatch):
        import yaml as _y
        gdir = tmp_path / "grammar"
        gdir.mkdir()
        (gdir / "morphology.yml").write_text(
            _y.safe_dump({"version": 1, "entries": [GOOD_ENTRY]}))
        (gdir / "show-grammar.yml").write_text(_y.safe_dump({
            "version": 1,
            "fallback": {"station": "floor", "anim": "idle"},
            "verbs": {"working": {
                "station": "desk", "anim": "work", "salience": 0,
                "codex": {"represents": "at desk",
                          "mechanism_path": "cabinet/services.yml",
                          "day0": "empty"}}},
        }))
        out = tmp_path / "legend.json"
        monkeypatch.setenv("CABINET_WORLD_GRAMMAR_DIR", str(gdir))
        monkeypatch.setenv("CABINET_WORLD_LEGEND_OUT", str(out))
        wl = _load("world_legend_fixture", "world-legend.py")
        assert wl.main() == 0
        legend = json.loads(out.read_text())
        assert legend["grammar_pending"] is False
        assert legend["show_grammar_version"] == 1
        assert legend["mappings"][0]["id"] == "captain_rules"
        assert legend["mappings"][0]["status"] == "OK"
        assert legend["codex_coverage"] == 1.0
