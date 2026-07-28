"""Phase-4 SHADOW detectors (G1) — cluster/triage/report laws + shadow proofs.

Pins this batch's laws for the detector lens:

* R-12 seam: the evidence clusterer lives INSIDE eval_pattern_detector.py
  (sibling function, shared threshold constants — one detector shape, one
  number set, never a sibling clusterer file);
* triage FAIL-OPEN (the signal-discriminator law, verbatim): NOISE only
  with affirmative evidence — an exact, in-window degradation attribution —
  else INCONCLUSIVE and the finding PASSES THROUGH to the report unchanged
  (uncertainty is never noise; absence of an explanation never suppresses);
* store byte-stability: the full detection pass leaves non-watermark store
  bytes identical, and repeated passes at tip are fully byte-identical
  (the verifier's first-verify watermark advance is the ONE sanctioned
  side effect — the two-pass tree-digest proof, label-join pattern);
* freeze respect (§2.4): ANY judging-freeze marker presence — garbage
  bytes, valid JSON, a dangling symlink — refuses the run with exit 0,
  ZERO store reads (fully byte-identical including no watermark sidecar
  creation) and ZERO report writes;
* shadow proof, grep-level: no officer-visible surface references the
  detector or its journal (allowlist with whys — wiring the weekly review
  later must consciously extend it); the module imports no org emitter, no
  Redis, no subprocess, no network; report keys carry no score-shaped
  deny tokens (never-a-score); the services row ships disabled:true and
  the instance watchdog enable-list keeps the Phase-4 rows dark;
* watchdog rows ground in INVARIANTS only, degrade to skip when
  unobservable, and fail only on affirmative observations.

Scratch stores only (tmp_path); the live instance/evidence store is never
touched. House interpreter: python3.12 (CI runs `pytest framework/`).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from framework import evidence_detectors as ed  # noqa: E402
from framework.evidence import EvidenceRecorder  # noqa: E402
from framework.measurement import eval_pattern_detector as epd  # noqa: E402
from framework.watchdog import registry  # noqa: E402

TODAY = datetime.now(timezone.utc).strftime("%Y%m%d")

# Never-a-score deny tokens (mirrors the EVAL-025 harness tokenizer and the
# query-plane pin in framework/evidence/tests/test_query_plane.py).
DENY_TOKENS = frozenset({
    "score", "scores", "scored", "scoring", "grade", "grades", "graded",
    "grading", "rank", "ranks", "ranked", "ranking", "rankings", "rating",
    "ratings", "rated", "percentile", "percentiles", "leaderboard",
    "leaderboards", "kpi", "kpis", "elo", "metric", "metrics", "aggregate",
    "aggregates", "aggregated", "rate", "rates", "avg", "average",
    "averages", "mean", "median", "quantile", "cost", "costs", "usd",
    "spend", "spent", "spending", "budget", "budgets", "token", "tokens",
    "fuel", "graduation", "graduations", "autonomy",
})


def _tree_digest(root: Path) -> dict[str, str]:
    """Per-file digest map of a store tree (label-join proof pattern)."""
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            out[rel] = "L:" + os.readlink(path)
        elif path.is_file():
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _non_watermark(tree: dict[str, str]) -> dict[str, str]:
    watermark_files = {".verify-watermarks.json", ".verify-watermarks.lock"}
    return {k: v for k, v in tree.items()
            if Path(k).name not in watermark_files}


def _walk_keys(value: object):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def _seed_failure_store(store: Path) -> None:
    """Two day-bounded trials with a 4-strong failure cluster + noise."""
    recorder = EvidenceRecorder(store)
    fail_detail = {"action": "probe_x", "result_code": "boom"}
    for trial in (f"evt-shadow-a-{TODAY}", f"evt-shadow-b-{TODAY}"):
        ctx = recorder.trace(trial, surface="system")
        for _ in range(2):
            recorder.append(
                ctx, phase="outcome", status="failed",
                actor={"kind": "system", "id": "probe-runner"},
                component={"name": "mirror-choke", "version": "1"},
                detail=fail_detail,
            )
        # below-threshold different component + a success (never clustered)
        recorder.append(
            ctx, phase="outcome", status="failed",
            actor={"kind": "system", "id": "probe-runner"},
            component={"name": f"solo-{trial}", "version": "1"},
        )
        recorder.append(
            ctx, phase="outcome", status="succeeded",
            actor={"kind": "system", "id": "probe-runner"},
            component={"name": "mirror-choke", "version": "1"},
        )


# ── R-12 clustering seam ──────────────────────────────────────────────────────


def test_cluster_seam_lives_in_eval_pattern_detector_with_shared_constants():
    # One detector shape, one threshold set (R-12): the evidence clusterer is
    # a sibling of detect_patterns and the orchestrator imports the SAME
    # constants — no second number anywhere.
    assert ed.detect_evidence_patterns is epd.detect_evidence_patterns
    source = (REPO_ROOT / "framework" / "evidence_detectors.py").read_text()
    assert "from framework.measurement.eval_pattern_detector import" in source
    assert ed._DEFAULT_WINDOW_DAYS == epd._DEFAULT_WINDOW_DAYS
    assert ed._DEFAULT_MIN_OCCURRENCES == epd._DEFAULT_MIN_OCCURRENCES
    # No locally-minted threshold constants in the orchestrator.
    assert not re.search(r"^_DEFAULT_(WINDOW_DAYS|MIN_OCCURRENCES)\s*=",
                         source, re.M)


def test_detect_evidence_patterns_thresholds_and_keys():
    def row(component: str, status: str = "failed", trial: str = "evt-x-20260701",
            result_code: str = "boom") -> dict:
        return {
            "component": {"name": component, "version": "1"},
            "phase": "outcome",
            "status": status,
            "detail": {"result_code": result_code},
            "trial_id": trial,
        }

    rows = [row("a"), row("a"), row("a", trial="evt-y-20260702"),
            row("b"), row("b"),                    # below threshold
            {"garbage": True}, "not-a-dict"]       # malformed rows skipped
    patterns = epd.detect_evidence_patterns(rows)
    assert [p["component"] for p in patterns] == ["a"]
    p = patterns[0]
    assert p["count"] == 3
    assert p["failure_type"] == "outcome/failed/boom"
    assert p["first_seen_day"] == "20260701"
    assert p["last_seen_day"] == "20260702"
    assert p["trial_count"] == 2
    # threshold honors the shared default (3) and the explicit override
    assert epd.detect_evidence_patterns(rows, min_occurrences=2)[0]["count"] >= 2


# ── Triage: FAIL-OPEN law ─────────────────────────────────────────────────────


def _finding(component: str = "mirror-choke") -> dict:
    return {"component": component, "phase": "outcome", "status": "failed",
            "result_code": "boom", "count": 4}


def test_triage_fail_open_defaults_to_inconclusive_pass_through():
    now = datetime.now(timezone.utc)
    # No degradation rows at all → INCONCLUSIVE (never NOISE on absence).
    verdict, why = ed.triage_finding(_finding(), [], now=now)
    assert verdict == ed.INCONCLUSIVE
    assert "passes through" in why
    # Unreadable ledger → uncertainty → INCONCLUSIVE.
    verdict, _ = ed.triage_finding(_finding(), [], ledger_readable=False, now=now)
    assert verdict == ed.INCONCLUSIVE
    # Wrong component, substring component, unparseable ts: all uncertainty.
    fresh = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    for row in (
        {"ts": fresh, "chokepoint": "other-choke", "reason": "r"},
        {"ts": fresh, "chokepoint": "mirror", "reason": "r"},      # substring ≠ affirmative
        {"ts": "not-a-time", "chokepoint": "mirror-choke", "reason": "r"},
        {"chokepoint": "mirror-choke", "reason": "r"},             # missing ts
    ):
        verdict, _ = ed.triage_finding(_finding(), [row], now=now)
        assert verdict == ed.INCONCLUSIVE, row


def test_triage_noise_requires_exact_in_window_attribution():
    now = datetime.now(timezone.utc)
    fresh = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    stale = (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Exact component + in-window ts → affirmative NOISE (still reported).
    verdict, why = ed.triage_finding(
        _finding(), [{"ts": fresh, "chokepoint": "mirror-choke",
                      "reason": "recorder_unimportable"}], now=now)
    assert verdict == ed.NOISE
    assert "recorder_unimportable" in why and "still reported" in why
    # Same row but outside the window → INCONCLUSIVE.
    verdict, _ = ed.triage_finding(
        _finding(), [{"ts": stale, "chokepoint": "mirror-choke",
                      "reason": "recorder_unimportable"}], now=now)
    assert verdict == ed.INCONCLUSIVE
    # Lifecycle-sidecar shape (component/error_code) also attributes.
    verdict, _ = ed.triage_finding(
        _finding(), [{"ts": fresh, "component": "mirror-choke",
                      "error_code": "trial_cap_exhausted"}], now=now)
    assert verdict == ed.NOISE


def test_load_degradation_rows_missing_vs_unreadable(tmp_path):
    rows, readable = ed.load_degradation_rows(tmp_path / "absent.jsonl")
    assert rows == [] and readable is True     # absence is certain, not uncertain
    ledger = tmp_path / "deg.jsonl"
    ledger.write_text('{"ts": "2026-07-17T00:00:00Z", "chokepoint": "c"}\n'
                      "not json\n{\"also\": \"ok\"}\n")
    rows, readable = ed.load_degradation_rows(ledger)
    assert readable is True and len(rows) == 2  # malformed lines skipped
    unreadable = tmp_path / "dir.jsonl"
    unreadable.mkdir()
    rows, readable = ed.load_degradation_rows(unreadable)
    assert rows == [] and readable is False     # stat/read error = uncertainty


# ── Full pass: shadow report + store byte-stability ──────────────────────────


def test_full_run_report_shape_and_two_pass_byte_stability(tmp_path, capsys):
    store = tmp_path / "evidence"
    _seed_failure_store(store)
    journal = tmp_path / "journal" / "evidence-shadow-findings.jsonl"

    pre = _tree_digest(store)
    rc = ed.main(["--store", str(store), "--journal", str(journal),
                  "--repo-root", str(tmp_path)])
    assert rc == 0
    assert "shadow report appended" in capsys.readouterr().out
    settled = _tree_digest(store)
    # Pass 1: only the watermark sidecar may have changed (first verify).
    assert _non_watermark(settled) == _non_watermark(pre), (
        "the detection pass wrote NON-watermark store bytes")
    # Pass 2 at tip: fully byte-identical, watermarks included.
    rc = ed.main(["--store", str(store), "--journal", str(journal),
                  "--repo-root", str(tmp_path)])
    assert rc == 0
    assert _tree_digest(store) == settled, (
        "a repeated detection pass changed store bytes at tip")

    lines = journal.read_text().strip().splitlines()
    assert len(lines) == 2
    report = json.loads(lines[0])
    assert report["schema"] == ed.SCHEMA
    assert report["mode"] == "shadow"
    assert "never act" in report["shadow_law"]
    assert "HP-1" in report["honest_claim"]
    assert "weak signals" in report["weak_signal"]
    assert report["counts"]["clusters_flagged"] == 1
    finding = report["findings"][0]
    assert finding["component"] == "mirror-choke"
    assert finding["count"] == 4
    assert finding["failure_type"] == "outcome/failed/boom"
    assert sorted(finding["trials"]) == [f"evt-shadow-a-{TODAY}",
                                         f"evt-shadow-b-{TODAY}"]
    # No degradation ledger in the scratch tree → fail-open pass-through
    # lands IN the report (the pinned INCONCLUSIVE behavior).
    assert finding["verdict"] == ed.INCONCLUSIVE
    assert "passes through" in finding["verdict_why"]
    assert report["counts"]["inconclusive"] == 1
    # Never-a-score: no report KEY tokenizes into the deny set; findings
    # are keyed by component/failure-class, never by actor.
    for key in _walk_keys(report):
        tokens = set(re.split(r"[^a-z0-9]+", str(key).lower())) - {""}
        assert not (tokens & DENY_TOKENS), f"deny token in report key: {key}"
    assert "actor" not in json.dumps(sorted(_walk_keys(report)))
    # The journal landed OUTSIDE the store.
    assert not str(journal.resolve()).startswith(str(store.resolve()))


def test_noise_explained_finding_still_reported(tmp_path):
    store = tmp_path / "evidence"
    _seed_failure_store(store)
    ledger = tmp_path / ed.DEGRADATION_LEDGER_REL
    ledger.parent.mkdir(parents=True, exist_ok=True)
    fresh = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ledger.write_text(json.dumps({"ts": fresh, "chokepoint": "mirror-choke",
                                  "reason": "recorder_unimportable"}) + "\n")
    report = ed.run_detection(store, degradation_ledger=ledger)
    finding = report["findings"][0]
    # Affirmative attribution → NOISE, but the finding is STILL in the
    # report (shadow: triage informs the Captain's read, never drops rows).
    assert finding["verdict"] == ed.NOISE
    assert report["counts"]["noise_explained"] == 1


# ── Freeze respect (§2.4) ────────────────────────────────────────────────────


@pytest.mark.parametrize("make_marker", [
    lambda p: p.write_text("{ this is not json"),
    lambda p: p.write_text(json.dumps({"reason": "drill", "drill": True})),
    lambda p: p.symlink_to(p.parent / "nowhere-dangling"),
])
def test_frozen_marker_refuses_zero_reads_zero_writes(tmp_path, capsys, make_marker):
    store = tmp_path / "evidence"
    _seed_failure_store(store)
    marker = tmp_path / ed.FREEZE_MARKER_REL
    marker.parent.mkdir(parents=True, exist_ok=True)
    make_marker(marker)
    journal = tmp_path / "journal.jsonl"

    pre = _tree_digest(store)
    rc = ed.main(["--store", str(store), "--journal", str(journal),
                  "--repo-root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "frozen — refusing to run" in out
    # ZERO reads: fully byte-identical INCLUDING no watermark sidecar birth.
    assert _tree_digest(store) == pre
    assert not journal.exists()


def test_frozen_helper_fail_closed_table(tmp_path):
    marker = tmp_path / ed.FREEZE_MARKER_REL
    assert ed.judging_frozen(tmp_path) == (False, str(marker))
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("garbage")
    frozen, path = ed.judging_frozen(tmp_path)
    assert frozen is True and path == str(marker)


def test_absent_store_quiet_exit_and_in_store_journal_refused(tmp_path, capsys):
    rc = ed.main(["--store", str(tmp_path / "no-store"),
                  "--journal", str(tmp_path / "j.jsonl"),
                  "--repo-root", str(tmp_path)])
    assert rc == 0
    assert "not activated" in capsys.readouterr().out
    assert not (tmp_path / "j.jsonl").exists()
    # A journal INSIDE the store is refused (byte-stability law).
    store = tmp_path / "evidence"
    _seed_failure_store(store)
    rc = ed.main(["--store", str(store),
                  "--journal", str(store / "trials" / "j.jsonl"),
                  "--repo-root", str(tmp_path)])
    assert rc == 2


# ── Watchdog rows: invariant grounding + staged-dark posture ─────────────────


class StubProbe(registry.Probe):
    def __init__(self, *, texts=None, mtimes=None, listings=None, now=None):
        self._texts = dict(texts or {})
        self._mtimes = dict(mtimes or {})
        self._listings = dict(listings or {})
        self._now = now or datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)

    def now(self):
        return self._now

    def read_text(self, path: str) -> str:
        return self._texts.get(path, "")

    def file_mtime(self, path: str):
        return self._mtimes.get(path)

    def listdir(self, path: str):
        return self._listings.get(path)


def _root(monkeypatch, tmp_path) -> Path:
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    return tmp_path


def test_catalog_rows_present_chair_tier_and_instance_dark():
    ids = {e.id: e for e in registry._CATALOG}
    for eid in ("evidence-store-invariants", "evidence-anchor-export-fresh",
                "evidence-shadow-detector-liveness"):
        assert eid in ids, eid
        assert ids[eid].tier is registry.Tier.ESCALATE_CHAIR
        assert ids[eid].auto_fix is None
    # Instance enable-list after the Captain's 2026-07-26 ceremony: ONLY
    # evidence-store-invariants is armed (its checker skips when the store is
    # not observable). The other two would page daily on a cabinet whose
    # evidence plane was never activated, so they stay commented — pinned by
    # equality in both directions, so neither a silent arming nor a silent
    # disarming of any of the three passes.
    text = (REPO_ROOT / "instance/config/watchdog.yml").read_text()
    assert re.search(r"^\s*- evidence-store-invariants\s*$", text, re.M), (
        "evidence-store-invariants must be ARMED in the instance enable-list "
        "(Captain ceremony 2026-07-26)")
    for eid in ("evidence-anchor-export-fresh",
                "evidence-shadow-detector-liveness"):
        assert not re.search(rf"^\s*- {re.escape(eid)}\s*$", text, re.M), (
            f"{eid} must stay staged dark (commented) in the instance "
            "enable-list — its producer/store precondition is unmet")
        assert f"# - {eid}" in text
    # Weak-signal doctrine is pinned in code, not just prose.
    registry_src = (REPO_ROOT / "framework" / "watchdog" / "registry.py").read_text()
    assert "WEAK-SIGNAL DOCTRINE" in registry_src
    assert "never expectation ground truth" in registry_src.lower() or \
        "never expectation ground truth" in registry_src


def test_registry_rel_constants_sync_pinned_to_owning_modules():
    """The registry's mirrored REL constants never drift from their owning
    modules. Mirror-not-import is deliberate (registry survival contract:
    never import the watched plane — journey and evidence_detectors both
    import framework.evidence at module scope); THIS pin is what makes the
    mirror a reuse instead of a second source (the EV_CAP_DEFAULT pattern),
    and it keeps the layer-separation posture honest: the couplings are
    declared single-string RELs, not silent Path-component literals."""
    from framework.onboarding.journey import EVIDENCE_REL
    assert registry._EV_STORE_REL == EVIDENCE_REL
    assert registry._EV_FREEZE_MARKER_REL == ed.FREEZE_MARKER_REL
    assert registry._EV_JOURNAL_REL == ed.JOURNAL_REL
    # The anchor CLI still reads the exact binding file the freshness row
    # watches (component-built there; cabinet/ is outside the layer gate).
    # The needle is BUILT from the registry constant, so a drift on either
    # side breaks this pin.
    anchor_cli = (REPO_ROOT / "cabinet" / "scripts"
                  / "evidence-anchor.py").read_text()
    needle = " / ".join(
        f'"{part}"' for part in Path(registry._EV_ANCHOR_CFG_REL).parts)
    assert needle in anchor_cli
    assert registry._EV_ANCHOR_CFG_REL.endswith("evidence-anchor.yml")


def test_store_invariants_skip_orphan_future_and_cap(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    trials = str(root / registry._EV_STORE_REL / "trials")
    sidecar = str(root / registry._EV_STORE_REL / ".verify-watermarks.json")
    doctor = str(root / "cabinet" / "scripts" / "cabinet-doctor.sh")
    now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
    day = now.strftime("%Y%m%d")

    # Unobservable (no listing) → skip, never fail.
    res = registry.verify_evidence_store_invariants(StubProbe(now=now))
    assert res.ok and res.skipped

    # Empty trials + surviving sidecar → affirmative orphan → FAIL.
    res = registry.verify_evidence_store_invariants(StubProbe(
        now=now, listings={trials: []}, texts={sidecar: '{"t": 1}'}))
    assert not res.ok and "orphaned" in res.detail

    # Empty trials, no sidecar → skip (plane empty).
    res = registry.verify_evidence_store_invariants(StubProbe(
        now=now, listings={trials: []}))
    assert res.ok and res.skipped

    # Future-dated ledger mtime → FAIL.
    name = f"evt-consequence-{day}"
    res = registry.verify_evidence_store_invariants(StubProbe(
        now=now, listings={trials: [name]},
        mtimes={f"{trials}/{name}/events.jsonl": now.timestamp() + 90000}))
    assert not res.ok and "future-dated" in res.detail

    # Cap breach: 501 events in a day trial vs EV_CAP_DEFAULT=500 parsed
    # from the doctor (reused constant — never minted here).
    res = registry.verify_evidence_store_invariants(StubProbe(
        now=now, listings={trials: [name]},
        mtimes={f"{trials}/{name}/events.jsonl": now.timestamp() - 60},
        texts={doctor: "EV_CAP_DEFAULT=500\n",
               f"{trials}/{name}/events.jsonl": "x\n" * 501}))
    assert not res.ok and "cap" in res.detail

    # All sane → ok.
    res = registry.verify_evidence_store_invariants(StubProbe(
        now=now, listings={trials: [name]},
        mtimes={f"{trials}/{name}/events.jsonl": now.timestamp() - 60},
        texts={doctor: "EV_CAP_DEFAULT=500\n",
               f"{trials}/{name}/events.jsonl": "x\n" * 3,
               sidecar: '{"w": 1}'}))
    assert res.ok and not res.skipped


_MANIFEST_DARK = (
    "services:\n"
    "  - name: evidence-anchor\n"
    "    label: com.cabinet.evidence-anchor\n"
    "    kind: cron\n"
    "    schedule: { calendar: [{hour: 5, minute: 20}] }\n"
    "    disabled: true\n"
    "  - name: evidence-shadow-detectors\n"
    "    label: com.cabinet.evidence-shadow-detectors\n"
    "    kind: cron\n"
    "    schedule: { calendar: [{hour: 5, minute: 50}] }\n"
    "    disabled: true\n"
)
_MANIFEST_LIVE = _MANIFEST_DARK.replace("    disabled: true\n", "")


def test_anchor_freshness_unconfigured_dark_stale_fresh(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    cfg = str(root / registry._EV_ANCHOR_CFG_REL)
    now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
    anchors = "/tmp/anchors-x/evidence-anchors.jsonl"

    # Unconfigured → skip.
    res = registry.verify_evidence_anchor_fresh(StubProbe(now=now))
    assert res.ok and res.skipped
    # Configured but service staged dark → skip.
    res = registry.verify_evidence_anchor_fresh(StubProbe(
        now=now, texts={cfg: "anchor_dir: /tmp/anchors-x\n",
                        registry.SERVICES_MANIFEST: _MANIFEST_DARK}))
    assert res.ok and res.skipped
    # Enabled + never exported → FAIL.
    res = registry.verify_evidence_anchor_fresh(StubProbe(
        now=now, texts={cfg: "anchor_dir: /tmp/anchors-x\n",
                        registry.SERVICES_MANIFEST: _MANIFEST_LIVE}))
    assert not res.ok and "missing" in res.detail
    # Enabled + stale beyond the schedule-derived floor → FAIL.
    res = registry.verify_evidence_anchor_fresh(StubProbe(
        now=now, texts={cfg: "anchor_dir: /tmp/anchors-x\n",
                        registry.SERVICES_MANIFEST: _MANIFEST_LIVE},
        mtimes={anchors: now.timestamp() - 30 * 3600}))
    assert not res.ok and "stale" in res.detail
    # Enabled + fresh → ok.
    res = registry.verify_evidence_anchor_fresh(StubProbe(
        now=now, texts={cfg: "anchor_dir: /tmp/anchors-x\n",
                        registry.SERVICES_MANIFEST: _MANIFEST_LIVE},
        mtimes={anchors: now.timestamp() - 3600}))
    assert res.ok and not res.skipped


def test_detector_liveness_dark_frozen_stale_fresh(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
    journal = str(root / registry._EV_JOURNAL_REL)
    marker = str(root / registry._EV_FREEZE_MARKER_REL)

    # Staged dark → skip (never a page while the shadow row is disabled).
    res = registry.verify_evidence_detector_liveness(StubProbe(
        now=now, texts={registry.SERVICES_MANIFEST: _MANIFEST_DARK}))
    assert res.ok and res.skipped
    # Enabled but judging-frozen → refusal is correct → skip.
    res = registry.verify_evidence_detector_liveness(StubProbe(
        now=now, texts={registry.SERVICES_MANIFEST: _MANIFEST_LIVE},
        mtimes={marker: now.timestamp() - 60}))
    assert res.ok and res.skipped and "freeze" in res.detail
    # Enabled + journal never landed → FAIL.
    res = registry.verify_evidence_detector_liveness(StubProbe(
        now=now, texts={registry.SERVICES_MANIFEST: _MANIFEST_LIVE}))
    assert not res.ok and "never been appended" in res.detail
    # Enabled + stale journal → FAIL; fresh → ok.
    res = registry.verify_evidence_detector_liveness(StubProbe(
        now=now, texts={registry.SERVICES_MANIFEST: _MANIFEST_LIVE},
        mtimes={journal: now.timestamp() - 30 * 3600}))
    assert not res.ok and "stale" in res.detail
    res = registry.verify_evidence_detector_liveness(StubProbe(
        now=now, texts={registry.SERVICES_MANIFEST: _MANIFEST_LIVE},
        mtimes={journal: now.timestamp() - 3600}))
    assert res.ok


# ── Shadow proof: no officer-visible surface consumes detector output ────────

# Files ALLOWED to reference the detector module or its journal, with whys.
# Wiring the weekly governance review later (a conscious, reviewed change)
# must add cabinet/scripts/governance-review.py here in the same commit.
_REFERENCE_ALLOWLIST = {
    # Expansion registry (2026-07-27): a future module under this same
    # shadow law needs the identical one-line entry in its own landing.
    "cabinet/config/architecture-baseline-sets.yml":
        "the architecture baseline sets are the census's inventory of WHICH framework modules exist, so every module path is there by construction — a member-name row in a data file, never an import and never a consumer",
    # Specifics ratchet (2026-07-28): same class, same forcing rule.
    "framework/tests/framework-specifics-baseline.txt":
        "the specifics-ratchet DEBT LEDGER keys one line per known third-party literal by the framework path that carries it, so a module that carries one is there by construction — a path-keyed debt row in a data file, never an import and never a consumer",
    "cabinet/config/state-persistence-policy.yml":
        "a path row in deploy-persistence accounting, never a consumer — "
        "state-persistence-preflight.py derives its durable set from "
        ".gitignore, so every ignored path needs an entry keyed by that exact "
        "path; this row records WHY the journal is deliberately not persisted "
        "across deploys (regenerable, report-only) and reads nothing",
    "framework/evidence_detectors.py": "the module itself",
    "framework/tests/test_evidence_detectors.py": "this proof",
    "cabinet/scripts/evidence-shadow-detectors.py": "the thin scheduled runner",
    "cabinet/services.yml": "the staged-dark service row",
    "framework/watchdog/registry.py":
        "liveness expectation — reads the journal's MTIME only, never findings",
    "framework/measurement/eval_pattern_detector.py":
        "the R-12 seam host — its docstring names the shadow caller; it "
        "consumes nothing (pure rows-in→clusters-out)",
    "cabinet/scripts/evidence-coverage.py":
        "the A2 gate ENUMERATES the module (infra row) so its evidence "
        "import maps somewhere — source-text scan only, no output consumed",
    ".gitignore": "the journal's never-commit line",
    # Phase-4 integration (seam reconciliation, 2026-07-17): the shadow
    # calibration reads the journal as the MACHINE LEG of Captain-label
    # pairs — itself report-only shadow with a zero-consumers grep of its
    # own; a shadow→shadow join, never a gate/score/act consumer.
    "framework/evidence_calibration.py":
        "G1↔G3 join: consumes findings as calibration machine-leg data "
        "(shadow, report-only — pinned by test_evidence_calibration.py)",
    "framework/tests/test_evidence_phase4_seams.py":
        "the composed Phase-4 seam proof (tests are not consumers)",
    "framework/tests/test_evidence_calibration.py":
        "its zero-callers proof allowlists THIS proof by path — a string "
        "in a proof file, never an import, never a consumer",
    "docs/runbooks/evidence-recorder-v1.md":
        "runbook prose — names the journal path for the Captain",
    "shared/interfaces/reviews/evidence-phase4-shadow-judge-cp1.md":
        "FW-019 review artifact for the Phase-4 branch (prose, not code)",
    "cabinet/scripts/docs-sweep-allowlist.txt":
        "the docs-sweep glob list names the journal's runtime path so the "
        "runbook may cite it — a pattern line, never a consumer",
    "cabinet/scripts/cog3-shadow-dividend.py":
        "WR rider R3 module docstring cites the findings journal FILENAME as "
        "a where-things-land precedent for its own shared/interfaces report "
        "path — prose in a docstring, never an import, never a consumer (its "
        "battery + cog2-import-gate pin it to serve-surface reads only)",
    "docs/plans/cognitive-core-phase-4-rollback-manifest-2026-07-24.yml":
        "the COG-4 rollback manifest (W6-e1) names THIS proof file in its "
        "out_of_phase_in_range retained rows — a path row in phase-rollback "
        "accounting, never an import, never a consumer (allowlisted at the "
        "W6 landing 2026-07-24)",
}


def _tracked_files() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=str(REPO_ROOT),
                             capture_output=True, check=True)
        return [p for p in out.stdout.decode().split("\0") if p]
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Exported tree (null-hatch runs the suite from a .git-less export):
        # walk the shipped files instead. Runtime-only paths (gitignored in
        # the dev repo, absent from a fresh export) are excluded so both
        # modes prove the same shipped-file set.
        skip_dirs = {".git", "node_modules", "__pycache__", ".next",
                     ".venv", "dist", "build"}
        skip_prefixes = ("cabinet/logs/", "instance/evidence/",
                         "instance/state/")
        rels: list[str] = []
        for root, dirs, files in os.walk(REPO_ROOT):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for name in files:
                rel = os.path.relpath(os.path.join(root, name), REPO_ROOT)
                rel = rel.replace(os.sep, "/")
                if rel.startswith(skip_prefixes):
                    continue
                rels.append(rel)
        return rels


def test_shadow_grep_proof_no_officer_surface_reads_detector_output():
    offenders = []
    for rel in _tracked_files():
        if rel in _REFERENCE_ALLOWLIST:
            continue
        path = REPO_ROOT / rel
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        if "evidence_detectors" in text or "evidence-shadow-findings" in text:
            offenders.append(rel)
    assert not offenders, (
        "detector output referenced outside the allowlist (shadow law: "
        f"nothing downstream consumes it): {offenders}")


def test_detector_module_is_pure_report_only():
    source = (REPO_ROOT / "framework" / "evidence_detectors.py").read_text()
    # No org-event emission, no Chair/Redis reach, no subprocess, no network.
    for forbidden in ("framework.events", "emitter", "trigger_send",
                      "import subprocess", "redis-cli", "StrictRedis",
                      "urllib", "socket", "http.client", "requests"):
        assert forbidden not in source, forbidden
    # Never the report-only scalar series (EVAL-025 C1; token built by
    # concatenation so THIS file never contains it either).
    for token in ("golden-eval-" + "scalar", "golden_" + "scalar"):
        assert token not in source, token
    # The journal lives outside the store and outside officer org surfaces.
    assert ed.JOURNAL_REL.startswith("shared/interfaces/")
    assert not ed.JOURNAL_REL.startswith("instance/evidence")
    # Mandatory doctrine strings in the module.
    for required in ("SHADOW LAW", "detect, never act", "HP-1",
                     "weak signal", "INCONCLUSIVE"):
        assert required.lower() in source.lower(), required


def test_services_row_is_armed_and_journal_gitignored():
    """The row was ARMED by the Captain's 2026-07-26 ceremony (it shipped
    `disabled: true` staged-dark before that). What the shadow law actually
    requires of this row survives the arming and is pinned here: the row still
    declares the shadow posture, still runs exactly ONE command, and its
    findings journal is still gitignored runtime data outside every plane.
    Enabling a DETECTOR is not enabling an ACTOR — the zero-consumer proof
    (test_shadow_grep_proof_no_officer_surface_reads_detector_output) is the
    test that would catch that, and it is untouched."""
    services = (REPO_ROOT / "cabinet" / "services.yml").read_text()
    block = services.split("- name: evidence-shadow-detectors", 1)[1]
    block = block.split("- name: ", 1)[0]
    assert "disabled: true" not in block
    assert "disabled_reason:" not in block   # a live row carries no parking note
    assert "shadow" in block                 # the posture is still declared
    assert "python3.12 cabinet/scripts/evidence-shadow-detectors.py" in block
    # ONE command, no && chain (plist wrapper execs a single program).
    command_line = next(l for l in block.splitlines() if "command:" in l)
    assert "&&" not in command_line
    gitignore = (REPO_ROOT / ".gitignore").read_text()
    assert "shared/interfaces/evidence-shadow-findings.jsonl" in gitignore
