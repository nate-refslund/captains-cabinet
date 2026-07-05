"""AX-4 — deployment-target attestation backends (axes spec 2026-07-05 §3).

`is_locked` dispatches on the deployment target: macbook/mac_mini ⇒ `schg`
(the pre-axes st_flags check, byte-for-byte), docker ⇒ `ro_mount` (host-side
read-only bind mount, probed in-container), UNKNOWN target ⇒ schg semantics
(fail-closed). The target resolves explicit arg → the deployment_target the
file itself declares → environment inference (/.dockerenv). ro_mount is
three fail-closed layers — symlink/realpath containment, an
O_NOFOLLOW|O_NONBLOCK open-append probe expecting EROFS/EACCES, and a
REQUIRED ro entry in /proc/mounts — with ANY ambiguity ⇒ not attested ⇒
guardian (a same-uid chmod-444 file must never self-attest).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.authority import posture as P

LOCKED = lambda p: True  # noqa: E731 — the injected attestation stub

# The EACCES leg of the open-append probe relies on the owner LACKING the
# write bit — root bypasses DAC, so those tests are meaningless under euid 0.
not_root = pytest.mark.skipif(os.geteuid() == 0, reason="chmod 444 cannot refuse root")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for var in ("CABINET_POSTURE", "CABINET_NEEDS_WIRED", "CABINET_ID",
                "CABINET_ROOT", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    # Pin inference off this machine's real topology: no docker sentinel.
    monkeypatch.setattr(P, "_DOCKERENV", tmp_path / "no-dockerenv")


def write_posture(root: Path, text: str | None = None, **overrides) -> Path:
    cfg = {
        "version": 1,
        "status": "ruled",
        "ruled_at": "2026-07-05T00:00:00Z",
        "basis": "test ruling",
        "deployment": "main",
        "flavor": "org",
        "posture": "sovereign",
    }
    cfg.update(overrides)
    # Path built from the kernel's own resolver (layer-separation gate:
    # no literal instance token here; test_posture.py pins the location).
    p = P.posture_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text if text is not None else yaml.safe_dump(cfg))
    return p


def write_mounts(tmp_path: Path, monkeypatch, text: str) -> None:
    fake = tmp_path / "proc-mounts"
    fake.write_text(text)
    monkeypatch.setattr(P, "_PROC_MOUNTS", fake)


def readonly(path: Path) -> Path:
    path.chmod(0o444)  # owner without the write bit ⇒ open(O_WRONLY) EACCES
    return path


def real(path: Path) -> str:
    # macOS tmp dirs live behind the /var → /private/var symlink; the probe
    # (and therefore the fake mount table) works on the REAL path.
    return os.path.realpath(str(path))


# ---------------------------------------------------------------------------
# Dispatch — target → backend, as data
# ---------------------------------------------------------------------------

def test_backend_map_covers_every_target_and_only_known_backends():
    assert set(P.ATTESTATION_BACKEND_BY_TARGET) == set(P.DEPLOYMENT_TARGETS)
    assert P.ATTESTATION_BACKEND_BY_TARGET["macbook"] == "schg"
    assert P.ATTESTATION_BACKEND_BY_TARGET["mac_mini"] == "schg"
    assert P.ATTESTATION_BACKEND_BY_TARGET["docker"] == "ro_mount"
    assert set(P._BACKEND_FNS) == set(P.ATTESTATION_BACKEND_BY_TARGET.values())


def test_explicit_target_selects_backend(tmp_path, monkeypatch):
    f = tmp_path / "f.yml"
    f.write_text("x: 1")
    monkeypatch.setitem(P._BACKEND_FNS, "schg", lambda p: False)
    monkeypatch.setitem(P._BACKEND_FNS, "ro_mount", lambda p: True)
    assert P.is_locked(f, "docker") is True
    assert P.is_locked(f, "macbook") is False
    assert P.is_locked(f, "mac_mini") is False


def test_unknown_target_gets_schg_semantics(tmp_path, monkeypatch):
    f = tmp_path / "f.yml"
    f.write_text("x: 1")
    # Real backends: an unlocked plain file attests False either way…
    assert P.is_locked(f, "quantum") is False
    # …and the dispatch proof: an unknown target lands on the schg entry.
    monkeypatch.setitem(P._BACKEND_FNS, "schg", lambda p: True)
    monkeypatch.setitem(P._BACKEND_FNS, "ro_mount", lambda p: False)
    assert P.is_locked(f, "quantum") is True


def test_declared_target_drives_one_arg_dispatch(tmp_path, monkeypatch):
    """The ruling names the backend that attests it — a one-arg is_locked on
    a file declaring `deployment_target: docker` probes ro_mount."""
    p = write_posture(tmp_path, deployment_target="docker")
    monkeypatch.setitem(P._BACKEND_FNS, "schg", lambda q: False)
    monkeypatch.setitem(P._BACKEND_FNS, "ro_mount", lambda q: True)
    assert P.is_locked(p) is True
    # No declared target (and no docker sentinel) ⇒ inferred macbook ⇒ schg.
    p2 = write_posture(tmp_path)
    assert P.is_locked(p2) is False
    # A declared-but-INVALID target never selects a backend ⇒ inference.
    p3 = write_posture(tmp_path, text="deployment_target: cloud\n")
    assert P.is_locked(p3) is False


def test_env_inference_picks_ro_mount_in_a_container(tmp_path, monkeypatch):
    sentinel = tmp_path / "dockerenv"
    sentinel.write_text("")
    monkeypatch.setattr(P, "_DOCKERENV", sentinel)
    f = tmp_path / "not-yaml.bin"
    f.write_bytes(b"\x00\x01")  # no declarable target ⇒ inference
    seen = []
    monkeypatch.setitem(
        P._BACKEND_FNS, "ro_mount", lambda q: seen.append(q) or True)
    assert P.is_locked(f) is True
    assert seen == [f]


def test_one_arg_signature_stays_backcompat(tmp_path):
    # The pre-axes contract everywhere no deployment_target appears: plain
    # positional single-argument call, schg semantics on this platform.
    p = write_posture(tmp_path)
    assert P.is_locked(p) is False  # tmp file carries no schg flag


# ---------------------------------------------------------------------------
# ro_mount backend — fail-closed truth table
# ---------------------------------------------------------------------------

def test_ro_mount_writable_file_never_attests(tmp_path, monkeypatch):
    f = tmp_path / "f.yml"
    f.write_text("x: 1")
    # Even a lying ro mount table cannot attest a file the probe can OPEN.
    write_mounts(tmp_path, monkeypatch,
                 f"tmpfs {real(tmp_path)} tmpfs ro,relatime 0 0\n")
    assert P.is_locked(f, "docker") is False


def test_ro_mount_missing_file_is_false(tmp_path):
    assert P.is_locked(tmp_path / "nope.yml", "docker") is False


@not_root
def test_ro_mount_symlink_is_never_attestable(tmp_path, monkeypatch):
    target = tmp_path / "real.yml"
    target.write_text("x: 1")
    readonly(target)
    link = tmp_path / "link.yml"
    link.symlink_to(target)
    write_mounts(tmp_path, monkeypatch,
                 f"tmpfs {real(tmp_path)} tmpfs ro,relatime 0 0\n")
    assert P.is_locked(link, "docker") is False
    assert P.is_locked(target, "docker") is True  # the real file itself does


def test_ro_mount_non_regular_file_is_false(tmp_path, monkeypatch):
    write_mounts(tmp_path, monkeypatch,
                 f"tmpfs {real(tmp_path)} tmpfs ro,relatime 0 0\n")
    assert P.is_locked(tmp_path, "docker") is False  # a directory
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    assert P.is_locked(fifo, "docker") is False  # never blocks, never attests


@not_root
def test_ro_mount_probe_refusal_without_proc_mounts_is_ambiguity(
        tmp_path, monkeypatch):
    """EACCES alone must NOT attest — a same-uid chmod-444 file off-Linux
    (no /proc/mounts) is exactly the self-attest forge this refuses."""
    f = readonly(write_posture(tmp_path, deployment_target="docker"))
    monkeypatch.setattr(P, "_PROC_MOUNTS", tmp_path / "no-proc-mounts")
    assert P.is_locked(f, "docker") is False


@not_root
def test_ro_mount_attests_on_probe_refusal_plus_ro_mount(tmp_path, monkeypatch):
    f = readonly(write_posture(tmp_path, deployment_target="docker"))
    write_mounts(tmp_path, monkeypatch,
                 "overlay / overlay rw,relatime 0 0\n"
                 f"tmpfs {real(tmp_path)} tmpfs ro,nosuid,relatime 0 0\n")
    assert P.is_locked(f, "docker") is True


@not_root
def test_ro_mount_rw_mount_refuses_chmod_forgery(tmp_path, monkeypatch):
    f = readonly(write_posture(tmp_path, deployment_target="docker"))
    write_mounts(tmp_path, monkeypatch,
                 f"tmpfs {real(tmp_path)} tmpfs rw,relatime 0 0\n")
    assert P.is_locked(f, "docker") is False


@not_root
def test_ro_mount_longest_prefix_mount_wins(tmp_path, monkeypatch):
    f = readonly(write_posture(tmp_path, deployment_target="docker"))
    # Deeper rw mount beats an ro root ⇒ refuse…
    write_mounts(tmp_path, monkeypatch,
                 "overlay / overlay ro,relatime 0 0\n"
                 f"tmpfs {real(tmp_path)} tmpfs rw,relatime 0 0\n")
    assert P.is_locked(f, "docker") is False
    # …and a deeper ro mount beats an rw root ⇒ attest.
    write_mounts(tmp_path, monkeypatch,
                 "overlay / overlay rw,relatime 0 0\n"
                 f"tmpfs {real(tmp_path)} tmpfs ro,relatime 0 0\n")
    assert P.is_locked(f, "docker") is True


@not_root
def test_ro_mount_single_file_bind_mountpoint(tmp_path, monkeypatch):
    """compose `-v host/posture.yml:container/posture.yml:ro` lists the FILE
    itself as the mountpoint — the exact-match arm must accept it."""
    f = readonly(write_posture(tmp_path, deployment_target="docker"))
    write_mounts(tmp_path, monkeypatch,
                 "overlay / overlay rw,relatime 0 0\n"
                 f"/dev/sda1 {real(f)} ext4 ro,relatime 0 0\n")
    assert P.is_locked(f, "docker") is True


@not_root
def test_ro_mount_octal_escaped_mountpoint(tmp_path, monkeypatch):
    d = tmp_path / "mnt point"  # kernel writes this as mnt\040point
    d.mkdir()
    f = d / "f.yml"
    f.write_text("x: 1")
    readonly(f)
    escaped = real(d).replace(" ", "\\040")
    write_mounts(tmp_path, monkeypatch,
                 f"tmpfs {escaped} tmpfs ro,relatime 0 0\n")
    assert P.is_locked(f, "docker") is True


@not_root
def test_ro_mount_prefix_is_component_wise(tmp_path, monkeypatch):
    """An ro mount at /x must not contain /x-sibling (string-prefix trap)."""
    sib = tmp_path / "cfg-sibling"
    sib.mkdir()
    f = sib / "f.yml"
    f.write_text("x: 1")
    readonly(f)
    write_mounts(tmp_path, monkeypatch,
                 f"tmpfs {real(tmp_path)}/cfg tmpfs ro,relatime 0 0\n")
    assert P.is_locked(f, "docker") is False  # only "/" would match — absent


# ---------------------------------------------------------------------------
# End-to-end — resolve_posture through the default attestation
# ---------------------------------------------------------------------------

def test_ruling_declared_target_selects_backend_in_resolve(
        tmp_path, monkeypatch):
    write_posture(tmp_path, deployment_target="docker")
    monkeypatch.setitem(P._BACKEND_FNS, "ro_mount", lambda q: True)
    monkeypatch.setitem(P._BACKEND_FNS, "schg", lambda q: False)
    assert P.resolve_posture(root=tmp_path) == "sovereign"
    # Same ruling WITHOUT the docker declaration ⇒ schg backend ⇒ guardian.
    write_posture(tmp_path)
    assert P.resolve_posture(root=tmp_path) == "guardian"


@not_root
def test_docker_deployment_attests_sovereign_via_real_ro_mount(
        tmp_path, monkeypatch):
    """The whole point of AX-4: a docker deployment reaches sovereign with no
    schg anywhere — the host's ro bind mount IS the Captain's signature."""
    f = readonly(write_posture(tmp_path, deployment_target="docker"))
    write_mounts(tmp_path, monkeypatch,
                 "overlay / overlay rw,relatime 0 0\n"
                 f"tmpfs {real(tmp_path)} tmpfs ro,relatime 0 0\n")
    assert P.resolve_posture(root=tmp_path) == "sovereign"
    assert P.load_posture_config(tmp_path) is not None
    assert P.max_auto_steps("sovereign", tmp_path) == 5


@not_root
def test_docker_rw_mount_fails_closed_to_guardian(tmp_path, monkeypatch):
    f = readonly(write_posture(tmp_path, deployment_target="docker"))
    write_mounts(tmp_path, monkeypatch,
                 f"tmpfs {real(tmp_path)} tmpfs rw,relatime 0 0\n")
    assert P.resolve_posture(root=tmp_path) == "guardian"
    assert P.load_posture_config(tmp_path) is None


@not_root
def test_macbook_declared_ruling_never_attests_via_ro_mount(
        tmp_path, monkeypatch):
    """Deployment-matched attestation: a ruling declaring a schg target
    cannot borrow the container's ro mount (and vice versa)."""
    f = readonly(write_posture(tmp_path, deployment_target="macbook"))
    write_mounts(tmp_path, monkeypatch,
                 f"tmpfs {real(tmp_path)} tmpfs ro,relatime 0 0\n")
    # Even with the docker sentinel present, the DECLARED target wins.
    sentinel = tmp_path / "dockerenv"
    sentinel.write_text("")
    monkeypatch.setattr(P, "_DOCKERENV", sentinel)
    assert P.resolve_posture(root=tmp_path) == "guardian"


def test_guardian_parity_without_target_config(tmp_path):
    """No deployment_target anywhere ⇒ the pre-axes truth table verbatim:
    unlocked ⇒ guardian, injected lock ⇒ sovereign, schg fn dispatched."""
    write_posture(tmp_path)
    assert P.resolve_posture(root=tmp_path) == "guardian"
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "sovereign"
    assert P._BACKEND_FNS["schg"] is P._is_locked_schg


def test_schg_backend_is_non_darwin_false(tmp_path, monkeypatch):
    p = write_posture(tmp_path, deployment_target="mac_mini")
    monkeypatch.setattr(P.sys, "platform", "linux")
    assert P.is_locked(p) is False
    assert P.is_locked(p, "mac_mini") is False
