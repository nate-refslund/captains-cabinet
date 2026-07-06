"""Flavor-A acting surface (flavor_a.acting) — the screenpipe gather->draft cell.

Moved here (with the adapter, SRC-3) from the framework acting tests
(test_skip_stick screenpipe classes + test_normalize_voice): the awaiting-thread
discovery filters (skip-list / calendar-invite / chair-lock), the live
self-reply/freshness detectors, and the captain-voice charset + first-of-day
greeting rules. The screenpipe ``draft_lib`` deps are monkeypatched (via
``sa._dl``) or fall back to the framework-vendored charset, so these touch no
live estate. ``sa`` is ``flavor_a.acting`` (was framework.acting.screenpipe_adapter);
``sa.parse_dt`` is re-exported from ``framework.acting.lane_dedup``."""
import datetime
import sys
from pathlib import Path

# instance/flavor-a on sys.path so ``flavor_a`` imports; repo root for framework.
_PKG_PARENT = Path(__file__).resolve().parents[2]   # instance/flavor-a
_REPO_ROOT = Path(__file__).resolve().parents[4]    # worktree / repo root
for _p in (str(_REPO_ROOT), str(_PKG_PARENT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from flavor_a import acting as sa


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


class TestNormalizeVoice:
    def test_em_and_en_dash(self):
        assert sa.normalize_voice("check — ship") == "check - ship"
        assert sa.normalize_voice("range 1–5") == "range 1 - 5"

    def test_right_arrow(self):
        assert sa.normalize_voice("a → b → c") == "a -> b -> c"
        assert sa.normalize_voice("x ⟶ y ➜ z ➔ w") == "x -> y -> z -> w"

    def test_bullets_line_and_inline(self):
        assert sa.normalize_voice("do:\n• x\n• y") == "do:\n- x\n- y"
        assert sa.normalize_voice("a • b") == "a - b"
        assert sa.normalize_voice("‣ p\n▪ q\n● r") == "- p\n- q\n- r"
        # indentation preserved (nested bullets)
        assert sa.normalize_voice("  • nested") == "  - nested"

    def test_mixed_chain(self):
        src = "plan: build A → tell them • done — verify"
        assert sa.normalize_voice(src) == "plan: build A -> tell them - done - verify"

    def test_ascii_untouched_and_idempotent(self):
        ascii_text = "fine -> yes\n- bullet"
        assert sa.normalize_voice(ascii_text) == ascii_text
        once = sa.normalize_voice("a — b → c\n• d")
        assert sa.normalize_voice(once) == once

    def test_no_fancy_glyph_survives(self):
        out = sa.normalize_voice("— – • ‣ ▪ ● → ⟶ ➜ ➔")
        for ch in "—–•‣▪●→⟶➜➔":
            assert ch not in out

    # --- charset-whitelist model (2026-06-25 refinement) ---
    def test_exotic_and_unanticipated_chars_caught(self):
        # dash variants beyond em/en, plus catch-all normalize/drop.
        assert sa.normalize_voice("a ― b") == "a - b"      # horizontal bar
        assert sa.normalize_voice("a⸺b") == "a - b"        # two-em dash
        assert sa.normalize_voice("5 − 3") == "5 - 3"      # math minus
        assert sa.normalize_voice("wait…") == "wait..."     # ellipsis
        assert sa.normalize_voice("ＡBC") == "ABC"          # fullwidth -> NFKD
        assert sa.normalize_voice("m²") == "m2"             # superscript -> NFKD
        assert sa.normalize_voice("a中b") == "ab"           # CJK dropped
        assert sa.normalize_voice("“x” det’s") == '"x" det\'s'  # curly quotes

    def test_emojis_and_danish_survive(self):
        assert sa.normalize_voice("ship 🚀👍") == "ship 🚀👍"
        assert sa.normalize_voice("DK 🇩🇰") == "DK 🇩🇰"       # flag
        assert sa.normalize_voice("dev 👨‍💻") == "dev 👨‍💻"  # ZWJ sequence
        assert sa.normalize_voice("blåbær på øen") == "blåbær på øen"
        assert sa.normalize_voice("café naïve") == "café naïve"
        assert sa.normalize_voice("5€ + 3$") == "5€ + 3$"

    def test_total_on_bad_input(self):
        assert sa.normalize_voice("") == ""
        assert sa.normalize_voice(None) is None
        assert sa.normalize_voice(123) == 123


class TestHejFirstOfDay:
    """The 'hej <name>' opener rule: strip a leading greeting line ONLY when Nate
    already messaged this person earlier today. messaged_today reads the thread's
    own messages (direction + ISO date); we drive it with controlled stamps and
    avoid the best-effort load_full_conversation by using a slug that resolves to
    no stored conversation (returns [] / errors -> ignored)."""

    def _iso_today(self, hour=8):
        import datetime as dt
        tz = sa._captain_tz()
        now = dt.datetime.now(tz)
        return now.replace(hour=hour, minute=0, second=0,
                           microsecond=0).astimezone(dt.timezone.utc).isoformat()

    def _iso_days_ago(self, days=3):
        import datetime as dt
        tz = sa._captain_tz()
        d = dt.datetime.now(tz) - dt.timedelta(days=days)
        return d.astimezone(dt.timezone.utc).isoformat()

    def _thread(self, msgs):
        # slug deliberately non-existent so load_full_conversation contributes
        # nothing (the test isolates the in-thread signal).
        return {"slug": "__no_such_person_zzz__", "person": "Kristoffer",
                "thread": msgs}

    def test_strips_greeting_when_already_messaged_today(self):
        th = self._thread([
            {"direction": "sent", "date": self._iso_today(8), "text": "morning note"},
            {"direction": "received", "date": self._iso_today(9), "text": "spm?"},
        ])
        out = sa.strip_greeting_if_not_first_of_day("Hej Kristoffer\nStatus: klar", th)
        assert out == "Status: klar"

    def test_keeps_greeting_when_first_of_day(self):
        # only a 3-day-old prior send -> NOT messaged today -> greeting kept
        th = self._thread([
            {"direction": "sent", "date": self._iso_days_ago(3), "text": "old"},
            {"direction": "received", "date": self._iso_today(9), "text": "spm?"},
        ])
        draft = "Hej Kristoffer\nStatus: klar"
        assert sa.strip_greeting_if_not_first_of_day(draft, th) == draft

    def test_keeps_greeting_when_no_history(self):
        th = self._thread([
            {"direction": "received", "date": self._iso_today(9), "text": "spm?"},
        ])
        draft = "Hej Kristoffer, kan du tjekke det?"
        assert sa.strip_greeting_if_not_first_of_day(draft, th) == draft

    def test_no_greeting_line_left_untouched(self):
        th = self._thread([
            {"direction": "sent", "date": self._iso_today(8), "text": "earlier"},
        ])
        draft = "Status: klar\n- a\n- b"
        assert sa.strip_greeting_if_not_first_of_day(draft, th) == draft

    def test_never_strips_into_empty(self):
        th = self._thread([
            {"direction": "sent", "date": self._iso_today(8), "text": "earlier"},
        ])
        # greeting is the whole message -> keep it rather than send nothing
        assert sa.strip_greeting_if_not_first_of_day("Hej Kristoffer", th) == "Hej Kristoffer"

    def test_messaged_today_true_false(self):
        assert sa.messaged_today(self._thread(
            [{"direction": "sent", "date": self._iso_today(7), "text": "x"}])) is True
        assert sa.messaged_today(self._thread(
            [{"direction": "sent", "date": self._iso_days_ago(2), "text": "x"}])) is False
        # a RECEIVED message today is not Nate sending -> False
        assert sa.messaged_today(self._thread(
            [{"direction": "received", "date": self._iso_today(7), "text": "x"}])) is False

    def test_total_on_bad_input(self):
        assert sa.strip_greeting_if_not_first_of_day("", {"thread": []}) == ""
        assert sa.strip_greeting_if_not_first_of_day(None, {"thread": []}) is None
