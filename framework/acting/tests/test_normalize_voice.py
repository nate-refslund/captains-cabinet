"""Nate-voice character normalize in the cabinet draft-lane composer.

These exercise screenpipe_adapter.normalize_voice — the pure string transform
applied to every draft draft_fn returns, enforcing the teams-message-voice-
formatting rules (em/en dash -> "-", bullet glyphs -> "-", → -> "->"). No
screenpipe libs, no I/O: when draft_lib is on the path normalize_voice delegates
to the shared draft_lib.humanize (single source of truth); otherwise it applies
the identical rules locally. We assert the OUTPUT contract either way, plus
idempotency and that none of the four fancy glyphs survive.
"""
from framework.acting import screenpipe_adapter as sa


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
