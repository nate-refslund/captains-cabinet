"""Cross-trial query plane (Phase 3) — fail-closed display, never-a-score,
doorway parity, and zero-store-mutation proofs.

Bypass replay obligation: every NEW arg shape re-runs the PR#140/#149
catalog shapes (path traversal, newline smuggling, compound commands,
flag-shaped args, oversize tokens) against the CLI parser AND the officer
doorway script.  The doorway itself is byte-identical in this phase —
selector tokens fit its existing one-token grammar — so these tests pin
that fit instead of relaxing anything.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from framework.evidence import EvidenceRecorder
from framework.evidence import query
from framework.evidence.__main__ import main as evidence_cli
from framework.evidence.recorder import EvidenceError

REPO_ROOT = Path(__file__).resolve().parents[3]
DOORWAY = REPO_ROOT / "cabinet" / "scripts" / "evidence-read.sh"
# The exact token class the officer doorway and both hook doorway regexes
# enforce.  Selector shapes MUST keep fitting it: a selector that needs a
# doorway/hook change fails here first, deliberately.
DOORWAY_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

# Never-a-score deny tokens (mirrors the EVAL-025 harness tokenizer): no
# key anywhere in an officer-served query result may tokenize into these.
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


def run_cli(capsys: pytest.CaptureFixture, argv: list[str]) -> tuple[int, dict]:
    code = evidence_cli(argv)
    return code, json.loads(capsys.readouterr().out.strip())


def append(recorder: EvidenceRecorder, trial: str, *, actor: dict, component: str,
           phase: str = "intent", status: str = "started") -> dict:
    context = recorder.trace(trial, surface="test")
    return recorder.append(
        context,
        phase=phase,
        status=status,
        actor=actor,
        component={"name": component, "version": "1"},
    )


def seed_store(store: Path) -> EvidenceRecorder:
    """Three trials with distinct actors/components/statuses.

    qp-a-1: officer cos on action-lane (started, succeeded)
    qp-b-1: system undo-sweep on recon (failed)
    qp-c-1: officer cto on action-lane (verification verified)
    """
    recorder = EvidenceRecorder(store)
    append(recorder, "qp-a-1", actor={"kind": "officer", "id": "cos"}, component="action-lane")
    append(recorder, "qp-a-1", actor={"kind": "officer", "id": "cos"}, component="action-lane",
           phase="outcome", status="succeeded")
    append(recorder, "qp-b-1", actor={"kind": "system", "id": "undo-sweep"}, component="recon",
           phase="outcome", status="failed")
    append(recorder, "qp-c-1", actor={"kind": "officer", "id": "cto"}, component="action-lane",
           phase="verification", status="verified")
    return recorder


def tamper_duplicate_first_line(store: Path, trial: str) -> None:
    """Break continuity without touching filter-relevant bytes: re-append a
    copy of the first event line (sequence + previous_hash now fail)."""
    ledger = store / "trials" / trial / "events.jsonl"
    raw = ledger.read_bytes()
    first = raw.split(b"\n", 1)[0]
    ledger.write_bytes(raw + first + b"\n")


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            digest.update(f"L\0{rel}\0{os.readlink(path)}\0".encode())
        elif path.is_file():
            digest.update(f"F\0{rel}\0".encode())
            digest.update(path.read_bytes())
            digest.update(b"\0")
        else:
            digest.update(f"D\0{rel}\0".encode())
    return digest.hexdigest()


def walk_keys(value: object):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_keys(item)


def today_token() -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"by-time:{day}-{day}"


# --- happy paths: one filter dimension per doorway-shaped token ---------------


def test_by_actor_serves_only_matching_trials_with_projection_records(tmp_path, capsys):
    store = tmp_path / "store"
    seed_store(store)

    code, out = run_cli(capsys, ["--store", str(store), "project", "by-actor:cos"])
    assert code == 0
    assert out["schema"] == "cabinet.evidence-query/v1"
    assert out["mode"] == "read_only_redacted"
    assert out["selector"] == {"name": "by-actor", "value": "cos"}
    assert [t["trial_id"] for t in out["trials"]] == ["qp-a-1"]
    trial = out["trials"][0]
    assert trial["verification"] == "verified"
    assert [r["sequence"] for r in trial["records"]] == [1, 2]
    for record in trial["records"]:
        assert record["trust"] == "untrusted_observation"
        # The served shape is the sanctioned projection record: raw-row
        # fields like actor/ts/hashes must never leak into the query plane.
        assert "actor" not in record and "ts" not in record
        assert "event_hash" not in record and "signature" not in record
    assert out["counts"] == {
        "trials_scanned": 3,
        "trials_served": 1,
        "trials_unverified": 0,
        "records": 2,
        "truncated": False,
    }


def test_by_actor_kind_qualified_form(tmp_path, capsys):
    store = tmp_path / "store"
    seed_store(store)
    code, out = run_cli(capsys, ["--store", str(store), "project", "by-actor:officer:cto"])
    assert code == 0
    assert [t["trial_id"] for t in out["trials"]] == ["qp-c-1"]


def test_by_component_and_by_status_filters(tmp_path, capsys):
    store = tmp_path / "store"
    seed_store(store)

    code, out = run_cli(capsys, ["--store", str(store), "project", "by-component:action-lane"])
    assert code == 0
    assert [t["trial_id"] for t in out["trials"]] == ["qp-a-1", "qp-c-1"]

    code, out = run_cli(capsys, ["--store", str(store), "project", "by-status:failed"])
    assert code == 0
    assert [t["trial_id"] for t in out["trials"]] == ["qp-b-1"]
    assert out["counts"]["records"] == 1


def test_by_time_range_inclusive_and_honest_empty(tmp_path, capsys):
    store = tmp_path / "store"
    seed_store(store)

    code, out = run_cli(capsys, ["--store", str(store), "project", today_token()])
    assert code == 0
    assert [t["trial_id"] for t in out["trials"]] == ["qp-a-1", "qp-b-1", "qp-c-1"]

    code, out = run_cli(capsys, ["--store", str(store), "project", "by-time:19700101-19700102"])
    assert code == 0
    assert out["trials"] == []
    assert out["counts"]["records"] == 0
    # The instruction boundary rides every result, including honest-empty.
    assert out["instruction_boundary"] == query.INSTRUCTION_BOUNDARY


def test_deterministic_ordering_and_repeatability(tmp_path, capsys):
    store = tmp_path / "store"
    seed_store(store)
    first = run_cli(capsys, ["--store", str(store), "project", "by-component:action-lane"])
    second = run_cli(capsys, ["--store", str(store), "project", "by-component:action-lane"])
    assert first == second
    trial_ids = [t["trial_id"] for t in first[1]["trials"]]
    assert trial_ids == sorted(trial_ids)


# --- fail-closed display -------------------------------------------------------


def test_tampered_trial_renders_explicit_unverified_stub(tmp_path, capsys):
    store = tmp_path / "store"
    seed_store(store)
    tamper_duplicate_first_line(store, "qp-a-1")

    code, out = run_cli(capsys, ["--store", str(store), "project", "by-component:action-lane"])
    assert code == 0
    by_id = {t["trial_id"]: t for t in out["trials"]}
    # Never silently dropped, never silently included: the tampered trial
    # is present, explicitly unverified, with the reason and zero records.
    assert set(by_id) == {"qp-a-1", "qp-c-1"}
    stub = by_id["qp-a-1"]
    assert stub["verification"] == "unverified"
    assert stub["errors"] == ["ledger_integrity"]
    assert stub["reason"]
    assert stub["records"] == []
    assert by_id["qp-c-1"]["verification"] == "verified"
    assert len(by_id["qp-c-1"]["records"]) == 1
    assert out["counts"]["trials_unverified"] == 1


def test_single_trial_projection_refusal_is_unchanged(tmp_path, capsys):
    store = tmp_path / "store"
    seed_store(store)

    code, out = run_cli(capsys, ["--store", str(store), "project", "qp-a-1"])
    assert code == 0 and out["mode"] == "read_only_redacted"
    assert out["trial_id"] == "qp-a-1"

    tamper_duplicate_first_line(store, "qp-a-1")
    code, out = run_cli(capsys, ["--store", str(store), "project", "qp-a-1"])
    # Back-compat pin: the single-trial view keeps the hard typed refusal.
    assert (code, out["code"]) == (3, "ledger_integrity")


def test_banner_is_byte_identical_to_single_trial_projection(tmp_path, capsys):
    store = tmp_path / "store"
    seed_store(store)
    _, single = run_cli(capsys, ["--store", str(store), "project", "qp-a-1"])
    _, cross = run_cli(capsys, ["--store", str(store), "project", "by-actor:cos"])
    assert cross["instruction_boundary"] == single["instruction_boundary"]
    assert query.INSTRUCTION_BOUNDARY == single["instruction_boundary"]


def test_cross_trial_record_shape_equals_single_trial_record_shape(tmp_path, capsys):
    store = tmp_path / "store"
    seed_store(store)
    _, single = run_cli(capsys, ["--store", str(store), "project", "qp-a-1"])
    _, cross = run_cli(capsys, ["--store", str(store), "project", "by-actor:cos"])
    single_keys = {frozenset(r) for r in single["records"]}
    cross_keys = {frozenset(r) for r in cross["trials"][0]["records"]}
    assert cross_keys == single_keys


# --- never-a-score -------------------------------------------------------------


def is_score_shaped(key: str) -> bool:
    tokens = [t for t in re.split(r"[_\-.]+", str(key).lower()) if t]
    return any(t in DENY_TOKENS for t in tokens)


def test_never_a_score_key_pins(tmp_path, capsys):
    store = tmp_path / "store"
    seed_store(store)
    tamper_duplicate_first_line(store, "qp-b-1")

    _, out = run_cli(capsys, ["--store", str(store), "project", "by-component:action-lane"])
    _, failed = run_cli(capsys, ["--store", str(store), "project", "by-status:failed"])

    # Top-level and counts shapes are pinned exactly: adding any rollup
    # section (per-actor summaries, rates, rankings) fails here.
    assert set(out) == {"schema", "mode", "selector", "instruction_boundary", "trials", "counts"}
    assert set(out["counts"]) == {
        "trials_scanned", "trials_served", "trials_unverified", "records", "truncated",
    }
    for result in (out, failed):
        for trial in result["trials"]:
            assert set(trial) in (
                {"trial_id", "verification", "records"},
                {"trial_id", "verification", "errors", "reason", "records"},
            )
        for key in walk_keys(result):
            assert not is_score_shaped(key), f"score-shaped key served to officers: {key}"
        # Counts are plain integers/booleans — no floats, no ratios.
        for name, value in result["counts"].items():
            if name == "truncated":
                assert isinstance(value, bool)
            else:
                assert isinstance(value, int) and not isinstance(value, bool)


# --- strict arg validation: PR#140/#149 bypass shapes against the CLI ----------


@pytest.mark.parametrize("token,expected_code", [
    ("by-actor:", "selector_value_invalid"),            # empty value
    ("by-bogus:x", "selector_unknown"),                 # unknown selector name
    ("by-status:winning", "selector_value_invalid"),    # out-of-vocabulary enum
    ("by-time:2026", "selector_value_invalid"),         # malformed range
    ("by-time:20261301-20261401", "selector_value_invalid"),  # unreal dates
    ("by-time:20260715-20260701", "selector_value_invalid"),  # reversed range
    ("by-actor:../../etc/passwd", "selector_invalid"),  # path traversal shape
    ("by-actor:..", "selector_value_invalid"),          # dot-dot value (leading non-alnum)
    ("by-actor:-flag", "selector_value_invalid"),       # flag-shaped value
    ("by-actor:cos\ncat /etc/passwd", "selector_invalid"),   # newline smuggle
    ("by-actor:cos; cat /etc/passwd", "selector_invalid"),   # compound command
    ("by-actor:cos cat", "selector_invalid"),           # second word smuggle
    ("by-actor:" + "a" * 200, "selector_invalid"),      # oversize token
])
def test_selector_validation_refuses_bypass_shapes(tmp_path, capsys, token, expected_code):
    store = tmp_path / "store"
    seed_store(store)
    before = tree_hash(store)
    code, out = run_cli(capsys, ["--store", str(store), "project", token])
    assert (code, out["ok"]) == (3, False)
    assert out["code"] == expected_code
    # Hostile values are never echoed back into officer-visible output.
    assert "/etc/passwd" not in json.dumps(out)
    assert tree_hash(store) == before


def test_traversal_shaped_values_never_touch_paths_outside_the_store(tmp_path, capsys):
    store = tmp_path / "store"
    seed_store(store)
    # Legal charset, traversal-flavored: compared in memory only, so the
    # query succeeds with zero matches instead of resolving any path.
    code, out = run_cli(capsys, ["--store", str(store), "project", "by-component:a..b"])
    assert code == 0
    assert out["trials"] == [] and out["counts"]["records"] == 0


def test_reserved_namespace_takes_precedence_over_trial_lookup(tmp_path, capsys, monkeypatch):
    store = tmp_path / "store"
    seed_store(store)

    def forbidden(self, trial_id, *, limit=200):  # pragma: no cover - must not run
        raise AssertionError("selector token must never reach the single-trial projection")

    monkeypatch.setattr(EvidenceRecorder, "cabinet_projection", forbidden)
    code, out = run_cli(capsys, ["--store", str(store), "project", "by-bogus:anything"])
    assert (code, out["code"]) == (3, "selector_unknown")


def test_parse_selector_is_fail_closed_for_non_string_input():
    with pytest.raises(EvidenceError) as caught:
        query.parse_selector(None)  # type: ignore[arg-type]
    assert caught.value.code == "selector_invalid"
    assert query.is_selector_token(None) is False
    assert query.is_selector_token("by-actor:cos") is True
    assert query.is_selector_token("qp-a-1") is False


def test_documented_selector_shapes_fit_the_doorway_token_grammar():
    # Pins the zero-doorway-change property: every documented selector
    # example (and the maximum-length legal token) fits the byte-identical
    # doorway/hook grammar. A selector design that breaks this needs a
    # hook ceremony and must fail here first.
    examples = [
        "by-actor:cos",
        "by-actor:officer:cos",
        "by-component:action-lane",
        "by-status:failed",
        "by-time:20260701-20260715",
        "by-actor:" + "a" * 119,  # 128 chars total — doorway maximum
    ]
    for token in examples:
        assert DOORWAY_TOKEN_RE.fullmatch(token), token
        assert query.is_selector_token(token)
        query.parse_selector(token)  # must not raise


# --- bounded output ------------------------------------------------------------


def test_limit_clamps_and_truncates_honestly(tmp_path, capsys):
    store = tmp_path / "store"
    recorder = EvidenceRecorder(store)
    for _ in range(6):
        append(recorder, "qp-many-1", actor={"kind": "officer", "id": "cos"},
               component="action-lane")

    code, out = run_cli(capsys, ["--store", str(store), "project", "by-actor:cos", "--limit", "3"])
    assert code == 0
    assert out["counts"]["records"] == 3
    assert out["counts"]["truncated"] is True
    assert len(out["trials"][0]["records"]) == 3

    # Mirror of the single-trial clamp: 0 clamps up to 1, oversize clamps
    # down to the 1..1000 window (the doorway numeric bound).
    code, out = run_cli(capsys, ["--store", str(store), "project", "by-actor:cos", "--limit", "0"])
    assert code == 0 and out["counts"]["records"] == 1
    code, out = run_cli(capsys, ["--store", str(store), "project", "by-actor:cos", "--limit", "5000"])
    assert code == 0 and out["counts"]["records"] == 6
    assert out["counts"]["truncated"] is False


def test_verification_budget_bounds_served_trials(tmp_path, capsys, monkeypatch):
    store = tmp_path / "store"
    seed_store(store)
    monkeypatch.setattr(query, "MAX_QUERY_TRIALS", 1)
    code, out = run_cli(capsys, ["--store", str(store), "project", "by-component:action-lane"])
    assert code == 0
    assert [t["trial_id"] for t in out["trials"]] == ["qp-a-1"]
    assert out["counts"]["truncated"] is True


# --- zero store mutation (read_only_held) ---------------------------------------


def test_query_paths_leave_store_bytes_identical(tmp_path, capsys):
    store = tmp_path / "store"
    seed_store(store)
    # Priming read: the verifier's signed anti-rollback watermark advances
    # to tip exactly as any existing read does; from tip, re-verification
    # writes nothing. Store-level verify primes every trial's mark.
    run_cli(capsys, ["--store", str(store), "verify"])

    before = tree_hash(store)
    run_cli(capsys, ["--store", str(store), "project", "by-actor:cos"])
    run_cli(capsys, ["--store", str(store), "project", "by-status:failed"])
    run_cli(capsys, ["--store", str(store), "project", "by-component:action-lane"])
    run_cli(capsys, ["--store", str(store), "project", today_token()])
    run_cli(capsys, ["--store", str(store), "project", "by-time:19700101-19700102"])
    run_cli(capsys, ["--store", str(store), "project", "by-bogus:x"])
    run_cli(capsys, ["--store", str(store), "project", "by-actor:../../x"])
    run_cli(capsys, ["--store", str(store), "project", "qp-a-1"])
    assert tree_hash(store) == before


def test_unverified_stub_path_writes_nothing(tmp_path, capsys):
    store = tmp_path / "store"
    seed_store(store)
    run_cli(capsys, ["--store", str(store), "project", "by-component:action-lane"])
    tamper_duplicate_first_line(store, "qp-a-1")

    before = tree_hash(store)
    _, out = run_cli(capsys, ["--store", str(store), "project", "by-component:action-lane"])
    assert out["counts"]["trials_unverified"] == 1
    assert tree_hash(store) == before


# --- officer doorway parity (subprocess replay of the bypass catalog) -----------


def doorway_store_path() -> Path:
    """The doorway's own fixed store path, parsed from its shipped bytes.

    Pinning the captured argv against what `evidence-read.sh` DECLARES (not
    a re-typed copy of its path literal) keeps this framework test free of
    any instance-path literal (layer-separation law) and makes the pin
    stronger: if the doorway's store line ever drifts, this parse fails
    loudly instead of two literals drifting apart silently."""
    body = DOORWAY.read_text(encoding="utf-8")
    match = re.search(r'--store "\$REPO(/[^"]+)"', body)
    assert match, "evidence-read.sh no longer declares its fixed --store path"
    return REPO_ROOT / match.group(1).lstrip("/")


def doorway_env(tmp_path: Path) -> tuple[dict, Path]:
    """PATH-shim python3.12 canary: captures the exec argv, runs nothing."""
    shim_dir = tmp_path / "shim-bin"
    shim_dir.mkdir(exist_ok=True)
    capture = tmp_path / "captured-argv"
    shim = shim_dir / "python3.12"
    shim.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\0\' "$@" > "$QP_CAPTURE"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = f"{shim_dir}:{env.get('PATH', '')}"
    env["QP_CAPTURE"] = str(capture)
    return env, capture


def run_doorway(args: list[str], env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(DOORWAY), *args],
        env=env, capture_output=True, text=True, timeout=30,
    )


@pytest.mark.parametrize("args", [
    [],                                            # no token
    ["--store"],                                   # flag-shaped token
    ["by-actor:cos\ncat /etc/passwd"],             # newline smuggle
    ["by-actor:cos; cat /etc/passwd"],             # compound command
    ["by actor:cos"],                              # embedded space
    ["../qp-a-1"],                                 # path traversal
    ["by-actor:" + "a" * 200],                     # oversize token
    ["by-actor:cos", "abc"],                       # non-numeric limit
    ["by-actor:cos", "0"],                         # limit below bound
    ["by-actor:cos", "1001"],                      # limit above doorway bound
])
def test_doorway_rejects_bypass_shapes_before_any_exec(tmp_path, args):
    env, capture = doorway_env(tmp_path)
    proc = run_doorway(args, env)
    assert proc.returncode == 2, proc.stderr
    assert not capture.exists(), "doorway executed python for a rejected shape"


@pytest.mark.parametrize("args,expected_token,expected_limit", [
    (["by-actor:cos"], "by-actor:cos", "200"),
    (["by-status:failed", "100"], "by-status:failed", "100"),
    (["by-time:20260701-20260715", "7"], "by-time:20260701-20260715", "7"),
    (["qp-a-1", "5"], "qp-a-1", "5"),
])
def test_doorway_passes_selector_tokens_with_pinned_fixed_argv(
    tmp_path, args, expected_token, expected_limit,
):
    env, capture = doorway_env(tmp_path)
    proc = run_doorway(args, env)
    assert proc.returncode == 0, proc.stderr
    argv = [part for part in capture.read_text(encoding="utf-8").split("\0") if part]
    assert argv == [
        "-m", "framework.evidence",
        "--store", str(doorway_store_path()),
        "project", expected_token,
        "--limit", expected_limit,
    ]
