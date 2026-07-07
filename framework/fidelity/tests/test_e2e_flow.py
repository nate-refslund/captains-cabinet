"""T4 — end-to-end flow integration test (stubbed deterministic LLM).

Nate's directive: prove the WHOLE flow wires together. This test drives the
FULL fidelity pipeline on a synthetic held-out case with NO live LLM call (the
officer LLM is stubbed via run_case(llm=...), the judge via score(judge=...)),
so it is deterministic, costs nothing, and stays leak-safe. It is the seam
test that the discrete unit tests (test_f4_run_case_gather / test_scorer /
test_f4_consequence_intent / test_graduation) cannot give individually: that
the pieces compose into one working chain.

The chain under test (design docs/fidelity-harness-design-2026-06-18.md):
  1. Case (synthetic held-out reply, cutoff = the held-out reply ts)
  2. gather_cutoff_context  — leak-safe: a post-cutoff vault hit + a
     post-cutoff commitment are EXCLUDED; only pre-cutoff records survive.
  3. run_case(blind)        — stubbed officer LLM; the draft is captured, NO
     side effects beyond the isolated ledger; real_reply never in the prompt.
  4. score                  — stubbed judge; decision_verdict + intent_verdict
     + composite. The §3.4 quadrants are asserted END-TO-END:
       divergent × intent-aligned -> 1.0  (F4 credit path)
       match     × intent-divergent -> 0.0 (hollow surface-match gated)
  5. emit_case_scored (T3)  — a consequence event carrying the intent fields.
  6. read_ledger / compute_ratios — the scored cell's intent + review ratios.
  7. graduation.evaluate    — a SANE fail-safe state on synthetic data
     (unmeasured / propose_only — never silently graduated).

All LLM seams are stubbed; the leak guard, the ledger I/O, the ratio math, and
the graduation gate are the LIVE code paths.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from framework.fidelity import fidelity_events, graduation, leakguard, officer_runner, scorer
from framework.fidelity.consequence import (
    UNSTAMPED_ACTION_TYPE,
    compute_ratios,
    read_ledger,
)
from framework.fidelity.officer_prompt import build_eval_system, format_situation
from framework.fidelity.types import Case

CUTOFF = "2026-06-10T12:00:00+00:00"
ACTION_TYPE = "internal_message"
LANE = "send-1to1-reply"
OFFICER = "chair"

# The held-out reply Nate actually sent. It carries a distinctive verbatim
# phrase that MUST never surface in the prompt — the only-because-withheld leak
# check (its topic words DO appear in the thread, so `not in` is non-trivial).
_REAL_REPLY = "Ja, lad os tage lon-snakken fredag kl 14 HEMMELIGT-SVAR-T4"


def _case() -> Case:
    """A synthetic held-out reply case (the send-1to1-reply cell)."""
    c = Case.from_retro_case({
        "case_id": "e2ecase001",
        "reply_key": "msgraph|MID-T4",
        "slug": "ulrik", "person": "Ulrik", "channel": "msgraph",
        "language": "da", "reply_ts": CUTOFF, "subject": "Re: lon",
        "n_prior": 1,
        "thread_before": [
            {"slug": "ulrik", "person": "Ulrik",
             "date": "2026-06-09T08:00:00+00:00", "direction": "received",
             "who": "Ulrik <u@x>", "source": "msgraph", "to": "", "cc": "",
             "text": "kan vi snakke lon snart?"},
        ],
        "real_reply": _REAL_REPLY,
    })
    return c


# ---------------------------------------------------------------------------
# A leak-trap BrainAdapter: returns one PRE-cutoff and one POST-cutoff record
# in every fence-able source, so gather_cutoff_context's leak guard is exercised
# for real. No network, no live brain — pure in-memory fakes.
# ---------------------------------------------------------------------------

class _LeakTrapBrain:
    def search(self, handle, topic=None):
        return {
            "topic_terms": ["lon"],
            "hits": [
                # PRE-cutoff content (path-dated 2026-05-12) — must SURVIVE.
                {"path": "1-Daily/2026-05-12.md", "heading": "lon",
                 "text": "Nate noted the salary review is due before summer",
                 "ts": "2026-05-12T09:00:00+00:00", "source": "vault"},
                # POST-cutoff content (path-dated 2026-06-20) — must be DROPPED.
                {"path": "1-Daily/2026-06-20.md", "heading": "lon",
                 "text": "POSTCUTOFF the raise was agreed at the friday meeting",
                 "ts": "2026-06-20T09:00:00+00:00", "source": "vault"},
            ],
        }

    def open_commitments(self, direction):
        # CONTRACT direction values (base.PersonalSource — T1 widen).
        if direction == "owed_by_captain":
            return [
                # PRE-cutoff commitment — must SURVIVE.
                {"commitment_id": "c-pre", "direction": direction,
                 "text": "schedule the salary conversation with Ulrik",
                 "source_date": "2026-05-01T09:00:00+00:00",
                 "due": "2026-06-15", "status": "open"},
                # POST-cutoff commitment — must be DROPPED.
                {"commitment_id": "c-post", "direction": direction,
                 "text": "POSTCUTOFF follow up after the friday agreement",
                 "source_date": "2026-06-19T09:00:00+00:00", "status": "open"},
            ]
        return []

    def person_intel(self, slug):
        # Static atemporal frontmatter (timeless) + a dated leak line that the
        # _static_frontmatter strip must remove.
        return ("role: VP Product & Publishers\n"
                "relationship: manager\n"
                "2026-06-20 POSTCUTOFF salary settled\n")

    def read_note(self, path):  # pragma: no cover - read_paths not used here
        return ""


# Stubbed officer LLM — deterministic, records the prompt it saw.
def _capture_officer_llm():
    seen = {}

    def fake(payload, system, max_tokens=1500, model="claude-sonnet-4-6"):
        seen["system"] = system
        seen["payload"] = payload
        # A clean, leak-free draft (no post-cutoff ISO timestamp).
        return "Ja, fredag passer fint - lad os tage lon-snakken da."

    return fake, seen


# Deterministic fake embedder (identical text -> identical vector -> cosine 1.0)
def _fake_embedder(texts):
    def vec(t):
        return [float(len(t or "")), 1.0, 0.0]
    return [vec(t) for t in texts]


_CENTROIDS = {"msgraph": _fake_embedder(["x"])[0]}


def _stub_judge(decision_verdict, intent_verdict, grounded="From Ulrik at 2026-06-09: lon"):
    """A judge stand-in matching scorer.judge_with_oauth's return shape: a
    decision dict the retro scorer consumes (verdict + the keys score_case
    needs) plus the F4 intent axis. NEVER calls a live LLM."""
    def judge(case_dict, clone_draft, reconstructed_intent="",
              full_cutoff_context=None):
        return {
            "verdict": decision_verdict,
            "rationale": "stub",
            "what_diverged": "",
            "real_decision": "",
            "draft_decision": "",
            "intent_verdict": intent_verdict,
            "intent_rationale": "stub",
            "intent_what_diverged": "",
            "intent_grounded_fact": grounded,
        }
    return judge


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    """Isolate the consequence + org-event ledgers to a tmp dir, so run_case
    side effects (events) and emit_case_scored land nowhere durable."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return tmp_path


# ===========================================================================
# 1. gather_cutoff_context — leak-safe (post-cutoff records EXCLUDED).
# ===========================================================================

class TestGatherLeakSafe:
    def test_post_cutoff_records_excluded(self):
        case = _case()
        ctx = officer_runner.gather_cutoff_context(case, brain=_LeakTrapBrain())

        # the PRE-cutoff vault hit survives, the POST-cutoff one is dropped.
        vault_text = " ".join(str(h.get("text") or "") for h in ctx["vault_hits"])
        assert "salary review is due before summer" in vault_text
        assert "POSTCUTOFF" not in vault_text
        assert len(ctx["vault_hits"]) == 1

        # the PRE-cutoff commitment survives; the POST-cutoff one is dropped.
        commit_text = " ".join(str(c.get("text") or "") for c in ctx["commitments"])
        assert "schedule the salary conversation" in commit_text
        assert "POSTCUTOFF" not in commit_text
        assert len(ctx["commitments"]) == 1

        # the dated leak line is stripped from the static frontmatter; the
        # atemporal attributes survive.
        assert "VP Product & Publishers" in ctx["person_static"]
        assert "POSTCUTOFF" not in ctx["person_static"]

        # un-fenceable sources are surfaced, never silently passed through.
        assert any("search_brain" in e for e in ctx["excluded"])

    def test_no_post_cutoff_iso_anywhere_in_context(self):
        # Hard leak invariant: NOTHING in the rendered context carries an ISO
        # timestamp at/after the cutoff (mirrors the live post-output scan).
        case = _case()
        ctx = officer_runner.gather_cutoff_context(case, brain=_LeakTrapBrain())
        blob = scorer._render_context(ctx)
        leaks = leakguard.scan_for_leaks(blob, case.thread_before, case.cutoff_ts)
        assert leaks == [], f"context leaked post-cutoff signals: {leaks}"


# ===========================================================================
# 2. run_case blind — draft captured, NO side effects, real_reply withheld.
# ===========================================================================

class TestRunCaseBlind:
    def test_blind_draft_captured_no_side_effects(self, event_log_dir):
        case = _case()
        fake, seen = _capture_officer_llm()
        # emit_events=False -> zero ledger writes (no side effects at all).
        decision = officer_runner.run_case(
            case, OFFICER, llm=fake, emit_events=False,
            gather=lambda c: officer_runner.gather_cutoff_context(
                c, brain=_LeakTrapBrain()),
        )
        # the officer's blind draft is captured verbatim.
        assert decision.decision == "Ja, fredag passer fint - lad os tage lon-snakken da."
        # NO side effect: no consequence ledger and no org-event ledger written.
        assert not list(Path(event_log_dir).glob("consequence-events-*.jsonl"))
        assert not list(Path(event_log_dir).glob("events-2*.jsonl"))
        # the LLM really saw the situation + the leak-guarded context block.
        assert seen["payload"].startswith(format_situation(case))
        assert "CONTEXT (gathered as-of cutoff" in seen["payload"]
        assert "salary review is due before summer" in seen["payload"]

    def test_real_reply_never_in_prompt(self, event_log_dir):
        case = _case()
        fake, seen = _capture_officer_llm()
        officer_runner.run_case(
            case, OFFICER, llm=fake, emit_events=False,
            gather=lambda c: officer_runner.gather_cutoff_context(
                c, brain=_LeakTrapBrain()),
        )
        blob = seen["system"] + seen["payload"]
        # the held-out reply, verbatim, never appears — yet its topic words do
        # (so the `not in` check is non-trivial).
        assert _REAL_REPLY not in blob
        assert "HEMMELIGT-SVAR-T4" not in blob
        assert "lon" in blob.lower()


# ===========================================================================
# 3. score — decision + intent + composite; the §3.4 quadrants END-TO-END.
# ===========================================================================

class TestScoreQuadrants:
    def _run_and_score(self, decision_verdict, intent_verdict, event_log_dir):
        case = _case()
        fake, _ = _capture_officer_llm()
        decision = officer_runner.run_case(
            case, OFFICER, llm=fake, emit_events=False,
            gather=lambda c: officer_runner.gather_cutoff_context(
                c, brain=_LeakTrapBrain()),
        )
        ctx = officer_runner.gather_cutoff_context(case, brain=_LeakTrapBrain())
        intent_ctx = {"reconstructed_intent": case.intent or "Goal: reply Core: x",
                      "full_cutoff_context": ctx}
        cs = scorer.score(
            case, decision, baseline_draft="Sure, sounds good.",
            centroids=_CENTROIDS, embedder=_fake_embedder,
            judge=_stub_judge(decision_verdict, intent_verdict),
            intent_ctx=intent_ctx,
        )
        return cs

    def test_divergent_x_intent_aligned_credits_one(self, event_log_dir):
        # The F4 credit path: a draft that diverges from the literal reply but
        # serves the SAME intent earns 1.0 end-to-end.
        cs = self._run_and_score("divergent", "intent-aligned", event_log_dir)
        assert cs.decision_verdict == "divergent"
        assert cs.intent_verdict == "intent-aligned"
        assert cs.intent_composite == 1.0
        # the decision-only composite stays 0.0 (the F1 channel is unchanged).
        assert cs.composite == 0.0

    def test_match_x_intent_divergent_gates_to_zero(self, event_log_dir):
        # The hollow surface-match: a literal match whose intent is off is gated
        # to 0.0 end-to-end, regardless of the decision verdict.
        cs = self._run_and_score("match", "intent-divergent", event_log_dir)
        assert cs.decision_verdict == "match"
        assert cs.intent_verdict == "intent-divergent"
        assert cs.intent_composite == 0.0
        # the decision-only composite is 1.0 (literal match) — the blend differs.
        assert cs.composite == 1.0


# ===========================================================================
# 4-7. emit_case_scored -> ledger -> ratios -> graduation, END-TO-END.
# ===========================================================================

class TestEmitLedgerRatiosGraduation:
    def test_scored_event_carries_intent_then_ratios_then_graduation(
            self, event_log_dir):
        case = _case()
        fake, _ = _capture_officer_llm()
        decision = officer_runner.run_case(
            case, OFFICER, llm=fake, emit_events=False,
            gather=lambda c: officer_runner.gather_cutoff_context(
                c, brain=_LeakTrapBrain()),
        )
        ctx = officer_runner.gather_cutoff_context(case, brain=_LeakTrapBrain())
        cs = scorer.score(
            case, decision, baseline_draft="Sure.",
            centroids=_CENTROIDS, embedder=_fake_embedder,
            judge=_stub_judge("divergent", "intent-aligned"),
            intent_ctx={"reconstructed_intent": case.intent,
                        "full_cutoff_context": ctx},
        )

        # 4. emit the scored consequence event (T3) carrying the intent axis.
        out = fidelity_events.emit_case_scored(
            cs, officer=OFFICER, lane=LANE, action_type=ACTION_TYPE,
            endorsement="unknown")
        assert out["action"] == "fidelity-case-scored"
        assert out["intent_verdict"] == "intent-aligned"
        assert out["intent_composite"] == 1.0
        assert out["review"]["verdict"] == "confirmed"  # aligned -> confirmed

        # 5. read_ledger sees exactly that one scored row.
        events = read_ledger()
        assert len(events) == 1
        ev = events[0]
        assert ev["subject"] == case.case_id
        assert ev["action_type"] == ACTION_TYPE
        assert ev["decision_verdict"] == "divergent"

        # 6. compute_ratios surfaces the intent + review channels for the cell.
        cell_key = (f"officer:{OFFICER}", LANE, ACTION_TYPE)
        cells = compute_ratios()
        assert cell_key in cells
        cell = cells[cell_key]
        assert cell.intent_aligned == 1
        assert cell.intent_divergent == 0
        assert cell.intent_match_rate == 1.0
        assert cell.confirmed == 0                # judge confirmed ≠ promotion fuel
        assert cell.review_confirmed_rate is None  # flavor-A: human-only channel

        # 7. graduation returns a SANE fail-safe state on this thin synthetic
        #    data — proven-but-not-graduated (one sample is far below any bar).
        result = graduation.evaluate(cell_key)
        assert result["state"] in ("unmeasured", "propose_only", "eligible")
        assert result["state"] != "graduated"  # never auto on one sample
        ev_evidence = result["evidence"]
        assert ev_evidence["sample_count"] == 1
        # the bar was READ (not hardcoded) — the evidence carries it.
        assert "match_rate" in ev_evidence["bar"]
        assert "samples" in ev_evidence["bar"]

    def test_intent_divergent_scored_event_demotes_review_to_wrong(
            self, event_log_dir):
        # The inverse seam: an intent-divergent scored case maps review->wrong,
        # so the graduation channel sees a divergent, not a silent unknown.
        case = _case()
        fake, _ = _capture_officer_llm()
        decision = officer_runner.run_case(
            case, OFFICER, llm=fake, emit_events=False,
            gather=lambda c: officer_runner.gather_cutoff_context(
                c, brain=_LeakTrapBrain()),
        )
        ctx = officer_runner.gather_cutoff_context(case, brain=_LeakTrapBrain())
        cs = scorer.score(
            case, decision, baseline_draft="Sure.",
            centroids=_CENTROIDS, embedder=_fake_embedder,
            judge=_stub_judge("match", "intent-divergent"),
            intent_ctx={"reconstructed_intent": case.intent,
                        "full_cutoff_context": ctx},
        )
        out = fidelity_events.emit_case_scored(
            cs, officer=OFFICER, lane=LANE, action_type=ACTION_TYPE)
        assert out["review"]["verdict"] == "wrong"
        assert out["intent_composite"] == 0.0

        cell = compute_ratios()[(f"officer:{OFFICER}", LANE, ACTION_TYPE)]
        assert cell.intent_divergent == 1
        assert cell.wrong == 1
        # one wrong on its own is not yet the demote cluster (>=2 in last 10):
        # the cell stays sub-bar, never silently graduated.
        result = graduation.evaluate((f"officer:{OFFICER}", LANE, ACTION_TYPE))
        assert result["state"] != "graduated"

    def test_unstamped_scored_event_buckets_under_sentinel(self, event_log_dir):
        # An emit WITHOUT action_type lands in the visible UNSTAMPED bucket, not
        # under its free-text action — and that bucket can never graduate.
        case = _case()
        fake, _ = _capture_officer_llm()
        decision = officer_runner.run_case(
            case, OFFICER, llm=fake, emit_events=False)
        ctx = officer_runner.gather_cutoff_context(case, brain=_LeakTrapBrain())
        cs = scorer.score(
            case, decision, baseline_draft="Sure.",
            centroids=_CENTROIDS, embedder=_fake_embedder,
            judge=_stub_judge("divergent", "intent-aligned"),
            intent_ctx={"reconstructed_intent": case.intent,
                        "full_cutoff_context": ctx},
        )
        fidelity_events.emit_case_scored(cs, officer=OFFICER, lane=LANE)
        cells = compute_ratios()
        sentinel_key = (f"officer:{OFFICER}", LANE, UNSTAMPED_ACTION_TYPE)
        assert sentinel_key in cells
        # graduation on the sentinel bucket is never auto.
        assert graduation.evaluate(sentinel_key)["state"] != "graduated"
