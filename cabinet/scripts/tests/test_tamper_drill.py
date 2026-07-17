"""Phase-4 tamper game-day drill + judging-frozen marker tests.

Pins, per the batch invariants:

* The freeze marker is FAIL-CLOSED: any presence (valid JSON, garbage,
  symlink, directory) reads FROZEN; only provable absence reads unfrozen;
  first-freeze-wins; unfreeze is Captain-token-gated via the EXISTING
  evidence-CLI capability mechanism (no second auth scheme).
* The drill operates ONLY on a scratch store it created (there is no
  ``--store`` option to point it anywhere), proves the local verifier is
  blind to a whole-store restore-to-earlier, proves the production
  ``evidence-anchor.py --check`` path catches it (exit 2, ``first_run``
  False — the vacuous-pass trap), freezes judging at a scratch pseudo-root
  in test mode, and emits a would-page line instead of a real Chair page.
* Byte-stability: ``--check`` leaves a store tree byte-identical
  (watermark sidecar included — check never runs the verifier), and the
  drill never touches stores named by environment variables.

Everything runs against scratch stores under tmp_path; the repo-root
conftest already fences all CABINET_* env vars to a session sandbox.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework import evidence_freeze as ef  # noqa: E402
from framework.evidence import __main__ as evidence_cli  # noqa: E402
from framework.evidence import verify_store  # noqa: E402
from framework.evidence.recorder import EvidenceError, EvidenceRecorder  # noqa: E402
from framework.evidence_anchor import collect_anchor  # noqa: E402

_SCRIPT = _REPO_ROOT / "cabinet" / "scripts" / "evidence-tamper-drill.py"
_ANCHOR_CLI = _REPO_ROOT / "cabinet" / "scripts" / "evidence-anchor.py"
_ACTOR = {"kind": "system", "id": "drill-test"}
_COMPONENT = {"name": "drill-test", "version": "1"}


def _seed_store(store: Path) -> EvidenceRecorder:
    recorder = EvidenceRecorder(store)
    for trial_id in ("seed-alpha-001", "seed-beta-001"):
        context = recorder.trace(trial_id, surface="system")
        recorder.append(
            context, phase="intent", status="started",
            actor=_ACTOR, component=_COMPONENT,
            detail={"action": "seed"}, links=[],
        )
        recorder.append(
            context, phase="execution", status="succeeded",
            actor=_ACTOR, component=_COMPONENT,
            detail={"action": "seed"}, links=[],
        )
    return recorder


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8") + b"\0")
        if path.is_symlink():
            digest.update(b"symlink\0" + os.readlink(path).encode("utf-8"))
        elif path.is_file():
            digest.update(b"file\0" + path.read_bytes())
        elif path.is_dir():
            digest.update(b"dir\0")
    return digest.hexdigest()


def _mint_token(store: Path, path: Path) -> Path:
    key = (store / ".signing-key").read_bytes()
    token = hmac.new(
        key, evidence_cli.CAPTAIN_TOKEN_PURPOSE.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    path.write_text(token + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _thaw(root: Path) -> None:
    """Test cleanup only: lift the scratch marker's immutable flag + remove."""
    marker = ef.marker_path(root)
    ef._lift_immutable(marker)
    try:
        marker.unlink()
    except OSError:
        pass


def _run(argv: list[str], env_extra: dict[str, str] | None = None,
         timeout: int = 600) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, *argv],
        capture_output=True, text=True, timeout=timeout,
        cwd=str(_REPO_ROOT), env=env,
    )


# ---------------------------------------------------------------------------
# Marker semantics
# ---------------------------------------------------------------------------

def test_marker_fail_closed_table(tmp_path):
    # Provable absence: unfrozen.
    assert ef.is_frozen(tmp_path / "absent-root") is False

    # A real marker: frozen.
    frozen_root = tmp_path / "frozen"
    ef.freeze(frozen_root, "test freeze", finding_kinds=["trial_rollback"])
    assert ef.is_frozen(frozen_root) is True
    _thaw(frozen_root)

    # Garbage bytes: still frozen (presence is presence).
    garbage_root = tmp_path / "garbage"
    marker = ef.marker_path(garbage_root)
    marker.parent.mkdir(parents=True)
    marker.write_bytes(b"\x00not json at all")
    assert ef.is_frozen(garbage_root) is True

    # A dangling symlink: frozen (corrupting the marker never unfreezes).
    symlink_root = tmp_path / "symlinked"
    marker = ef.marker_path(symlink_root)
    marker.parent.mkdir(parents=True)
    os.symlink("does-not-exist-anywhere", marker)
    assert ef.is_frozen(symlink_root) is True

    # A directory at the marker path: frozen.
    dir_root = tmp_path / "dir-marker"
    ef.marker_path(dir_root).mkdir(parents=True)
    assert ef.is_frozen(dir_root) is True

    # A parent path component replaced by a FILE (ENOTDIR): still FROZEN.
    # Swapping the state dir for a file would otherwise be an unfreeze
    # primitive that bypasses the marker's own immutable flag.
    notdir_root = tmp_path / "notdir"
    (notdir_root / "instance").mkdir(parents=True)
    (notdir_root / "instance" / "state").write_text("a file, not a dir")
    assert ef.is_frozen(notdir_root) is True

    # A genuinely absent parent chain is ENOENT: provable absence, unfrozen
    # (a fresh deployment must not read frozen).
    assert ef.is_frozen(tmp_path / "never" / "created" / "root") is False


def test_freeze_atomic_first_wins(tmp_path):
    root = tmp_path / "root"
    path = ef.freeze(
        root, "first reason", finding_kinds=["b-kind", "a-kind", "a-kind"],
        set_by="tester", drill=True,
    )
    try:
        assert path == ef.marker_path(root)
        mode = stat.S_IMODE(os.lstat(path).st_mode)
        assert mode == 0o600
        content = json.loads(path.read_text(encoding="utf-8"))
        assert content["schema"] == ef.FREEZE_SCHEMA
        assert content["reason"] == "first reason"
        assert content["finding_kinds"] == ["a-kind", "b-kind"]
        assert content["drill"] is True
        assert content["frozen_at"].endswith("Z")

        # First-freeze-wins: a second freeze never overwrites.
        again = ef.freeze(root, "second reason", set_by="someone-else")
        assert again == path
        assert json.loads(path.read_text())["reason"] == "first reason"

        # Atomicity: no tmp droppings next to the marker.
        leftovers = [p.name for p in path.parent.iterdir() if ".tmp." in p.name]
        assert leftovers == []
    finally:
        _thaw(root)


def test_status_reports(tmp_path):
    root = tmp_path / "root"
    empty = ef.status(root)
    assert empty["frozen"] is False and empty["content"] is None

    ef.freeze(root, "why", finding_kinds=["k"], set_by="t")
    try:
        info = ef.status(root)
        assert info["frozen"] is True
        assert info["error"] is None
        assert info["content"]["reason"] == "why"
    finally:
        _thaw(root)

    garbage_root = tmp_path / "garbage"
    marker = ef.marker_path(garbage_root)
    marker.parent.mkdir(parents=True)
    marker.write_text("not json")
    info = ef.status(garbage_root)
    assert info["frozen"] is True
    assert info["content"] is None
    assert info["error"] is not None


# ---------------------------------------------------------------------------
# Captain-token unfreeze (reuses the evidence-CLI capability gate)
# ---------------------------------------------------------------------------

def test_captain_clear_token_gate(tmp_path, monkeypatch):
    monkeypatch.delenv("CABINET_CAPTAIN_TOKEN_FILE", raising=False)
    store = tmp_path / "store"
    EvidenceRecorder(store)  # mints the signing key
    root = tmp_path / "root"
    ef.freeze(root, "gate test")

    # No token presented: typed refusal, marker untouched.
    with pytest.raises(EvidenceError) as excinfo:
        ef.captain_clear(root, store)
    assert excinfo.value.code == "captain_capability_required"
    assert ef.is_frozen(root) is True

    # Wrong token: typed refusal, marker untouched.
    wrong = tmp_path / "wrong.token"
    wrong.write_text("0" * 64 + "\n", encoding="utf-8")
    wrong.chmod(0o600)
    with pytest.raises(EvidenceError) as excinfo:
        ef.captain_clear(root, store, captain_token_file=wrong)
    assert excinfo.value.code == "captain_capability_invalid"
    assert ef.is_frozen(root) is True

    # The store-derived token clears it.
    token = _mint_token(store, tmp_path / "captain.token")
    result = ef.captain_clear(root, store, captain_token_file=token)
    assert result["cleared"] is True
    assert ef.is_frozen(root) is False

    # Clearing when not frozen is a no-op, honestly reported.
    result = ef.captain_clear(root, store, captain_token_file=token)
    assert result == {
        "ok": True, "cleared": False,
        "path": str(ef.marker_path(root)), "note": "no freeze marker present",
    }

    # A missing store dir refuses (the recorder must never side-effect-create
    # a store during an unfreeze) and points at the manual runbook path.
    root2 = tmp_path / "root2"
    ef.freeze(root2, "no store")
    try:
        with pytest.raises(ef.FreezeError) as excinfo:
            ef.captain_clear(root2, tmp_path / "absent-store",
                             captain_token_file=token)
        assert excinfo.value.code == "captain_clear_no_store"
        assert ef.is_frozen(root2) is True
        assert not (tmp_path / "absent-store").exists()
    finally:
        _thaw(root2)


def test_unfreeze_cli_verb(tmp_path):
    store = tmp_path / "store"
    EvidenceRecorder(store)
    token = _mint_token(store, tmp_path / "captain.token")
    root = tmp_path / "root"

    # Wrong token via the CLI: exit 3, marker stays.
    ef.freeze(root, "cli test")
    wrong = tmp_path / "wrong.token"
    wrong.write_text("f" * 64 + "\n", encoding="utf-8")
    wrong.chmod(0o600)
    proc = _run([str(_SCRIPT), "unfreeze", "--root", str(root),
                 "--store", str(store), "--captain-token-file", str(wrong)])
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["code"] == "captain_capability_invalid"
    assert ef.is_frozen(root) is True

    # Right token via the CLI: exit 0, marker cleared.
    proc = _run([str(_SCRIPT), "unfreeze", "--root", str(root),
                 "--store", str(store), "--captain-token-file", str(token)])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["cleared"] is True
    assert ef.is_frozen(root) is False

    # freeze-status verb round-trip.
    proc = _run([str(_SCRIPT), "freeze-status", "--root", str(root)])
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["frozen"] is False


# ---------------------------------------------------------------------------
# Drill harness
# ---------------------------------------------------------------------------

def test_drill_run_refuses_store_argument():
    proc = _run([str(_SCRIPT), "run", "--store", "/definitely/not/allowed"])
    assert proc.returncode != 0
    assert "unrecognized arguments" in proc.stderr


def test_live_mode_requires_confirm(tmp_path):
    out_root = tmp_path / "out"
    proc = _run([str(_SCRIPT), "run", "--mode", "live",
                 "--out-root", str(out_root)])
    assert proc.returncode == 64
    assert "--confirm-live" in proc.stderr
    # Refused BEFORE any side effect: no report surfaces, no marker.
    assert not out_root.exists()
    assert not ef.is_frozen(_REPO_ROOT)


def test_live_mode_refuses_over_existing_freeze(tmp_path):
    """A live drill over a REAL freeze would muddy triage: the guard runs
    before any side effect (no scratch, no page, no report surfaces).
    Freezing THIS clone's root is safe — instance/state/ is runtime-only."""
    ef.freeze(_REPO_ROOT, "test: pre-existing real freeze", set_by="pytest")
    try:
        out_root = tmp_path / "out"
        proc = _run([str(_SCRIPT), "run", "--mode", "live", "--confirm-live",
                     "--out-root", str(out_root)])
        assert proc.returncode == 64
        assert "ALREADY frozen" in proc.stderr
        assert not out_root.exists()
        # First-freeze-wins held: the original marker survived untouched.
        content = ef.status(_REPO_ROOT)["content"]
        assert content is not None and content["set_by"] == "pytest"
    finally:
        _thaw(_REPO_ROOT)
    assert not ef.is_frozen(_REPO_ROOT)


def test_anchor_check_is_byte_stable(tmp_path):
    store = tmp_path / "store"
    _seed_store(store)
    assert verify_store(store)["ok"] is True  # watermarks advance NOW
    record = collect_anchor(store)
    anchors = tmp_path / "anchors.jsonl"
    anchors.write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    before = _tree_digest(store)
    proc = _run([str(_ANCHOR_CLI), "--store", str(store),
                 "--check", str(anchors)])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["ok"] is True and result["first_run"] is False
    # --check never verifies and never writes: byte-identical, sidecar included.
    assert _tree_digest(store) == before


def test_drill_end_to_end_test_mode(tmp_path):
    out_root = tmp_path / "out"
    proc = _run([str(_SCRIPT), "run", "--out-root", str(out_root)])
    assert proc.returncode == 0, proc.stdout + proc.stderr

    rows_file = out_root / "cabinet" / "logs" / "tamper-drills.jsonl"
    rows = [json.loads(line) for line in
            rows_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    row = rows[0]

    assert row["schema"] == "cabinet.tamper-drill/v1"
    assert row["mode"] == "test"
    assert row["caught"] is True
    assert row["first_run"] is False  # vacuous-pass trap guarded
    assert {"trial_rollback", "trial_missing", "watermark_regression"} <= set(
        row["finding_kinds"]
    )
    assert row["verifier_blind"] is True  # local verify green on restored copy
    assert row["events_after_restore"] < row["events_at_anchor"]
    assert row["paged"] == "would-page"
    assert row["gaps"] == []
    assert "necessary, not sufficient" in row["honest_claim"]

    # TEST mode paged nothing and froze only a scratch pseudo-root.
    assert "WOULD PAGE Chair (" in proc.stdout
    assert row["freeze_scope"] == "scratch"
    assert row["froze"].startswith(row["scratch"])
    assert not ef.is_frozen(_REPO_ROOT)
    assert not (_REPO_ROOT / "instance" / "state"
                / "evidence-judging-freeze.json").exists()

    # Zero trace: the scratch dir (store, snapshot, anchors, marker) is gone.
    assert not Path(row["scratch"]).exists()

    # The outcome doc renders with the mandatory honest-claim text.
    doc = Path(row["outcome_doc"])
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "necessary, not sufficient" in text
    assert "## Response steps taken" in text
    assert "## Gaps found" in text
    assert str(row["time_to_catch_s"]) in text


def test_drill_ignores_env_named_stores(tmp_path):
    """The harness must never resolve a store from the environment: a decoy
    store named by every evidence-related env var stays byte-identical."""
    decoy = tmp_path / "decoy-store"
    _seed_store(decoy)
    assert verify_store(decoy)["ok"] is True  # settle watermarks first
    before = _tree_digest(decoy)

    out_root = tmp_path / "out"
    proc = _run(
        [str(_SCRIPT), "run", "--out-root", str(out_root)],
        env_extra={
            "CABINET_EVIDENCE_DIR": str(decoy),
            "CABINET_ACTION_EVIDENCE_STORE": str(decoy),
            "CABINET_EVIDENCE_MIRROR_STORE": str(decoy),
        },
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _tree_digest(decoy) == before
