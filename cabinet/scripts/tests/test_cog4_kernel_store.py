"""COG-4 W3 u1 — C3 kernel store disciplines (contract §6.1 e/f/g + §6.3) and
the kernel's own boundary (§8.3 row 6 / §8.4 stdlib-only closure).

  * (e) ATOMIC WRITE crash-safety — a subprocess driver calls the REAL
    kernel.atomic_write and DIES (os._exit via a patched os hook) at each
    pre-replace boundary (during fsync / at replace): the target file keeps
    its old bytes EXACTLY — never a partial; the O_EXCL tmp discipline bites
    (a pre-existing tmp collision fails loud, target untouched); tmp debris is
    0o600.
  * (f) VERIFIED SINGLE-READ — the hash binds the rows THAT read returned:
    exactly ONE filesystem read of the store (counted), the returned rows
    re-hash to the returned hash even after the on-disk store is tampered
    post-serve, and every REFUSE limb refuses via the domain factory —
    INCLUDING the mandatory-present rows-hash key (§6.3: an ABSENT key
    refuses; the objectives query.py:214-215 `is not None and` skip-hole is
    structurally impossible through the kernel). The parameterized extra-limb
    runner runs AFTER the hash binding, in declared order.
  * (g) CANONICAL-CUTOFF validator — the kernel pattern is the EXACT literal
    replicated at framework/cortex/query.py and framework/objectives/graph.py
    (pinned by VALUE against both source texts — no cortex/objectives import;
    test_cog4_* files are not allowlisted importers of either tree), plus the
    accept/reject behavioral arms.
  * BOUNDARY — framework/projection is import-inert at the package root and
    stdlib-only in transitive closure: a subprocess import of
    framework.projection.kernel loads NO other framework module and NOTHING
    from the action/authority/fidelity planes (the exact scan the armed
    test_cog4_scheduler_ast_pin closure arm runs over this tree once its
    vacuity skip is retired), plus a static AST scan pinning every import in
    the tree to the stdlib.

S0: python3.12, no DB, no network. Provenance: authored per the 2026-07-07
full-autonomy grant + the 2026-07-20 cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import ast
import json
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent          # cabinet/scripts/tests
_REPO = _HERE.parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from framework.projection import kernel  # noqa: E402  (row-6 allowlisted glob)


class Refused(Exception):
    """The domain refusal type of these tests (the `refuse` factory input)."""


def _rows_hash(rows) -> str:
    return kernel.chained_rows_hash(
        rows, algebra=kernel.ALGEBRA_DIGEST_LIST, seed="",
        order_key=kernel.canonical_bytes)


def _write_store(cache: Path, rows, *, hash_key="rows_hash",
                 store="store.jsonl", manifest="manifest.json") -> dict:
    """A minimal kernel-built store (rows + envelope, atomically written)."""
    body = "".join(kernel.canonical_bytes(r).decode("utf-8") + "\n" for r in rows)
    kernel.atomic_write(cache / store, body)
    env = kernel.manifest_envelope(
        schema_version="cog4-kernel-test/v1", epoch={"scope": "test"},
        store_hash_key=hash_key, store_hash=_rows_hash(rows),
        counts={"row_count": len(rows)})
    kernel.atomic_write(cache / manifest,
                        json.dumps(env, ensure_ascii=False, sort_keys=True) + "\n")
    return env


_ROWS = [{"id": "a", "v": 1}, {"id": "b", "v": 2}, {"id": "c", "v": 3}]


def _serve(cache: Path, **kw):
    return kernel.verified_single_read(
        cache, store_filename="store.jsonl", manifest_filename="manifest.json",
        store_hash_key="rows_hash", rows_hash=_rows_hash, refuse=Refused, **kw)


# ===========================================================================
# (e) atomic write — crash-safety at every pre-replace boundary
# ===========================================================================
_CRASH_DRIVER = """\
import os, sys
sys.path.insert(0, sys.argv[3])
from framework.projection import kernel
mode = sys.argv[2]
if mode == "fsync":
    os.fsync = lambda fd: os._exit(137)      # die DURING the flushed write
elif mode == "replace":
    os.replace = lambda a, b: os._exit(137)  # die AT the replace boundary
kernel.atomic_write(sys.argv[1], "NEW PAYLOAD THAT MUST NEVER LAND PARTIALLY\\n")
os._exit(0)
"""


class TestAtomicWriteCrashSafety:
    def _crash(self, tmp_path: Path, mode: str) -> Path:
        driver = tmp_path / "crash_driver.py"
        driver.write_text(_CRASH_DRIVER, encoding="utf-8")
        target = tmp_path / "cache" / "artifact.json"
        target.parent.mkdir(parents=True)
        target.write_text("OLD BYTES\n", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(driver), str(target), mode, str(_REPO)],
            capture_output=True, text=True)
        assert r.returncode == (0 if mode == "none" else 137), (mode, r.stderr)
        return target

    @pytest.mark.parametrize("mode", ["fsync", "replace"])
    def test_kill_before_replace_leaves_no_partial(self, tmp_path, mode):
        target = self._crash(tmp_path, mode)
        # the LAW: death at any pre-replace point leaves the target
        # byte-untouched — never a partial, never the new payload.
        assert target.read_text(encoding="utf-8") == "OLD BYTES\n"
        debris = [p for p in target.parent.iterdir() if p.name.endswith(".tmp")]
        assert len(debris) == 1                       # inert, dot-prefixed
        assert debris[0].name.startswith(".artifact.json.")
        assert stat.S_IMODE(debris[0].stat().st_mode) == 0o600

    def test_success_path_replaces_exactly(self, tmp_path):
        target = self._crash(tmp_path, "none")
        assert target.read_text(encoding="utf-8") == (
            "NEW PAYLOAD THAT MUST NEVER LAND PARTIALLY\n")
        assert [p for p in target.parent.iterdir() if p.name.endswith(".tmp")] == []

    def test_o_excl_collision_fails_loud_target_untouched(self, tmp_path, monkeypatch):
        class _Fixed:
            hex = "deadbeefcafe"
        monkeypatch.setattr(uuid, "uuid4", lambda: _Fixed)
        target = tmp_path / "artifact.json"
        target.write_text("OLD BYTES\n", encoding="utf-8")
        import os as _os
        tmp = target.with_name(f".artifact.json.{_os.getpid()}.deadbe.tmp")
        tmp.write_text("squatter", encoding="utf-8")
        with pytest.raises(FileExistsError):
            kernel.atomic_write(target, "NEW\n")
        assert target.read_text(encoding="utf-8") == "OLD BYTES\n"


# ===========================================================================
# (f) verified single-read — no-window binding + the REFUSE-limb runner
# ===========================================================================
class TestVerifiedSingleRead:
    def test_serves_and_hash_binds_the_returned_rows(self, tmp_path):
        env = _write_store(tmp_path, _ROWS)
        served_hash, rows, manifest = _serve(tmp_path)
        assert manifest == env
        assert rows == _ROWS
        assert served_hash == env["rows_hash"] == _rows_hash(rows)

    def test_exactly_one_store_read(self, tmp_path, monkeypatch):
        _write_store(tmp_path, _ROWS)
        reads: list[str] = []
        real = Path.read_text

        def counting(self, *a, **kw):
            reads.append(self.name)
            return real(self, *a, **kw)

        monkeypatch.setattr(Path, "read_text", counting)
        _serve(tmp_path)
        assert reads.count("store.jsonl") == 1        # THE one read (F4)
        assert reads.count("manifest.json") == 1

    def test_rows_stay_bound_after_post_serve_tamper(self, tmp_path):
        _write_store(tmp_path, _ROWS)
        served_hash, rows, _ = _serve(tmp_path)
        (tmp_path / "store.jsonl").write_text(
            kernel.canonical_bytes({"id": "z", "v": 99}).decode("utf-8") + "\n",
            encoding="utf-8")
        # the returned rows re-hash to the returned hash — they were bound at
        # the read; the on-disk mutation cannot reach them (no second read)...
        assert _rows_hash(rows) == served_hash
        # ...and a NEW serve refuses the tampered store.
        with pytest.raises(Refused, match="rows-hash mismatch"):
            _serve(tmp_path)

    def test_absent_hash_key_refuses_never_skips(self, tmp_path):
        # §6.3 MANDATORY-PRESENT — the objectives skip-hole closed: a manifest
        # OMITTING the rows-hash key refuses (the forged/partial-manifest arm).
        _write_store(tmp_path, _ROWS)
        m = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        del m["rows_hash"]
        (tmp_path / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
        with pytest.raises(Refused, match="MANDATORY-PRESENT"):
            _serve(tmp_path)

    @pytest.mark.parametrize("value", [None, "", 7])
    def test_null_empty_or_nonstring_hash_refuses(self, tmp_path, value):
        _write_store(tmp_path, _ROWS)
        m = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        m["rows_hash"] = value
        (tmp_path / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
        with pytest.raises(Refused, match="MANDATORY-PRESENT"):
            _serve(tmp_path)

    def test_manifest_unreadable_or_nondict_refuses(self, tmp_path):
        _write_store(tmp_path, _ROWS)
        (tmp_path / "manifest.json").unlink()
        with pytest.raises(Refused, match="unreadable"):
            _serve(tmp_path)
        (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(Refused, match="unreadable"):
            _serve(tmp_path)
        (tmp_path / "manifest.json").write_text("[1, 2]", encoding="utf-8")
        with pytest.raises(Refused, match="MANDATORY-PRESENT"):
            _serve(tmp_path)

    def test_malformed_store_refuses(self, tmp_path):
        _write_store(tmp_path, _ROWS)
        with (tmp_path / "store.jsonl").open("a", encoding="utf-8") as fh:
            fh.write("{truncated\n")
        with pytest.raises(Refused, match="unreadable/malformed"):
            _serve(tmp_path)

    def test_row_shape_breaking_the_domain_hash_refuses(self, tmp_path):
        # a KeyError/TypeError inside the domain's rows_hash is a malformed
        # store, wrapped into the refusal — never a traceback past the caller.
        _write_store(tmp_path, _ROWS)

        def keyed_hash(rows):
            return kernel.chained_rows_hash(
                rows, algebra=kernel.ALGEBRA_SHA256_CHAIN, seed=b"s",
                order_key=lambda r: r["missing_key"])

        with pytest.raises(Refused, match="unreadable/malformed"):
            kernel.verified_single_read(
                tmp_path, store_filename="store.jsonl",
                manifest_filename="manifest.json", store_hash_key="rows_hash",
                rows_hash=keyed_hash, refuse=Refused)

    def test_extra_limbs_run_in_order_after_the_hash_binding(self, tmp_path):
        _write_store(tmp_path, _ROWS)
        ran: list[str] = []

        def limb_pass(manifest, rows):
            ran.append("pass")
            return None

        def limb_refuse(manifest, rows):
            ran.append("refuse")
            return "counterfactual manifest — domain limb refuses"

        served_hash, _, _ = _serve(tmp_path, extra_limbs=(limb_pass,))
        assert ran == ["pass"] and served_hash
        ran.clear()
        with pytest.raises(Refused, match="counterfactual manifest"):
            _serve(tmp_path, extra_limbs=(limb_pass, limb_refuse))
        assert ran == ["pass", "refuse"]
        # limbs NEVER run when the hash binding already refused (order law).
        ran.clear()
        m = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        m["rows_hash"] = "0" * 64
        (tmp_path / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
        with pytest.raises(Refused, match="rows-hash mismatch"):
            _serve(tmp_path, extra_limbs=(limb_pass,))
        assert ran == []


# ===========================================================================
# (g) the canonical-cutoff validator — ONE definition, mirrored by value
# ===========================================================================
class TestCanonicalCutoff:
    def test_pattern_equals_both_shipped_replicas_by_value(self):
        # text-scan (no import): the EXACT pattern literal must appear in both
        # shipped sources — the kernel is the extraction of those replicas.
        for rel in ("framework/cortex/query.py", "framework/objectives/graph.py"):
            source = (_REPO / rel).read_text(encoding="utf-8")
            assert kernel.CANONICAL_CUTOFF_PATTERN in source, rel

    @pytest.mark.parametrize("good", ["2026-07-20T00:00:00Z", "1999-01-31T23:59:59Z"])
    def test_accepts_canonical(self, good):
        assert kernel.is_canonical_cutoff(good)
        assert kernel.require_canonical_cutoff(good, refuse=Refused) == good

    @pytest.mark.parametrize("bad", [
        "2026-07-20T00:00:00+00:00",      # legal ISO, non-canonical offset
        "2026-07-20T00:00:00.123Z",       # fractional seconds
        "2026-07-20 00:00:00Z",           # space separator
        "garbage", "", None, 20260720,
    ])
    def test_rejects_noncanonical_via_the_domain_factory(self, bad):
        assert not kernel.is_canonical_cutoff(bad)
        with pytest.raises(Refused, match="non-canonical cutoff"):
            kernel.require_canonical_cutoff(bad, refuse=Refused)


# ===========================================================================
# the kernel's own boundary — import-inert root, stdlib-only closure (§8.3/§8.4)
# ===========================================================================
class TestKernelBoundary:
    _FORBIDDEN_NS = ("framework.authority", "framework.acting",
                     "framework.frontdoor", "framework.fidelity",
                     "framework.missions", "framework.ovi")

    def _loaded_after(self, module: str) -> list[str]:
        code = ("import sys, json\n"
                f"import {module}\n"
                "print(json.dumps(sorted(m for m in sys.modules"
                " if m == 'framework' or m.startswith('framework.'))))\n")
        r = subprocess.run([sys.executable, "-c", code], cwd=str(_REPO),
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)

    def test_package_root_is_import_inert(self):
        assert self._loaded_after("framework.projection") == [
            "framework", "framework.projection"]

    def test_kernel_closure_is_stdlib_plus_self_only(self):
        loaded = self._loaded_after("framework.projection.kernel")
        assert loaded == ["framework", "framework.projection",
                          "framework.projection.kernel"]
        # the exact armed-closure assertion (test_cog4_scheduler_ast_pin's
        # retirement condition runs this over the real tree): nothing from the
        # action/authority/fidelity planes is reachable.
        assert [m for m in loaded
                if any(m == f or m.startswith(f + ".")
                       for f in self._FORBIDDEN_NS)] == []

    def test_static_ast_every_import_is_stdlib(self):
        tree_dir = _REPO / "framework" / "projection"
        stdlib = frozenset(sys.stdlib_module_names)
        for path in sorted(tree_dir.rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name.split(".")[0] in stdlib, (
                            path.name, alias.name)
                elif isinstance(node, ast.ImportFrom):
                    assert node.level == 0, (path.name, "relative import")
                    assert node.module is not None
                    assert node.module.split(".")[0] in stdlib, (
                        path.name, node.module)
