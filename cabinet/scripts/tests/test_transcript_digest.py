"""Tests for cabinet/scripts/transcript-digest.py (ORG-SENSES-1 organ).

Fixture-JSONL driven; NO network, NO redis, NO psql — the queue seam is
monkeypatched and experience records land under a tmp CABINET_ROOT (the repo
conftest fences the event ledger). Pins the load-bearing contracts:

  * structural taint firewall — tool_result blocks NEVER reach a digest
    (captain-model/voice content only arrives via tool results);
  * taint belt — lines naming captain-model/voice surfaces are dropped;
  * names-not-values redaction — secret-shaped values are scrubbed, the
    NAMES survive (the doctor's discipline);
  * stable source_id (td:<session_id>) so re-digest upserts, not duplicates;
  * incremental state — unchanged files skip; grown files re-digest;
  * queue failure leaves the file un-digested (retry next sweep);
  * prompt-pattern lessons: recurrence rule, per-(session,sig) dedup,
    per-sig record cap; records are framework.learning.experience rows
    (skill-induction evidence, propose-only — the organ never writes
    memory/skills/**);
  * flight-recorder typescript ingestion (seed source).

Run: python3.12 -m pytest cabinet/scripts/tests/test_transcript_digest.py -q
"""
from __future__ import annotations

import importlib.util as _ilu
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "transcript-digest.py"

spec = _ilu.spec_from_file_location("transcript_digest", _SCRIPT)
td = _ilu.module_from_spec(spec)
sys.modules["transcript_digest"] = td
spec.loader.exec_module(td)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _jsonl_line(**kw) -> str:
    return json.dumps(kw)


def _session_lines(session_id: str, officer: str = "cos",
                   secret_in_prompt: bool = False,
                   taint_in_text: bool = False) -> list[str]:
    """A minimal but shape-faithful officer session."""
    boot = (f"You are {officer}. Read your role definition at "
            f".claude/agents/{officer}.md and your session start checklist.")
    prompt2 = "Fix the failing deploy gate for the bakery lane"
    asst_text = "Decision: I approved the gate fix. Lesson learned: check PATH."
    if secret_in_prompt:
        # Marker-matched so the line ENTERS the digest — the scrub must then
        # strip the values while keeping the env-var names.
        asst_text += ("\nLesson: gotcha — set "
                      "NEON_CONNECTION_STRING=postgres://user:hunter2@host/db "
                      "and VOYAGE_API_KEY=pa-abc123def456 before the run")
    if taint_in_text:
        # Marker-matched on purpose: these WOULD enter the digest as
        # decision/lesson lines — the taint belt must drop them there.
        asst_text += ("\nDecision: per the captain-model, prefer terse replies."
                      "\nLesson learned from the voice-profile: warm phrasing.")
    lines = [
        _jsonl_line(type="user", sessionId=session_id,
                    timestamp="2026-07-07T08:00:00.000Z",
                    message={"role": "user", "content": boot}),
        _jsonl_line(type="user", sessionId=session_id,
                    timestamp="2026-07-07T08:01:00.000Z",
                    message={"role": "user", "content": prompt2}),
        _jsonl_line(type="assistant", sessionId=session_id,
                    timestamp="2026-07-07T08:02:00.000Z",
                    message={"role": "assistant", "content": [
                        {"type": "thinking", "thinking": "private chain"},
                        {"type": "text", "text": asst_text},
                        {"type": "tool_use", "name": "Bash", "id": "t1",
                         "input": {"command": "echo hi"}},
                    ]}),
        # tool_result carrying a canary that must NEVER surface in a digest
        _jsonl_line(type="user", sessionId=session_id,
                    timestamp="2026-07-07T08:03:00.000Z",
                    message={"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": "t1",
                         "content": "TOOLRESULT-CANARY nate_model dump xyz"},
                    ]}),
        _jsonl_line(type="assistant", sessionId=session_id,
                    timestamp="2026-07-07T08:04:00.000Z",
                    message={"role": "assistant", "content": [
                        {"type": "text", "text": "Done. Root cause was PATH."},
                    ]}),
    ]
    return lines


def _write_session(dirpath: Path, session_id: str, **kw) -> Path:
    p = dirpath / f"{session_id}.jsonl"
    p.write_text("\n".join(_session_lines(session_id, **kw)) + "\n")
    return p


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Isolated source/state/log dirs + tmp CABINET_ROOT for records."""
    src = tmp_path / "projects"
    src.mkdir()
    orch = tmp_path / "orch-projects"
    orch.mkdir()
    fr = tmp_path / "hatch-logs"
    fr.mkdir()
    monkeypatch.setenv("CABINET_TRANSCRIPT_DIRS", str(src))
    monkeypatch.setenv("CABINET_ORCH_TRANSCRIPT_DIRS", str(orch))
    monkeypatch.setenv("CABINET_FLIGHT_RECORDER_DIRS", str(fr))
    monkeypatch.setenv("CABINET_TD_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("CABINET_TD_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))  # records → tmp tier3
    return {"src": src, "orch": orch, "fr": fr, "tmp": tmp_path,
            "state": tmp_path / "state.json"}


@pytest.fixture()
def queued(monkeypatch):
    """Capture queue_digest payloads instead of touching redis."""
    calls: list[dict] = []

    def fake_queue(digest, repo_root=None):
        calls.append(digest)
        return True

    monkeypatch.setattr(td, "queue_digest", fake_queue)
    return calls


# ---------------------------------------------------------------------------
# Redaction + taint
# ---------------------------------------------------------------------------

def test_redaction_names_not_values():
    text = ("NEON_CONNECTION_STRING=postgres://user:hunter2@db.host/x\n"
            "VOYAGE_API_KEY=pa-abc123def456\n"
            "Authorization: Bearer abcdef123456789\n"
            "token ghp_" + "a" * 24 + " and AKIAABCDEFGHIJKLMNOP\n")
    red, hits, drops = td.redact_text(text)
    assert hits >= 4
    assert drops == 0
    # names survive
    assert "NEON_CONNECTION_STRING" in red
    assert "VOYAGE_API_KEY" in red
    # values are gone
    assert "hunter2" not in red
    assert "pa-abc123def456" not in red
    assert "ghp_" + "a" * 24 not in red
    assert "AKIAABCDEFGHIJKLMNOP" not in red


def test_taint_belt_drops_captain_model_lines():
    text = ("normal line about work\n"
            "the captain-model says X\n"
            "voice-profile tone notes\n"
            "nate_model internals\n"
            "me_signal blob\n"
            "another normal line\n")
    red, _, drops = td.redact_text(text)
    assert drops == 4
    assert "captain-model" not in red
    assert "voice-profile" not in red
    assert "normal line about work" in red


def test_tool_results_structurally_excluded(env, queued):
    _write_session(env["src"], "sess-taint", secret_in_prompt=True,
                   taint_in_text=True)
    summary = td.run_sweep()
    assert summary["sessions_digested"] == 1
    content = queued[0]["content"]
    # tool_result canary never surfaces — structural firewall
    assert "TOOLRESULT-CANARY" not in content
    # taint belt dropped the captain-model/voice lines from assistant text
    assert "captain-model" not in content
    assert "voice-profile" not in content
    assert queued[0]["metadata"]["taint_lines_dropped"] >= 1
    # secrets scrubbed, names kept
    assert "hunter2" not in content
    assert "pa-abc123def456" not in content
    assert queued[0]["metadata"]["redacted_secrets"] >= 1


# ---------------------------------------------------------------------------
# Digest shape + provenance
# ---------------------------------------------------------------------------

def test_digest_shape_and_provenance(env, queued):
    p = _write_session(env["src"], "sess-shape")
    td.run_sweep()
    d = queued[0]
    assert d["source_id"] == "td:sess-shape"          # stable → upsert
    assert d["officer"] == "cos"                       # boot-prompt detection
    assert d["source_ts"] == "2026-07-07T08:04:00.000Z"  # content_ts = last event
    md = d["metadata"]
    assert md["source_path"] == str(p)                 # provenance
    assert md["source_kind"] == "session-jsonl"
    assert md["digest_version"] == td.DIGEST_VERSION
    assert md["content_ts"] == "2026-07-07T08:04:00.000Z"
    assert md["apoptosis_class"] == "digest-exhaust"
    assert "sunset" in md
    # decision/lesson markers extracted
    assert "decision-marked lines" in d["content"]
    assert "lesson-marked lines" in d["content"]
    assert "Bash×1" in d["content"]


def test_incremental_skip_and_regrow(env, queued):
    p = _write_session(env["src"], "sess-incr")
    s1 = td.run_sweep()
    assert s1["sessions_digested"] == 1
    s2 = td.run_sweep()
    assert s2["sessions_digested"] == 0
    assert s2["skipped_unchanged"] == 1
    # session grows → re-digest, SAME source_id (upsert lane)
    with p.open("a") as fh:
        fh.write(_jsonl_line(
            type="assistant", sessionId="sess-incr",
            timestamp="2026-07-07T09:00:00.000Z",
            message={"role": "assistant",
                     "content": [{"type": "text", "text": "more work"}]}) + "\n")
    s3 = td.run_sweep()
    assert s3["sessions_digested"] == 1
    assert queued[-1]["source_id"] == "td:sess-incr"
    assert queued[-1]["source_ts"] == "2026-07-07T09:00:00.000Z"


def test_queue_failure_leaves_file_for_retry(env, monkeypatch):
    _write_session(env["src"], "sess-fail")
    monkeypatch.setattr(td, "queue_digest", lambda d, repo_root=None: False)
    s1 = td.run_sweep()
    assert s1["queue_failures"] == 1
    assert s1["queued"] == 0
    # nothing marked digested — next sweep retries
    state = json.loads(env["state"].read_text()) if env["state"].exists() else {"files": {}}
    assert all("digested_at" not in v for v in state.get("files", {}).values())
    monkeypatch.setattr(td, "queue_digest", lambda d, repo_root=None: True)
    s2 = td.run_sweep()
    assert s2["sessions_digested"] == 1


def test_dry_run_writes_nothing(env, queued):
    _write_session(env["src"], "sess-dry")
    s = td.run_sweep(dry_run=True)
    assert s["sessions_digested"] == 1
    assert queued == []                      # queue seam never called for real
    assert not env["state"].exists()         # no state
    assert not (env["tmp"] / "logs").exists()  # no heartbeat


def test_heartbeat_after_completed_sweep(env, queued):
    _write_session(env["src"], "sess-hb")
    td.run_sweep()
    log = env["tmp"] / "logs" / "transcript-digest.log"
    assert log.exists()
    line = log.read_text().strip()
    assert "DIGESTED" in line and "sessions=1" in line


# ---------------------------------------------------------------------------
# Prompt-pattern lessons → experience records (propose-only evidence)
# ---------------------------------------------------------------------------

def _records_on_disk(root: Path) -> list[dict]:
    recs = []
    d = root / "memory" / "tier3" / "experience-records"
    for f in sorted(d.glob("records-*.jsonl")) if d.exists() else []:
        for line in f.read_text().splitlines():
            if line.strip():
                recs.append(json.loads(line))
    return recs


def test_pattern_records_recurrence_and_dedup(env, queued):
    # same distinctive prompt in two sessions → cross-session recurrence
    for sid in ("sess-a", "sess-b"):
        _write_session(env["src"], sid)
    s = td.run_sweep()
    recs = _records_on_disk(env["tmp"])
    # signature "fix the failing deploy gate..." seen in 2 sessions →
    # emitted for the 2nd (and only the 2nd) session at minimum
    assert s["pattern_records"] == len(recs) >= 1
    assert all(r["lesson_type"] == "pattern" for r in recs)
    assert all(r["applicability_scope"] == "this_role" for r in recs)
    assert all(r["trigger_signal"].startswith("prompt-pattern: ") for r in recs)
    assert all(r["actor"] == "cos" for r in recs)
    # re-sweep: unchanged files skip; no duplicate records
    before = len(recs)
    td.run_sweep()
    assert len(_records_on_disk(env["tmp"])) == before


def test_pattern_record_per_sig_cap(env, queued):
    for i in range(td.MAX_RECORDS_PER_SIG + 4):
        _write_session(env["src"], f"sess-cap-{i:02d}")
    td.run_sweep()
    recs = _records_on_disk(env["tmp"])
    per_sig: dict[str, int] = {}
    for r in recs:
        per_sig[r["trigger_signal"]] = per_sig.get(r["trigger_signal"], 0) + 1
    assert per_sig
    assert all(v <= td.MAX_RECORDS_PER_SIG for v in per_sig.values())


def test_machine_prompts_yield_no_signature():
    for noise in ("You are cos. Read your role definition",
                  "<command-message>loop</command-message>",
                  "🔔 Trigger received — new officer message",
                  "[Request interrupted by user]",
                  "Stop hook feedback: keep going",
                  "This session is being continued from a previous one",
                  "Caveat: the messages below were generated",
                  "# /loop — schedule a recurring prompt"):
        assert td.prompt_signature(noise) is None, noise
    sig = td.prompt_signature("Fix the failing deploy gate for lane 7")
    assert sig is not None and "#" in sig  # digits normalized


# ---------------------------------------------------------------------------
# Flight-recorder typescripts (seed source)
# ---------------------------------------------------------------------------

def test_flight_recorder_ingest(env, queued):
    ts = env["fr"] / "mini-hatch-20260707-210000.typescript"
    body = ("Script started on 2026-07-07\n"
            "\x1b[1m$ bash setup.sh\x1b[0m\n"
            "step 1 ok\n"
            "ERROR: launchctl bootstrap failed: 5: Input/output error\n"
            "retried after re-lock — approved by captain\n"
            "export API_TOKEN=supersecretvalue123\n"
            "Script done on 2026-07-07\n")
    ts.write_text(body)
    s = td.run_sweep()
    assert s["flight_digested"] == 1
    d = queued[0]
    assert d["source_id"].startswith("td:fr:")
    assert d["metadata"]["source_kind"] == "flight-recorder"
    assert "error-marked lines" in d["content"]
    # ANSI stripped, secret value scrubbed with name kept
    assert "\x1b" not in d["content"]
    assert "supersecretvalue123" not in d["content"]
    assert "API_TOKEN" in d["content"]


def test_unusable_file_marked_once(env, queued):
    junk = env["src"] / "empty.jsonl"
    junk.write_text("")
    s1 = td.run_sweep()
    assert s1["sessions_digested"] == 0
    s2 = td.run_sweep()
    assert s2["skipped_unchanged"] >= 1  # not re-parsed nightly


# ---------------------------------------------------------------------------
# Orchestrator sources (ORCH-SESSION-DIGEST, 2026-07-09)
# ---------------------------------------------------------------------------

def _write_orch_session(dirpath: Path, session_id: str) -> Path:
    """A captain-side (orchestrator) session — NO officer boot prompt."""
    lines = [
        _jsonl_line(type="user", sessionId=session_id,
                    timestamp="2026-07-09T08:00:00.000Z",
                    message={"role": "user", "content":
                             "Ship the improve-how-we-improve package"}),
        _jsonl_line(type="assistant", sessionId=session_id,
                    timestamp="2026-07-09T08:01:00.000Z",
                    message={"role": "assistant", "content": [
                        {"type": "text",
                         "text": "Decision: ledger rows appended. "
                                 "Lesson learned: dirty-guard first."},
                        {"type": "tool_use", "name": "Bash", "id": "t1",
                         "input": {"command": "git status"}},
                    ]}),
    ]
    p = dirpath / f"{session_id}.jsonl"
    p.write_text("\n".join(lines) + "\n")
    return p


def test_orchestrator_source_provenance(env, queued):
    p = _write_orch_session(env["orch"], "sess-orch")
    s = td.run_sweep()
    assert s["orchestrator_digested"] == 1
    assert s["sessions_digested"] == 0
    d = queued[0]
    assert d["source_id"] == "td:sess-orch"          # same stable upsert lane
    assert d["metadata"]["source_kind"] == "orchestrator-session"
    assert d["metadata"]["source_path"] == str(p)
    assert d["officer"] == ""


def test_orchestrator_officer_boot_keeps_session_kind(env, queued):
    # An officer-boot session sitting in an orchestrator dir keeps officer
    # provenance — the dir gives the hint, the session content decides.
    _write_session(env["orch"], "sess-orch-officer")
    s = td.run_sweep()
    assert s["sessions_digested"] == 1
    assert s["orchestrator_digested"] == 0
    d = queued[0]
    assert d["metadata"]["source_kind"] == "session-jsonl"
    assert d["officer"] == "cos"


def test_orchestrator_redaction_applies(env, queued):
    # The orchestrator lane rides the SAME belt + scrub pipeline.
    _write_session(env["orch"], "sess-orch-red", secret_in_prompt=True,
                   taint_in_text=True)
    td.run_sweep()
    content = queued[0]["content"]
    assert "TOOLRESULT-CANARY" not in content         # structural firewall
    assert "captain-model" not in content             # taint belt
    assert "hunter2" not in content                   # names-not-values
    assert "NEON_CONNECTION_STRING" in content


def test_orchestrator_overlap_dedup(env, queued, monkeypatch):
    # The repo project dir sits in BOTH source lists on the live deployment;
    # point both env vars at ONE dir and prove single digestion per path.
    monkeypatch.setenv("CABINET_ORCH_TRANSCRIPT_DIRS", str(env["src"]))
    _write_session(env["src"], "sess-overlap")
    s = td.run_sweep()
    assert len(queued) == 1                       # one digest, not two
    assert s["sessions_digested"] == 1            # officer boot → session kind
    assert s["orchestrator_digested"] == 0
    assert s["skipped_unchanged"] == 0
