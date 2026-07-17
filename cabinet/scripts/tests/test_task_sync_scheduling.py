"""task-sync scheduling + cadence-truth locks (adapter kit, 2026-07-17).

Grep-level, offline locks (yaml parse + render smoke; no launchctl, no
network) pinning the adapter-kit repair of the task-sync story:

  * before: runner + cron headers claimed "every 5 min via launchd", the
    hand-kept template plist said 900s, and NOTHING was scheduled — three
    conflicting stories, zero reality;
  * after: cabinet/services.yml owns the truth (task-sync @ interval_s 900,
    task-sync-drift nightly), both rows render through generate-plists.py,
    the stale headers are corrected, the orphaned template plist is gone
    (verify-launchagents.sh included), and cabinet-doctor carries the
    drift-falsifier probe with its documented captain-card escalation.

Run: python3 -m pytest cabinet/scripts/tests/test_task_sync_scheduling.py -q
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
SERVICES_YML = _REPO_ROOT / "cabinet/services.yml"
RUNNER = _SCRIPTS_DIR / "task_sync_runner.py"
CRON_WRAPPER = _REPO_ROOT / "cabinet/cron/task-sync.sh"
FALSIFIER = _SCRIPTS_DIR / "task-sync-drift-falsifier.py"
DOCTOR = _SCRIPTS_DIR / "cabinet-doctor.sh"
VERIFY_LA = _SCRIPTS_DIR / "verify-launchagents.sh"
RUNBOOK = _REPO_ROOT / "cabinet/runbooks/task-adapter-authoring.md"


def _load_services() -> list[dict]:
    data = yaml.safe_load(SERVICES_YML.read_text())
    assert isinstance(data.get("services"), list), "services.yml: no services list"
    return data["services"]


def _row(name: str) -> dict:
    rows = [s for s in _load_services() if s.get("name") == name]
    assert rows, f"cabinet/services.yml lost the {name} row — the cadence truth is gone"
    assert len(rows) == 1, f"duplicate {name} rows"
    return rows[0]


def _render(row: dict) -> dict:
    spec = importlib.util.spec_from_file_location(
        "generate_plists", _SCRIPTS_DIR / "generate-plists.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.render(row, Path("/repo"), Path("/home/x"))


class TestTaskSyncRow:
    def test_enabled_cron_at_900s(self):
        svc = _row("task-sync")
        assert svc.get("label") == "com.cabinet.task-sync"
        assert svc.get("kind") == "cron"
        assert not svc.get("disabled"), "task-sync row is disabled — seam unscheduled again"
        assert svc.get("schedule") == {"interval_s": 900}, (
            "task-sync cadence truth is interval_s: 900 (the value the deleted "
            f"template plist carried); got {svc.get('schedule')!r}"
        )
        assert svc.get("command") == "bash cabinet/cron/task-sync.sh"
        assert CRON_WRAPPER.exists()

    def test_renders_through_generate_plists(self):
        pl = _render(_row("task-sync"))
        assert pl["Label"] == "com.cabinet.task-sync"
        assert pl["StartInterval"] == 900
        assert any("task-sync.sh" in a for a in pl["ProgramArguments"]), pl["ProgramArguments"]


class TestDriftFalsifierRow:
    def test_enabled_nightly_cron(self):
        svc = _row("task-sync-drift")
        assert svc.get("label") == "com.cabinet.task-sync-drift"
        assert svc.get("kind") == "cron"
        assert not svc.get("disabled")
        sched = svc.get("schedule")
        assert isinstance(sched, dict) and "calendar" in sched, sched
        for entry in sched["calendar"]:
            assert "hour" in entry and "weekday" not in entry and "day" not in entry, (
                "the drift falsifier must run NIGHTLY: a sparser cadence lets a "
                f"dead sync hide for a week (got {entry!r})"
            )
        assert "cabinet/scripts/task-sync-drift-falsifier.py" in svc["command"]
        assert FALSIFIER.exists(), "the falsifier the row schedules does not exist"

    def test_renders_through_generate_plists(self):
        pl = _render(_row("task-sync-drift"))
        assert pl["Label"] == "com.cabinet.task-sync-drift"
        assert "StartCalendarInterval" in pl
        assert any("task-sync-drift-falsifier.py" in a for a in pl["ProgramArguments"])

    def test_falsifier_header_pins_probe_and_honest_noop(self):
        head = FALSIFIER.read_text()[:3500]
        assert "--probe" in head and "no-adapters-configured" in head, (
            "falsifier header lost its probe/honest-no-op contract"
        )

    def test_verdict_ledger_path_stays_runtime_gitignored(self):
        gitignore = (_REPO_ROOT / ".gitignore").read_text()
        assert "cabinet/logs/*" in gitignore, (
            "cabinet/logs/* left .gitignore — the drift verdict ledger would "
            "become tracked repo content"
        )


class TestStaleStoriesAreGone:
    def test_no_five_minute_claim_survives(self):
        for path in (RUNNER, CRON_WRAPPER):
            text = path.read_text()
            assert "every 5 min" not in text and "every 5 minutes" not in text, (
                f"{path.name} still claims the pre-2026-07-17 5-min cadence that "
                "never existed anywhere"
            )
            assert "services.yml" in text, (
                f"{path.name} must cite cabinet/services.yml as the cadence truth"
            )

    def test_cron_wrapper_pins_the_house_interpreter(self):
        text = CRON_WRAPPER.read_text()
        assert "CABINET_PYTHON" in text and "python3.12" in text, (
            "task-sync.sh lost the CABINET_PYTHON pin — bare python3 under "
            "launchd is the system 3.9 (repo-documented failure class)"
        )

    def test_orphaned_template_plist_is_gone_everywhere(self):
        assert not (_REPO_ROOT / "cabinet/launchd/com.cabinet.task-sync.template.plist").exists(), (
            "the orphaned task-sync template plist is back — services.yml + "
            "generate-plists.py is the single install source"
        )
        # the quoted form is the OPTIONAL_PLISTS array-entry shape; prose
        # provenance comments may still narrate the 2026-07-17 removal
        assert '"com.cabinet.task-sync"' not in VERIFY_LA.read_text(), (
            "verify-launchagents.sh re-grew an OPTIONAL_PLISTS entry for the "
            "deleted task-sync template"
        )


class TestDoctorProbeWiring:
    def test_check_12_reads_the_probe(self):
        text = DOCTOR.read_text()
        assert "task-sync-drift-falsifier.py --probe" in text, (
            "cabinet-doctor lost the drift-falsifier probe (check 12)"
        )

    def test_escalation_ladder_is_documented_in_the_probe_text(self):
        text = DOCTOR.read_text()
        assert "captain card" in text and "self-heal" in text, (
            "doctor check 12 must document the escalation ladder: AMBER + "
            "self-heal hint first, captain card (filed by the FALSIFIER) only "
            "after the breach persists"
        )
        # the doctor itself stays read-only: the probe never submits anything
        assert "attention-submit.sh" not in "".join(
            l for l in text.splitlines()
            if "task-sync-drift" in l and not l.lstrip().startswith("#")
        ), "doctor check 12 must never invoke the attention gateway itself"


class TestRunbookTracksTheKit:
    def test_runbook_exists_and_names_the_surfaces(self):
        assert RUNBOOK.exists(), (
            "cabinet/runbooks/task-adapter-authoring.md missing — base.py, "
            "_template.py and the factory error message all point at it"
        )
        text = RUNBOOK.read_text()
        for needle in ("_template.py", "ADAPTER_REGISTRY", "conformance",
                       "task-sync-drift", "services.yml"):
            assert needle in text, f"runbook lost its {needle} section"
