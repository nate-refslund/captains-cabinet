"""F4 leak-integrity tests for gather_cutoff_context (design §2, §9).

This is the leak boundary: gather_cutoff_context must admit ONLY structured,
per-record, content-timestamped-before-cutoff sources. Every un-fenceable
source is excluded by default — gather_context.brief (un-fenceable prose),
Tier-2 (sent/screen/monday — live = "now", and _fetch_sent IS the held-out
reply), search_brain (mtime is the wrong clock, NO mtime fallback ever),
and the live `## Notes from replies` dossier section (derived from the
held-out reply). Admitted sources are run through leakguard.filter_mcp_result.
read_note is vault-jailed (no traversal) and pre-cutoff-paths only.

The brain tools are MOCKED via an injectable adapter so these tests exercise
the actual gather_cutoff_context pipeline with NO live MCP / network.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from framework.fidelity import officer_runner
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


class FakeBrain:
    """An injectable brain adapter that records calls and lets each test
    decide what each tool returns. Tier-2 must NEVER be invoked: the vault
    fetcher asserts sources=["vault"], and there is no Tier-2 entry point that
    can be reached (gather_cutoff_context only ever calls search)."""

    def __init__(self, *, vault_hits=None, brief="", person_md="",
                 owed_by=None, owed_to=None, notes=None):
        self._vault_hits = vault_hits or []
        self._brief = brief
        self._person_md = person_md
        self._owed_by = owed_by or []
        self._owed_to = owed_to or []
        self._notes = notes or {}
        self.calls = []
        self.tier2_invoked = False

    def search(self, handle, topic=None):
        # gather_cutoff_context MUST scope to the vault tier only. The real
        # adapter calls context_lib.gather(handle, sources=["vault"]); this
        # fake mirrors the {hits, brief} shape and records the call. If any
        # code path tried to reach a Tier-2 fetcher it would have to call a
        # method that does not exist here -> AttributeError, surfacing the bug.
        self.calls.append(("search", handle))
        self.last_topic = topic
        return {"hits": list(self._vault_hits), "brief": self._brief}

    def person_intel(self, slug):
        self.calls.append(("person_intel", slug))
        return self._person_md

    def open_commitments(self, direction):
        self.calls.append(("open_commitments", direction))
        # CONTRACT direction values (base.PersonalSource — T1 widen).
        return list(self._owed_by if direction == "owed_by_captain"
                    else self._owed_to)

    def read_note(self, path):
        self.calls.append(("read_note", path))
        if path not in self._notes:
            raise FileNotFoundError(path)
        return self._notes[path]


class TestBriefExcluded:
    def test_brief_excluded(self):
        # gather_context.brief is un-fenceable prose that already summarized
        # post-cutoff facts -> it must NEVER appear in the output, and the
        # output must carry no free-text source field.
        brain = FakeBrain(
            brief="LEAK_BRIEF: Nate already replied with the Husqvarna URL on "
                  "2026-06-11. Lawn is 3000 m2.",
            vault_hits=[{"path": "1-Daily/2026-05-12.md", "heading": "house",
                         "text": "new house at Mosevraavej, big lawn",
                         "ts": "2026-05-12T09:00:00+00:00", "source": "vault"}],
        )
        ctx = officer_runner.gather_cutoff_context(_case(), brain=brain)
        flat = repr(ctx)
        assert "LEAK_BRIEF" not in flat
        assert "brief" not in ctx
        # no free-text prose source field smuggled in
        for v in ctx.values():
            assert not (isinstance(v, str) and "Husqvarna URL" in v)


class TestTopicAwareRetrieval:
    """The vault query is TOPIC-aware: gather_cutoff_context passes the inbound
    message (what's being replied to) as topic=, so retrieval is driven by what
    the conversation is ABOUT, not the bare person slug (the vault_hits=0 fix).
    NEVER reads real_reply."""

    def test_reply_topic_extracts_inbound_message(self):
        assert officer_runner._reply_topic(_case()) == "kan vi snakke lon?"

    def test_topic_passed_through_to_search(self):
        brain = FakeBrain(vault_hits=[])
        officer_runner.gather_cutoff_context(_case(), brain=brain)
        assert brain.last_topic == "kan vi snakke lon?"

    def test_topic_terms_surfaced_for_observability(self):
        brain = FakeBrain(vault_hits=[])
        ctx = officer_runner.gather_cutoff_context(_case(), brain=brain)
        assert "topic_terms" in ctx

    def test_reply_topic_never_reads_real_reply(self):
        # The real_reply ("Ja, lad os tage det fredag.") is the held-out ground
        # truth — it must NEVER be the topic.
        assert officer_runner._reply_topic(_case()) != "Ja, lad os tage det fredag."

    def test_no_inbound_message_is_none_not_crash(self):
        c = _case()
        c.thread_before = []
        assert officer_runner._reply_topic(c) is None


class TestTier2Unreachable:
    def test_tier2_unreachable(self):
        # gather_cutoff_context must call the vault tier ONLY. Assert the
        # search call happened and that no Tier-2 fetcher entry point
        # exists on the path (the fake has none — a Tier-2 attempt would
        # AttributeError). The real adapter's sources=["vault"] scoping is proven
        # in the Flavor-A adapter's own tests (flavor_a tests).
        brain = FakeBrain(vault_hits=[])
        officer_runner.gather_cutoff_context(_case(), brain=brain)
        assert ("search", "ulrik") in brain.calls or \
               any(c[0] == "search" for c in brain.calls)
        # no Tier-2 method was ever added/called
        assert not brain.tier2_invoked

    # NOTE: the BrainAdapter-internal scoping proofs (context_lib sources=["vault"]
    # + the Tier-2-fetcher-raises guard) moved WITH the adapter to the Flavor-A
    # adapter's own tests (instance/flavor-a/flavor_a/tests/test_adapter_internals.py,
    # against ScreenpipeSource) when BrainAdapter re-homed there (SRC-3).


class TestSearchBrainMtimeNotTrusted:
    def test_search_brain_mtime_not_trusted(self):
        # A search_brain-shaped hit with mtime = post-cutoff epoch float and NO
        # content ts must be EXCLUDED (no mtime fallback ever). Even though the
        # hit "looks" retrievable, _content_ts returns None -> dropped.
        brain = FakeBrain(vault_hits=[
            {"path": "5-Reflections/voice.md", "heading": "tone",
             "text": "AFTER_CUTOFF_CONTENT should be excluded",
             "mtime": 1_900_000_000.0, "score": 0.9, "source": "vault"},
        ])
        ctx = officer_runner.gather_cutoff_context(_case(), brain=brain)
        assert ctx["vault_hits"] == []
        assert "AFTER_CUTOFF_CONTENT" not in repr(ctx)

    def test_content_ts_has_no_mtime_fallback(self):
        # _content_ts: ISO ts -> path date -> None. mtime is NEVER consulted.
        assert officer_runner._content_ts(
            {"ts": "2026-05-12T09:00:00+00:00"}) == "2026-05-12T09:00:00+00:00"
        # path-date fallback
        assert officer_runner._content_ts(
            {"path": "1-Daily/2026-05-12.md"}).startswith("2026-05-12")
        # mtime present but no content date -> excluded (None)
        assert officer_runner._content_ts(
            {"path": "5-Reflections/voice.md", "mtime": 1_900_000_000.0}) is None
        assert officer_runner._content_ts({}) is None


class TestContentTsPreferred:
    """The brain index now emits a per-chunk `content_ts` (ISO, the true
    authored/event time). _content_ts MUST prefer it — this is what lets a
    conversation chunk (NO date in its path) be fenced + admitted instead of
    silently excluded (the vault_hits=0 fix)."""

    def test_content_ts_admits_a_pathless_conversation_chunk(self):
        # 3-People conversation: no date in the path; previously -> None
        # (excluded). With content_ts it returns the real authored time.
        hit = {"ref": "3-People/sobuc/conversations.md", "heading": "msg",
               "content_ts": "2026-05-12T09:00:00+00:00",
               "mtime": 1_900_000_000.0}
        assert officer_runner._content_ts(hit) == "2026-05-12T09:00:00+00:00"

    def test_content_ts_preferred_over_path_date(self):
        # content_ts wins over a (possibly misleading) date in the path.
        hit = {"path": "1-Daily/2026-01-01.md",
               "content_ts": "2026-05-12T09:00:00+00:00"}
        assert officer_runner._content_ts(hit) == "2026-05-12T09:00:00+00:00"

    def test_absent_content_ts_falls_back_to_path_date(self):
        # back-compat: no content_ts -> existing path-date behavior.
        assert officer_runner._content_ts(
            {"path": "1-Daily/2026-05-12.md"}).startswith("2026-05-12")

    def test_non_iso_content_ts_ignored(self):
        # a junk/non-ISO content_ts must not be trusted; falls through.
        assert officer_runner._content_ts(
            {"content_ts": "not-a-date", "ref": "3-People/x/conversations.md"}) is None

    def test_pathless_chunk_with_no_content_ts_still_excluded(self):
        # the fail-safe still holds: no content_ts + no path date -> excluded.
        assert officer_runner._content_ts(
            {"ref": "3-People/x/conversations.md", "mtime": 1_900_000_000.0}) is None

    def test_vault_hit_at_or_after_cutoff_dropped(self):
        # A vault hit with an ISO content ts >= cutoff is dropped by the
        # pre-filter (strict <) AND by filter_mcp_result (belt + suspenders).
        brain = FakeBrain(vault_hits=[
            {"path": "3-People/x.md", "text": "AT_CUTOFF",
             "ts": CUTOFF, "source": "vault"},
            {"path": "1-Daily/2026-05-12.md", "text": "BEFORE",
             "ts": "2026-05-12T09:00:00+00:00", "source": "vault"},
        ])
        ctx = officer_runner.gather_cutoff_context(_case(), brain=brain)
        texts = [h.get("text") for h in ctx["vault_hits"]]
        assert "BEFORE" in texts
        assert "AT_CUTOFF" not in texts


class TestPersonIntelDatedSectionStripped:
    def test_person_intel_dated_section_stripped(self):
        # The live dossier absorbs '## Notes from replies' derived from the
        # held-out reply -> only the atemporal frontmatter survives.
        dossier = (
            "---\n"
            "role: VP Product & Publishers\n"
            "relationship: manager\n"
            "primary_email: ulrik@x\n"
            "---\n"
            "\n"
            "## Notes from replies\n"
            "- 2026-06-11: Nate agreed to the Husqvarna mower (LEAK).\n"
        )
        brain = FakeBrain(person_md=dossier)
        ctx = officer_runner.gather_cutoff_context(_case(), brain=brain)
        ps = ctx["person_static"]
        assert "VP Product & Publishers" in ps
        assert "primary_email: ulrik@x" in ps
        assert "Notes from replies" not in ps
        assert "Husqvarna" not in ps
        assert "2026-06-11" not in ps

    def test_static_frontmatter_strips_any_iso_dated_line(self):
        # Any line carrying an ISO date is dropped even outside the Notes block.
        md = ("role: x\n"
              "Last interaction 2026-06-11T08:00:00+00:00 with Nate (LEAK)\n"
              "relationship: peer\n")
        out = officer_runner._static_frontmatter(md)
        assert "role: x" in out
        assert "relationship: peer" in out
        assert "2026-06-11" not in out
        assert "LEAK" not in out

    def test_static_frontmatter_empty_safe(self):
        assert officer_runner._static_frontmatter("") == ""
        assert officer_runner._static_frontmatter(None) == ""

    def test_notes_section_anchored_to_next_heading_atemporal_survives(self):
        # 'Notes from replies' is bounded by the NEXT ##-level heading, so a
        # legitimate atemporal section AFTER it survives. The slash-dated line in
        # the Notes block is dropped; a compact-dated line is dropped too; the
        # ## Contact attributes survive.
        dossier = (
            "role: VP Product\n"
            "relationship: manager\n"
            "\n"
            "## Notes from replies\n"
            "- 2026/06/11: Nate agreed to the Husqvarna mower (SLASH LEAK).\n"
            "- 20260611 compact-dated note (COMPACT LEAK).\n"
            "\n"
            "## Contact\n"
            "primary_email: ulrik@x\n"
            "phone: +45 12 34 56 78\n"
        )
        out = officer_runner._static_frontmatter(dossier)
        # atemporal section after Notes survives
        assert "## Contact" in out
        assert "primary_email: ulrik@x" in out
        assert "+45 12 34 56 78" in out
        # the role frontmatter still survives
        assert "role: VP Product" in out
        # the dated Notes lines are gone (slash + compact forms both stripped)
        assert "Husqvarna" not in out
        assert "2026/06/11" not in out
        assert "20260611" not in out
        assert "COMPACT LEAK" not in out
        assert "Notes from replies" not in out

    def test_static_frontmatter_strips_slash_and_compact_dates(self):
        # Broadened date forms: slash-dated and compact-dated lines anywhere are
        # stripped, not only ISO-hyphen dates.
        md = ("role: x\n"
              "Last sync 2026/06/11 with Nate (SLASH LEAK)\n"
              "Backfilled 20260611 (COMPACT LEAK)\n"
              "relationship: peer\n")
        out = officer_runner._static_frontmatter(md)
        assert "role: x" in out
        assert "relationship: peer" in out
        assert "SLASH LEAK" not in out
        assert "COMPACT LEAK" not in out
        assert "2026/06/11" not in out
        assert "20260611" not in out


class TestCommitmentsFenced:
    def test_commitments_fenced(self):
        # A commitment with source_date >= cutoff is dropped by
        # filter_mcp_result; both directions are admitted and merged.
        brain = FakeBrain(
            owed_by=[
                {"commitment_id": "c1", "text": "send the deck",
                 "source_date": "2026-05-01T09:00:00+00:00", "status": "open"},
                {"commitment_id": "c2", "text": "AFTER promise (leak)",
                 "source_date": "2026-06-11T09:00:00+00:00", "status": "open"},
            ],
            owed_to=[
                {"commitment_id": "c3", "text": "Ulrik to review",
                 "source_date": "2026-05-02T09:00:00+00:00", "status": "open"},
            ],
        )
        ctx = officer_runner.gather_cutoff_context(_case(), brain=brain)
        ids = [c["commitment_id"] for c in ctx["commitments"]]
        assert "c1" in ids and "c3" in ids
        assert "c2" not in ids
        assert "AFTER promise" not in repr(ctx)

    def test_both_directions_queried(self):
        # The runner asks in CONTRACT direction values (base.PersonalSource —
        # the Flavor-A adapter owns the owed_by_nate storage mapping).
        brain = FakeBrain()
        officer_runner.gather_cutoff_context(_case(), brain=brain)
        dirs = [c[1] for c in brain.calls if c[0] == "open_commitments"]
        assert "owed_by_captain" in dirs and "owed_to_captain" in dirs


class TestReadNotePathValidation:
    @pytest.mark.parametrize("bad", [
        "../../etc/passwd",
        "..",
        "/etc/passwd",
        "1-Daily/../../0-Self/nate-model.md",
        "\x00/etc/passwd",
        "//etc/passwd",
    ])
    def test_read_note_path_traversal_rejected(self, bad):
        # gather_cutoff_context must reject traversal / absolute / leading-slash
        # / null-byte paths BEFORE delegating to brain.read_note (defense in
        # depth on the brain server's own vault-jail). The brain mock must
        # NEVER be called for a rejected path.
        brain = FakeBrain(notes={})
        case = _case()
        with pytest.raises((ValueError, PermissionError)):
            officer_runner.gather_cutoff_context(case, brain=brain,
                                                 read_paths=[bad])
        assert not any(c[0] == "read_note" for c in brain.calls)

    def test_read_note_pre_cutoff_path_admitted(self):
        # An explicit, vault-relative, pre-cutoff daily-note path is admitted
        # and ISO-scrubbed of any post-cutoff date line.
        brain = FakeBrain(notes={
            "1-Daily/2026-05-12.md":
                "Looked at mowers for the new house lawn (~3000 m2).\n"
                "Follow-up 2026-06-11T09:00:00+00:00 leak line.\n",
        })
        ctx = officer_runner.gather_cutoff_context(
            _case(), brain=brain, read_paths=["1-Daily/2026-05-12.md"])
        notes = ctx.get("notes", [])
        body = " ".join(n.get("text", "") for n in notes)
        assert "3000 m2" in body
        assert "2026-06-11" not in body  # post-cutoff date line scrubbed

    def test_read_note_post_cutoff_dated_path_rejected(self):
        # A daily-note path whose embedded date is >= cutoff is a future note
        # -> rejected, brain.read_note never called.
        brain = FakeBrain(notes={"1-Daily/2026-06-11.md": "future note"})
        with pytest.raises((ValueError, PermissionError)):
            officer_runner.gather_cutoff_context(
                _case(), brain=brain, read_paths=["1-Daily/2026-06-11.md"])
        assert not any(c[0] == "read_note" for c in brain.calls)

    def test_read_note_scrubs_slash_and_compact_dated_lines(self):
        # Audit finding #2b: _scrub_iso_lines must use the SAME broad dated-line
        # matching as _static_frontmatter (ISO + slash + compact + full
        # timestamps). A pre-cutoff daily note (filename passes the path gate)
        # whose BODY carries post-cutoff dates in the slash or compact form must
        # have those lines scrubbed — exactly like the ISO form already is.
        # The scrub is conservative (drops ANY dated line, since a single date
        # string can't be reliably cutoff-compared); undated pre-cutoff content
        # lines survive.
        brain = FakeBrain(notes={
            "1-Daily/2026-05-12.md":
                "Looked at mowers for the new house lawn (~3000 m2).\n"
                "Follow-up 2026/06/11 with Husqvarna (SLASH LEAK)\n"
                "Ordered backup blade 20260611 (COMPACT LEAK)\n"
                "Plan: pick a model and order it before the weekend.\n",
        })
        ctx = officer_runner.gather_cutoff_context(
            _case(), brain=brain, read_paths=["1-Daily/2026-05-12.md"])
        notes = ctx.get("notes", [])
        body = " ".join(n.get("text", "") for n in notes)
        # the post-cutoff slash- and compact-dated lines are both scrubbed
        assert "SLASH LEAK" not in body
        assert "COMPACT LEAK" not in body
        assert "2026/06/11" not in body
        assert "20260611" not in body
        # …and the undated content lines survive (the scrub is line-scoped)
        assert "3000 m2" in body
        assert "pick a model and order it" in body


class TestRealVaultHitShape:
    """The REAL fence proof. The other vault-hit tests feed an ISO-STRING ``ts``
    — a shape that NEVER occurs via the real adapter. context_lib.gather emits
    each vault hit as {"ref": <path>, "ts": <datetime from mtime>, "text", ...}
    (context_lib.py:144-147, _fetch_vault). So the LOAD-BEARING fence on vault
    hits is _content_ts's PATH-DATE extraction (over-exclusion-by-default); the
    datetime/mtime ts must NEVER admit a hit. These drive gather_cutoff_context
    with the real shape to prove exactly that."""

    BRIEF = ("BRIEF_PROSE: Nate already replied with the Husqvarna URL on "
             "2026-06-11 (un-fenceable summary that must never reach the officer)")

    @staticmethod
    def _real_hit(ref, text, *, mtime_iso="2026-07-01T00:00:00+00:00"):
        # Mirror context_lib._fetch_vault (context_lib.py:144-147): ts is a
        # DATETIME derived from mtime (the wrong clock — always set POST-cutoff
        # here to prove it never admits a hit on its own), path keyed under
        # `ref`. NO per-hit `brief` — the real hit shape has none; the brief is
        # the TOP-LEVEL gather_context field (set via FakeBrain(brief=...)).
        return {
            "source": "vault", "ref": ref,
            "heading": "", "text": text,
            "base_score": 0.8,
            "ts": datetime.fromisoformat(mtime_iso),  # datetime, NOT a str
        }

    def test_pre_cutoff_daily_note_admitted_via_path_date(self):
        # (a) ref = pre-cutoff daily-note path + datetime ts → ADMITTED via
        # _content_ts path-date (NOT via the datetime ts, which is post-cutoff).
        hit = self._real_hit("1-Daily/2026-05-12.md",
                             "new house at Mosevraavej, big lawn ~3000 m2")
        brain = FakeBrain(vault_hits=[hit], brief=self.BRIEF)
        ctx = officer_runner.gather_cutoff_context(_case(), brain=brain)
        assert len(ctx["vault_hits"]) == 1
        # the hit's text survives (admitted, not just present-but-empty)
        assert any("3000 m2" in (h.get("text") or "")
                   for h in ctx["vault_hits"])

    def test_non_dated_path_with_datetime_ts_excluded(self):
        # (b) ref = a NON-dated path + datetime ts → EXCLUDED. No derivable
        # content-ts; the datetime (mtime) ts must NOT admit it — mtime is the
        # wrong clock. This is the over-exclusion fence in action.
        hit = self._real_hit("3-People/sobuc/conversations.md",
                             "SOBUC_CONTENT must be excluded (mtime-only)")
        brain = FakeBrain(vault_hits=[hit], brief=self.BRIEF)
        ctx = officer_runner.gather_cutoff_context(_case(), brain=brain)
        assert ctx["vault_hits"] == []
        assert "SOBUC_CONTENT" not in repr(ctx)

    def test_post_cutoff_daily_note_path_excluded(self):
        # (c) ref = a POST-cutoff daily-note path → EXCLUDED (path date >= cutoff).
        hit = self._real_hit("1-Daily/2026-07-01.md",
                             "FUTURE_DAILY content must be excluded")
        brain = FakeBrain(vault_hits=[hit], brief=self.BRIEF)
        ctx = officer_runner.gather_cutoff_context(_case(), brain=brain)
        assert ctx["vault_hits"] == []
        assert "FUTURE_DAILY" not in repr(ctx)

    def test_gather_context_brief_never_in_output(self):
        # (d) the top-level gather_context `brief` (un-fenceable post-cutoff
        # prose) is never present in the output — even with an admitted hit,
        # gather_cutoff_context reads only vault["hits"], never vault["brief"].
        hit = self._real_hit("1-Daily/2026-05-12.md", "admissible content")
        brain = FakeBrain(vault_hits=[hit], brief=self.BRIEF)
        ctx = officer_runner.gather_cutoff_context(_case(), brain=brain)
        assert "BRIEF_PROSE" not in repr(ctx)
        assert "Husqvarna" not in repr(ctx)
        assert "brief" not in ctx


class TestSafeShape:
    def test_returns_structured_ts_keyed_dict_never_prose(self):
        brain = FakeBrain(
            vault_hits=[{"path": "1-Daily/2026-05-12.md", "text": "ok",
                         "ts": "2026-05-12T09:00:00+00:00", "source": "vault"}],
            brief="prose brief that must never appear",
            person_md="role: x\n",
        )
        ctx = officer_runner.gather_cutoff_context(_case(), brain=brain)
        # thread carried through
        assert ctx["thread"] == _case().thread_before
        # excluded list names the dropped un-fenceable sources (audit trail)
        joined = " ".join(ctx["excluded"]).lower()
        assert "search_brain" in joined
        assert "brief" in joined
        assert "tier-2" in joined or "tier 2" in joined
        # structured containers only — no top-level free-text source field
        assert isinstance(ctx["vault_hits"], list)
        assert isinstance(ctx["commitments"], list)
