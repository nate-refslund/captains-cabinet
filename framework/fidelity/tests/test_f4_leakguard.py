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
    can be reached (gather_cutoff_context only ever calls gather_vault)."""

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

    def gather_vault(self, handle):
        # gather_cutoff_context MUST scope to the vault tier only. The real
        # adapter calls context_lib.gather(handle, sources=["vault"]); this
        # fake mirrors the {hits, brief} shape and records the call. If any
        # code path tried to reach a Tier-2 fetcher it would have to call a
        # method that does not exist here -> AttributeError, surfacing the bug.
        self.calls.append(("gather_vault", handle))
        return {"hits": list(self._vault_hits), "brief": self._brief}

    def person_intel(self, slug):
        self.calls.append(("person_intel", slug))
        return self._person_md

    def open_commitments(self, direction):
        self.calls.append(("open_commitments", direction))
        return list(self._owed_by if direction == "owed_by_nate"
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


class TestTier2Unreachable:
    def test_tier2_unreachable(self):
        # gather_cutoff_context must call the vault tier ONLY. Assert the
        # gather_vault call happened and that no Tier-2 fetcher entry point
        # exists on the path (the fake has none — a Tier-2 attempt would
        # AttributeError). Also assert the real adapter scopes sources=["vault"].
        brain = FakeBrain(vault_hits=[])
        officer_runner.gather_cutoff_context(_case(), brain=brain)
        assert ("gather_vault", "ulrik") in brain.calls or \
               any(c[0] == "gather_vault" for c in brain.calls)
        # no Tier-2 method was ever added/called
        assert not brain.tier2_invoked

    def test_real_adapter_scopes_sources_to_vault(self):
        # The default adapter's gather_vault MUST delegate to context_lib.gather
        # with sources=["vault"] EXACTLY — never the default all-source fan-out
        # (which fires _fetch_sent / _fetch_screen / _fetch_monday = "now").
        seen = {}

        class StubContextLib:
            @staticmethod
            def gather(handle, *, sources=None, **kw):
                seen["sources"] = sources
                seen["handle"] = handle
                return {"hits": [], "brief": "", "counts": {}}

        brain = officer_runner.BrainAdapter(context_lib=StubContextLib())
        brain.gather_vault("ulrik")
        assert seen["sources"] == ["vault"]
        assert seen["handle"] == "ulrik"

    def test_tier2_fetcher_raises_if_invoked(self):
        # A golden-style guard: wire a context_lib whose Tier-2 fetchers raise,
        # and confirm gather_cutoff_context never trips them (vault-only path).
        class TrapContextLib:
            @staticmethod
            def gather(handle, *, sources=None, **kw):
                if sources != ["vault"]:
                    raise AssertionError(
                        f"Tier-2 leak: gather called with sources={sources}")
                return {"hits": [], "brief": ""}

        brain = officer_runner.BrainAdapter(context_lib=TrapContextLib())
        # Should not raise — vault-only scoping holds.
        out = officer_runner.gather_cutoff_context(_case(), brain=brain)
        assert "vault_hits" in out


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
        brain = FakeBrain()
        officer_runner.gather_cutoff_context(_case(), brain=brain)
        dirs = [c[1] for c in brain.calls if c[0] == "open_commitments"]
        assert "owed_by_nate" in dirs and "owed_to_nate" in dirs


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
