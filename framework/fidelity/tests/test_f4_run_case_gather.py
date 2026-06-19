"""F4 T4 tests — run_case gather param + conditional EVAL_MODE_RULES.

Design §1.3, §2.4, §4, §8.

The A/B knob must be honest:
  - gather=None reproduces F1 BYTE-FOR-BYTE: the system prompt is exactly
    build_eval_system + the strict EVAL_MODE_RULES (incl. F1's original
    "Return ONLY the reply text" line), and the user payload is exactly
    format_situation(case) with NO appended context block.
  - gather=<fn> appends the leak-guarded context block AFTER format_situation
    (in the USER message — no new system authority) and adds the conditional
    "use gathered context / propose options" permission + the reconciled
    output line to the system prompt.

The held-out reply (case.real_reply) must NEVER appear in either arm. The
gathered context is rendered from the already-leak-guarded gather output; this
test injects a fake gather so it exercises the render path with no live MCP.
"""

from __future__ import annotations

from framework.fidelity import officer_runner
from framework.fidelity.officer_prompt import build_eval_system, format_situation
from framework.fidelity.types import Case

CUTOFF = "2026-06-10T12:00:00+00:00"


def _case():
    return Case.from_retro_case({
        "case_id": "abc1234567",
        "reply_key": "msgraph|MID1",
        "slug": "ulrik", "person": "Ulrik", "channel": "msgraph",
        "language": "da", "reply_ts": CUTOFF, "subject": "Re: lon",
        "n_prior": 3,
        "thread_before": [
            {"slug": "ulrik", "person": "Ulrik",
             "date": "2026-06-09T08:00:00+00:00", "direction": "received",
             "who": "Ulrik <u@x>", "source": "msgraph", "to": "", "cc": "",
             "text": "kan vi snakke lon?"},
        ],
        "real_reply": "Ja, lad os tage det fredag.",
    })


# A held-out reply that SHARES topic words with the thread ("lon"/"snakke") and
# with the gather context ("fredag"), but carries a distinctive verbatim phrase
# that must never surface in the prompt. This makes the real_reply leak checks
# non-trivial: the `not in` assertion can only pass because the harness withholds
# the reply, not because the reply's vocabulary is absent from the prompt.
_DISTINCTIVE_REPLY_PHRASE = "lad os tage lon-snakken fredag kl 14 HEMMELIGT-SVAR-99"


def _topic_overlap_case():
    c = _case()
    c.real_reply = _DISTINCTIVE_REPLY_PHRASE
    c.ground_truth = {"real_reply": _DISTINCTIVE_REPLY_PHRASE}
    return c


def _capture_llm():
    """Return (fake_llm, seen) — the fake records system+payload it is called
    with and returns a clean draft."""
    seen = {}

    def fake(payload, system, max_tokens=1500, model="claude-sonnet-4-6"):
        seen["system"] = system
        seen["payload"] = payload
        return "Ja, fredag passer fint."

    return fake, seen


class TestGatherNoneIsF1:
    def test_gather_none_is_f1(self):
        # gather=None must yield a BYTE-IDENTICAL prompt to the F1 path:
        # system == build_eval_system + the strict EVAL_MODE_RULES, and
        # payload == format_situation(case), with no context block.
        case = _case()
        fake, seen = _capture_llm()
        officer_runner.run_case(case, "chair", llm=fake)  # gather defaults None

        expected_system = (
            build_eval_system(case, "chair")
            + officer_runner.EVAL_MODE_RULES.format(cutoff_ts=case.cutoff_ts)
        )
        expected_payload = format_situation(case)

        assert seen["system"] == expected_system
        assert seen["payload"] == expected_payload

    def test_gather_none_explicit_matches_default(self):
        case = _case()
        fake_a, seen_a = _capture_llm()
        fake_b, seen_b = _capture_llm()
        officer_runner.run_case(case, "chair", llm=fake_a)
        officer_runner.run_case(_case(), "chair", llm=fake_b, gather=None)
        assert seen_a["system"] == seen_b["system"]
        assert seen_a["payload"] == seen_b["payload"]

    def test_gather_none_has_no_gather_rules_or_context(self):
        case = _case()
        fake, seen = _capture_llm()
        officer_runner.run_case(case, "chair", llm=fake)
        # the gather-only permission language must be absent in the None arm
        assert "gathered as-of the cutoff" not in seen["system"]
        assert "propose the fitting course of action" not in seen["system"]
        # F1's strict output line is present (not the reconciled one)
        assert "Return ONLY the reply text" in seen["system"]
        # no context block appended to the payload
        assert "CONTEXT (gathered as-of cutoff" not in seen["payload"]

    def test_real_reply_never_in_prompt_none_arm(self):
        case = _case()
        fake, seen = _capture_llm()
        officer_runner.run_case(case, "chair", llm=fake)
        assert case.real_reply not in seen["system"]
        assert case.real_reply not in seen["payload"]

    def test_topic_overlapping_real_reply_never_verbatim_none_arm(self):
        # Harden the leak check: a real_reply whose TOPIC words ("lon", "fredag")
        # DO appear in the thread must still never appear VERBATIM in the prompt.
        # This proves the `not in` assertion isn't trivially true because the
        # reply's vocabulary is disjoint from the prompt.
        case = _topic_overlap_case()
        fake, seen = _capture_llm()
        officer_runner.run_case(case, "chair", llm=fake)
        blob = seen["system"] + seen["payload"]
        # the held-out reply, verbatim, is absent from both halves
        assert case.real_reply not in seen["system"]
        assert case.real_reply not in seen["payload"]
        assert _DISTINCTIVE_REPLY_PHRASE not in blob
        # …yet its topic words ARE present (so the `not in` check is non-trivial)
        assert "lon" in blob.lower()


def _fake_gather_factory(captured):
    """A gather stand-in matching gather_cutoff_context's signature/shape, so
    run_case exercises the render+inject path without touching the live brain.
    Records that it was called with the case."""
    def _gather(case):
        captured.append(case)
        return {
            "thread": case.thread_before,
            "commitments": [
                {"commitment_id": "c1", "text": "send the deck",
                 "source_date": "2026-05-01T09:00:00+00:00", "status": "open"},
            ],
            "vault_hits": [
                {"path": "1-Daily/2026-05-12.md", "heading": "house",
                 "text": "new house at Mosevraavej, big lawn ~3000 m2",
                 "ts": "2026-05-12T09:00:00+00:00", "source": "vault"},
            ],
            "person_static": "role: VP Product & Publishers\nrelationship: manager",
            "excluded": [
                "search_brain (mtime != content-ts; no mtime fallback)",
                "gather_context.brief (un-fenceable prose)",
                "gather_context Tier-2 sent/audio/ocr/monday (live = now)",
            ],
        }
    return _gather


class TestGatherSetInjectsContextAndRules:
    def test_gather_set_calls_gather_with_case(self):
        case = _case()
        fake, seen = _capture_llm()
        captured = []
        officer_runner.run_case(case, "chair", llm=fake,
                                gather=_fake_gather_factory(captured))
        assert captured and captured[0] is case

    def test_gather_set_appends_context_after_situation(self):
        case = _case()
        fake, seen = _capture_llm()
        captured = []
        officer_runner.run_case(case, "chair", llm=fake,
                                gather=_fake_gather_factory(captured))
        payload = seen["payload"]
        situation = format_situation(case)
        # The situation text comes FIRST; the context block is APPENDED after it.
        assert payload.startswith(situation)
        assert len(payload) > len(situation)
        # the fenced records are rendered into the appended block
        assert "1-Daily/2026-05-12.md" in payload
        assert "3000 m2" in payload
        assert "send the deck" in payload
        assert "VP Product & Publishers" in payload
        # the context block is in the USER message, not the system prompt
        assert "1-Daily/2026-05-12.md" not in seen["system"]
        assert "3000 m2" not in seen["system"]

    def test_gather_set_adds_conditional_permission_rules(self):
        case = _case()
        fake, seen = _capture_llm()
        captured = []
        officer_runner.run_case(case, "chair", llm=fake,
                                gather=_fake_gather_factory(captured))
        system = seen["system"]
        # strict cutoff boundary still present (ALWAYS)
        assert "You have NO knowledge of events at or after" in system
        assert case.cutoff_ts in system
        # gather-only permission to use context + propose options
        assert "gathered as-of the cutoff" in system
        assert "propose the fitting course of action" in system
        assert "Serve the intent" in system
        # reconciled output line replaces F1's strict "Return ONLY the reply text"
        assert "Return ONLY the reply text" not in system
        assert "no JSON, no meta-commentary" in system

    def test_gather_set_real_reply_never_in_prompt(self):
        case = _case()
        fake, seen = _capture_llm()
        captured = []
        officer_runner.run_case(case, "chair", llm=fake,
                                gather=_fake_gather_factory(captured))
        assert case.real_reply not in seen["system"]
        assert case.real_reply not in seen["payload"]

    def test_gather_set_topic_overlapping_real_reply_never_verbatim(self):
        # Same hardening on the gather arm: even when the gathered context block
        # is appended to the payload, a topic-overlapping held-out reply never
        # appears verbatim. The context block IS present (proving the payload is
        # the right haystack), so the `not in` check is non-trivial.
        case = _topic_overlap_case()
        fake, seen = _capture_llm()
        captured = []
        officer_runner.run_case(case, "chair", llm=fake,
                                gather=_fake_gather_factory(captured))
        blob = seen["system"] + seen["payload"]
        assert case.real_reply not in seen["system"]
        assert case.real_reply not in seen["payload"]
        assert _DISTINCTIVE_REPLY_PHRASE not in blob
        # the gathered context block really is in the payload (right haystack)
        assert "CONTEXT (gathered as-of cutoff" in seen["payload"]
        # …and the reply's topic words ARE present (non-trivial `not in`)
        assert "lon" in blob.lower()
