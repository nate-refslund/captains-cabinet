"""SOV-8 grant-seeker tests — rank/render + the --argue-lanes flavor-A flip
case. The seeker GRANTS NOTHING: it only ranks, renders, and files needs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.learning import grant_seeker  # noqa: E402

NOW = "2026-07-05T12:00:00Z"
IN_WINDOW = "2026-07-01T09:00:00Z"


def _need(nid, *, kind="standing_grant", cost="medium", count=1,
          risk_class="external_comms", action_type="external_email",
          lane="polads", grant_line="- {id: GRANT-x}"):
    return {"id": nid, "kind": kind, "status": "open", "cost_of_delay": cost,
            "count": count, "risk_class": risk_class,
            "action_type": action_type, "lane": lane,
            "why": "blocked step", "proposed_grant_line": grant_line}


def _acted(subject, *, lane="polads", ts=IN_WINDOW, review=None,
           action_type="task_status_move"):
    ev = {"ts": ts, "actor": {"kind": "officer", "id": f"{lane}-ceo"},
          "lane": lane, "action": "board_move", "subject": subject,
          "refs": [], "action_type": action_type,
          "proposal": {"required": False, "decision": None},
          "outcome": {"status": "ok", "evidence": "ok"}}
    if review is not None:
        ev["review"] = review
    return ev


class TestRank:
    def test_blocking_and_count_outrank(self):
        rows = [
            _need("NEED-aaaaaaaa", cost="medium", count=1),
            _need("NEED-bbbbbbbb", cost="blocking", count=1),
            _need("NEED-cccccccc", cost="medium", count=9),
        ]
        ranked = grant_seeker.rank(rows, now=NOW)
        assert [r["need_id"] for r in ranked] == [
            "NEED-bbbbbbbb", "NEED-cccccccc", "NEED-aaaaaaaa"]

    def test_only_grant_shaped_open_needs(self):
        rows = [
            _need("NEED-aaaaaaaa", kind="decision"),
            dict(_need("NEED-bbbbbbbb"), status="denied"),
            _need("NEED-cccccccc", kind="credential"),
        ]
        ranked = grant_seeker.rank(rows, now=NOW)
        assert [r["need_id"] for r in ranked] == ["NEED-cccccccc"]

    def test_rank_never_raises(self):
        assert grant_seeker.rank([{"bad": object()}], now=NOW) == []


class TestRender:
    def test_grant_line_carries_machine_effective_scope(self):
        lines = grant_seeker.render(grant_seeker.rank(
            [_need("NEED-aaaaaaaa", grant_line="- {id: GRANT-aaaaaaaa, x: 1}")],
            now=NOW))
        assert len(lines) == 1
        assert "machine-effective scope: - {id: GRANT-aaaaaaaa, x: 1}" in lines[0]
        assert "NEED-aaaaaaaa" in lines[0]

    def test_marker_stripped(self):
        rows = [_need("NEED-aaaaaaaa")]
        rows[0]["why"] = "poisoned·marker"
        lines = grant_seeker.render(grant_seeker.rank(rows, now=NOW))
        assert "·" not in lines[0] and "poisonedmarker" in lines[0]


class TestArgueLanes:
    def test_qualifying_lane_files_decision_need(self, tmp_path, monkeypatch):
        root = tmp_path / "cab"
        monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
        ledger = [_acted(f"s{i}") for i in range(5)]
        ledger.append(_acted("s-confirmed", review={
            "verdict": "confirmed", "source": "verdict_human"}))
        out = grant_seeker.argue_lanes(ledger=ledger, root=root, now=NOW)
        assert [c["lane"] for c in out["qualifying"]] == ["polads"]
        case = out["qualifying"][0]
        assert case["acted"] == 6 and case["wrong"] == 0
        assert case["need_id"] and case["need_id"].startswith("NEED-")
        text = (root / "shared" / "interfaces" / "needs-ledger.jsonl").read_text()
        assert case["need_id"] in text and "lane polads earned" in text
        # deterministic id — re-running dedups instead of duplicating
        again = grant_seeker.argue_lanes(ledger=ledger, root=root, now=NOW)
        assert again["qualifying"][0]["need_id"] == case["need_id"]

    def test_wrong_verdict_disqualifies(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
        ledger = [_acted(f"s{i}") for i in range(6)]
        ledger.append(_acted("s-wrong", review={
            "verdict": "wrong", "source": "verdict_human"}))
        out = grant_seeker.argue_lanes(ledger=ledger, root=tmp_path / "cab",
                                       now=NOW)
        assert out["qualifying"] == []
        assert out["considered"]["polads"]["wrong"] == 1

    def test_thin_evidence_disqualifies(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
        ledger = [_acted(f"s{i}") for i in range(3)]
        out = grant_seeker.argue_lanes(ledger=ledger, root=tmp_path / "cab",
                                       now=NOW)
        assert out["qualifying"] == []

    def test_stale_rows_outside_window_excluded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
        ledger = [_acted(f"s{i}", ts="2026-01-01T00:00:00Z") for i in range(9)]
        out = grant_seeker.argue_lanes(ledger=ledger, root=tmp_path / "cab",
                                       now=NOW)
        assert out["qualifying"] == []

    def test_unwired_guardian_files_nothing(self, tmp_path, monkeypatch):
        # needs_enabled false ⇒ file_need no-ops ⇒ need_id None, no ledger
        monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path / "cab"))
        ledger = [_acted(f"s{i}") for i in range(6)]
        out = grant_seeker.argue_lanes(ledger=ledger, root=tmp_path / "cab",
                                       now=NOW)
        assert out["qualifying"][0]["need_id"] is None
        assert not (tmp_path / "cab" / "shared" / "interfaces"
                    / "needs-ledger.jsonl").exists()

    def test_render_lane_flip_line(self):
        case = {"kind": "lane_flip", "lane": "polads",
                "why": "lane polads earned a sovereign flip: 6 acted", "score": 7}
        lines = grant_seeker.render([case])
        assert "lane flip case — polads" in lines[0]
        assert "posture.yml lanes: {polads: sovereign}" in lines[0]


class TestCLI:
    def test_argue_lanes_json(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path / "cab"))
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
        monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
        rc = grant_seeker.main(["--argue-lanes", "--json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert "qualifying" in out and "considered" in out
