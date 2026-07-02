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


def _open_row(subject, ts):
    """A ledger row shaped like read_ledger() returns for an OPEN (undecided,
    no-outcome) proposal."""
    return {"ts": ts, "actor": {"kind": "officer", "id": "cos"},
            "lane": "send-1to1-reply", "action": "draft-reply", "subject": subject,
            "proposal": {"required": True, "decision": None}}


class TestOpenSubjectTs:
    def test_maps_subject_to_proposal_ts(self):
        rows = [_open_row("kristoffer", "2026-06-24T21:00:00+00:00")]
        d = sa.open_subject_ts(rows=rows)
        assert d["kristoffer"] == sa.parse_dt("2026-06-24T21:00:00+00:00")

    def test_keeps_newest_open_ts_per_subject(self):
        rows = [
            _open_row("kristoffer", "2026-06-24T21:00:00+00:00"),
            _open_row("kristoffer", "2026-06-25T07:00:00+00:00"),  # newer
        ]
        d = sa.open_subject_ts(rows=rows)
        assert d["kristoffer"] == sa.parse_dt("2026-06-25T07:00:00+00:00")

    def test_decided_proposal_excluded(self):
        rows = [_decided_row("lisa", "2026-06-24T09:00:00+00:00")]
        assert sa.open_subject_ts(rows=rows) == {}

    def test_superseded_with_outcome_excluded(self):
        rows = [{"ts": "2026-06-24T21:00:00+00:00",
                 "actor": {"kind": "officer", "id": "cos"},
                 "lane": "send-1to1-reply", "action": "draft-reply",
                 "subject": "lisa",
                 "proposal": {"required": True, "decision": None},
                 "outcome": {"status": "ok", "evidence": "shipped"}}]
        assert sa.open_subject_ts(rows=rows) == {}


class TestOpenProposalBlocks:
    """Fix 3: an OPEN proposal suppresses a thread ONLY until a genuinely-new
    inbound arrives — the Kristoffer Round-2 bug, where a Round-1 draft sat open
    overnight and silently swallowed the 11h-newer Round-2 message."""

    def test_open_and_no_new_message_blocks(self):
        # Last inbound (20:00) is OLDER than the open proposal (21:00) -> blocked
        # (the pending draft already covers this message).
        open_ts = {"kristoffer": sa.parse_dt("2026-06-24T21:00:00+00:00")}
        t = _thread(date="2026-06-24T20:00:00+00:00")
        assert sa.open_proposal_blocks(t, open_ts) is True

    def test_open_equal_time_blocks(self):
        open_ts = {"kristoffer": sa.parse_dt("2026-06-24T21:00:00+00:00")}
        t = _thread(date="2026-06-24T21:00:00+00:00")
        assert sa.open_proposal_blocks(t, open_ts) is True

    def test_new_inbound_after_open_proposal_re_presents(self):
        # THE FIX: a fresh message (2026-06-25 08:53) after the open proposal
        # (2026-06-24 21:00) -> NOT blocked -> the lane re-presents Round-2.
        open_ts = {"kristoffer": sa.parse_dt("2026-06-24T21:00:00+00:00")}
        t = _thread(date="2026-06-25T08:53:34+00:00")
        assert sa.open_proposal_blocks(t, open_ts) is False

    def test_no_open_proposal_does_not_block(self):
        # A subject with no open proposal is never blocked by this gate.
        t = _thread(slug="freshperson")
        assert sa.open_proposal_blocks(t, {}) is False

    def test_unparseable_inbound_with_open_proposal_blocks(self):
        # Open proposal exists but the inbound date is garbage -> cannot prove a
        # newer message -> block (don't double-draft a pending thread).
        open_ts = {"kristoffer": sa.parse_dt("2026-06-24T21:00:00+00:00")}
        t = _thread(date="garbage-date")
        assert sa.open_proposal_blocks(t, open_ts) is True


class TestSubjectHasOpenProposal:
    """Live (moment-of-use) dup guard: the duplicate-draft fix. Two concurrent
    runs both snapshot 'no open Maria proposal' before either emits; re-reading
    the ledger right before emit makes the second run SEE the first's proposal."""

    def test_open_proposal_for_subject_is_true(self):
        rows = [_open_row("Maria-Skougaard-Andersen", "2026-06-25T09:56:53+00:00")]
        assert sa.subject_has_open_proposal("Maria-Skougaard-Andersen", rows=rows) is True

    def test_no_open_proposal_for_subject_is_false(self):
        rows = [_open_row("someone-else", "2026-06-25T09:56:53+00:00")]
        assert sa.subject_has_open_proposal("Maria-Skougaard-Andersen", rows=rows) is False

    def test_decided_proposal_does_not_count_as_open(self):
        # A decided proposal must NOT block a fresh draft via this guard (the
        # recency path handles decided threads separately).
        rows = [_decided_row("Maria-Skougaard-Andersen", "2026-06-25T09:00:00+00:00")]
        assert sa.subject_has_open_proposal("Maria-Skougaard-Andersen", rows=rows) is False


class TestOpenProposalBlocksLive:
    """RECENCY-AWARE Layer-2 pre-emit dup guard (open_proposal_blocks_live).
    Regression cover for the Morten-Stagaard 17:05 DPA miss: the blunt
    subject_has_open_proposal predecessor skipped on ANY open proposal, so a
    legitimately-NEW inbound that passed the recency-aware top-of-loop gate was
    then killed here by a STALE older open proposal. The live variant must apply
    the SAME last_dt <= when recency test as open_proposal_blocks."""

    def test_morten_newer_inbound_not_blocked_by_stale_open(self):
        # The exact failure: an open draft for Morten's 14:53 (12:53Z) message
        # sits undecided; his 17:05 (15:05Z) reply is genuinely NEW. The live
        # guard must NOT block it (newer than the open proposal) -> it re-presents.
        rows = [_open_row("Morten-Stagaard", "2026-06-25T13:15:58+00:00")]
        t = _thread(slug="Morten-Stagaard", date="2026-06-25T15:05:13+00:00")
        assert sa.open_proposal_blocks_live(t, rows=rows) is False

    def test_same_message_open_proposal_blocks(self):
        # A proposal that landed DURING our draft for the SAME (or older-than-our)
        # inbound is a true duplicate -> block. Inbound 13:00Z <= open 13:15Z.
        rows = [_open_row("Morten-Stagaard", "2026-06-25T13:15:58+00:00")]
        t = _thread(slug="Morten-Stagaard", date="2026-06-25T13:00:00+00:00")
        assert sa.open_proposal_blocks_live(t, rows=rows) is True

    def test_no_open_proposal_not_blocked(self):
        rows = [_open_row("someone-else", "2026-06-25T13:15:58+00:00")]
        t = _thread(slug="Morten-Stagaard", date="2026-06-25T15:05:13+00:00")
        assert sa.open_proposal_blocks_live(t, rows=rows) is False

    def test_decided_proposal_not_blocked(self):
        # A decided proposal is handled by the decided/already_handled path, not
        # this open-proposal guard -> not blocked here.
        rows = [_decided_row("Morten-Stagaard", "2026-06-25T13:00:00+00:00")]
        t = _thread(slug="Morten-Stagaard", date="2026-06-25T15:05:13+00:00")
        assert sa.open_proposal_blocks_live(t, rows=rows) is False

    def test_unparseable_inbound_with_open_proposal_blocks(self):
        # Open proposal exists but inbound date is garbage -> cannot prove newer
        # -> block (conservative: never double-draft a pending thread).
        rows = [_open_row("Morten-Stagaard", "2026-06-25T13:15:58+00:00")]
        t = _thread(slug="Morten-Stagaard", date="garbage")
        assert sa.open_proposal_blocks_live(t, rows=rows) is True


class _StubDL:
    """Minimal draft_lib stand-in: find_awaiting_threads returns a fixed slug set
    (or raises, to exercise the fail-safe); load_full_conversation returns a fixed
    message list (or raises) for the FIX-2 self-reply detector."""
    def __init__(self, slugs=None, raises=False, convo=None, convo_raises=False):
        self._slugs = slugs or []
        self._raises = raises
        self._convo = convo or []
        self._convo_raises = convo_raises

    def find_awaiting_threads(self, hours=72):
        if self._raises:
            raise RuntimeError("brain unreachable")
        return [{"slug": s} for s in self._slugs]

    def load_full_conversation(self, slug, max_messages=40):
        if self._convo_raises:
            raise RuntimeError("conversation unreadable")
        return list(self._convo)


class TestStillAwaiting:
    """Live freshness re-check at present()-time: a backlog draft must be DROPPED
    if Nate has since replied (his message is now the newest), since the lane is
    slower than he is. Fail-safe: undeterminable -> surface (return None)."""

    def test_still_inbound_returns_true(self, monkeypatch):
        monkeypatch.setattr(sa, "_dl",
                            lambda: _StubDL(slugs=["kristoffer", "lisa"]))
        assert sa.still_awaiting("kristoffer") is True

    def test_nate_replied_slug_gone_returns_false(self, monkeypatch):
        # Slug is NO LONGER awaiting (dropped out because Nate's reply is newest)
        # -> False -> the lane drops the stale draft.
        monkeypatch.setattr(sa, "_dl", lambda: _StubDL(slugs=["lisa"]))
        assert sa.still_awaiting("kristoffer") is False

    def test_brain_error_returns_none_failsafe(self, monkeypatch):
        # A transient brain failure must NOT suppress a real reply -> None ->
        # caller surfaces.
        monkeypatch.setattr(sa, "_dl", lambda: _StubDL(raises=True))
        assert sa.still_awaiting("kristoffer") is None


def _cal_thread(text="", who="Lisa Stentoft <lisa@stepnetwork.dk>", slug="lisa-stentoft"):
    return {"slug": slug, "person": slug.replace("-", " ").title(),
            "last": {"date": "2026-06-24T08:00:00+00:00",
                     "text": text, "who": who, "source": "msgraph"}}


class TestIsCalendarInvite:
    """is_calendar_invite must catch meeting invitations / organizer updates
    (answered by Accept/Decline, never a prose reply) WITHOUT swallowing normal
    human emails that merely mention a meeting."""

    # --- positives: real invite shapes ---

    def test_the_lisa_bug_danish_recurring_invite(self):
        # The exact reported regression: a recurring DA organizer invite that
        # was surfacing as awaiting-reply.
        body = (
            "Ugentlig Planlægning – Agenda\n"
            "Hvornår: mandag den 30. juni 2026 09:00-09:30\n"
            "Hvor: Microsoft Teams Meeting\n"
            "Gentages hver uge\n"
            "________________________________________\n"
            "Join Microsoft Teams Meeting\n"
        )
        assert sa.is_calendar_invite(_cal_thread(text=body)) is True

    def test_english_outlook_invite_skeleton(self):
        body = ("When: Tuesday, June 30, 2026 1:00 PM-1:30 PM\n"
                "Where: Microsoft Teams Meeting\n"
                "Organizer: Oliver Gray\n")
        assert sa.is_calendar_invite(_cal_thread(text=body)) is True

    def test_ics_payload(self):
        body = "BEGIN:VCALENDAR\nMETHOD:REQUEST\nBEGIN:VEVENT\nSUMMARY:Sync\nEND:VEVENT"
        assert sa.is_calendar_invite(_cal_thread(text=body)) is True

    def test_teams_join_block_alone(self):
        body = ("Quick sync tomorrow.\n\n"
                "Join Microsoft Teams Meeting\n"
                "+45 12 34 56 78 Denmark, Copenhagen\n")
        assert sa.is_calendar_invite(_cal_thread(text=body)) is True

    def test_rsvp_response_line(self):
        body = "Kristoffer has accepted on behalf of the team."
        assert sa.is_calendar_invite(_cal_thread(text=body)) is True

    def test_room_resource_sender(self):
        # A room/resource mailbox is a calendar resource, not a person.
        t = _cal_thread(text="booked", who="ODE-SN-mode6@step.dk", slug="ode-sn-mode6")
        assert sa.is_calendar_invite(t) is True

    # --- negatives: must NOT filter genuine human reply-needing mail ---

    def test_plain_human_email_about_a_meeting_is_not_filtered(self):
        # Mentions a meeting in prose but is a real question awaiting a reply.
        body = ("Hi Nate, can we move our meeting to Thursday? "
                "I also need your sign-off on the DPA before then.")
        assert sa.is_calendar_invite(_cal_thread(text=body)) is False

    def test_danish_human_email_mentioning_mode_is_not_filtered(self):
        body = ("Hej Nate, jeg synes vi skal tage et møde om PolAds-lanceringen. "
                "Hvad tænker du om onsdag?")
        assert sa.is_calendar_invite(_cal_thread(text=body)) is False

    def test_when_without_where_is_not_an_invite(self):
        # A single header-ish line is not enough; require the invite skeleton.
        body = "When can you review the PR? It's blocking the release."
        assert sa.is_calendar_invite(_cal_thread(text=body)) is False

    def test_empty_and_malformed_are_safe(self):
        assert sa.is_calendar_invite({}) is False
        assert sa.is_calendar_invite({"last": None}) is False
        assert sa.is_calendar_invite({"last": {"text": None, "who": None}}) is False


class _FakeRun:
    """Stand-in for subprocess.run(redis-cli ...) used by chair_holds_thread.
    Records the GET key it was asked for and returns a CompletedProcess-like
    object with the configured stdout, or raises to exercise the fail-safe."""
    class _CP:
        def __init__(self, stdout):
            self.stdout = stdout

    def __init__(self, stdout="", raises=False):
        self._stdout = stdout
        self._raises = raises
        self.last_key = None

    def __call__(self, argv, **kw):
        if self._raises:
            raise RuntimeError("redis down")
        # argv == ["redis-cli", "-h", host, "GET", key]
        if "GET" in argv:
            self.last_key = argv[argv.index("GET") + 1]
        return self._CP(self._stdout)


class TestChairHoldsThread:
    """FIX 1 — the Chair active-thread lock helper. A present non-empty redis
    value means the Chair holds the thread (lane must skip); a missing key, an
    empty value, or any redis error means NOT held (degrade-safe, no exclusion)."""

    def test_present_key_is_held(self, monkeypatch):
        fake = _FakeRun(stdout="1\n")
        monkeypatch.setattr(sa.subprocess, "run", fake)
        assert sa.chair_holds_thread("Morten-Stagaard") is True
        # key derivation: sanitized slug under the active-thread namespace.
        assert fake.last_key == "cabinet:chair:active-thread:Morten-Stagaard"

    def test_missing_key_is_not_held(self, monkeypatch):
        monkeypatch.setattr(sa.subprocess, "run", _FakeRun(stdout=""))
        assert sa.chair_holds_thread("Morten-Stagaard") is False

    def test_whitespace_only_value_is_not_held(self, monkeypatch):
        # redis-cli prints a trailing newline even for (nil)/empty -> not held.
        monkeypatch.setattr(sa.subprocess, "run", _FakeRun(stdout="\n"))
        assert sa.chair_holds_thread("Morten-Stagaard") is False

    def test_redis_error_is_not_held_failsafe(self, monkeypatch):
        # A redis outage must NEVER suppress the only drafter -> not held.
        monkeypatch.setattr(sa.subprocess, "run", _FakeRun(raises=True))
        assert sa.chair_holds_thread("Morten-Stagaard") is False

    def test_key_is_flattened(self):
        # Spaces/colons in a slug must not fracture the keyspace (mirrors the
        # handled-key hygiene, and the Chair-side helper's sed sanitization).
        k = sa._active_thread_key("Anna Grobelscheg: PolAds")
        assert k.startswith("cabinet:chair:active-thread:")
        suffix = k[len("cabinet:chair:active-thread:"):]
        assert " " not in suffix and ":" not in suffix


class TestFindThreadsActiveLock:
    """FIX 1 wiring — find_threads DROPS a Chair-locked thread BEFORE the gate /
    drafter, keeps unlocked threads, and is degrade-safe (no lock -> no
    exclusion). The skip-list + calendar filters are stubbed empty here so the
    test isolates the lock behavior."""

    def _wire(self, monkeypatch, slugs, locked):
        # Two awaiting threads from the brain; `locked` is the set the Chair holds.
        monkeypatch.setattr(sa, "_dl", lambda: _StubDL(slugs=slugs))
        monkeypatch.setattr(sa, "_load_skip_groups", lambda: [])
        monkeypatch.setattr(sa, "is_calendar_invite", lambda t: False)
        monkeypatch.setattr(sa, "chair_holds_thread", lambda slug: slug in locked)

    def test_locked_thread_is_dropped(self, monkeypatch):
        self._wire(monkeypatch, ["morten-stagaard", "lisa"], {"morten-stagaard"})
        out = {t["slug"] for t in sa.find_threads(hours=72)}
        assert out == {"lisa"}  # the locked thread is gone, the other remains

    def test_no_lock_keeps_all(self, monkeypatch):
        self._wire(monkeypatch, ["morten-stagaard", "lisa"], set())
        out = {t["slug"] for t in sa.find_threads(hours=72)}
        assert out == {"morten-stagaard", "lisa"}  # nothing locked -> normal flow

    def test_degrade_safe_no_redis_no_exclusion(self, monkeypatch):
        # chair_holds_thread already returns False on a redis error (its own
        # fail-safe); wiring the REAL helper with a raising subprocess proves the
        # whole find_threads path degrades to no-exclusion, not an empty result.
        monkeypatch.setattr(sa, "_dl",
                            lambda: _StubDL(slugs=["morten-stagaard", "lisa"]))
        monkeypatch.setattr(sa, "_load_skip_groups", lambda: [])
        monkeypatch.setattr(sa, "is_calendar_invite", lambda t: False)
        monkeypatch.setattr(sa.subprocess, "run", _FakeRun(raises=True))
        out = {t["slug"] for t in sa.find_threads(hours=72)}
        assert out == {"morten-stagaard", "lisa"}  # redis down -> no thread dropped


def _sent(date):
    return {"direction": "sent", "date": date, "who": "Nate", "text": "my reply"}


def _recv(date):
    return {"direction": "received", "date": date, "who": "Morten", "text": "their msg"}


class TestNateRepliedSince:
    """FIX 2 detection — nate_replied_since(slug, when): did Nate send an OUTBOUND
    message strictly newer than the open proposal's ts? This is the precise signal
    that auto-expires a stale-open proposal (Nate replied to the counterparty
    himself, bypassing the approve gate, so the proposal dangles + suppresses
    future inbound). True == newer self-reply; False == datable sends but none
    newer; None == undeterminable (fall back to the time backstop)."""

    def _convo(self, monkeypatch, msgs, raises=False):
        monkeypatch.setattr(sa, "_dl",
                            lambda: _StubDL(convo=msgs, convo_raises=raises))

    def test_newer_self_reply_returns_true(self, monkeypatch):
        # Proposal at 12:00; Nate sent at 13:00 -> True (he replied himself).
        self._convo(monkeypatch, [_recv("2026-06-25T11:00:00+00:00"),
                                  _sent("2026-06-25T13:00:00+00:00")])
        when = sa.parse_dt("2026-06-25T12:00:00+00:00")
        assert sa.nate_replied_since("morten-stagaard", when) is True

    def test_only_older_self_reply_returns_false(self, monkeypatch):
        # His latest send (11:30) PREDATES the proposal (12:00) -> not newer ->
        # False (leave the proposal open; he genuinely hasn't replied since).
        self._convo(monkeypatch, [_sent("2026-06-25T11:30:00+00:00"),
                                  _recv("2026-06-25T11:45:00+00:00")])
        when = sa.parse_dt("2026-06-25T12:00:00+00:00")
        assert sa.nate_replied_since("morten-stagaard", when) is False

    def test_equal_time_is_not_newer(self, monkeypatch):
        # A send exactly AT the proposal time is not STRICTLY newer -> False.
        self._convo(monkeypatch, [_sent("2026-06-25T12:00:00+00:00")])
        when = sa.parse_dt("2026-06-25T12:00:00+00:00")
        assert sa.nate_replied_since("morten-stagaard", when) is False

    def test_no_sent_messages_returns_false(self, monkeypatch):
        # Only inbound in the convo -> we COULD read it, there is simply no
        # self-reply -> False (definitively not, not "can't tell").
        self._convo(monkeypatch, [_recv("2026-06-25T13:00:00+00:00")])
        when = sa.parse_dt("2026-06-25T12:00:00+00:00")
        assert sa.nate_replied_since("morten-stagaard", when) is False

    def test_unparseable_sent_dates_returns_none(self, monkeypatch):
        # A sent message exists but its date is garbage -> can't tell -> None ->
        # caller falls back to the time backstop, never expiring on uncertainty.
        self._convo(monkeypatch, [{"direction": "sent", "date": "garbage",
                                   "who": "Nate", "text": "x"}])
        when = sa.parse_dt("2026-06-25T12:00:00+00:00")
        assert sa.nate_replied_since("morten-stagaard", when) is None

    def test_empty_conversation_returns_none(self, monkeypatch):
        # No messages at all -> no datable self-reply -> None (fall back).
        self._convo(monkeypatch, [])
        when = sa.parse_dt("2026-06-25T12:00:00+00:00")
        assert sa.nate_replied_since("morten-stagaard", when) is None

    def test_unreadable_conversation_returns_none(self, monkeypatch):
        # load_full_conversation raised -> None (best-effort, fall back).
        self._convo(monkeypatch, [], raises=True)
        when = sa.parse_dt("2026-06-25T12:00:00+00:00")
        assert sa.nate_replied_since("morten-stagaard", when) is None

    def test_none_when_returns_none(self, monkeypatch):
        # An unparseable proposal ts (when=None) -> None (can't compare).
        self._convo(monkeypatch, [_sent("2026-06-25T13:00:00+00:00")])
        assert sa.nate_replied_since("morten-stagaard", None) is None
