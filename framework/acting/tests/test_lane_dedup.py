"""Pure draft/action-lane dedup + recency helpers (framework.acting.lane_dedup).

Moved from the former ``test_skip_stick.py`` when the screenpipe acting surface
re-homed to the Flavor-A adapter (SRC-3): these classes exercise the PURE
(zero-screenpipe) helpers — timestamp parsing, the decided/open proposal maps
from the consequence ledger, the recency-aware open/handled gates, and redis
key hygiene — which stayed in ``framework.acting.lane_dedup``. Bodies unchanged;
only the module handle is ``ld`` (lane_dedup) instead of the old ``sa``."""
import datetime

from framework.acting import lane_dedup as ld


def _thread(slug="casper", date="2026-06-20T10:00:00+00:00", text="hej Ada"):
    return {"slug": slug, "person": slug.title(),
            "last": {"date": date, "text": text, "source": "msgraph"}}


def _decided_row(subject, decided_at, ts=None):
    """A ledger row shaped like read_ledger() returns for a DECIDED proposal."""
    return {"ts": ts or decided_at, "actor": {"kind": "officer", "id": "cos"},
            "lane": "send-1to1-reply", "action": "draft-reply", "subject": subject,
            "proposal": {"required": True, "decision": "rejected",
                         "decided_at": decided_at}}


class TestParseDt:
    def test_msgraph_offset(self):
        d = ld.parse_dt("2026-06-18T12:49:44+00:00")
        assert d is not None and d.tzinfo is not None
        assert d == datetime.datetime(2026, 6, 18, 12, 49, 44,
                                      tzinfo=datetime.timezone.utc)

    def test_teams_zulu_fractional(self):
        d = ld.parse_dt("2026-02-03T19:59:48.471Z")
        assert d is not None
        assert d.year == 2026 and d.tzinfo == datetime.timezone.utc

    def test_naive_assumed_utc(self):
        d = ld.parse_dt("2026-06-20T10:00:00")
        assert d is not None and d.tzinfo == datetime.timezone.utc

    def test_garbage_is_none(self):
        assert ld.parse_dt("not-a-date") is None
        assert ld.parse_dt("") is None
        assert ld.parse_dt(None) is None


class TestDecidedSubjects:
    def test_maps_subject_to_decided_at(self):
        rows = [_decided_row("casper", "2026-06-20T09:00:00+00:00")]
        d = ld.decided_subjects(rows=rows)
        assert "casper" in d
        assert d["casper"] == ld.parse_dt("2026-06-20T09:00:00+00:00")

    def test_keeps_latest_decision_per_subject(self):
        rows = [
            _decided_row("casper", "2026-06-20T09:00:00+00:00"),
            _decided_row("casper", "2026-06-21T09:00:00+00:00"),  # newer
        ]
        d = ld.decided_subjects(rows=rows)
        assert d["casper"] == ld.parse_dt("2026-06-21T09:00:00+00:00")

    def test_pending_proposal_excluded(self):
        rows = [{"ts": "2026-06-20T09:00:00+00:00",
                 "actor": {"kind": "officer", "id": "cos"},
                 "lane": "send-1to1-reply", "action": "draft-reply",
                 "subject": "lena",
                 "proposal": {"required": True, "decision": None}}]
        assert ld.decided_subjects(rows=rows) == {}

    def test_falls_back_to_ts_when_no_decided_at(self):
        rows = [{"ts": "2026-06-20T09:00:00+00:00",
                 "actor": {"kind": "officer", "id": "cos"},
                 "lane": "send-1to1-reply", "action": "draft-reply",
                 "subject": "lena",
                 "proposal": {"required": True, "decision": "approved"}}]
        d = ld.decided_subjects(rows=rows)
        assert d["lena"] == ld.parse_dt("2026-06-20T09:00:00+00:00")


class TestAlreadyHandledTimestamp:
    def test_decided_and_no_new_message_is_handled(self):
        # last inbound (10:00) is OLDER than the decision (12:00) -> handled.
        decided = {"casper": ld.parse_dt("2026-06-20T12:00:00+00:00")}
        t = _thread(date="2026-06-20T10:00:00+00:00")
        assert ld.already_handled(t, decided) is True

    def test_decided_equal_time_is_handled(self):
        # last inbound == decision time -> not strictly newer -> handled.
        decided = {"casper": ld.parse_dt("2026-06-20T12:00:00+00:00")}
        t = _thread(date="2026-06-20T12:00:00+00:00")
        assert ld.already_handled(t, decided) is True

    def test_new_inbound_after_decision_re_presents(self):
        # a fresh message (13:00) AFTER the decision (12:00) -> NOT handled.
        decided = {"casper": ld.parse_dt("2026-06-20T12:00:00+00:00")}
        t = _thread(date="2026-06-20T13:00:00+00:00")
        assert ld.already_handled(t, decided) is False

    def test_never_decided_is_not_handled(self):
        # no decision recorded for this subject -> a fresh thread, present it.
        t = _thread(slug="newperson")
        assert ld.already_handled(t, {}) is False


class TestAlreadyHandledSignatureFallback:
    def test_signature_match_handled_when_no_timestamp(self, monkeypatch):
        # No parseable decision time (subject absent from decided map) but the
        # last-inbound text matches the recorded handled signature -> handled.
        t = _thread(text="same message body")
        sig = ld.last_inbound_sig(t)
        monkeypatch.setattr(ld, "handled_signature", lambda slug: sig)
        assert ld.already_handled(t, {}) is True

    def test_signature_mismatch_re_presents(self, monkeypatch):
        t = _thread(text="a brand new message body")
        monkeypatch.setattr(ld, "handled_signature", lambda slug: "deadbeef")
        assert ld.already_handled(t, {}) is False

    def test_unparseable_date_uses_signature(self, monkeypatch):
        # Decision exists, but the inbound date is garbage -> timestamp path
        # cannot fire -> fall back to the signature.
        t = _thread(date="garbage-date", text="hello")
        sig = ld.last_inbound_sig(t)
        decided = {"casper": ld.parse_dt("2026-06-20T12:00:00+00:00")}
        monkeypatch.setattr(ld, "handled_signature", lambda slug: sig)
        assert ld.already_handled(t, decided) is True


class TestRedisKeyHygiene:
    def test_slug_with_spaces_and_colons_is_flattened(self):
        # The redis key must never carry spaces/colons that fracture the keyspace.
        k = ld._handled_key("Alma Kruse: Bakery")
        assert k.startswith("cabinet:draft-handled:")
        suffix = k[len("cabinet:draft-handled:"):]
        assert " " not in suffix and ":" not in suffix


def _open_row(subject, ts):
    """A ledger row shaped like read_ledger() returns for an OPEN (undecided,
    no-outcome) proposal."""
    return {"ts": ts, "actor": {"kind": "officer", "id": "cos"},
            "lane": "send-1to1-reply", "action": "draft-reply", "subject": subject,
            "proposal": {"required": True, "decision": None}}


class TestOpenSubjectTs:
    def test_maps_subject_to_proposal_ts(self):
        rows = [_open_row("casper", "2026-06-24T21:00:00+00:00")]
        d = ld.open_subject_ts(rows=rows)
        assert d["casper"] == ld.parse_dt("2026-06-24T21:00:00+00:00")

    def test_keeps_newest_open_ts_per_subject(self):
        rows = [
            _open_row("casper", "2026-06-24T21:00:00+00:00"),
            _open_row("casper", "2026-06-25T07:00:00+00:00"),  # newer
        ]
        d = ld.open_subject_ts(rows=rows)
        assert d["casper"] == ld.parse_dt("2026-06-25T07:00:00+00:00")

    def test_decided_proposal_excluded(self):
        rows = [_decided_row("lena", "2026-06-24T09:00:00+00:00")]
        assert ld.open_subject_ts(rows=rows) == {}

    def test_superseded_with_outcome_excluded(self):
        rows = [{"ts": "2026-06-24T21:00:00+00:00",
                 "actor": {"kind": "officer", "id": "cos"},
                 "lane": "send-1to1-reply", "action": "draft-reply",
                 "subject": "lena",
                 "proposal": {"required": True, "decision": None},
                 "outcome": {"status": "ok", "evidence": "shipped"}}]
        assert ld.open_subject_ts(rows=rows) == {}


class TestOpenProposalBlocks:
    """Fix 3: an OPEN proposal suppresses a thread ONLY until a genuinely-new
    inbound arrives — the Casper Round-2 bug, where a Round-1 draft sat open
    overnight and silently swallowed the 11h-newer Round-2 message."""

    def test_open_and_no_new_message_blocks(self):
        # Last inbound (20:00) is OLDER than the open proposal (21:00) -> blocked
        # (the pending draft already covers this message).
        open_ts = {"casper": ld.parse_dt("2026-06-24T21:00:00+00:00")}
        t = _thread(date="2026-06-24T20:00:00+00:00")
        assert ld.open_proposal_blocks(t, open_ts) is True

    def test_open_equal_time_blocks(self):
        open_ts = {"casper": ld.parse_dt("2026-06-24T21:00:00+00:00")}
        t = _thread(date="2026-06-24T21:00:00+00:00")
        assert ld.open_proposal_blocks(t, open_ts) is True

    def test_new_inbound_after_open_proposal_re_presents(self):
        # THE FIX: a fresh message (2026-06-25 08:53) after the open proposal
        # (2026-06-24 21:00) -> NOT blocked -> the lane re-presents Round-2.
        open_ts = {"casper": ld.parse_dt("2026-06-24T21:00:00+00:00")}
        t = _thread(date="2026-06-25T08:53:34+00:00")
        assert ld.open_proposal_blocks(t, open_ts) is False

    def test_no_open_proposal_does_not_block(self):
        # A subject with no open proposal is never blocked by this gate.
        t = _thread(slug="freshperson")
        assert ld.open_proposal_blocks(t, {}) is False

    def test_unparseable_inbound_with_open_proposal_blocks(self):
        # Open proposal exists but the inbound date is garbage -> cannot prove a
        # newer message -> block (don't double-draft a pending thread).
        open_ts = {"casper": ld.parse_dt("2026-06-24T21:00:00+00:00")}
        t = _thread(date="garbage-date")
        assert ld.open_proposal_blocks(t, open_ts) is True


class TestSubjectHasOpenProposal:
    """Live (moment-of-use) dup guard: the duplicate-draft fix. Two concurrent
    runs both snapshot 'no open Petra proposal' before either emits; re-reading
    the ledger right before emit makes the second run SEE the first's proposal."""

    def test_open_proposal_for_subject_is_true(self):
        rows = [_open_row("Petra-Berg-Holm", "2026-06-25T09:56:53+00:00")]
        assert ld.subject_has_open_proposal("Petra-Berg-Holm", rows=rows) is True

    def test_no_open_proposal_for_subject_is_false(self):
        rows = [_open_row("someone-else", "2026-06-25T09:56:53+00:00")]
        assert ld.subject_has_open_proposal("Petra-Berg-Holm", rows=rows) is False

    def test_decided_proposal_does_not_count_as_open(self):
        # A decided proposal must NOT block a fresh draft via this guard (the
        # recency path handles decided threads separately).
        rows = [_decided_row("Petra-Berg-Holm", "2026-06-25T09:00:00+00:00")]
        assert ld.subject_has_open_proposal("Petra-Berg-Holm", rows=rows) is False


class TestOpenProposalBlocksLive:
    """RECENCY-AWARE Layer-2 pre-emit dup guard (open_proposal_blocks_live).
    Regression cover for the Milo-Archer 17:05 DPA miss: the blunt
    subject_has_open_proposal predecessor skipped on ANY open proposal, so a
    legitimately-NEW inbound that passed the recency-aware top-of-loop gate was
    then killed here by a STALE older open proposal. The live variant must apply
    the SAME last_dt <= when recency test as open_proposal_blocks."""

    def test_morten_newer_inbound_not_blocked_by_stale_open(self):
        # The exact failure: an open draft for Milo's 14:53 (12:53Z) message
        # sits undecided; his 17:05 (15:05Z) reply is genuinely NEW. The live
        # guard must NOT block it (newer than the open proposal) -> it re-presents.
        rows = [_open_row("Milo-Archer", "2026-06-25T13:15:58+00:00")]
        t = _thread(slug="Milo-Archer", date="2026-06-25T15:05:13+00:00")
        assert ld.open_proposal_blocks_live(t, rows=rows) is False

    def test_same_message_open_proposal_blocks(self):
        # A proposal that landed DURING our draft for the SAME (or older-than-our)
        # inbound is a true duplicate -> block. Inbound 13:00Z <= open 13:15Z.
        rows = [_open_row("Milo-Archer", "2026-06-25T13:15:58+00:00")]
        t = _thread(slug="Milo-Archer", date="2026-06-25T13:00:00+00:00")
        assert ld.open_proposal_blocks_live(t, rows=rows) is True

    def test_no_open_proposal_not_blocked(self):
        rows = [_open_row("someone-else", "2026-06-25T13:15:58+00:00")]
        t = _thread(slug="Milo-Archer", date="2026-06-25T15:05:13+00:00")
        assert ld.open_proposal_blocks_live(t, rows=rows) is False

    def test_decided_proposal_not_blocked(self):
        # A decided proposal is handled by the decided/already_handled path, not
        # this open-proposal guard -> not blocked here.
        rows = [_decided_row("Milo-Archer", "2026-06-25T13:00:00+00:00")]
        t = _thread(slug="Milo-Archer", date="2026-06-25T15:05:13+00:00")
        assert ld.open_proposal_blocks_live(t, rows=rows) is False

    def test_unparseable_inbound_with_open_proposal_blocks(self):
        # Open proposal exists but inbound date is garbage -> cannot prove newer
        # -> block (conservative: never double-draft a pending thread).
        rows = [_open_row("Milo-Archer", "2026-06-25T13:15:58+00:00")]
        t = _thread(slug="Milo-Archer", date="garbage")
        assert ld.open_proposal_blocks_live(t, rows=rows) is True
