"""R-8 migration gate: byte-identical evidence stream across the helper migration.

The Phase-1 design of record requires ``journey.py`` migrated onto the shared
recording helper (``framework.evidence.lifecycle``) with a BYTE-IDENTICAL
event stream — not merely "dogfood green".  This harness proves it by running
the SAME scripted action sequence against

  (a) the vendored PRE-migration journey — a verbatim snapshot of
      ``framework/onboarding/journey.py`` at commit ``eef927f4`` (the tree the
      helper was extracted from), and
  (b) the vendored POST-migration journey — the verbatim snapshot at commit
      ``4467476f``, the single commit that performed the migration,

both stored as inert test data and loaded from source at test time, with every
nondeterminism source pinned (uuid4, monotonic clock, the recorder's UTC clock,
the journey wall clock, provenance env vars, and a fixed test-only signing key),
on the SAME base path, and asserting the entire produced tree — evidence
``events.jsonl`` (hash chain + HMAC signatures), anchors, watermarks, control
file, purge receipts, and the onboarding plane — is byte-for-byte identical
after every step.

WHY BOTH SIDES ARE FROZEN (changed 2026-07-27, three-entry-modes unit). Arm (b)
used to be the LIVE module, which made a claim about a HISTORICAL commit
("4467476f changed no behaviour") depend on every future commit, and therefore
froze the onboarding product surface permanently: the first deliberate
behaviour change would red it, and the only ways out are to weaken the gate or
to abandon the change. The First Window's relevance ordering and coverage
accounting are exactly that change. Freezing both sides keeps the R-8 claim
byte-exact and TRUE FOREVER — it is a statement about two commits, and neither
of them moves again — while the LIVE module keeps its own arm below, asserting
the properties a frozen snapshot cannot: that today's journey still produces a
complete, hash-chained, signed, verifiable evidence stream across the same
scenario. Nothing was removed; the comparison was pointed at the two things it
was actually about.

The scenario deliberately covers the branches the migration touched: happy
path, idempotent duplicate replay, core refusal, unexpected error, malformed
caller ids (id unification), a tombstoned live trial healed by the PRE-FLIGHT
re-mint (ghost trial dir), a tombstoned live trial healed by the MID-RECORD
re-mint-once retry, verification, and the typed purge tail.

Hermetic: every mutable root is tmp_path; no network, subprocess, or Redis.
"""
from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from framework.evidence import EvidenceRecorder
from framework.evidence import recorder as recorder_module
from framework.evidence.verifier import verify_trial
from framework.onboarding import journey

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parents[2]
FIXTURES = REPO / "framework" / "onboarding" / "fixtures"
SNAPSHOT = TESTS / "data" / "premigration_journey_eef927f4.py.txt"
# sha256 of the verbatim pre-migration source (git show
# eef927f4:framework/onboarding/journey.py). Guards the fixture against
# accidental edits — a drifted snapshot would make this gate meaningless.
SNAPSHOT_SHA256 = "20e5802cc2a6f0c20de9af3ba6fcef83a29fabde9ac816d49af9428238a96276"
POST_SNAPSHOT = TESTS / "data" / "postmigration_journey_4467476f.py.txt"
# sha256 of the verbatim post-migration source (git show
# 4467476f:framework/onboarding/journey.py) — the commit whose message claims
# "zero behavior change" and the only commit to touch journey.py between the
# two pins. This gate is what turns that claim into a proof.
POST_SNAPSHOT_SHA256 = "9d7c75b3a3bb137374d40dd6f2ede306248674477f5300841f6b965428557ccd"
EVIDENCE_REL = "instance/evidence/v1"
STATE_REL = "instance/onboarding/v2/state.json"
# Fixed TEST-ONLY signing key so HMAC signatures are comparable across the
# two runs. Never key material for any real store.
TEST_SIGNING_KEY = bytes(range(32))


def _load_snapshot(path: Path, name: str):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _load_premigration():
    loader = importlib.machinery.SourceFileLoader(
        "_premigration_journey_eef927f4", str(SNAPSHOT)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class _FixedDatetime(datetime):
    """Pin the journey wall clock (used only when ``now=`` is omitted)."""

    @classmethod
    def now(cls, tz=None):  # noqa: D102 - datetime API
        return cls(2026, 7, 16, 12, 0, 0, tzinfo=tz)


class _Pins:
    """Deterministic counters for every nondeterminism seam, resettable per run.

    Byte-identity requires both runs to observe the SAME sequences, which also
    pins the two implementations to the SAME number and order of uuid/clock
    calls — a helper that minted an extra id or recomputed a duration would
    shift every later value and fail loudly.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._uuid = 0
        self._monotonic = 0
        self._utc = 0

    def install(self, monkeypatch, modules) -> None:
        def fake_uuid4():
            self._uuid += 1
            return uuid.UUID(int=self._uuid)

        def fake_monotonic_ns():
            self._monotonic += 1_000_000  # +1ms per observation
            return self._monotonic

        def fake_utc_now():
            self._utc += 1
            return f"2026-07-16T00:00:00.{self._utc:06d}Z"

        monkeypatch.setattr(uuid, "uuid4", fake_uuid4)
        monkeypatch.setattr(time, "monotonic_ns", fake_monotonic_ns)
        monkeypatch.setattr(recorder_module, "_utc_now", fake_utc_now)
        for module in modules:
            monkeypatch.setattr(module, "datetime", _FixedDatetime)
        for name in (
            "CABINET_BUILD_VERSION",
            "CABINET_GIT_COMMIT",
            "CABINET_EVIDENCE_DIR",
            "CABINET_ROOT",
        ):
            monkeypatch.delenv(name, raising=False)


def _seed_store(base: Path) -> None:
    store = base / EVIDENCE_REL
    store.mkdir(parents=True)
    fd = os.open(store / ".signing-key", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(TEST_SIGNING_KEY)


def _tree_bytes(base: Path) -> dict[str, bytes]:
    tree: dict[str, bytes] = {}
    for path in sorted(base.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        tree[path.relative_to(base).as_posix()] = path.read_bytes()
    return tree


def _canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=repr)


def _live_trial(base: Path) -> str:
    return str(json.loads((base / STATE_REL).read_text(encoding="utf-8"))["evidence_trial_id"])


def _run_scenario(mod, *, base: Path, source: Path, pins: _Pins) -> list[dict]:
    if base.exists():
        shutil.rmtree(base)
    _seed_store(base)
    pins.reset()

    steps: list[dict] = []
    chain: dict[str, dict] = {}

    def run(label: str, fn) -> None:
        try:
            value = fn()
            outcome = {"ok": True, "value": _canonical_json(value)}
            chain[label] = value
        except Exception as exc:  # captured for cross-run comparison
            outcome = {
                "ok": False,
                "error_type": type(exc).__name__,
                "error_code": getattr(exc, "code", None),
                "error_message": str(exc),
                "cause_code": getattr(exc.__cause__, "code", None),
            }
        steps.append({"label": label, "outcome": outcome, "tree": _tree_bytes(base)})

    propose_request = {
        "action": "propose_window",
        "action_id": "propose-1",
        "surface": "dashboard",
        "source": str(source),
        "purpose": "Find one release risk before it surprises the team.",
        "relationship_destination": "reversible",
    }
    run("propose", lambda: mod.act(dict(propose_request), base, now="2026-07-16T10:00:00Z"))
    run("duplicate-replay", lambda: mod.act(dict(propose_request), base, now="2026-07-16T10:00:01Z"))
    run(
        "unknown-action-refusal",
        lambda: mod.act(
            {"action": "reticulate_splines", "action_id": "bogus-1", "surface": "cli"},
            base,
            now="2026-07-16T10:00:02Z",
        ),
    )
    run(
        "ratify",
        lambda: mod.act(
            {
                "action": "ratify_charter",
                "action_id": "ratify-1",
                "surface": "telegram",
                "charter_hash": chain["propose"]["state"]["charter"]["hash"],
                "expected_revision": chain["propose"]["state"]["revision"],
            },
            base,
            now="2026-07-16T10:00:03Z",
        ),
    )
    run(
        "observe-transport",
        lambda: mod.observe(
            {
                "surface": "dashboard",
                "phase": "transport",
                "status": "succeeded",
                "trace_id": "trace-bytegate-1",
                "action_id": "observe-1",
                "correlation_id": "corr-bytegate-1",
                "detail": {"transport": "https", "retry_count": 2},
            },
            base,
        ),
    )

    def unexpected_error():
        original = mod._act_core

        def explode(*args, **kwargs):
            raise RuntimeError("synthetic instability")

        mod._act_core = explode
        try:
            return mod.act(
                {"action": "pause", "action_id": "boom-1", "surface": "world"},
                base,
                now="2026-07-16T10:00:04Z",
            )
        finally:
            mod._act_core = original

    run("unexpected-error", unexpected_error)
    run(
        "malformed-caller-ids",
        lambda: mod.act(
            {
                "action": "pause",
                "action_id": "!!!not an id!!!",
                "trace_id": "***bad***",
                "correlation_id": "also bad",
                "surface": "companion",
            },
            base,
            now="2026-07-16T10:00:05Z",
        ),
    )

    def tombstone(ghost: bool):
        trial = _live_trial(base)
        recorder = EvidenceRecorder(base / EVIDENCE_REL)
        receipt = recorder.purge_trial(trial, confirmation=f"PURGE {trial}", actor="captain")
        if ghost:
            # A raced re-created empty dir: forces the PRE-FLIGHT
            # recover_interrupted path to see the tombstone and re-mint.
            (base / EVIDENCE_REL / "trials" / trial).mkdir()
        return {"tombstoned": trial, "receipt": receipt}

    # Pre-flight re-mint: trial dir present but tombstoned.
    run("tombstone-live-trial-ghost", lambda: tombstone(ghost=True))
    run(
        "pause-after-preflight-remint",
        lambda: mod.act(
            {"action": "pause", "action_id": "pause-1", "surface": "dashboard"},
            base,
            now="2026-07-16T10:00:06Z",
        ),
    )
    # Mid-record re-mint: trial dir gone, first append hits trial_purged and
    # the re-mint-once retry swaps trials between two appends.
    run("tombstone-live-trial-midrecord", lambda: tombstone(ghost=False))
    run(
        "undo-after-midrecord-remint",
        lambda: mod.act(
            {"action": "undo", "action_id": "undo-1", "surface": "telegram"},
            base,
            now="2026-07-16T10:00:07Z",
        ),
    )

    def verify_live():
        # ``undo`` restores a historical state snapshot wholesale (including
        # its then-live evidence_trial_id, since purged), so verify the trial
        # the undo's events actually landed on — the mid-record re-mint.
        trial = chain["undo-after-midrecord-remint"]["evidence"]["trial_id"]
        report = verify_trial(base / EVIDENCE_REL, trial)
        return {"trial": trial, "ok": report["ok"], "errors": report.get("errors")}

    run("verify-live-trial", verify_live)
    run(
        "purge",
        lambda: mod.act(
            {
                "action": "purge",
                "action_id": "purge-1",
                "surface": "dashboard",
                "confirmation": "PURGE",
            },
            base,
            now="2026-07-16T10:00:08Z",
        ),
    )
    run(
        "act-after-purge",
        lambda: mod.act(
            {"action": "pause", "action_id": "pause-2", "surface": "cli"},
            base,
            now="2026-07-16T10:00:09Z",
        ),
    )
    return steps


def _assert_trees_equal(label: str, expected: dict[str, bytes], actual: dict[str, bytes]) -> None:
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    assert not missing and not extra, (
        f"step {label!r}: file set diverged (missing post-migration: {missing}; "
        f"extra post-migration: {extra})"
    )
    for rel in sorted(expected):
        if expected[rel] == actual[rel]:
            continue
        if rel.endswith(".jsonl"):
            pre_lines = expected[rel].split(b"\n")
            post_lines = actual[rel].split(b"\n")
            for index, (pre, post) in enumerate(zip(pre_lines, post_lines)):
                if pre != post:
                    pytest.fail(
                        f"step {label!r}: {rel} line {index + 1} diverged:\n"
                        f"  pre : {pre[:400]!r}\n  post: {post[:400]!r}"
                    )
            pytest.fail(
                f"step {label!r}: {rel} line count diverged "
                f"({len(pre_lines)} pre vs {len(post_lines)} post)"
            )
        pytest.fail(
            f"step {label!r}: {rel} bytes diverged "
            f"({len(expected[rel])}B pre vs {len(actual[rel])}B post)"
        )


def _all_events(steps: list[dict]) -> list[dict]:
    """Union of every evidence event visible in any step snapshot."""
    seen: dict[tuple[str, int], dict] = {}
    for step in steps:
        for rel, data in step["tree"].items():
            if not (rel.startswith(f"{EVIDENCE_REL}/trials/") and rel.endswith("events.jsonl")):
                continue
            for raw in data.split(b"\n"):
                if not raw.strip():
                    continue
                row = json.loads(raw)
                seen[(row["trial_id"], row["sequence"])] = row
    return list(seen.values())


def test_snapshot_fixture_is_the_pinned_premigration_source():
    digest = hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()
    assert digest == SNAPSHOT_SHA256, (
        "the vendored pre-migration journey snapshot drifted; the byte-identity "
        "gate would no longer compare against eef927f4"
    )


def test_snapshot_fixture_is_the_pinned_postmigration_source():
    digest = hashlib.sha256(POST_SNAPSHOT.read_bytes()).hexdigest()
    assert digest == POST_SNAPSHOT_SHA256, (
        "the vendored post-migration journey snapshot drifted; the byte-identity "
        "gate would no longer compare against 4467476f"
    )


def _assert_lifecycle_breadth(steps: list[dict]) -> None:
    """The anti-vacuity block: a run that proves nothing must not pass.

    Applied to whichever module the caller ran, so it holds for the frozen
    comparison AND for the live module.
    """
    events = _all_events(steps)
    assert len(events) >= 40, f"scenario too thin to gate on ({len(events)} events)"
    statuses = {row["status"] for row in events}
    assert {
        "started", "proposed", "allowed", "succeeded", "verified",
        "duplicate", "refused", "failed", "paused", "recovered",
    } <= statuses, f"missing lifecycle coverage: {sorted(statuses)}"
    remints = [
        row for row in events
        if row["status"] == "recovered"
        and row["detail"].get("action") == "remint_evidence_trial"
    ]
    assert len(remints) >= 2, "both re-mint paths (pre-flight and mid-record) must appear"
    for row in events:
        assert len(row["event_hash"]) == 64 and len(row["signature"]) == 64
    verify_step = next(s for s in steps if s["label"] == "verify-live-trial")
    assert verify_step["outcome"]["ok"] is True
    assert json.loads(verify_step["outcome"]["value"])["ok"] is True


def test_act_event_stream_is_byte_identical_across_the_helper_migration(tmp_path, monkeypatch):
    source = tmp_path / "sources" / "software-product"
    shutil.copytree(FIXTURES / "software-product", source)
    base = tmp_path / "cabinet-base"

    premigration = _load_premigration()
    postmigration = _load_snapshot(POST_SNAPSHOT, "_postmigration_journey_4467476f")
    pins = _Pins()
    pins.install(monkeypatch, modules=(premigration, postmigration))

    before = _run_scenario(premigration, base=base, source=source, pins=pins)
    after = _run_scenario(postmigration, base=base, source=source, pins=pins)

    assert [s["label"] for s in before] == [s["label"] for s in after]
    for expected, actual in zip(before, after):
        label = expected["label"]
        assert actual["outcome"] == expected["outcome"], (
            f"step {label!r}: surfaced result diverged:\n"
            f"  pre : {expected['outcome']}\n  post: {actual['outcome']}"
        )
        _assert_trees_equal(label, expected["tree"], actual["tree"])

    # The gate must not pass vacuously: prove the scenario exercised the
    # breadth the migration touched, on the migrated run.
    _assert_lifecycle_breadth(after)


def test_the_byte_identity_comparison_actually_detects_a_diverged_stream(tmp_path, monkeypatch):
    """A comparison never seen to FAIL is a green tick, not a gate.

    One byte of real behaviour is changed in a throwaway copy of the
    post-migration snapshot — the First Window's file ceiling, which reaches
    the manifest, the dividend, the hash chain and every signature after it —
    and the same comparison must reject it.
    """
    source = tmp_path / "sources" / "software-product"
    shutil.copytree(FIXTURES / "software-product", source)
    base = tmp_path / "cabinet-base"

    mutated_path = tmp_path / "mutated_journey.py.txt"
    text = POST_SNAPSHOT.read_text(encoding="utf-8")
    assert "\nMAX_FILES = 200\n" in text
    mutated_path.write_text(text.replace("\nMAX_FILES = 200\n", "\nMAX_FILES = 2\n"), encoding="utf-8")

    premigration = _load_premigration()
    mutated = _load_snapshot(mutated_path, "_mutated_journey_for_negative_arm")
    pins = _Pins()
    pins.install(monkeypatch, modules=(premigration, mutated))

    before = _run_scenario(premigration, base=base, source=source, pins=pins)
    after = _run_scenario(mutated, base=base, source=source, pins=pins)

    with pytest.raises(BaseException):
        for expected, actual in zip(before, after):
            assert actual["outcome"] == expected["outcome"]
            _assert_trees_equal(expected["label"], expected["tree"], actual["tree"])


def test_live_journey_still_produces_a_complete_verifiable_evidence_stream(tmp_path, monkeypatch):
    """What the frozen comparison cannot say: TODAY's journey is still sound.

    The byte-identity arm above is a statement about two historical commits.
    This one runs the same twelve-step scenario against the live module and
    demands the properties that actually matter going forward — a full
    lifecycle vocabulary, both re-mint recovery paths, a 64-hex hash and
    signature on every event, and a green verification of the live trial.
    """
    source = tmp_path / "sources" / "software-product"
    shutil.copytree(FIXTURES / "software-product", source)
    base = tmp_path / "cabinet-base"

    pins = _Pins()
    pins.install(monkeypatch, modules=(journey,))

    _assert_lifecycle_breadth(_run_scenario(journey, base=base, source=source, pins=pins))
