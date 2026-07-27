"""ask_mint — same-source ask batching, the producer-side helper.

Pins the properties that make ONE card safe to answer for N asks: the
grouping is deterministic, the body lists every member it covers, the
membership parses back EXACTLY (so a fan-out can only reach what the
Captain saw), every unreadable body fails closed to no members at all,
the degenerate end (one ask) is never dressed up as a batch, a group
larger than the cap defers its tail instead of hiding it, and the helper
itself writes nothing anywhere — its only effect is the injected
``file_need`` seam.
"""
from __future__ import annotations

from pathlib import Path

import ask_mint as am

_LIB = Path(__file__).resolve().parents[1]


class Recorder:
    """file_need seam: records every card the helper tries to file."""

    def __init__(self, need_id="NEED-feedbeef"):
        self.calls = []
        self.need_id = need_id

    def __call__(self, kind, **kw):
        self.calls.append((kind, kw))
        return self.need_id


def _asks(pairs):
    return [{"source": s, "member": m} for s, m in pairs]


def _group(asks):
    return am.group_by_source(asks, source_of=lambda a: a["source"],
                              member_of=lambda a: a["member"])


class TestGrouping:
    def test_eleven_same_source_asks_are_one_group_of_eleven(self):
        groups = _group(_asks([("row-42", f"ask-{i:02d}") for i in range(11)]))
        assert len(groups) == 1
        key, members = groups[0]
        assert key == "row-42" and len(members) == 11
        assert members == tuple(sorted(f"ask-{i:02d}" for i in range(11)))

    def test_three_distinct_sources_stay_three_groups(self):
        groups = _group(_asks([("a", "ask-1"), ("b", "ask-2"), ("c", "ask-3")]))
        assert [k for k, _ in groups] == ["a", "b", "c"]
        assert all(len(m) == 1 for _, m in groups)

    def test_grouping_is_deterministic_and_deduped(self):
        raw = _asks([("b", "y"), ("a", "x"), ("b", "y"), ("b", "x")])
        assert _group(raw) == [("a", ("x",)), ("b", ("x", "y"))]
        assert _group(raw) == _group(list(reversed(raw)))

    def test_unusable_ids_and_sources_are_skipped_not_fatal(self):
        raw = [{"source": "a", "member": "ok-1"},
               {"source": "", "member": "ok-2"},
               {"source": "a", "member": None},
               {"source": "a", "member": "has space"},
               {"source": "a b", "member": "ok-3"}]
        assert _group(raw) == [("a", ("ok-1",))]

    def test_a_raising_accessor_never_breaks_the_group(self):
        def boom(_ask):
            raise RuntimeError("nope")

        assert am.group_by_source([{"x": 1}], source_of=boom,
                                  member_of=lambda a: "m") == []


class TestBodyRoundTrip:
    def test_body_lists_every_member_and_parses_back_exactly(self):
        members = tuple(f"sup-{i:04d}" for i in range(11))
        body = am.render_batch_body("row-42", members,
                                    noun="memory supersessions")
        assert "11 memory supersessions cued by row row-42" in body
        assert "approve all / list / skip all" in body
        assert am.batch_members(body) == members
        for member in members:
            assert member in body

    def test_body_carries_no_pid_marker_char(self):
        # U+00B7 is the binder's bindable marker; needs._clean strips it, so
        # a body that leaned on it would lose its membership silently.
        body = am.render_batch_body("r", ("a", "b"), noun="asks",
                                    detail="approve all = do both")
        assert "·" not in body

    def test_a_needs_row_dict_parses_the_same_as_its_why(self):
        body = am.render_batch_body("r", ("a", "b"), noun="asks")
        assert am.batch_members({"why": body}) == ("a", "b")


class TestFailClosedMembership:
    def test_no_membership_line_yields_no_members(self):
        assert am.batch_members("2 asks cued by row r — approve all") == ()
        assert am.batch_members("") == ()
        assert am.batch_members(None) == ()
        assert am.batch_members({"why": None}) == ()

    def test_a_count_that_disagrees_with_the_list_yields_no_members(self):
        body = am.render_batch_body("r", ("a", "b", "c"), noun="asks")
        assert am.batch_members(body.replace("members (3)", "members (2)")) == ()
        assert am.batch_members(body.replace(", c", "")) == ()

    def test_a_second_membership_line_yields_no_members(self):
        body = am.render_batch_body("r", ("a", "b"), noun="asks",
                                    detail="members (1): c")
        assert am.batch_members(body) == ()

    def test_a_token_that_is_not_an_id_yields_no_members(self):
        body = am.render_batch_body("r", ("a", "b"), noun="asks")
        assert am.batch_members(body.replace("b", "b/../etc")) == ()
        assert am.batch_members("members (2): a, ") == ()

    def test_a_duplicated_member_yields_no_members(self):
        assert am.batch_members("members (2): a, a") == ()


class TestMinting:
    def test_eleven_members_mint_exactly_one_card(self):
        rec = Recorder()
        members = [f"sup-{i:04d}" for i in range(11)]
        out = am.group_pending_asks("row-42", members, producer="organ",
                                    noun="asks", filed_by="system:organ",
                                    file_need_fn=rec)
        assert out["batched"] is True and out["need_id"] == "NEED-feedbeef"
        assert len(rec.calls) == 1
        kind, kw = rec.calls[0]
        assert kind == "decision"
        assert kw["action_type"] == "organ:batch:row-42"
        assert kw["cid"] == "row-42" and kw["filed_by"] == "system:organ"
        assert am.batch_members(kw["why"]) == tuple(sorted(members))

    def test_one_member_is_not_a_batch_and_files_nothing(self):
        rec = Recorder()
        out = am.group_pending_asks("row-42", ["sup-0001"], producer="organ",
                                    noun="asks", filed_by="system:organ",
                                    file_need_fn=rec)
        assert out["batched"] is False and out["need_id"] is None
        assert rec.calls == []

    def test_zero_members_or_unusable_source_is_not_a_batch(self):
        rec = Recorder()
        for key, members in (("row-42", []), ("", ["a", "b"]),
                             (None, ["a", "b"]), ("bad key", ["a", "b"])):
            out = am.group_pending_asks(key, members, producer="organ",
                                        noun="asks", filed_by="s",
                                        file_need_fn=rec)
            assert out["batched"] is False
        assert rec.calls == []

    def test_a_group_past_the_cap_defers_its_tail_instead_of_hiding_it(self):
        rec = Recorder()
        members = [f"sup-{i:04d}" for i in range(am.MAX_BATCH_MEMBERS + 5)]
        out = am.group_pending_asks("row-42", members, producer="organ",
                                    noun="asks", filed_by="s",
                                    file_need_fn=rec)
        assert len(out["members"]) == am.MAX_BATCH_MEMBERS
        assert len(out["deferred"]) == 5
        assert set(out["members"]) | set(out["deferred"]) == set(members)
        body = rec.calls[0][1]["why"]
        assert am.batch_members(body) == out["members"]
        for member in out["deferred"]:
            assert member not in body

    def test_a_no_op_ledger_leaves_need_id_none_without_raising(self):
        out = am.group_pending_asks("row-42", ["a", "b"], producer="organ",
                                    noun="asks", filed_by="s",
                                    file_need_fn=lambda kind, **kw: None)
        assert out["batched"] is True and out["need_id"] is None

    def test_a_raising_seam_never_escapes(self):
        def boom(kind, **kw):
            raise RuntimeError("ledger down")

        out = am.group_pending_asks("row-42", ["a", "b"], producer="organ",
                                    noun="asks", filed_by="s",
                                    file_need_fn=boom)
        assert out["batched"] is True and out["need_id"] is None


class TestActionTypeGrammar:
    def test_batch_actions_are_producer_scoped(self):
        action = am.batch_action_type("organ", "row-42")
        assert action == "organ:batch:row-42"
        assert am.is_batch_action(action, producer="organ") is True
        assert am.is_batch_action(action, producer="other") is False
        assert am.batch_source_key(action) == "row-42"

    def test_a_per_item_action_is_never_read_as_a_batch(self):
        assert am.is_batch_action("organ:sup-abc", producer="organ") is False
        assert am.batch_source_key("organ:sup-abc") is None
        assert am.is_batch_action(None) is False


class TestNoSideEffects:
    def test_the_helper_writes_nothing_of_its_own(self):
        # The ONLY effect a batcher may have is the injected file_need seam:
        # a helper that reached a store directly would put a second writer
        # behind the germline needs API.
        src = (_LIB / "ask_mint.py").read_text()
        for primitive in ("open(", ".write(", ".write_text(", "os.",
                          "shutil", "subprocess", "requests"):
            assert primitive not in src, \
                f"ask_mint reached for {primitive!r} — it must stay pure"
