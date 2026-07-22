"""Tests for cabinet/scripts/task-sync-drift-falsifier.py (adapter kit, 2026-07-17).

Pins the falsifier's honesty contract:
  * all-NoOp deployment (the live shape today) → one honest
    no-adapters-configured line, exit 0 — loud-degrade, never a crash-loop;
  * drift detection via the canonical JSON seam + the in-memory reference
    adapter (negative control: agreeing sides verdict `ok`);
  * configured-vs-broken canonical split (2026-07-17 review): NOT CONFIGURED
    (no conn/psql, no seam) → canonical-unreadable exit 0; CONFIGURED but
    FAILING (psql non-zero / garbage output) → `error` exit 1 + probe ERROR
    — credential rot must never mute the watchdog — and the connection
    string NEVER appears in ledger/stdout/stderr;
  * escalation ONLY after a persisted breach (previous DATE also breached);
    same-day re-runs are the self-heal attempt and never escalate; an
    intervening ok DATE resets the ladder even with older breaches on file
    (trailing-consecutive, not any-breach-ever);
  * linked_kind routing: an unmapped destination never samples another
    tracker's linked rows (false presence drift) — kinded rows + no map
    entry is a loud `error`; a mapped destination ignores foreign kinds;
  * --probe tokens for cabinet-doctor (NOFILE/NOSYNC/OK/DRIFT/STALE/BADLINE);
  * injection control: hostile canonical titles land SCRUBBED in the ledger,
    are never executed, and never reach the captain-card argv.
"""
from __future__ import annotations

import importlib.util as _ilu
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "task-sync-drift-falsifier.py"
_REPO = Path(__file__).resolve().parents[3]

# hyphenated filename — load via importlib (same pattern as test_world_census.py)
spec = _ilu.spec_from_file_location("task_sync_drift_falsifier", _SCRIPT)
tsd = _ilu.module_from_spec(spec)
sys.modules["task_sync_drift_falsifier"] = tsd
spec.loader.exec_module(tsd)

sys.path.insert(0, str(_REPO))
from cabinet.scripts.task_adapters import base as adapters_base  # noqa: E402
from cabinet.scripts.task_adapters.reference_inmemory import (  # noqa: E402
    InMemoryReferenceAdapter,
)


def _seed_root(tmp_path, monkeypatch, project_yaml: str | None) -> Path:
    root = tmp_path / "cabroot"
    (root / "cabinet" / "logs").mkdir(parents=True)
    if project_yaml is not None:
        config = root / "instance" / "config"
        (config / "projects").mkdir(parents=True)
        (config / "active-project.txt").write_text("test-proj\n")
        (config / "projects" / "test-proj.yml").write_text(project_yaml)
    monkeypatch.setenv("CABINET_ROOT", str(root))
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("NEON_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("TASK_SYNC_DRIFT_CANONICAL_JSON", raising=False)
    monkeypatch.delenv("TASK_SYNC_DRIFT_ATTENTION_SUBMIT", raising=False)
    # test_end_to_end_subprocess_exit_0 spawns a REAL child that inherits
    # os.environ; a dev box exporting either COG2 seam would arm the spawned
    # cog2 parity child and flake it to rc=1. Scrub both so the child stays an
    # honest unconfigured no-op.
    monkeypatch.delenv("COG2_PARITY_DATA_JSON", raising=False)
    monkeypatch.delenv("COG2_PARITY_CORTEX_CMD", raising=False)
    # main() also runs the COG-2 shadow-parity SUBPROCESS on its default path.
    # These drift/COG-1 tests do not exercise COG-2 (its wiring has dedicated
    # coverage in test_cog2_parity_wiring.py), and a spawned child would falsely
    # ERROR here — the fixture's tmp CABINET_ROOT has no framework/ on disk for
    # the child's consequence reader. Neutralize it so the existing suite stays
    # hermetic (no subprocess spawn) and focused. The real end-to-end subprocess
    # test spawns its own process and is unaffected.
    monkeypatch.setattr(tsd, "run_cog2_parity", lambda: 0)
    return root


def _ledger_lines(root: Path) -> list[dict]:
    path = root / "cabinet" / "logs" / "task-sync-drift.jsonl"
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _patched_reference_adapter(monkeypatch, mirror_rows: list[dict]) -> InMemoryReferenceAdapter:
    """Route get_adapter to a reference adapter whose tracker mirrors
    `mirror_rows` ({external_id,title,status})."""
    adapter = InMemoryReferenceAdapter({"system": "reference-inmemory", "config": {}})
    for row in mirror_rows:
        adapter.tracker.items[str(row["external_id"])] = {
            "canonical_id": f"c-{row['external_id']}",
            "title": row["title"],
            "description": "",
            "status": row["status"],
            "priority": "normal",
            "tags": [],
        }
    monkeypatch.setattr(adapters_base, "get_adapter", lambda cfg: adapter)
    monkeypatch.setenv("REFERENCE_TASKS_TOKEN", "test-token-not-a-secret")
    return adapter


def _seed_canonical(tmp_path, monkeypatch, rows: list[dict]) -> None:
    seam = tmp_path / "canonical.json"
    seam.write_text(json.dumps(rows))
    monkeypatch.setenv("TASK_SYNC_DRIFT_CANONICAL_JSON", str(seam))


_SYNC_YML = "product:\n  name: T\ntasks:\n  system: github-issues\n  config:\n    repo: o/r\n"


def _fake_psql(tmp_path, monkeypatch, script_body: str) -> Path:
    """Plant a fake `psql` first on PATH (configured-canonical test seam)."""
    bindir = tmp_path / "fakebin"
    bindir.mkdir(exist_ok=True)
    psql = bindir / "psql"
    psql.write_text("#!/bin/sh\n" + script_body)
    psql.chmod(psql.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ.get('PATH', '')}")
    return psql


class TestHonestNoOp:
    def test_no_tasks_block_is_loud_degrade_exit_0(self, tmp_path, monkeypatch, capsys):
        root = _seed_root(tmp_path, monkeypatch, "product:\n  name: T\n")
        assert tsd.main([]) == 0
        lines = _ledger_lines(root)
        assert len(lines) == 1 and lines[0]["status"] == "no-adapters-configured"
        assert "no-adapters-configured" in capsys.readouterr().out

    def test_missing_active_project_is_honest_not_a_crash(self, tmp_path, monkeypatch):
        root = _seed_root(tmp_path, monkeypatch, None)  # no instance/config at all
        assert tsd.main([]) == 0
        assert _ledger_lines(root)[0]["status"] == "no-adapters-configured"

    def test_canonical_unreadable_is_honest_exit_0(self, tmp_path, monkeypatch):
        root = _seed_root(tmp_path, monkeypatch, _SYNC_YML)
        _patched_reference_adapter(monkeypatch, [])
        # no JSON seam, no conn string, no cabinet/.env in the tmp root
        assert tsd.main([]) == 0
        assert _ledger_lines(root)[0]["status"] == "canonical-unreadable"

    def test_end_to_end_subprocess_exit_0(self, tmp_path, monkeypatch):
        """Real interpreter run of the no-adapter path (what launchd executes)."""
        root = _seed_root(tmp_path, monkeypatch, "product:\n  name: T\n")
        env = dict(os.environ, CABINET_ROOT=str(root))
        result = subprocess.run(
            ["python3.12", str(_SCRIPT)], capture_output=True, text=True,
            env=env, cwd=str(_REPO), timeout=120,
        )
        assert result.returncode == 0, result.stderr
        assert "no-adapters-configured" in result.stdout


class TestCanonicalStoreFailure:
    """CONFIGURED-but-broken canonical reads must be LOUD (2026-07-17 review:
    previously psql failure collapsed into canonical-unreadable/exit 0/NOSYNC
    → doctor GREEN — the watchdog silently disabled by credential rot)."""

    _CONN = "postgresql://cabinet:sekret-cred-a7x9@db.invalid:5432/tasks"

    def test_failing_psql_is_error_exit_1_not_silent_nosync(
            self, tmp_path, monkeypatch, capsys):
        root = _seed_root(tmp_path, monkeypatch, _SYNC_YML)
        _patched_reference_adapter(monkeypatch, [])
        monkeypatch.setenv("NEON_CONNECTION_STRING", self._CONN)
        _fake_psql(tmp_path, monkeypatch, "exit 2\n")
        assert tsd.main([]) == 1
        line = _ledger_lines(root)[-1]
        assert line["status"] == "error"
        assert "psql exited 2" in line["note"]
        assert "configured but unreadable" in line["note"]
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
        # the probe must render ERROR (→ doctor WARN), never NOSYNC/green
        assert tsd.main(["--probe"]) == 0
        assert capsys.readouterr().out.startswith("ERROR age=")

    def test_conn_string_never_leaks_into_ledger_or_output(
            self, tmp_path, monkeypatch, capsys):
        """The conn string rides psql argv ONLY — a failing read must not
        echo it (str(TimeoutExpired)/stderr both embed it upstream)."""
        root = _seed_root(tmp_path, monkeypatch, _SYNC_YML)
        _patched_reference_adapter(monkeypatch, [])
        monkeypatch.setenv("NEON_CONNECTION_STRING", self._CONN)
        _fake_psql(tmp_path, monkeypatch,
                   "echo \"psql: error: connection to $1 failed\" >&2\nexit 2\n")
        assert tsd.main([]) == 1
        captured = capsys.readouterr()
        ledger_raw = (root / "cabinet" / "logs" / "task-sync-drift.jsonl").read_text()
        for surface, text in (("ledger", ledger_raw),
                              ("stdout", captured.out), ("stderr", captured.err)):
            assert "sekret-cred-a7x9" not in text, f"conn string leaked into {surface}"
            assert "db.invalid" not in text, f"conn host leaked into {surface}"

    def test_garbage_psql_output_is_error_not_nosync(self, tmp_path, monkeypatch):
        root = _seed_root(tmp_path, monkeypatch, _SYNC_YML)
        _patched_reference_adapter(monkeypatch, [])
        monkeypatch.setenv("NEON_CONNECTION_STRING", self._CONN)
        _fake_psql(tmp_path, monkeypatch, "echo 'definitely | not json'\n")
        assert tsd.main([]) == 1
        line = _ledger_lines(root)[-1]
        assert line["status"] == "error"
        assert "not parseable JSON" in line["note"]

    def test_psql_present_but_no_conn_string_stays_not_configured(
            self, tmp_path, monkeypatch):
        """Negative control for the split: a psql binary alone (no conn
        string, no seam) is still the honest NOT-CONFIGURED no-op."""
        root = _seed_root(tmp_path, monkeypatch, _SYNC_YML)
        _patched_reference_adapter(monkeypatch, [])
        _fake_psql(tmp_path, monkeypatch, "echo '[]'\n")
        assert tsd.main([]) == 0
        line = _ledger_lines(root)[-1]
        assert line["status"] == "canonical-unreadable"
        assert "configured" in line["note"]  # "no canonical source configured"

    def test_working_psql_feeds_the_comparison(self, tmp_path, monkeypatch):
        """End-to-end over the Postgres loader: fake psql emits one
        officer_tasks row that agrees with the mirror → verdict ok."""
        root = _seed_root(tmp_path, monkeypatch, _SYNC_YML)
        adapter = _patched_reference_adapter(
            monkeypatch, [{"external_id": "1", "title": "Same", "status": "open"}])
        adapter.destination = "github-issues"  # mapped → linked_kind 'github'
        monkeypatch.setenv("NEON_CONNECTION_STRING", self._CONN)
        _fake_psql(tmp_path, monkeypatch,
                   "echo '[{\"id\":1,\"title\":\"Same\",\"status\":\"queue\","
                   "\"blocked\":false,\"linked_kind\":\"github\",\"linked_id\":\"1\"}]'\n")
        assert tsd.main([]) == 0
        line = _ledger_lines(root)[-1]
        assert line["status"] == "ok" and line["sampled"] == 1


class TestDriftDetection:
    def test_agreeing_sides_verdict_ok(self, tmp_path, monkeypatch):
        """Negative control: no drift → ok, exit 0, no escalation path."""
        root = _seed_root(tmp_path, monkeypatch, _SYNC_YML)
        rows = [{"external_id": "1", "title": "Same title", "status": "open"}]
        _patched_reference_adapter(monkeypatch, rows)
        _seed_canonical(tmp_path, monkeypatch, rows)
        assert tsd.main([]) == 0
        line = _ledger_lines(root)[0]
        assert line["status"] == "ok" and line["sampled"] == 1 and line["drift_count"] == 0

    def test_first_drift_flags_but_does_not_escalate(self, tmp_path, monkeypatch):
        root = _seed_root(tmp_path, monkeypatch, _SYNC_YML)
        _patched_reference_adapter(
            monkeypatch, [{"external_id": "1", "title": "Mirror title", "status": "done"}])
        _seed_canonical(
            tmp_path, monkeypatch,
            [{"external_id": "1", "title": "Canonical title", "status": "open"}])
        assert tsd.main([]) == 1
        line = _ledger_lines(root)[0]
        assert line["status"] == "drift"
        assert line["drift_count"] == 2  # status + title diverge
        assert line["consecutive_breach_dates"] == 1
        assert line["escalated"] is None

    def test_missing_mirror_row_is_presence_drift(self, tmp_path, monkeypatch):
        root = _seed_root(tmp_path, monkeypatch, _SYNC_YML)
        _patched_reference_adapter(monkeypatch, [])
        _seed_canonical(
            tmp_path, monkeypatch,
            [{"external_id": "9", "title": "Lost task", "status": "open"}])
        assert tsd.main([]) == 1
        drifts = _ledger_lines(root)[0]["drifts"]
        assert drifts and drifts[0]["field"] == "presence" and drifts[0]["mirror"] == "missing"


def _fake_attention(tmp_path, monkeypatch) -> Path:
    capture = tmp_path / "attention-argv.txt"
    script = tmp_path / "fake-attention-submit.sh"
    script.write_text(
        "#!/bin/sh\n"
        # one argv element per line — proves untrusted text rode as single args
        'for a in "$@"; do printf \'%s\\n---ARG---\\n\' "$a"; done > '
        f'"{capture}"\n'
        "exit 0\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("TASK_SYNC_DRIFT_ATTENTION_SUBMIT", str(script))
    return capture


class TestEscalation:
    def _drift_setup(self, tmp_path, monkeypatch, title="Canonical title"):
        root = _seed_root(tmp_path, monkeypatch, _SYNC_YML)
        _patched_reference_adapter(
            monkeypatch, [{"external_id": "1", "title": "Mirror title", "status": "done"}])
        _seed_canonical(
            tmp_path, monkeypatch,
            [{"external_id": "1", "title": title, "status": "open"}])
        return root

    def _seed_prior_breach(self, root: Path, date: str, status: str = "drift") -> None:
        line = {"ts": f"{date}T04:20:00Z", "date": date, "status": status,
                "destination": "reference-inmemory", "sampled": 1, "drift_count": 1,
                "drifts": [], "consecutive_breach_dates": 1, "escalated": None, "note": ""}
        path = root / "cabinet" / "logs" / "task-sync-drift.jsonl"
        with open(path, "a") as fh:
            fh.write(json.dumps(line) + "\n")

    def test_second_breach_date_files_the_captain_card(self, tmp_path, monkeypatch):
        root = self._drift_setup(tmp_path, monkeypatch)
        self._seed_prior_breach(root, "2020-01-01")
        capture = _fake_attention(tmp_path, monkeypatch)
        assert tsd.main([]) == 1
        line = _ledger_lines(root)[-1]
        assert line["escalated"] == "card-filed"
        assert line["consecutive_breach_dates"] == 2
        argv = capture.read_text()
        assert "task-sync-drift" in argv and "persisted" in argv

    def test_same_day_rerun_never_escalates(self, tmp_path, monkeypatch):
        """The same-day re-run IS the self-heal attempt."""
        root = self._drift_setup(tmp_path, monkeypatch)
        capture = _fake_attention(tmp_path, monkeypatch)
        assert tsd.main([]) == 1  # first drift today
        assert tsd.main([]) == 1  # re-run, same date
        for line in _ledger_lines(root):
            assert line["escalated"] is None
        assert not capture.exists()

    def test_prior_ok_date_resets_the_ladder(self, tmp_path, monkeypatch):
        root = self._drift_setup(tmp_path, monkeypatch)
        self._seed_prior_breach(root, "2020-01-01", status="ok")
        capture = _fake_attention(tmp_path, monkeypatch)
        assert tsd.main([]) == 1
        assert _ledger_lines(root)[-1]["escalated"] is None
        assert not capture.exists()

    def test_breach_then_ok_then_drift_does_not_escalate(self, tmp_path, monkeypatch):
        """TRAILING-consecutive semantics, not any-breach-ever: an older
        breach followed by a recovered (ok) date must NOT arm the ladder —
        drift today is breach #1 again, no captain card (mutant control:
        counting every historical breach date would escalate here)."""
        root = self._drift_setup(tmp_path, monkeypatch)
        self._seed_prior_breach(root, "2020-01-01", status="drift")
        self._seed_prior_breach(root, "2020-01-02", status="ok")
        capture = _fake_attention(tmp_path, monkeypatch)
        assert tsd.main([]) == 1
        line = _ledger_lines(root)[-1]
        assert line["escalated"] is None
        assert line["consecutive_breach_dates"] == 1
        assert not capture.exists()

    def test_hostile_title_is_scrubbed_inert_and_kept_out_of_the_card(
            self, tmp_path, monkeypatch):
        marker = tmp_path / "pwned.flag"
        hostile = f"pwn $(touch {marker}) `id` \x1b[31mred\x07"
        root = self._drift_setup(tmp_path, monkeypatch, title=hostile)
        self._seed_prior_breach(root, "2020-01-01")
        capture = _fake_attention(tmp_path, monkeypatch)
        assert tsd.main([]) == 1
        assert not marker.exists(), "hostile canonical title was EXECUTED"
        raw = (root / "cabinet" / "logs" / "task-sync-drift.jsonl").read_text()
        assert "\x1b" not in raw and "\x07" not in raw, "control chars reached the ledger"
        assert "$(touch" in raw, "scrub must keep printable text verbatim (inert data)"
        card_argv = capture.read_text()
        assert "$(touch" not in card_argv, "raw task text leaked into the captain card"
        assert not marker.exists()


class TestLinkedKindRouting:
    """_LINKED_KIND_BY_DESTINATION contract: never compare another tracker's
    linked rows against this adapter's mirror (2026-07-17 review — the old
    unmapped-destination default sampled ALL linked rows → guaranteed false
    presence drift → false captain card on any future unmapped adapter)."""

    def test_unmapped_destination_with_kinded_rows_is_loud_error(
            self, tmp_path, monkeypatch):
        root = _seed_root(tmp_path, monkeypatch, _SYNC_YML)
        _patched_reference_adapter(monkeypatch, [])  # destination reference-inmemory: unmapped
        _seed_canonical(tmp_path, monkeypatch, [
            {"external_id": "7", "title": "GH task", "status": "open",
             "linked_kind": "github"},
        ])
        assert tsd.main([]) == 1
        line = _ledger_lines(root)[-1]
        assert line["status"] == "error"
        assert "_LINKED_KIND_BY_DESTINATION" in line["note"]
        assert line["drift_count"] == 0  # a config bug is not mirror drift

    def test_mapped_destination_ignores_foreign_kinds(self, tmp_path, monkeypatch):
        """Foreign-kind rows (linear) missing from a github mirror are NOT
        presence drift — they belong to a different tracker."""
        root = _seed_root(tmp_path, monkeypatch, _SYNC_YML)
        adapter = _patched_reference_adapter(
            monkeypatch, [{"external_id": "1", "title": "Same", "status": "open"}])
        adapter.destination = "github-issues"  # mapped → 'github'
        _seed_canonical(tmp_path, monkeypatch, [
            {"external_id": "1", "title": "Same", "status": "open",
             "linked_kind": "github"},
            {"external_id": "99", "title": "Linear-linked", "status": "open",
             "linked_kind": "linear"},
        ])
        assert tsd.main([]) == 0
        line = _ledger_lines(root)[-1]
        assert line["status"] == "ok" and line["sampled"] == 1

    def test_unmapped_destination_with_only_kindless_rows_still_compares(
            self, tmp_path, monkeypatch):
        """Kind-less rows (JSON-seam deployments) stay comparable for any
        destination — the error fires only when kinded rows exist."""
        root = _seed_root(tmp_path, monkeypatch, _SYNC_YML)
        _patched_reference_adapter(
            monkeypatch, [{"external_id": "1", "title": "Same", "status": "open"}])
        _seed_canonical(
            tmp_path, monkeypatch,
            [{"external_id": "1", "title": "Same", "status": "open"}])
        assert tsd.main([]) == 0
        assert _ledger_lines(root)[-1]["status"] == "ok"


class TestProbe:
    def test_nofile(self, tmp_path, monkeypatch, capsys):
        _seed_root(tmp_path, monkeypatch, None)
        assert tsd.main(["--probe"]) == 0
        assert capsys.readouterr().out.strip() == "NOFILE"

    def test_nosync_after_noop_run(self, tmp_path, monkeypatch, capsys):
        _seed_root(tmp_path, monkeypatch, "product:\n  name: T\n")
        tsd.main([])
        capsys.readouterr()
        assert tsd.main(["--probe"]) == 0
        assert capsys.readouterr().out.startswith("NOSYNC status=no-adapters-configured")

    def test_ok_and_drift_tokens(self, tmp_path, monkeypatch, capsys):
        root = _seed_root(tmp_path, monkeypatch, _SYNC_YML)
        rows = [{"external_id": "1", "title": "Same", "status": "open"}]
        _patched_reference_adapter(monkeypatch, rows)
        _seed_canonical(tmp_path, monkeypatch, rows)
        tsd.main([])
        capsys.readouterr()
        tsd.main(["--probe"])
        assert capsys.readouterr().out.startswith("OK age=")
        drift_line = {"ts": tsd._now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "date": tsd._now().strftime("%Y-%m-%d"), "status": "drift",
                      "sampled": 3, "drift_count": 2, "consecutive_breach_dates": 2}
        with open(root / "cabinet" / "logs" / "task-sync-drift.jsonl", "a") as fh:
            fh.write(json.dumps(drift_line) + "\n")
        tsd.main(["--probe"])
        assert capsys.readouterr().out.startswith("DRIFT n=2 drift_count=2")

    def test_stale_and_badline_tokens(self, tmp_path, monkeypatch, capsys):
        root = _seed_root(tmp_path, monkeypatch, None)
        ledger = root / "cabinet" / "logs" / "task-sync-drift.jsonl"
        ledger.write_text(json.dumps(
            {"ts": "2020-01-01T00:00:00Z", "date": "2020-01-01", "status": "ok"}) + "\n")
        tsd.main(["--probe"])
        assert capsys.readouterr().out.startswith("STALE age=")
        ledger.write_text("not json at all\n")
        tsd.main(["--probe"])
        assert capsys.readouterr().out.strip() == "BADLINE"

    def test_probe_needs_no_framework_imports(self, tmp_path, monkeypatch):
        """Doctor runs --probe on any box: subprocess run with an empty
        PYTHONPATH from a scratch cwd must still work."""
        root = _seed_root(tmp_path, monkeypatch, None)
        env = dict(os.environ, CABINET_ROOT=str(root))
        env.pop("PYTHONPATH", None)
        result = subprocess.run(
            ["python3.12", str(_SCRIPT), "--probe"], capture_output=True, text=True,
            env=env, cwd=str(tmp_path), timeout=60,
        )
        assert result.returncode == 0 and result.stdout.strip() == "NOFILE"


class TestSampleRotation:
    def test_sample_bounded_and_deterministic(self, tmp_path, monkeypatch):
        root = _seed_root(tmp_path, monkeypatch, _SYNC_YML)
        rows = [{"external_id": str(i), "title": f"T{i}", "status": "open"}
                for i in range(1, 31)]
        _patched_reference_adapter(monkeypatch, rows)
        _seed_canonical(tmp_path, monkeypatch, rows)
        monkeypatch.setenv("TASK_SYNC_DRIFT_SAMPLE_N", "7")
        assert tsd.main([]) == 0
        assert tsd.main([]) == 0
        first, second = _ledger_lines(root)[-2:]
        assert first["sampled"] == 7 == second["sampled"]

    def test_junk_sample_env_falls_back_loudly(self, tmp_path, monkeypatch, capsys):
        root = _seed_root(tmp_path, monkeypatch, _SYNC_YML)
        rows = [{"external_id": "1", "title": "Same", "status": "open"}]
        _patched_reference_adapter(monkeypatch, rows)
        _seed_canonical(tmp_path, monkeypatch, rows)
        monkeypatch.setenv("TASK_SYNC_DRIFT_SAMPLE_N", "$(evil)")
        assert tsd.main([]) == 0
        assert "WARN" in capsys.readouterr().err
        assert _ledger_lines(root)[0]["sampled"] == 1


class TestCog2ParitySubprocess:
    """run_cog2_parity() honesty split (2026-07-22 review): a CONFIGURED child
    that HANGS past the timeout ceiling is LOUD (exit 1) — a momentary green
    over a wedged reader would mute the watchdog. Only a genuine launch failure
    (OSError: sibling absent / interpreter missing) stays an honest no-op
    (exit 0). Hermetic — subprocess.run is patched, no child is ever spawned.
    (_seed_root stubs run_cog2_parity itself, so these call the REAL function.)"""

    def test_hung_child_past_the_ceiling_is_a_loud_exit_1(
            self, monkeypatch, capsys):
        def _boom(*a, **k):
            raise subprocess.TimeoutExpired(cmd=["cog2"], timeout=300)
        monkeypatch.setattr(tsd.subprocess, "run", _boom)
        assert tsd.run_cog2_parity() == 1               # loud, not a green no-op
        err = capsys.readouterr().err
        assert "ERROR" in err and "timed out" in err

    def test_launch_failure_stays_an_honest_no_op_exit_0(
            self, monkeypatch, capsys):
        def _boom(*a, **k):
            raise FileNotFoundError("no interpreter")   # OSError launch failure
        monkeypatch.setattr(tsd.subprocess, "run", _boom)
        assert tsd.run_cog2_parity() == 0               # honest no-op
        assert "WARN" in capsys.readouterr().err
