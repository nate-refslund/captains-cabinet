"""Tests for cabinet/scripts/attention-well-spent.py — the Captain-facing
north-star instrument ("attention well spent").

EVIDENCE NOTE ON TEST STRENGTH. The module under test is BRAND NEW, so
"the test fails when the file is absent" is worth nothing — an absence
failure proves only that the import line runs. Every guard this instrument
adds is therefore pinned by a TARGETED GUARD MUTATION: `_mutant()` copies the
real source, applies one surgical replacement, ASSERTS the replacement
actually changed the expected number of occurrences (a silent no-op replace
has certified false passes in this program), loads the mutant, and the test
asserts the property FLIPS. Both directions are explicit in every arm:
the real module holds the property, the one-guard-weaker module does not.

The suite also proves the headline claim against the SHIPPED old metric:
`test_inversion_against_ovi_captain_attention_cost` runs one event corpus
through `framework.ovi.compute` and through this instrument, and shows they
move in OPPOSITE directions when the Captain is cut out of the loop.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
_SCRIPT = _REPO / "cabinet" / "scripts" / "attention-well-spent.py"
_CONFIG = _REPO / "cabinet" / "config" / "attention-well-spent.yml"
_MATRIX = _REPO / "framework" / "policies" / "authority-matrix.yml"

NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
TS = (NOW - timedelta(hours=2)).isoformat()


def _load(path: Path, name: str = "attention_well_spent"):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def aws():
    return _load(_SCRIPT)


@pytest.fixture(scope="module")
def law(aws):
    return aws.load_must_ask_law(_MATRIX)


@pytest.fixture(scope="module")
def cfg(aws):
    return aws.load_config(_CONFIG)


def _mutant(tmp_path: Path, old: str, new: str, *, expect: int = 1, name: str = "mutant"):
    """Copy the real module, apply ONE targeted replacement, assert the
    replacement bit, and return the loaded mutant with REPO_ROOT preserved."""
    source = _SCRIPT.read_text()
    assert source.count(old) == expect, (
        f"guard-mutation anchor drifted: expected {expect} occurrence(s) of {old!r}, "
        f"found {source.count(old)} — the mutation would have been a silent no-op")
    mutated = source.replace(old, new)
    assert mutated != source
    target = tmp_path / f"{name}.py"
    target.write_text(mutated)
    module = _load(target, name)
    module.REPO_ROOT = _REPO  # tmp location must not repoint the repo anchors
    return module


# ---------------------------------------------------------------------------
# Row / event builders
# ---------------------------------------------------------------------------


def crow(action_type, *, decision=None, required=None, status="ok", actor="cos",
         subject=None, ts=TS, **extra):
    """A consequence-ledger row (framework/schemas/consequence-event.schema.json)."""
    row = {
        "ts": ts,
        "actor": {"kind": "officer", "id": actor},
        "lane": None,
        "action": f"did-{action_type or 'thing'}",
        "subject": subject or f"subject-{action_type or 'thing'}",
        "outcome": {"status": status, "evidence": None},
    }
    if action_type is not None:
        row["action_type"] = action_type
    if required is None:
        required = decision is not None
    if required:
        row["proposal"] = {"required": True, "decision": decision}
    row.update(extra)
    return row


def oevent(event_type, *, actor="cos", payload=None, created_at=TS, eid=None):
    return {
        "id": eid or f"{event_type}-{actor}-{(payload or {}).get('task_id', '')}",
        "event_type": event_type,
        "actor": actor,
        "payload": payload or {},
        "parent_id": None,
        "created_at": created_at,
    }


def run(aws_mod, law, cfg, rows=(), events=(), **kw):
    return aws_mod.compute(window_days=7, now=NOW, config=cfg, law=law,
                           consequence_rows=list(rows), org_events=list(events), **kw)


# ---------------------------------------------------------------------------
# The floor is the ratified law, not a local copy
# ---------------------------------------------------------------------------


def test_floor_is_the_ratified_hard_ceiling_from_the_locked_matrix(aws, law):
    """The must-ask floor is the authority matrix's own hard_ceiling classes.

    framework/policies/ is schg-locked germline, so narrowing the floor means
    editing a system-immutable file — it is not a knob in this instrument.
    """
    assert law["source"] == str(_MATRIX)
    assert set(law["risk_classes"]) == {
        "external_comms", "deploy_prod", "spend", "secrets",
        "network_write", "credentials_grant"}
    # every ceiling action_type the shipped matrix names is in the floor
    for action_type in ("external_email", "external_message", "purchase", "billing",
                        "provision_paid", "secret_read", "secret_write", "env_write",
                        "mcp_post", "mcp_put", "mcp_delete", "oauth_grant",
                        "token_grant", "vercel_deploy_prod", "git_push_main"):
        assert action_type in law["action_types"], action_type
    # ...and ordinary reversible work is NOT (the floor is not "everything")
    for action_type in ("task_status_move", "label", "local_edit", "draft_only",
                        "internal_message", "vercel_deploy_preview"):
        assert action_type not in law["action_types"], action_type


def test_unreadable_or_empty_law_is_a_hard_error_never_a_green_reading(aws, tmp_path):
    """An instrument that cannot read its own law must not report a reading."""
    with pytest.raises(aws.LawUnreadable):
        aws.load_must_ask_law(tmp_path / "absent.yml")

    empty = tmp_path / "empty-ceiling.yml"
    empty.write_text("policy:\n  hard_ceiling: []\n  risk_classes:\n    spend:\n"
                     "      action_types: [purchase]\n")
    with pytest.raises(aws.LawUnreadable):
        aws.load_must_ask_law(empty)

    # MUTATION: drop the empty-ceiling guard -> an empty floor is accepted and a
    # hard-ceiling breach reads clean. That is the failure this guard prevents.
    mut = _mutant(tmp_path,
                  'if not isinstance(ceiling, list) or not ceiling:',
                  'if False:')
    mlaw = mut.load_must_ask_law(empty)
    assert mlaw["action_types"] == frozenset()
    # the benign approved row keeps the SILENT-WINDOW rule out of the way, so
    # this arm isolates the empty-floor guard rather than a second defence.
    breach = [crow("purchase", required=False), crow("label", decision="approved")]
    assert run(mut, mlaw, mut.load_config(_CONFIG), rows=breach)["verdict"] != "red"
    # real module, same corpus, real law: RED
    assert run(aws, aws.load_must_ask_law(_MATRIX), aws.load_config(_CONFIG),
               rows=breach)["verdict"] == "red"


# ---------------------------------------------------------------------------
# P1 — under-asking is a FAILURE
# ---------------------------------------------------------------------------


def test_executed_hard_ceiling_action_without_a_captain_verdict_breaches_the_floor(
        aws, law, cfg, tmp_path):
    # the approved `label` row is deliberate: it keeps the SILENT-WINDOW rule
    # (a second, independent defence) from firing, so this arm isolates the
    # must-ask classification guard.
    rows = [crow("external_email", required=False),
            crow("purchase", decision=None, required=True),
            crow("label", decision="approved")]
    report = run(aws, law, cfg, rows=rows)
    assert report["under_asking"]["must_ask_floor"] == "breached"
    assert report["verdict"] == "red"
    assert {u["action_type"] for u in report["under_asking"]["unasked"]} == {
        "external_email", "purchase"}
    assert {u["risk_class"] for u in report["under_asking"]["unasked"]} == {
        "external_comms", "spend"}

    # MUTATION: stop classifying rows against the floor -> the same corpus reads clean.
    mut = _mutant(tmp_path, 'if action_type not in must_ask:\n            continue',
                  'if True:\n            continue')
    mreport = run(mut, law, cfg, rows=rows)
    assert mreport["under_asking"]["unasked"] == []
    assert mreport["verdict"] != "red"


def test_asking_clears_the_floor_and_a_verdict_that_is_not_the_captains_does_not(
        aws, law, cfg):
    """approved/edited/rejected clear it; 'expired' does not — an unanswered
    card is not a decision."""
    for decision in ("approved", "edited", "rejected"):
        rep = run(aws, law, cfg, rows=[crow("purchase", decision=decision)])
        assert rep["under_asking"]["must_ask_floor"] == "held", decision
        assert rep["verdict"] == "green", decision
    rep = run(aws, law, cfg, rows=[crow("purchase", decision="expired")])
    assert rep["under_asking"]["must_ask_floor"] == "breached"
    assert rep["verdict"] == "red"


def test_unstamped_executed_rows_make_the_floor_unprovable_not_held(
        aws, law, cfg, tmp_path):
    """action_type is nullable on the schema, so 'never stamp it' would be a
    free way out of the floor. Coverage is part of the answer."""
    rows = [crow(None, decision="approved"), crow("purchase", decision="approved")]
    report = run(aws, law, cfg, rows=rows)
    assert report["under_asking"]["must_ask_floor"] == "unprovable"
    assert report["verdict"] == "amber"
    assert len(report["under_asking"]["unclassified_executed"]) == 1

    # MUTATION: stop recording the coverage gap -> the same corpus reads green.
    mut = _mutant(tmp_path, 'if action_type is None:\n            unclassified_executed',
                  'if False:\n            unclassified_executed')
    mreport = run(mut, law, cfg, rows=rows)
    assert mreport["under_asking"]["must_ask_floor"] == "held"
    assert mreport["verdict"] == "green"


# ---------------------------------------------------------------------------
# P2 — going quiet cannot raise the reading
# ---------------------------------------------------------------------------


def test_silent_window_is_a_breach_so_doing_nothing_visible_is_not_a_clean_sheet(
        aws, law, cfg, tmp_path):
    """Org activity with ZERO Captain touches is under-asking by construction.
    Without this rule the degenerate strategy is 0/0 -> share null -> no penalty."""
    rows = [crow("local_edit", required=False), crow("task_status_move", required=False)]
    report = run(aws, law, cfg, rows=rows)
    assert report["under_asking"]["silent_window"] is True
    assert report["under_asking"]["must_ask_floor"] == "breached"
    assert report["verdict"] == "red"

    # a genuinely empty window is honest absence, NOT a breach
    quiet = run(aws, law, cfg, rows=[], events=[])
    assert quiet["under_asking"]["silent_window"] is False
    assert quiet["verdict"] == "unmeasured"

    # MUTATION: disable the silent-window rule -> going quiet becomes free again.
    mut = _mutant(tmp_path,
                  'silent_window = (\n        org_actions >= int(cfg.get("silent_window_min_actions", 1)) and not touches)',
                  'silent_window = False')
    mreport = run(mut, law, cfg, rows=rows)
    assert mreport["verdict"] != "red"


def test_cutting_the_captain_out_lowers_the_reading_it_never_raises_it(aws, law, cfg):
    """The core inversion, stated as the property this instrument exists to
    deliver: removing the Captain from a decision can only make the reading
    worse."""
    with_captain = run(aws, law, cfg, rows=[
        crow("external_email", decision="approved"),
        crow("secret_write", decision="approved")])
    without_captain = run(aws, law, cfg, rows=[
        crow("external_email", required=False),
        crow("secret_write", required=False)])
    order = {"unmeasured": 0, "red": 0, "amber": 1, "green": 2}
    assert with_captain["verdict"] == "green"
    assert without_captain["verdict"] == "red"
    assert order[without_captain["verdict"]] < order[with_captain["verdict"]]


# ---------------------------------------------------------------------------
# P5 — card spam lowers the share
# ---------------------------------------------------------------------------


def test_expired_cards_cost_attention_so_spamming_the_queue_lowers_the_share(
        aws, law, cfg, tmp_path):
    base = [crow("purchase", decision="approved")]
    spam = base + [crow("task_status_move", decision="expired") for _ in range(6)]
    clean = run(aws, law, cfg, rows=base)
    spammed = run(aws, law, cfg, rows=spam)
    assert clean["share"] == 1.0
    assert spammed["share"] < clean["share"]
    assert spammed["denominator"]["by_kind"]["expired"] == 6

    # MUTATION: price expiries out of the denominator -> spam becomes free.
    mut = _mutant(tmp_path, 'elif decision == EXPIRED:', 'elif False:')
    assert run(mut, law, cfg, rows=spam)["share"] == clean["share"]


# ---------------------------------------------------------------------------
# P4 — the denominator is MEASURED, never declared
# ---------------------------------------------------------------------------


def test_no_producer_can_declare_its_own_minutes(aws, law, cfg):
    """The old burden index took --captain-attention-minutes as a DECLARED
    input defaulting to 0 (cabinet/scripts/lib/org_runtime.py). Here, a row
    carrying such a field changes nothing: minutes come only from the published
    constant table."""
    honest = [crow("purchase", decision="approved")]
    liar = [crow("purchase", decision="approved",
                 captain_attention_minutes=0, minutes=0, burden_index=1.0,
                 verified_value=9999)]
    assert (run(aws, law, cfg, rows=liar)["denominator"]["measured_minutes"]
            == run(aws, law, cfg, rows=honest)["denominator"]["measured_minutes"]
            == cfg["minute_costs"]["decided"])
    assert run(aws, law, cfg, rows=liar)["denominator"]["declared_inputs"] == []


def test_source_reads_no_declarable_cost_field(aws):
    """Structural backstop for the behavioural arm above: the module must not
    read any of the declarable knobs the old metric trusted."""
    source = _SCRIPT.read_text()
    for knob in ("captain_attention_minutes", "burden_index", "verified_value",
                 "captain-attention-minutes", "verified-value"):
        assert f'get("{knob}")' not in source
        assert f"get('{knob}')" not in source
        assert f'["{knob}"]' not in source


def test_an_officer_cannot_mint_captain_minutes_under_its_own_actor_id(
        aws, law, cfg, tmp_path):
    forged = [oevent("captain_goal_declared", actor="cos"),
              oevent("captain_outcome_ratified", actor="cro")]
    real = [oevent("captain_goal_declared", actor="captain")]
    assert run(aws, law, cfg, events=forged)["denominator"]["touches"] == 0
    assert run(aws, law, cfg, events=real)["denominator"]["touches"] == 1
    assert run(aws, law, cfg, events=real)["numerator"]["captain_only_minutes"] == (
        cfg["minute_costs"]["captain_event"])

    # MUTATION: drop the actor allowlist -> officers mint Captain minutes.
    mut = _mutant(tmp_path,
                  'if str(event.get("actor") or "") not in captain_actors:\n            continue',
                  'if False:\n            continue')
    assert run(mut, law, cfg, events=forged)["denominator"]["touches"] == 2


# ---------------------------------------------------------------------------
# P3 — verified only on a probe, a counterparty, or the Captain
# ---------------------------------------------------------------------------


def _verify_corpus(*, verifier, evidence_text=None, evidence_path=None, doer="cos"):
    payload = {"task_id": "task-1", "status": "verified",
               "evidence_text": evidence_text, "evidence_path": evidence_path}
    return [
        oevent("work_item_completed", actor=doer,
               payload={"task_id": "task-1", "status": "done"}),
        oevent("work_item_verified", actor=verifier, payload=payload),
    ]


def test_an_officers_own_verification_of_its_own_work_counts_zero(
        aws, law, cfg, tmp_path):
    """The live degenerate strategy: emit work_item_verified as the same actor,
    with no evidence (--evidence is optional on work-graph-complete.sh)."""
    events = _verify_corpus(verifier="cos", doer="cos")
    report = run(aws, law, cfg, events=events)
    assert report["verified_outcomes"]["counted"] == 0
    assert report["verified_outcomes"]["self_attested_rejected"] == 1

    # MUTATION: treat any verifier as a counterparty -> self-attestation counts.
    mut = _mutant(tmp_path, 'elif doers and actor not in doers:', 'elif True:')
    assert run(mut, law, cfg, events=events)["verified_outcomes"]["counted"] == 1


def test_prose_evidence_is_not_a_probe_but_a_pointer_is(aws, law, cfg, tmp_path):
    prose = run(aws, law, cfg, events=_verify_corpus(
        verifier="cos", evidence_text="looks good, tests pass"))
    assert prose["verified_outcomes"]["counted"] == 0
    assert prose["verified_outcomes"]["self_attested_rejected"] == 1

    pointer = run(aws, law, cfg, events=_verify_corpus(
        verifier="cos",
        evidence_text="https://github.com/acme/repo/actions/runs/1234567890"))
    assert pointer["verified_outcomes"]["counted"] == 1
    assert pointer["verified_outcomes"]["by_attestor"] == {"probe": 1}

    # near-misses stay prose: too short, whitespace-bearing, wrong prefix
    assert not aws.is_probe_ref("eval:1", cfg)
    assert not aws.is_probe_ref("https://github.com/acme x", cfg)
    assert not aws.is_probe_ref("ok: verified by me thoroughly", cfg)
    assert aws.is_probe_ref("eval:run-2026-07-25-abc123", cfg)

    # MUTATION: open the probe wall -> prose becomes evidence.
    mut = _mutant(tmp_path,
                  'text = _clip(value).strip()',
                  'text = _clip(value).strip()\n    return True')
    assert run(mut, law, cfg, events=_verify_corpus(
        verifier="cos", evidence_text="looks good"))["verified_outcomes"]["counted"] == 1


def test_a_counterparty_or_the_captain_does_count(aws, law, cfg):
    counterparty = run(aws, law, cfg,
                       events=_verify_corpus(verifier="cto", doer="cos"))
    assert counterparty["verified_outcomes"]["by_attestor"] == {"counterparty": 1}
    captain = run(aws, law, cfg, events=_verify_corpus(verifier="captain", doer="cos"))
    assert captain["verified_outcomes"]["by_attestor"] == {"captain": 1}


# ---------------------------------------------------------------------------
# The inversion, proven against the SHIPPED old metric
# ---------------------------------------------------------------------------


def test_inversion_against_ovi_captain_attention_cost(aws, law, cfg, tmp_path,
                                                      monkeypatch):
    """One corpus, two engines, opposite directions.

    framework/ovi/compute.py counts Captain-input events as
    `captain_attention_cost` with `direction: inverse` — so DELETING the
    Captain's involvement RAISES the OVI component score. This instrument goes
    the other way: the same deletion breaches the must-ask floor.
    """
    sys.path.insert(0, str(_REPO))
    from framework.ovi.compute import compute_ovi, gather_from_events

    log_dir = tmp_path / "events"
    log_dir.mkdir()
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(log_dir))

    day = NOW.strftime("%Y-%m-%d")
    ceiling_rows = [crow("external_email", ts=TS, subject=f"s{i}") for i in range(4)]

    def write_events(captain_events: int):
        lines = []
        for i in range(4):
            lines.append(oevent("work_item_completed", actor="cos",
                                payload={"task_id": f"t{i}", "outcome_id": "o1"},
                                created_at=TS, eid=f"c{i}"))
        for i in range(captain_events):
            lines.append(oevent("captain_decision_logged", actor="captain",
                                payload={"decision": "approved"}, created_at=TS,
                                eid=f"k{i}"))
        (log_dir / f"events-{day}.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in lines))

    # --- LOOP CLOSED: the Captain decided all four ceiling actions ----------
    write_events(4)
    ovi_engaged = compute_ovi(gather_from_events(window_days=7), emit_event=False)
    aws_engaged = run(aws, law, cfg,
                      rows=[crow("external_email", decision="approved", subject=f"s{i}")
                            for i in range(4)])

    # --- CAPTAIN CUT OUT: same work, zero Captain involvement ---------------
    write_events(0)
    ovi_quiet = compute_ovi(gather_from_events(window_days=7), emit_event=False)
    aws_quiet = run(aws, law, cfg, rows=ceiling_rows)

    # the OLD metric rewards going quiet...
    assert ovi_quiet["raw_data"]["captain_attention_cost"] == 0.0
    assert ovi_engaged["raw_data"]["captain_attention_cost"] == 4.0
    assert (ovi_quiet["components"]["captain_attention_cost"]
            > ovi_engaged["components"]["captain_attention_cost"])

    # ...and the NEW instrument punishes it.
    assert aws_engaged["verdict"] == "green"
    assert aws_quiet["verdict"] == "red"
    assert len(aws_quiet["under_asking"]["unasked"]) == 4


# ---------------------------------------------------------------------------
# Never-a-score: this reading is Captain-facing only
# ---------------------------------------------------------------------------


def test_the_instrument_emits_nothing_and_is_read_by_no_selection_surface():
    """The ratified law: evidence-derived aggregates are monitoring metrics and
    kill criteria ONLY — never officer-visible scores, never generation or
    selection inputs (cabinet/evals/never-a-score/)."""
    source = _SCRIPT.read_text()
    for writer in ("from framework.events.emitter import emit",
                   "append_event(", "append-interface.sh"):
        assert writer not in source, writer
    # no CALL site of any emitter (the docstring names `emit()` as prose; a
    # call is a statement, so anchor on line starts).
    assert re.search(r"^\s*(?:\w+\.)?emit\(", source, re.MULTILINE) is None

    # the guarded report-only scalar-series tokens are assembled, never written
    # literally: naming one in a new file is itself the violation the eval scans for.
    for token in ("golden-eval" + "-scalar", "golden" + "_scalar"):
        assert token not in source

    # nothing on the officer/generation plane names this instrument.
    # (git grep, never grep -r: the local grep wrapper silently skips
    # gitignored files and drops em-dash-heavy markdown as binary.)
    if not (_REPO / ".git").exists():
        pytest.skip("gitless tree (egg / hatch) — the tracked-file scan needs git")
    try:
        out = subprocess.run(
            ["git", "grep", "-l", "-e", "attention-well-spent", "-e", "attention_well_spent",
             "--", "framework/", "presets/", "cabinet/dashboard/src/", ".claude/"],
            cwd=_REPO, capture_output=True, text=True)
    except FileNotFoundError:  # pragma: no cover - git absent
        pytest.skip("git unavailable")
    assert out.stdout.strip() == "", f"selection-plane reader(s): {out.stdout}"


def test_the_report_refuses_to_be_written_inside_the_repo_tree(aws, tmp_path):
    """A report that can land in the tree is a report some selector can read."""
    with pytest.raises(SystemExit):
        aws.resolve_out_path(str(_REPO / "shared" / "aws.json"))
    with pytest.raises(SystemExit):
        aws.resolve_out_path(str(_REPO))
    assert aws.resolve_out_path(str(tmp_path / "aws.json")) == tmp_path / "aws.json"

    # MUTATION: drop the containment check -> the report lands in the tree.
    mut = _mutant(tmp_path, 'if resolved == root or root in resolved.parents:', 'if False:')
    assert mut.resolve_out_path(str(_REPO / "shared" / "aws.json"))


# ---------------------------------------------------------------------------
# End-to-end through the real ledgers + CLI
# ---------------------------------------------------------------------------


def test_cli_reads_the_real_ledgers_and_reports_the_breach(tmp_path):
    """The property the component exists to deliver, through the real read
    paths (framework.fidelity.consequence.read_ledger + events replay) and the
    real CLI — not just the injected-row API."""
    log_dir = tmp_path / "ledger"
    log_dir.mkdir()
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(hours=1)).isoformat()
    day = now.strftime("%Y-%m-%d")

    (log_dir / f"consequence-events-{day}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in [
            crow("external_email", required=False, ts=ts, subject="unasked-1"),
            crow("purchase", decision="approved", ts=ts, subject="asked-1"),
        ]))
    (log_dir / f"events-{day}.jsonl").write_text(
        json.dumps(oevent("work_item_completed", actor="cos",
                          payload={"task_id": "t1"}, created_at=ts)) + "\n")

    env = dict(os.environ, CABINET_EVENT_LOG_DIR=str(log_dir),
               PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--window-days", "7", "--json"],
        cwd=_REPO, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)

    assert report["schema_version"] == "attention-well-spent/v1"
    assert report["verdict"] == "red"
    assert report["under_asking"]["must_ask_floor"] == "breached"
    assert [u["action_type"] for u in report["under_asking"]["unasked"]] == ["external_email"]
    assert report["denominator"]["touches"] == 1
    assert report["share"] == 1.0          # the one touch he had was Captain-only
    assert "never an input to generation or selection" in report["surface"]


def test_cli_text_render_leads_with_the_floor(tmp_path):
    env = dict(os.environ, CABINET_EVENT_LOG_DIR=str(tmp_path / "empty"),
               PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run([sys.executable, str(_SCRIPT)], cwd=_REPO, env=env,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "must-ask floor" in proc.stdout
    assert "Attention well spent" in proc.stdout


def test_window_membership_is_decided_on_instants_not_iso_string_order(
        aws, law, cfg, tmp_path):
    """ISO stamps with different offsets do not sort lexicographically in real
    time order. 13:00+02:00 is 11:00Z — an hour INSIDE a window ending at
    12:00Z, but lexically past its upper bound."""
    inside = [crow("purchase", decision="approved", ts="2026-07-25T13:00:00+02:00")]
    assert run(aws, law, cfg, rows=inside)["denominator"]["touches"] == 1
    # an undatable row is honestly excluded, never silently included
    assert run(aws, law, cfg,
               rows=[crow("purchase", decision="approved", ts="whenever")]
               )["denominator"]["touches"] == 0

    # MUTATION: decide membership by string compare -> the in-window row vanishes.
    mut = _mutant(tmp_path,
                  'return dt is not None and since <= dt <= until',
                  'return since.isoformat() <= str(value) <= until.isoformat()')
    assert run(mut, law, cfg, rows=inside)["denominator"]["touches"] == 0


def test_shipped_config_is_loadable_and_publishes_its_constants(aws, cfg):
    assert cfg["minute_costs"]["decided"] > cfg["minute_costs"]["expired"] > 0
    assert cfg["captain_actors"] == ["captain"]
    assert cfg["silent_window_min_actions"] >= 1
    assert 0 < cfg["share_amber_below"] <= 1
