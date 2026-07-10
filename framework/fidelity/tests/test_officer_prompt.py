from __future__ import annotations

import pytest

from framework.fidelity import officer_prompt
from framework.fidelity.types import Case

CUTOFF = "2026-06-10T12:00:00+00:00"


@pytest.fixture(autouse=True)
def _synthetic_captain(monkeypatch):
    """Pin the captain identity to the synthetic fixture captain (Ada) so the
    prompt-content assertions are hermetic — never coupled to this
    deployment's instance/config captain_name value."""
    monkeypatch.setattr(officer_prompt, "captain_name", lambda: "Ada")


def _case():
    return Case.from_retro_case({
        "case_id": "abc1234567", "reply_key": "k", "slug": "otto",
        "person": "Otto", "channel": "msgraph", "language": "da",
        "reply_ts": CUTOFF, "subject": "Re: lon", "n_prior": 2,
        "thread_before": [
            {"slug": "otto", "person": "Otto",
             "date": "2026-06-08T08:00:00+00:00", "direction": "sent",
             "who": "Ada", "source": "msgraph", "to": "", "cc": "",
             "text": "Hej, vi tager den i naeste uge."},
            {"slug": "otto", "person": "Otto",
             "date": "2026-06-09T08:00:00+00:00", "direction": "received",
             "who": "Otto <u@x>", "source": "msgraph", "to": "", "cc": "",
             "text": "kan vi snakke lon paa fredag?"},
        ],
        "real_reply": "Ja, fredag passer.",
    })


class TestRoleDefinition:
    def test_missing_role_returns_fallback_not_crash(self):
        out = officer_prompt.role_definition("nonexistent-role-xyz")
        assert isinstance(out, str) and "nonexistent-role-xyz" in out

    def test_existing_role_loads_charter_from_agents_dir(self, tmp_path,
                                                          monkeypatch):
        """Happy path: when .claude/agents/<role>.md exists, its real charter
        text is returned (not the fallback stub). Guards the wrong-path bug:
        the dir must match load-preset.sh's $CABINET_ROOT/.claude/agents."""
        sentinel = "SENTINEL-CHAIR-OF-STAFF-CHARTER-12345"
        (tmp_path / "cos.md").write_text(
            f"# Chief of Staff\n{sentinel}\n")
        monkeypatch.setattr(officer_prompt, "_AGENTS_DIR", tmp_path)
        out = officer_prompt.role_definition("cos")
        assert sentinel in out
        assert "Role definition file not found" not in out

    def test_build_eval_system_includes_real_charter(self, tmp_path,
                                                     monkeypatch):
        """The assembled eval system prompt must carry the officer's actual
        charter, not just the decision-context block."""
        sentinel = "SENTINEL-CHAIR-OF-STAFF-CHARTER-12345"
        (tmp_path / "cos.md").write_text(
            f"# Chief of Staff\n{sentinel}\n")
        monkeypatch.setattr(officer_prompt, "_AGENTS_DIR", tmp_path)
        s = officer_prompt.build_eval_system(_case(), "cos")
        assert sentinel in s

    def test_agents_dir_matches_runtime_populated_path(self):
        """The module's default _AGENTS_DIR must end in .claude/agents (no extra
        'cabinet' segment) so it matches the dir load-preset.sh populates."""
        assert officer_prompt._AGENTS_DIR.parts[-2:] == (".claude", "agents")


class TestBuildEvalSystem:
    def test_includes_lane_and_decision_type(self):
        s = officer_prompt.build_eval_system(_case(), "chair")
        assert "send-1to1-reply" in s
        assert "reply" in s

    def test_never_includes_held_out_reply(self):
        s = officer_prompt.build_eval_system(_case(), "chair")
        assert "Ja, fredag passer." not in s


class TestFormatSituation:
    def test_oldest_first_and_both_messages_present(self):
        s = officer_prompt.format_situation(_case())
        i_first = s.index("naeste uge")
        i_last = s.index("snakke lon")
        assert i_first < i_last  # oldest-first

    def test_carries_cutoff_header(self):
        s = officer_prompt.format_situation(_case())
        assert CUTOFF in s
        assert "HELD-OUT SITUATION" in s

    def test_never_includes_held_out_reply(self):
        s = officer_prompt.format_situation(_case())
        assert "Ja, fredag passer." not in s

    def test_sent_messages_labelled_captain(self):
        s = officer_prompt.format_situation(_case())
        assert "Ada:" in s


def _identity():
    """A clone-identity priors dict {voice, patterns, lessons, person_static}
    as BrainAdapter (voice_profile / nate_model_patterns / drafting_lessons /
    static person frontmatter) would hand it to the clone arm. Each value
    carries a distinctive sentinel so the tests can assert it reached (or did
    NOT reach) the assembled prompt."""
    return {
        "voice": "VOICE-SENTINEL: korte saetninger, ingen tankestreger.",
        "patterns": "PATTERNS-SENTINEL: beslutter hurtigt, anbefaler direkte.",
        "lessons": "LESSONS-SENTINEL: spoerg ikke om audience, du kender den.",
        "person_static": "PERSON-SENTINEL: Otto, head baker & site lead.",
    }


class TestBuildCloneEvalSystem:
    def test_identity_priors_inform_the_prompt(self):
        """All four identity priors must reach the assembled clone prompt — the
        IDENTITY is what drives the draft (voice + patterns + lessons +
        person_static), not just the role charter."""
        ident = _identity()
        s = officer_prompt.build_clone_eval_system(_case(), "chair", ident)
        assert ident["voice"] in s
        assert ident["patterns"] in s
        assert ident["lessons"] in s
        assert ident["person_static"] in s

    def test_carries_role_context(self):
        """The role charter may stay as light role context — lane/decision_type
        from build_eval_system still ride along so the officer keeps role
        framing even though identity drives the draft."""
        s = officer_prompt.build_clone_eval_system(_case(), "chair", _identity())
        assert "send-1to1-reply" in s
        assert "reply" in s

    def test_contains_explicit_privacy_fence_instruction(self):
        """An explicit privacy-fence instruction MUST be present: the priors
        shape HOW the clone writes/decides but must NEVER be quoted, pasted, or
        referenced into the reply (brain-bridge rule; mirrors me_signal PRIVATE
        fence)."""
        s = officer_prompt.build_clone_eval_system(_case(), "chair", _identity())
        low = s.lower()
        assert "never quote" in low or "never quote, paste" in low
        # the fence names that these are Ada's private model (shape HOW only)
        assert "private" in low
        assert "how you write" in low or "how you write and decide" in low

    def test_never_includes_held_out_reply(self):
        """The held-out reply is the ground truth — it must NEVER appear in the
        clone prompt, exactly as build_eval_system guarantees."""
        s = officer_prompt.build_clone_eval_system(_case(), "chair", _identity())
        assert "Ja, fredag passer." not in s

    def test_missing_identity_keys_do_not_crash(self):
        """A partial/empty identity dict (a prior unavailable for this case)
        must degrade gracefully — assemble the prompt, still fence, never
        KeyError."""
        s = officer_prompt.build_clone_eval_system(_case(), "chair", {})
        assert isinstance(s, str) and s
        assert "private" in s.lower()

    def test_drives_as_nate_clone_framing(self):
        """The clone arm drafts AS ADA'S CLONE — the prompt must frame the
        officer as drafting in Ada's identity, not merely as the role."""
        s = officer_prompt.build_clone_eval_system(_case(), "chair", _identity())
        assert "Ada" in s


def _mower_case():
    """A richer multi-message thread to exercise intent reconstruction:
    >5 messages so the <=5 last-message window is provably enforced, with a
    distinctive earliest message ('SECRET-OLDEST-MARKER') that must NOT appear
    when only the last 5 are read."""
    msgs = []
    msgs.append({
        "direction": "received", "who": "Bo <b@x>",
        "date": "2026-05-01T08:00:00+00:00", "source": "msgraph",
        "text": "SECRET-OLDEST-MARKER: hej, helt andet emne her."})
    msgs.append({
        "direction": "sent", "who": "Ada",
        "date": "2026-05-02T08:00:00+00:00", "source": "msgraph",
        "text": "Vi har koebt nyt hus paa Kagevej."})
    msgs.append({
        "direction": "received", "who": "Bo <b@x>",
        "date": "2026-05-03T08:00:00+00:00", "source": "msgraph",
        "text": "Stor graesplaene der, ikke?"})
    msgs.append({
        "direction": "sent", "who": "Ada",
        "date": "2026-05-04T08:00:00+00:00", "source": "msgraph",
        "text": "Ja, 3000 m2. Ingen kanttraad tak."})
    msgs.append({
        "direction": "received", "who": "Bo <b@x>",
        "date": "2026-05-05T08:00:00+00:00", "source": "msgraph",
        "text": "Vil du have hjaelp til at finde en robotplaeneklipper?"})
    return Case.from_retro_case({
        "case_id": "mower12345", "reply_key": "k", "slug": "bo",
        "person": "Bo", "channel": "msgraph", "language": "da",
        "reply_ts": "2026-05-06T12:00:00+00:00", "subject": "mower",
        "n_prior": 5, "thread_before": msgs,
        "real_reply": "Her er en Husqvarna-mejetaerskerlink HEMMELIGT-SVAR.",
    })


class TestIntentAndContext:
    def test_returns_two_string_fields(self):
        out = officer_prompt.intent_and_context(_case())
        assert set(out.keys()) == {"reconstructed_intent", "mission_or_goal"}
        assert isinstance(out["reconstructed_intent"], str)
        assert isinstance(out["mission_or_goal"], str)

    def test_derives_from_thread_content(self):
        """Intent must be textually grounded in thread_before — the
        counterparty's actual ask reaches the reconstructed intent."""
        out = officer_prompt.intent_and_context(_mower_case())
        blob = (out["reconstructed_intent"] + " " + out["mission_or_goal"]).lower()
        assert "robotplaeneklipper" in blob

    def test_never_reads_real_reply(self):
        """The held-out reply is the ground truth — its text (and the SECRET
        marker embedded in it) must NEVER surface in the reconstructed intent."""
        c = _mower_case()
        out = officer_prompt.intent_and_context(c)
        joined = out["reconstructed_intent"] + " " + out["mission_or_goal"]
        assert "HEMMELIGT-SVAR" not in joined
        assert "Husqvarna" not in joined

    def test_only_last_five_messages(self):
        """Derived from the LAST <=5 messages of thread_before ONLY — an
        earlier (6th-from-last) message must not leak through."""
        out = officer_prompt.intent_and_context(_mower_case())
        joined = out["reconstructed_intent"] + " " + out["mission_or_goal"]
        assert "SECRET-OLDEST-MARKER" not in joined

    def test_field_char_caps(self):
        """Each field is capped at <=500 chars to keep the judge payload lean
        (design §1.2). Hold against a pathologically long thread."""
        long_msg = {
            "direction": "received", "who": "Bo <b@x>",
            "date": "2026-05-05T08:00:00+00:00", "source": "msgraph",
            "text": "robotplaeneklipper " + ("x" * 5000)}
        c = Case.from_retro_case({
            "case_id": "long123456", "reply_key": "k", "slug": "bo",
            "person": "Bo", "channel": "msgraph", "language": "da",
            "reply_ts": "2026-05-06T12:00:00+00:00", "subject": "s",
            "n_prior": 1, "thread_before": [long_msg],
            "real_reply": "x",
        })
        out = officer_prompt.intent_and_context(c)
        assert len(out["reconstructed_intent"]) <= 500
        assert len(out["mission_or_goal"]) <= 500

    def test_empty_thread_does_not_crash(self):
        c = Case.from_retro_case({
            "case_id": "empty12345", "reply_key": "k", "slug": "bo",
            "person": "Bo", "channel": "msgraph", "language": "da",
            "reply_ts": "2026-05-06T12:00:00+00:00", "subject": "s",
            "n_prior": 0, "thread_before": [],
            "real_reply": "x",
        })
        out = officer_prompt.intent_and_context(c)
        assert isinstance(out["reconstructed_intent"], str)
        assert isinstance(out["mission_or_goal"], str)

    def test_pure_no_mcp_or_network(self, monkeypatch):
        """Pure function: no MCP/network/filesystem. Sabotage the obvious
        escape hatches — any attempt to use them would raise here."""
        import socket
        monkeypatch.setattr(
            socket, "socket",
            lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("intent_and_context made a network call")))
        # role_definition is the only fs read in this module; it must not be
        # touched by a pure thread-only reconstruction.
        monkeypatch.setattr(
            officer_prompt, "role_definition",
            lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("intent_and_context read a role file")))
        out = officer_prompt.intent_and_context(_mower_case())
        assert isinstance(out, dict)

    def test_reflects_language_and_core(self):
        """The 'core' half should encode the channel/language so the judge
        scores mission × core, not mission alone."""
        out = officer_prompt.intent_and_context(_mower_case())
        assert "da" in out["reconstructed_intent"].lower()

    def test_core_half_survives_cap_when_goal_is_oversized(self):
        """Regression: a naive f'Goal: {goal} Core: {core}'[:500] truncates from
        the right and chops the ENTIRE Core half on a long goal. The goal slice
        must be budgeted separately so 'Core:' (and the language axis) always
        survive the 500-char cap."""
        long_ask = "robotplaeneklipper til en kaempe graesplaene " + ("y" * 5000)
        c = Case.from_retro_case({
            "case_id": "cap1234567", "reply_key": "k", "slug": "bo",
            "person": "Bo", "channel": "msgraph", "language": "da",
            "reply_ts": "2026-05-06T12:00:00+00:00", "subject": "s",
            "n_prior": 1,
            "thread_before": [
                {"direction": "received", "who": "Bo <b@x>",
                 "date": "2026-05-05T08:00:00+00:00", "source": "msgraph",
                 "text": long_ask},
            ],
            "real_reply": "x",
        })
        out = officer_prompt.intent_and_context(c)
        ri = out["reconstructed_intent"]
        # the field is still within the cap
        assert len(ri) <= 500
        # mission_or_goal is at/over the budget that would otherwise eat Core
        assert len(out["mission_or_goal"]) >= 1
        # BOTH halves survive: the Core marker and the language axis are present
        assert "Core:" in ri
        assert "da" in ri.lower()
        # the standing-style core text actually made it in (not just the label)
        assert "direct recommendation" in ri
