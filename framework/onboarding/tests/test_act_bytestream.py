"""R-8 migration gate: the evidence stream across the helper migration.

The Phase-1 design of record requires ``journey.py`` migrated onto the shared
recording helper (``framework.evidence.lifecycle``) with a BYTE-IDENTICAL
event stream — not merely "dogfood green".  This harness proves it by running
the SAME scripted action sequence against

  (a) the vendored pre-migration journey — a verbatim snapshot of
      ``framework/onboarding/journey.py`` at commit ``eef927f4`` (the tree the
      helper was extracted from), stored as inert test data and loaded from
      source at test time, and
  (b) the live, migrated ``framework.onboarding.journey``,

with every nondeterminism source pinned (uuid4, monotonic clock, the
recorder's UTC clock, the journey wall clock, provenance env vars, and a
fixed test-only signing key), on the SAME base path, and comparing the entire
produced tree — evidence ``events.jsonl`` (hash chain + HMAC signatures),
anchors, watermarks, control file, purge receipts, and the onboarding plane.

BYTE-IDENTITY WAS NARROWED BY A RULING, 2026-07-27, not weakened.  The
ownership ceiling now binds the declared ownership class into the Charter
payload, so the two arms can no longer produce identical bytes and the old
assertion is literally wrong.  What remains is strictly enumerated: the
recording SKELETON (which events, in what order, for which act, by which
actor, with which status) must still match exactly — that was always the R-8
claim — the file sets must match, every diverging path must sit in the
declared ownership set, and the divergence must be non-empty and be exactly
the ownership keys.  Any unrelated change to the event stream still fails.

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
EVIDENCE_REL = "instance/evidence/v1"
STATE_REL = "instance/onboarding/v2/state.json"
# Fixed TEST-ONLY signing key so HMAC signatures are comparable across the
# two runs. Never key material for any real store.
TEST_SIGNING_KEY = bytes(range(32))


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
        # The ownership ceiling (2026-07-27) is REQUIRED by the live journey and
        # simply unread by the pre-migration snapshot, which has no such field.
        # Sending it to both arms keeps ONE scripted scenario: the pre arm
        # behaves exactly as it always did, the post arm is driven through its
        # ceiling, and the divergence that remains is the charter payload — the
        # enumerated, asserted difference below, not an unexplained one.
        "ownership": "self",
        "authority_basis": "my own machine, my own folder",
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


#: The ONLY paths the ownership ceiling is permitted to move. Anything else
#: diverging between the two arms is an unexplained behaviour change and fails.
#: `access-records/` is new in kind (the pre-migration journey has no concept of
#: a record that survives its own purge); the rest diverge because the charter
#: payload now carries the ownership class, which reaches the state, manifest,
#: dividend and every hash chained over them.
_OWNERSHIP_DIVERGENCE_PREFIXES = (
    "instance/onboarding/access-records/",
    "instance/onboarding/v2/",
    "instance/onboarding/purge-receipts/",
    f"{EVIDENCE_REL}/trials/",
    f"{EVIDENCE_REL}/purge-receipts/",
    f"{EVIDENCE_REL}/.verify-watermarks.json",
)


def _event_skeleton(rows: list[dict]) -> list[tuple]:
    """Everything about a recorded event EXCEPT the payload bytes.

    This is the R-8 claim itself: the helper migration must not change WHICH
    events are recorded, in what order, for which act, by which actor, with
    which status. It survives the ownership change intact, and it is what the
    byte-identity assertion was really protecting.
    """
    return sorted(
        (
            row["trial_id"], row["sequence"], row["status"], row.get("phase"),
            json.dumps(row.get("actor"), sort_keys=True),
            json.dumps(row.get("component"), sort_keys=True),
            row["action_id"], row["surface"],
        )
        for row in rows
    )


def test_act_event_stream_diverges_from_premigration_only_at_the_ownership_ceiling(
    tmp_path, monkeypatch
):
    """Successor to the byte-identity gate, narrowed by a ruling, not weakened.

    The original assertion — the pre-migration journey and the live one produce
    byte-identical trees — became literally wrong on 2026-07-27, when the
    ownership ceiling started binding the declared class into the Charter
    payload. Deleting the gate would retire a real sensor over a deliberate
    change, so it is INVERTED instead: the recording SKELETON must still match
    exactly (that was always the R-8 claim), the file SETS must still match,
    every diverging path must sit in the enumerated ownership set, and the
    divergence must be non-empty and be exactly the ownership keys. An
    unrelated regression in the event stream still fails here.
    """
    source = tmp_path / "sources" / "software-product"
    shutil.copytree(FIXTURES / "software-product", source)
    base = tmp_path / "cabinet-base"

    premigration = _load_premigration()
    pins = _Pins()
    pins.install(monkeypatch, modules=(premigration, journey))

    before = _run_scenario(premigration, base=base, source=source, pins=pins)
    after = _run_scenario(journey, base=base, source=source, pins=pins)

    assert [s["label"] for s in before] == [s["label"] for s in after]
    moved: set[str] = set()
    for expected, actual in zip(before, after):
        label = expected["label"]
        assert actual["outcome"]["ok"] == expected["outcome"]["ok"], (
            f"step {label!r}: success/refusal diverged:\n"
            f"  pre : {expected['outcome']}\n  post: {actual['outcome']}"
        )
        new_paths = sorted(set(actual["tree"]) - set(expected["tree"]))
        assert not (set(expected["tree"]) - set(actual["tree"])), (
            f"step {label!r}: the live arm dropped files the pre arm wrote"
        )
        for rel in new_paths:
            assert rel.startswith("instance/onboarding/access-records/"), (
                f"step {label!r}: unexplained new file {rel}"
            )
        for rel in sorted(set(expected["tree"]) & set(actual["tree"])):
            if expected["tree"][rel] == actual["tree"][rel]:
                continue
            assert rel.startswith(_OWNERSHIP_DIVERGENCE_PREFIXES), (
                f"step {label!r}: {rel} diverged outside the ownership set"
            )
            moved.add(rel)
        moved.update(new_paths)

    # Non-vacuity in BOTH directions: the ownership set must actually have
    # moved (otherwise the allowlist is hiding nothing and proves nothing), and
    # the recording skeleton must be untouched.
    assert moved, "no file diverged — the ownership ceiling is not reaching the charter"
    assert "instance/onboarding/v2/orientation-charter.json" in moved
    assert any(p.startswith("instance/onboarding/access-records/") for p in moved)
    assert _event_skeleton(_all_events(before)) == _event_skeleton(_all_events(after)), (
        "the recording skeleton diverged — that is the R-8 claim, and the "
        "ownership ceiling must not touch it"
    )

    # The divergence in the charter is EXACTLY the ownership keys, not a
    # coincidental difference that happens to live in an allowlisted path.
    pre_charter = json.loads(
        before[0]["tree"]["instance/onboarding/v2/orientation-charter.json"]
    )["payload"]
    post_charter = json.loads(
        after[0]["tree"]["instance/onboarding/v2/orientation-charter.json"]
    )["payload"]
    assert set(post_charter) - set(pre_charter) == {"attestation", "attestation_limit"}
    assert set(pre_charter) - set(post_charter) == set()
    assert post_charter["source"]["ownership"] == "self"
    assert "ownership" not in pre_charter["source"]

    # The behaviour change itself, in the same harness: the pre-migration
    # journey accepts an unclassified source; the live one refuses it.
    for module, expect_ok in ((premigration, True), (journey, False)):
        probe_base = tmp_path / f"probe-{module.__name__.rsplit('.', 1)[-1]}-{expect_ok}"
        try:
            module.act(
                {
                    "action": "propose_window",
                    "action_id": "unclassified-1",
                    "surface": "cli",
                    "source": str(source),
                    "purpose": "Read this without saying whose it is.",
                    "relationship_destination": "reversible",
                },
                probe_base,
                now="2026-07-16T11:00:00Z",
            )
            accepted = True
        except Exception as exc:  # noqa: BLE001 — the refusal type differs per arm
            accepted = False
            if not expect_ok:
                assert getattr(exc, "code", None) == "ownership_unclassified", exc
        assert accepted is expect_ok

    # The gate must not pass vacuously: prove the scenario exercised the
    # breadth the migration touched, on the migrated run.
    events = _all_events(after)
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
    verify_step = next(s for s in after if s["label"] == "verify-live-trial")
    assert verify_step["outcome"]["ok"] is True
    assert json.loads(verify_step["outcome"]["value"])["ok"] is True
