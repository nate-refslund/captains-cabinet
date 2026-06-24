"""Fix 1 — a decided draft proposal must STICK: the propose loop must NOT
re-present a thread Nate already ruled on (skip/send/edit) unless a genuinely
NEW inbound message arrived since the decision.

These exercise the PURE dedup helpers in screenpipe_adapter (no screenpipe libs
needed): timestamp parsing, the decided-subject map from the ledger, and the
already_handled() gate via both its primary (timestamp) and fallback (signature)
paths. The screenpipe-backed gather()/prep()/find_threads paths are out of scope
here (covered by the live DRY run); these lock the dedup logic that fixes the
2h-re-present bug."""
import datetime

from framework.acting import screenpipe_adapter as sa


def _thread(slug="kristoffer", date="2026-06-20T10:00:00+00:00", text="hej Nate"):
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
        d = sa.parse_dt("2026-06-18T12:49:44+00:00")
        assert d is not None and d.tzinfo is not None
        assert d == datetime.datetime(2026, 6, 18, 12, 49, 44,
                                      tzinfo=datetime.timezone.utc)

    def test_teams_zulu_fractional(self):
        d = sa.parse_dt("2026-02-03T19:59:48.471Z")
        assert d is not None
        assert d.year == 2026 and d.tzinfo == datetime.timezone.utc

    def test_naive_assumed_utc(self):
        d = sa.parse_dt("2026-06-20T10:00:00")
        assert d is not None and d.tzinfo == datetime.timezone.utc

    def test_garbage_is_none(self):
        assert sa.parse_dt("not-a-date") is None
        assert sa.parse_dt("") is None
        assert sa.parse_dt(None) is None


class TestDecidedSubjects:
    def test_maps_subject_to_decided_at(self):
        rows = [_decided_row("kristoffer", "2026-06-20T09:00:00+00:00")]
        d = sa.decided_subjects(rows=rows)
        assert "kristoffer" in d
        assert d["kristoffer"] == sa.parse_dt("2026-06-20T09:00:00+00:00")

    def test_keeps_latest_decision_per_subject(self):
        rows = [
            _decided_row("kristoffer", "2026-06-20T09:00:00+00:00"),
            _decided_row("kristoffer", "2026-06-21T09:00:00+00:00"),  # newer
        ]
        d = sa.decided_subjects(rows=rows)
        assert d["kristoffer"] == sa.parse_dt("2026-06-21T09:00:00+00:00")

    def test_pending_proposal_excluded(self):
        rows = [{"ts": "2026-06-20T09:00:00+00:00",
                 "actor": {"kind": "officer", "id": "cos"},
                 "lane": "send-1to1-reply", "action": "draft-reply",
                 "subject": "lisa",
                 "proposal": {"required": True, "decision": None}}]
        assert sa.decided_subjects(rows=rows) == {}

    def test_falls_back_to_ts_when_no_decided_at(self):
        rows = [{"ts": "2026-06-20T09:00:00+00:00",
                 "actor": {"kind": "officer", "id": "cos"},
                 "lane": "send-1to1-reply", "action": "draft-reply",
                 "subject": "lisa",
                 "proposal": {"required": True, "decision": "approved"}}]
        d = sa.decided_subjects(rows=rows)
        assert d["lisa"] == sa.parse_dt("2026-06-20T09:00:00+00:00")


class TestAlreadyHandledTimestamp:
    def test_decided_and_no_new_message_is_handled(self):
        # last inbound (10:00) is OLDER than the decision (12:00) -> handled.
        decided = {"kristoffer": sa.parse_dt("2026-06-20T12:00:00+00:00")}
        t = _thread(date="2026-06-20T10:00:00+00:00")
        assert sa.already_handled(t, decided) is True

    def test_decided_equal_time_is_handled(self):
        # last inbound == decision time -> not strictly newer -> handled.
        decided = {"kristoffer": sa.parse_dt("2026-06-20T12:00:00+00:00")}
        t = _thread(date="2026-06-20T12:00:00+00:00")
        assert sa.already_handled(t, decided) is True

    def test_new_inbound_after_decision_re_presents(self):
        # a fresh message (13:00) AFTER the decision (12:00) -> NOT handled.
        decided = {"kristoffer": sa.parse_dt("2026-06-20T12:00:00+00:00")}
        t = _thread(date="2026-06-20T13:00:00+00:00")
        assert sa.already_handled(t, decided) is False

    def test_never_decided_is_not_handled(self):
        # no decision recorded for this subject -> a fresh thread, present it.
        t = _thread(slug="newperson")
        assert sa.already_handled(t, {}) is False


class TestAlreadyHandledSignatureFallback:
    def test_signature_match_handled_when_no_timestamp(self, monkeypatch):
        # No parseable decision time (subject absent from decided map) but the
        # last-inbound text matches the recorded handled signature -> handled.
        t = _thread(text="same message body")
        sig = sa.last_inbound_sig(t)
        monkeypatch.setattr(sa, "handled_signature", lambda slug: sig)
        assert sa.already_handled(t, {}) is True

    def test_signature_mismatch_re_presents(self, monkeypatch):
        t = _thread(text="a brand new message body")
        monkeypatch.setattr(sa, "handled_signature", lambda slug: "deadbeef")
        assert sa.already_handled(t, {}) is False

    def test_unparseable_date_uses_signature(self, monkeypatch):
        # Decision exists, but the inbound date is garbage -> timestamp path
        # cannot fire -> fall back to the signature.
        t = _thread(date="garbage-date", text="hello")
        sig = sa.last_inbound_sig(t)
        decided = {"kristoffer": sa.parse_dt("2026-06-20T12:00:00+00:00")}
        monkeypatch.setattr(sa, "handled_signature", lambda slug: sig)
        assert sa.already_handled(t, decided) is True


class TestRedisKeyHygiene:
    def test_slug_with_spaces_and_colons_is_flattened(self):
        # The redis key must never carry spaces/colons that fracture the keyspace.
        k = sa._handled_key("Anna Grobelscheg: PolAds")
        assert k.startswith("cabinet:draft-handled:")
        suffix = k[len("cabinet:draft-handled:"):]
        assert " " not in suffix and ":" not in suffix
