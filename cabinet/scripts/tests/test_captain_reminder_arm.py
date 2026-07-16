"""Captain-arm — the missing delivery + create path for /tasks reminders.

Teeth, feature-wide:
  * parse-when: every documented form resolves; a bare date / past instant /
    ambiguous phrase / injection string is REFUSED (never guessed, never
    eval'd); local forms are DST-EXACT (summer +02 vs winter +01);
  * owner-slug: the framework.env captain slug (default 'captain');
  * file-card: fingerprint dedup — a re-file (crash-before-mark) is ONE card,
    count bumped, through the REAL needs API; the untrusted title survives
    quotes/semicolons/$()/newlines as DATA in the card body;
  * reconcile: grant → the need is closed 'granted' (mirrors grant-apply.sh),
    later → the task id is printed for the bump, deny/garbage-id never bump,
    all through the REAL needs API;
  * remind-captain.sh: the INSERT binds the untrusted text as a `psql -v`
    VALUE — the SQL program text never carries it (injection control);
    past/ambiguous when + missing text refuse loudly;
  * the tick routes a captain row → card and an officer row → trigger in ONE
    claim batch, and its reconcile phase bumps a snoozed reminder + closes a
    granted one;
  * a title carrying an embedded newline + tab CANNOT forge a synthetic officer
    trigger or truncate a benign one — the routing title is re-read by id, never
    carried on the claim TSV (P2 regression: exactly one trigger/card fires);
  * snooze → refire works through the REAL 041 re-arm trigger semantics
    (fixture-simulated) with a negative control that FAILS without the trigger;
  * migration 042 widens the type CHECK to admit 'reminder', idempotently, and
    is registered in BOTH schema apply lists;
  * against a REAL ephemeral Postgres (skipped when no server toolchain is
    present, like the redis-gated e2e), the tick's OWN extracted claim + bump
    SQL enforce their predicates: an already-fired row is NOT re-claimed, a
    not-yet-fired / future row is NOT bumped, the real 041 trigger clears
    reminder_fired_at on a bump, and the shipped RETURNING (title-less) emits no
    forged routing line — each with a negative control that mutates the SQL and
    FAILS. This is the teeth the substring fake-psql harness cannot give (a .sh
    SQL edit changes what these run); it also proves the :'var' binds reach the
    server via STDIN (psql never interpolates a -c string).
"""
from __future__ import annotations

import datetime as dt
import importlib.util as _ilu
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO / "cabinet" / "scripts"

if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _load(name: str, fname: str):
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    spec = _ilu.spec_from_file_location(name, _SCRIPTS / fname)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


arm = _load("captain_reminder_arm", "captain-reminder-arm.py")

NOW = dt.datetime(2026, 7, 16, 8, 0, 0, tzinfo=dt.timezone.utc)
CPH = ZoneInfo("Europe/Copenhagen")   # CET/CEST — a DST zone


def _iso(d: dt.datetime) -> str:
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ===========================================================================
# parse-when — deterministic, DST-exact, refuses ambiguity/past/injection
# ===========================================================================

class TestParseWhen:

    def test_iso_local_summer_is_cest(self):
        # 09:00 local on a July day → 07:00Z (CEST, +02:00)
        r = arm.parse_when("2026-07-20T09:00", now=NOW, tz=CPH)
        assert _iso(r) == "2026-07-20T07:00:00Z"

    def test_iso_local_winter_is_cet(self):
        # 09:00 local on a January day → 08:00Z (CET, +01:00) — DST-EXACT
        r = arm.parse_when("2026-01-20T09:00",
                           now=dt.datetime(2026, 1, 10, tzinfo=dt.timezone.utc),
                           tz=CPH)
        assert _iso(r) == "2026-01-20T08:00:00Z"

    def test_dst_boundary_shifts_utc_offset(self):
        """The SAME wall clock resolves to a DIFFERENT UTC instant across the
        DST boundary — proof zoneinfo (not a fixed offset) is doing the math."""
        summer = arm.parse_when("2026-07-01T12:00", now=NOW, tz=CPH)
        winter = arm.parse_when("2026-01-01T12:00",
                                now=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
                                tz=CPH)
        assert _iso(summer) == "2026-07-01T10:00:00Z"   # +02
        assert _iso(winter) == "2026-01-01T11:00:00Z"   # +01

    def test_tz_aware_iso_used_as_is(self):
        assert _iso(arm.parse_when("2026-07-20T09:00:00Z", now=NOW, tz=CPH)) \
            == "2026-07-20T09:00:00Z"
        assert _iso(arm.parse_when("2026-07-20T09:00:00+02:00", now=NOW, tz=CPH)) \
            == "2026-07-20T07:00:00Z"

    def test_tomorrow_and_today(self):
        assert _iso(arm.parse_when("tomorrow 09:00", now=NOW, tz=CPH)) \
            == "2026-07-17T07:00:00Z"
        assert _iso(arm.parse_when("today 23:30", now=NOW, tz=CPH)) \
            == "2026-07-16T21:30:00Z"

    def test_weekday_picks_next_occurrence(self):
        # NOW is Thu 2026-07-16; 'monday' → the following Mon 2026-07-20
        assert _iso(arm.parse_when("monday 09:00", now=NOW, tz=CPH)) \
            == "2026-07-20T07:00:00Z"

    def test_weekday_today_but_past_time_rolls_a_week(self):
        # NOW is Thursday 08:00Z (10:00 local). 'thursday 09:00' local (07:00Z)
        # already passed today → NEXT Thursday.
        r = arm.parse_when("thursday 09:00", now=NOW, tz=CPH)
        assert _iso(r) == "2026-07-23T07:00:00Z"

    def test_offsets(self):
        assert _iso(arm.parse_when("+3d", now=NOW, tz=CPH)) == "2026-07-19T08:00:00Z"
        assert _iso(arm.parse_when("+6h", now=NOW, tz=CPH)) == "2026-07-16T14:00:00Z"
        assert _iso(arm.parse_when("+90m", now=NOW, tz=CPH)) == "2026-07-16T09:30:00Z"

    @pytest.mark.parametrize("bad", [
        "", "someday", "next tuesday", "2026-07-20",          # bare date
        "2026-13-40T09:00", "tomorrow 25:00", "+0d", "+-3d",
        "$(rm -rf /)", "2026-07-20T09:00; rm -rf /", "'; DROP TABLE x --",
        "tomorrow", "09:00",
    ])
    def test_ambiguous_or_malformed_refused(self, bad):
        with pytest.raises(arm.WhenError):
            arm.parse_when(bad, now=NOW, tz=CPH)

    def test_cli_refuses_past_time_rc2(self):
        r = subprocess.run(
            [sys.executable, str(_SCRIPTS / "captain-reminder-arm.py"),
             "parse-when", "2020-01-01T09:00", "--now", "2026-07-16T08:00:00Z",
             "--tz", "Europe/Copenhagen"],
            capture_output=True, text=True)
        assert r.returncode == 2
        assert "past" in r.stderr.lower()
        assert r.stdout.strip() == ""    # never prints a time it refused

    def test_cli_refuses_ambiguous_rc2(self):
        r = subprocess.run(
            [sys.executable, str(_SCRIPTS / "captain-reminder-arm.py"),
             "parse-when", "someday soon", "--now", "2026-07-16T08:00:00Z"],
            capture_output=True, text=True)
        assert r.returncode == 2
        assert "refused" in r.stderr.lower()

    def test_cli_happy_prints_utc(self):
        r = subprocess.run(
            [sys.executable, str(_SCRIPTS / "captain-reminder-arm.py"),
             "parse-when", "+2d", "--now", "2026-07-16T08:00:00Z"],
            capture_output=True, text=True)
        assert r.returncode == 0
        assert r.stdout.strip() == "2026-07-18T08:00:00Z"


# ===========================================================================
# needs-API integration harness (REAL framework.authority.needs, tmp ledger)
# ===========================================================================

@pytest.fixture
def wired(tmp_path, monkeypatch):
    """A tmp cabinet root with the needs plane WIRED, isolated from the repo."""
    (tmp_path / "shared" / "interfaces").mkdir(parents=True)
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    monkeypatch.delenv("CABINET_CAPTAIN_SLUG", raising=False)
    import framework.env as fe
    fe._captain_slug_cache = None
    return tmp_path


def _ledger_rows(root: Path):
    from framework.authority import needs
    return needs._merged(needs.ledger_path(str(root)))


# ===========================================================================
# owner-slug
# ===========================================================================

class TestOwnerSlug:

    def test_default_is_captain(self, wired):
        r = subprocess.run(
            [sys.executable, str(_SCRIPTS / "captain-reminder-arm.py"),
             "owner-slug"], capture_output=True, text=True,
            env={**os.environ})
        assert r.returncode == 0
        assert r.stdout.strip() == "captain"


# ===========================================================================
# file-card — fingerprint dedup + injection stays data (REAL needs API)
# ===========================================================================

class TestFileCard:

    def test_dedup_one_card_per_task_after_crash_reclaim(self, wired):
        # Simulate: claimed → carded → (crash before some mark) → re-claimed →
        # carded again. The content-fingerprint id makes it ONE card, count 2.
        n1 = arm.file_card(42, "2026-07-20T07:00:00Z", "Call the dentist", tz=CPH)
        n2 = arm.file_card(42, "2026-07-20T07:00:00Z", "Call the dentist", tz=CPH)
        assert n1 and n1 == n2
        rows = _ledger_rows(wired)
        mine = [r for r in rows.values()
                if r.get("action_type") == "captain-reminder:42"]
        assert len(mine) == 1                      # ONE need, not two
        assert mine[0]["count"] == 2               # re-file bumped the count

    def test_distinct_tasks_distinct_cards(self, wired):
        a = arm.file_card(1, "2026-07-20T07:00:00Z", "a", tz=CPH)
        b = arm.file_card(2, "2026-07-20T07:00:00Z", "b", tz=CPH)
        assert a and b and a != b

    def test_injection_title_stays_data_in_card_body(self, wired):
        evil = "Call dentist'; DROP TABLE officer_tasks; -- $(whoami)\nline2 `id`"
        nid = arm.file_card(7, "2026-07-20T07:00:00Z", evil, tz=CPH)
        row = _ledger_rows(wired)[nid]
        why = row["why"]
        # every metacharacter survived VERBATIM as data (JSON-stored, not run)
        assert "DROP TABLE officer_tasks" in why
        assert "$(whoami)" in why
        assert "`id`" in why
        assert "line2" in why
        # and the verb legend is present + FIRST (survives the 160-char clip)
        assert why.startswith("grant = done / later = remind me in")
        assert "deny = drop" in why

    def test_card_kind_and_action_type(self, wired):
        nid = arm.file_card(55, "2026-07-20T07:00:00Z", "x", tz=CPH)
        row = _ledger_rows(wired)[nid]
        assert row["kind"] == "decision"
        assert row["action_type"] == "captain-reminder:55"
        assert row["filed_by"] == "system:captain-reminder"

    def test_dark_needs_plane_no_card_no_raise(self, tmp_path, monkeypatch):
        (tmp_path / "shared" / "interfaces").mkdir(parents=True)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)  # DARK
        nid = arm.file_card(9, "2026-07-20T07:00:00Z", "x", tz=CPH)
        assert nid is None                          # no-op, never raised
        assert not (tmp_path / "shared" / "interfaces" / "needs-ledger.jsonl").exists()


# ===========================================================================
# reconcile — grant closes, later prints task id, garbage never bumps
# ===========================================================================

class TestReconcile:

    def _seed(self, root, task_id, title="x"):
        return arm.file_card(task_id, "2026-07-20T07:00:00Z", title, tz=CPH)

    def _mark(self, nid, status):
        from framework.authority import needs
        needs.mark(nid, status, by="captain:binder")

    def test_grant_closes_snooze_prints(self, wired):
        n_done = self._seed(wired, 42)
        n_snz = self._seed(wired, 99)
        self._mark(n_done, "approved_pending_apply")   # grant = done/ack
        self._mark(n_snz, "snoozed")                    # later = +7d
        buf = io.StringIO()
        summary = arm.reconcile(out=buf)
        assert summary["closed"] == 1 and summary["snoozed"] == 1
        assert buf.getvalue().split() == ["99"]         # only the snoozed task id
        rows = _ledger_rows(wired)
        assert rows[n_done]["status"] == "granted"      # closed (mirror grant-apply)
        assert rows[n_snz]["status"] == "snoozed"       # left for the tick to bump

    def test_reconcile_is_idempotent(self, wired):
        n_done = self._seed(wired, 42)
        self._mark(n_done, "approved_pending_apply")
        arm.reconcile(out=io.StringIO())
        s2 = arm.reconcile(out=io.StringIO())            # already granted
        assert s2["closed"] == 0

    def test_garbage_task_id_never_bumps(self, wired):
        # A snoozed captain-reminder whose id segment is not an int (untrusted /
        # hand-edited ledger) must be SKIPPED, never printed for a ::bigint bump.
        merged = {
            "NEED-aaaa1111": {"id": "NEED-aaaa1111",
                              "action_type": "captain-reminder:5; rm -rf /",
                              "status": "snoozed"},
            "NEED-bbbb2222": {"id": "NEED-bbbb2222",
                              "action_type": "captain-reminder:not-an-int",
                              "status": "snoozed"},
        }
        buf = io.StringIO()
        marks = []
        s = arm.reconcile(merged_needs=merged, mark_fn=lambda *a, **k: marks.append(a),
                          out=buf)
        assert buf.getvalue().strip() == ""
        assert s["snoozed"] == 0 and s["skipped"] == 2

    def test_non_reminder_needs_ignored(self, wired):
        merged = {
            "NEED-cccc3333": {"id": "NEED-cccc3333",
                              "action_type": "memory-supersede:sup-x",
                              "status": "approved_pending_apply"},
        }
        marks = []
        s = arm.reconcile(merged_needs=merged, mark_fn=lambda *a, **k: marks.append(a),
                          out=io.StringIO())
        assert s == {"closed": 0, "snoozed": 0, "skipped": 0}
        assert marks == []                              # never touches foreign cards


# ===========================================================================
# migration 042 — widen type CHECK, idempotent, registered
# ===========================================================================

class TestMigration042:
    SQL = _REPO / "cabinet" / "sql" / "042-tasks-reminder-kind.sql"

    def test_widens_type_check_to_reminder(self):
        txt = self.SQL.read_text()
        assert "type IN ('task','epic','reminder')" in txt
        assert "officer_tasks_type_check" in txt

    def test_idempotent_and_non_destructive(self):
        txt = self.SQL.read_text().upper()
        assert "DO $$" in txt                           # guarded re-run
        assert "DROP TABLE" not in txt
        assert "DELETE FROM" not in txt
        assert "TRUNCATE" not in txt

    def test_registered_in_both_apply_lists(self):
        lp = (_SCRIPTS / "load-preset.sh").read_text()
        bs = (_SCRIPTS / "cabinet-bootstrap.sh").read_text()
        assert "042-tasks-reminder-kind.sql" in lp
        assert "cabinet/sql/042-tasks-reminder-kind.sql" in bs
        # ordering: after 039 (its type column + CHECK are the dependency)
        assert lp.index("039-linear-to-tasks-schema.sql") < \
            lp.index("042-tasks-reminder-kind.sql")


# ===========================================================================
# fake-psql harness for the bash create + tick paths
# ===========================================================================

_FAKE_PSQL = r"""#!/bin/bash
# The CLAIM uses -c (no :'var'); the title re-read, the snooze bump and the
# remind-captain INSERT all bind :'var' and therefore arrive on STDIN (psql
# interpolates variables only via STDIN/-f, never -c — matching my-tasks.sh's
# heredoc discipline). Dispatch on the -c value when present, else on the STDIN
# SQL body. Log argv (+ STDIN body when read) so tests can assert -v bindings.
cval=""; has_c=""; tid=""; prev=""
for a in "$@"; do
  [ "$prev" = "-c" ] && { cval="$a"; has_c=1; }
  [ "$prev" = "-v" ] && case "$a" in id=*) tid="${a#id=}" ;; esac
  prev="$a"
done
if [ -n "$has_c" ]; then
  { echo "=PSQL="; for a in "$@"; do echo "ARG=$a"; done; echo "=END="; } >> "$FAKE_PSQL_LOG"
  case "$cval" in
    *"WITH due_tasks"*)
      # Claim RETURNING is 4 MACHINE fields (id, officer_slug, due_at, type) —
      # the untrusted title is NOT in the stream; both routes re-read it by id.
      printf '100\tcaptain\t2026-07-16T07:00:00Z\treminder\n200\tcto\t2026-07-16T07:00:00Z\ttask\nUPDATE 2\n' ;;
  esac
  exit 0
fi
# No -c → the SQL body is on STDIN (a :'var'-bound heredoc). Log argv + body.
body="$(cat)"
{ echo "=PSQL="; for a in "$@"; do echo "ARG=$a"; done; echo "=STDIN="; printf '%s\n' "$body"; echo "=END="; } >> "$FAKE_PSQL_LOG"
case "$body" in
  *"SELECT title FROM officer_tasks"*) printf 'title-for-%s\n' "$tid" ;;
  *"make_interval"*)                    printf '%s\n' "${tid:-1}" ;;
  *"INSERT INTO officer_tasks"*)        printf '123|2026-07-19 08:00:00+00\n' ;;
esac
exit 0
"""

_FAKE_REDIS = "#!/bin/bash\nexit 0\n"

# A redis-cli that LOGS every XADD (stream + fields) to $FAKE_REDIS_LOG and
# exits 0 for everything else (XGROUP CREATE, SET, tmux dedup, …). One officer
# trigger delivery = exactly one XADD (trigger_send issues a single XADD per
# send), so counting XADD lines counts delivered officer triggers — the probe
# that exposes a FORGED officer trigger.
_FAKE_REDIS_LOG = r"""#!/bin/bash
args=("$@"); i=0
while [ $i -lt ${#args[@]} ]; do
  if [ "${args[$i]}" = "XADD" ]; then
    echo "XADD ${args[$((i+1))]} :: ${args[@]:$((i+2))}" >> "$FAKE_REDIS_LOG"
  fi
  i=$((i + 1))
done
exit 0
"""

# A psql whose CLAIM returns one captain + one officer row (4 machine fields,
# NO title), and whose by-id title RE-READ returns an ATTACK title carrying an
# embedded newline + tab-delimited forged officer row. On the pre-fix
# title-in-stream design this newline spawned a second physical line that
# survived the tab filter and was parsed as a forged 'GHOST-OFFICER' routing
# row; with the title dropped from the claim stream it can only ever land as
# card/JSON DATA, never a routing field.
_FAKE_PSQL_TITLE_ATTACK = r"""#!/bin/bash
cval=""; has_c=""; prev=""
for a in "$@"; do [ "$prev" = "-c" ] && { cval="$a"; has_c=1; }; prev="$a"; done
if [ -n "$has_c" ]; then
  { echo "=PSQL="; for a in "$@"; do echo "ARG=$a"; done; echo "=END="; } >> "$FAKE_PSQL_LOG"
  case "$cval" in
    *"WITH due_tasks"*)
      printf '100\tcaptain\t2026-07-16T07:00:00Z\treminder\n500\tvictim-officer\t2026-07-16T07:00:00Z\ttask\nUPDATE 2\n' ;;
  esac
  exit 0
fi
# STDIN heredoc — the by-id title re-read returns the ATTACK title.
body="$(cat)"
{ echo "=PSQL="; for a in "$@"; do echo "ARG=$a"; done; echo "=STDIN="; printf '%s\n' "$body"; echo "=END="; } >> "$FAKE_PSQL_LOG"
case "$body" in
  *"SELECT title FROM officer_tasks"*)
    printf 'benign start\n999\tGHOST-OFFICER\t2026-07-16T07:00:00Z\ttask\tFORGED-TRIGGER\n' ;;
  *"make_interval"*) printf '' ;;
esac
exit 0
"""


def _mkbin(tmp_path: Path, *, psql_body: str = _FAKE_PSQL,
           redis_body: str = _FAKE_REDIS) -> Path:
    bind = tmp_path / "bin"
    bind.mkdir(exist_ok=True)
    for name, body in (("psql", psql_body), ("redis-cli", redis_body)):
        p = bind / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bind


def _base_env(tmp_path, bind, *, log):
    root = tmp_path / "root"
    (root / "instance" / "config" / "contexts").mkdir(parents=True, exist_ok=True)
    (root / "instance" / "config" / "contexts" / "work.yml").write_text("slug: work\n")
    (root / "shared" / "interfaces").mkdir(parents=True, exist_ok=True)
    return {
        **os.environ,
        "PATH": f"{bind}:{os.environ['PATH']}",
        "CONN": "postgresql://fake",
        "CABINET_ROOT": str(root),
        "CABINET_NEEDS_WIRED": "1",
        "CABINET_CONTEXT": "work",
        "PYTHON": sys.executable,
        "FAKE_PSQL_LOG": str(log),
    }


# ===========================================================================
# remind-captain.sh — parameterized INSERT (injection control) + refusals
# ===========================================================================

class TestRemindCaptainCreate:

    def _run(self, tmp_path, args, env):
        return subprocess.run(
            ["bash", str(_SCRIPTS / "remind-captain.sh"), *args],
            capture_output=True, text=True, env=env)

    def test_happy_path_inserts_and_prints_id(self, tmp_path):
        bind = _mkbin(tmp_path)
        log = tmp_path / "psql.log"
        env = _base_env(tmp_path, bind, log=log)
        r = self._run(tmp_path, ["+3d", "call", "the", "dentist"], env)
        assert r.returncode == 0, r.stderr
        assert "REMINDER id=123" in r.stdout
        assert "owner=captain" in r.stdout

    def test_injection_text_bound_as_value_not_sql_text(self, tmp_path):
        bind = _mkbin(tmp_path)
        log = tmp_path / "psql.log"
        env = _base_env(tmp_path, bind, log=log)
        evil = "dentist'; DROP TABLE officer_tasks; -- $(rm -rf /)"
        r = self._run(tmp_path, ["+3d", evil], env)
        assert r.returncode == 0, r.stderr
        logged = log.read_text()
        argv = logged[:logged.index("=STDIN=")]
        body = logged[logged.index("=STDIN="):]
        # the untrusted text is a -v BOUND value...
        assert f"title={evil}" in argv
        # ...and the SQL program text carries only the :'title' placeholder
        assert ":'title'" in body
        assert "DROP TABLE officer_tasks" not in body
        assert "$(rm -rf /)" not in body

    def test_two_token_when_form(self, tmp_path):
        bind = _mkbin(tmp_path)
        log = tmp_path / "psql.log"
        env = _base_env(tmp_path, bind, log=log)
        r = self._run(tmp_path, ["tomorrow", "09:00", "standup"], env)
        assert r.returncode == 0, r.stderr
        assert "REMINDER id=123" in r.stdout

    def test_past_when_refused_no_insert(self, tmp_path):
        bind = _mkbin(tmp_path)
        log = tmp_path / "psql.log"
        env = _base_env(tmp_path, bind, log=log)
        r = self._run(tmp_path, ["2020-01-01T09:00", "old"], env)
        assert r.returncode == 2
        assert not log.exists() or "INSERT INTO officer_tasks" not in log.read_text()

    def test_missing_text_refused(self, tmp_path):
        bind = _mkbin(tmp_path)
        env = _base_env(tmp_path, bind, log=tmp_path / "psql.log")
        r = self._run(tmp_path, ["+3d"], env)
        assert r.returncode == 2


# ===========================================================================
# due-at-reminder-tick.sh — routing (one batch) + reconcile wiring
# ===========================================================================

class TestTickRoutingAndReconcile:

    def _seed_verdicts(self, root):
        """Seed the tmp needs-ledger with a snoozed (300) + granted-pending
        (400) captain reminder, through the REAL needs API."""
        env = {**os.environ, "CABINET_ROOT": str(root), "CABINET_NEEDS_WIRED": "1"}
        code = (
            "import sys; sys.path.insert(0, %r)\n" % str(_REPO) +
            "import importlib.util as u\n"
            "s=u.spec_from_file_location('a', %r)\n" % str(_SCRIPTS / "captain-reminder-arm.py") +
            "a=u.module_from_spec(s); s.loader.exec_module(a)\n"
            "from framework.authority import needs\n"
            "a.file_card(300,'2026-07-16T07:00:00Z','snoozed one')\n"
            "a.file_card(400,'2026-07-16T07:00:00Z','done one')\n"
            "m=needs._merged(needs.ledger_path())\n"
            "bt={r['action_type']:n for n,r in m.items()}\n"
            "needs.mark(bt['captain-reminder:300'],'snoozed',by='captain:binder')\n"
            "needs.mark(bt['captain-reminder:400'],'approved_pending_apply',by='captain:binder')\n"
        )
        subprocess.run([sys.executable, "-c", code], check=True, env=env,
                       capture_output=True, text=True)

    def test_routes_and_reconciles_in_one_tick(self, tmp_path):
        bind = _mkbin(tmp_path)
        log = tmp_path / "psql.log"
        env = _base_env(tmp_path, bind, log=log)
        root = Path(env["CABINET_ROOT"])
        self._seed_verdicts(root)

        r = subprocess.run(["bash", str(_SCRIPTS / "due-at-reminder-tick.sh")],
                           capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        # routing: officer row 200 → trigger (fired=1); captain row 100 → card
        assert "fired=1" in r.stdout
        assert "carded=1" in r.stdout
        assert "snooze_bumped=1" in r.stdout

        rows = _ledger_rows(root)
        by_at = {v.get("action_type"): v for v in rows.values()}
        # captain row 100 got a fresh card
        assert "captain-reminder:100" in by_at
        # done (400) closed granted; snoozed (300) still snoozed
        assert by_at["captain-reminder:400"]["status"] == "granted"
        assert by_at["captain-reminder:300"]["status"] == "snoozed"
        # the tick issued the guarded make_interval bump for task 300
        logged = log.read_text()
        assert "make_interval" in logged
        assert "id=300" in logged
        # ...and re-read the exact title for the captain card by id
        assert "id=100" in logged

    def test_officer_row_never_carded(self, tmp_path):
        bind = _mkbin(tmp_path)
        log = tmp_path / "psql.log"
        env = _base_env(tmp_path, bind, log=log)
        root = Path(env["CABINET_ROOT"])
        subprocess.run(["bash", str(_SCRIPTS / "due-at-reminder-tick.sh")],
                       capture_output=True, text=True, env=env)
        rows = _ledger_rows(root)
        ats = {v.get("action_type") for v in rows.values()}
        assert "captain-reminder:200" not in ats     # the officer row is NOT carded

    def test_newline_tab_title_cannot_forge_or_truncate(self, tmp_path):
        """P2 regression — a title carrying an embedded newline + a tab-delimited
        fake row (the exact shape that forged a synthetic officer trigger when
        the title rode the claim TSV) can no longer forge a routing row OR
        truncate a benign one: the title is re-read by id and only ever lands as
        card / JSON DATA. Exactly ONE officer trigger + ONE captain card fire."""
        redis_log = tmp_path / "redis.log"
        bind = _mkbin(tmp_path, psql_body=_FAKE_PSQL_TITLE_ATTACK,
                      redis_body=_FAKE_REDIS_LOG)
        log = tmp_path / "psql.log"
        env = _base_env(tmp_path, bind, log=log)
        env["FAKE_REDIS_LOG"] = str(redis_log)
        root = Path(env["CABINET_ROOT"])

        r = subprocess.run(["bash", str(_SCRIPTS / "due-at-reminder-tick.sh")],
                           capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        # EXACTLY one officer trigger + one captain card — no forgery, no dup.
        assert "fired=1" in r.stdout
        assert "carded=1" in r.stdout

        xadds = ([l for l in redis_log.read_text().splitlines() if "XADD" in l]
                 if redis_log.exists() else [])
        assert len(xadds) == 1, f"expected exactly 1 officer trigger, got {xadds!r}"
        # the single trigger targets the GENUINE officer row (victim-officer)…
        assert "cabinet:triggers:victim-officer" in xadds[0]
        # …and NO trigger was forged to the attacker's ghost stream.
        assert not any("cabinet:triggers:GHOST-OFFICER" in x for x in xadds)
        assert not any("cabinet:triggers:999" in x for x in xadds)
        # the attack text rides INSIDE the genuine payload as DATA: the newline is
        # JSON-escaped (\n), so it is a value, never a physical row break.
        assert "GHOST-OFFICER" in xadds[0] and "FORGED-TRIGGER" in xadds[0]
        assert r"\n999" in xadds[0]                 # escaped newline, not a new row
        # the captain row (100) still got its ONE card — a benign multi-line
        # title was not truncated away, and the officer row is NEVER carded.
        by_at = {v.get("action_type") for v in _ledger_rows(root).values()}
        assert "captain-reminder:100" in by_at
        assert "captain-reminder:500" not in by_at


# ===========================================================================
# snooze → refire through the REAL 041 re-arm trigger (fixture-simulated)
# ===========================================================================

class TestSnoozeRefireSimulation:
    """A fast, always-on MODEL of the 041 re-arm trigger + the tick's claim
    predicate + the guarded bump (no DB needed). The negative control proves the
    trigger clearing reminder_fired_at is load-bearing. Its authoritative
    real-SQL counterpart is TestLiveClaimBumpForgery below, which runs the
    tick's OWN extracted SQL against a live Postgres so a .sh SQL regression is
    actually caught (this model, being hand-mirrored, cannot catch one)."""

    @staticmethod
    def _rearm_on_due_change(row, new_due, *, trigger_on):
        # 041 officer_tasks_due_at_rearm: due_at change ⇒ reminder_fired_at NULL
        if trigger_on and new_due != row["due_at"]:
            row["reminder_fired_at"] = None
        row["due_at"] = new_due

    @staticmethod
    def _claimable(row, now):
        return (row["due_at"] is not None and row["due_at"] <= now
                and row["status"] in ("queue", "wip")
                and row["reminder_fired_at"] is None)

    @staticmethod
    def _bump_guard(row, now):
        return (row["status"] in ("queue", "wip") and row["due_at"] <= now
                and row["reminder_fired_at"] is not None)

    def test_snooze_bump_refires_and_is_idempotent(self):
        t0 = dt.datetime(2026, 7, 16, 7, 0, tzinfo=dt.timezone.utc)
        row = {"due_at": t0, "reminder_fired_at": t0, "status": "queue"}
        # already fired at t0 → NOT re-claimable this tick
        assert not self._claimable(row, t0)
        # Captain snoozed → the tick's guarded bump fires (overdue + fired)
        assert self._bump_guard(row, t0)
        new_due = t0 + dt.timedelta(days=7)
        self._rearm_on_due_change(row, new_due, trigger_on=True)
        # idempotent: a second reconcile-print no longer passes the guard
        assert not self._bump_guard(row, t0)
        # and at +7d the row REFIRES (the re-arm cleared reminder_fired_at)
        assert self._claimable(row, new_due)

    def test_negative_control_no_trigger_no_refire(self):
        t0 = dt.datetime(2026, 7, 16, 7, 0, tzinfo=dt.timezone.utc)
        row = {"due_at": t0, "reminder_fired_at": t0, "status": "queue"}
        new_due = t0 + dt.timedelta(days=7)
        # WITHOUT the re-arm trigger, reminder_fired_at stays set → NO refire
        self._rearm_on_due_change(row, new_due, trigger_on=False)
        assert not self._claimable(row, new_due)

    def test_041_trigger_clears_reminder_fired_at_on_due_change(self):
        sql = (_REPO / "cabinet" / "sql" / "041-tasks-due-at.sql").read_text()
        assert "officer_tasks_due_at_rearm" in sql
        assert "NEW.due_at IS DISTINCT FROM OLD.due_at" in sql
        assert "reminder_fired_at := NULL" in sql


# ===========================================================================
# LIVE Postgres — the tick's OWN extracted SQL against a real ephemeral cluster
# (claim predicate + snooze bump guard + real 041 re-arm + P2 no-forgery
# RETURNING), each with a mutate-the-SQL negative control. This is the teeth the
# substring fake-psql harness cannot give: editing the .sh SQL changes what
# these execute. Gated on a local Postgres server toolchain, skipped otherwise —
# the same posture as the redis-gated e2e suites.
# ===========================================================================

def _pg_toolchain():
    """Return a dir holding a full Postgres server toolchain (postgres, initdb,
    pg_ctl, psql), or None. Mirrors the redis-gated e2e tests' shutil.which gate,
    but also probes the common Homebrew / Linux keg locations because
    postgresql@N is frequently not on PATH."""
    import glob
    cands = []
    server = shutil.which("postgres")
    if server:
        cands.append(str(Path(server).parent))
    for pat in ("/opt/homebrew/opt/postgresql@*/bin",
                "/usr/local/opt/postgresql@*/bin",
                "/opt/homebrew/bin", "/usr/local/bin",
                "/usr/lib/postgresql/*/bin", "/usr/pgsql-*/bin"):
        cands.extend(sorted(glob.glob(pat), reverse=True))
    seen = set()
    for d in cands:
        if d in seen:
            continue
        seen.add(d)
        p = Path(d)
        if all((p / t).exists() for t in ("postgres", "initdb", "pg_ctl", "psql")):
            return p
    return None


_PG_BIN = _pg_toolchain()
_PG_SKIP = pytest.mark.skipif(
    _PG_BIN is None,
    reason="no local Postgres server toolchain (postgres/initdb/pg_ctl/psql)")


def _tick_sql(needle: str) -> str:
    """Extract the ONE shipped SQL statement from due-at-reminder-tick.sh that
    contains ``needle`` — from either a ``-c "…"`` argument or a ``<<'SQL' … SQL``
    heredoc. The live tests run the SCRIPT'S OWN SQL text, so a .sh SQL edit
    changes what is exercised (unlike a hand-mirrored re-implementation)."""
    sh = (_SCRIPTS / "due-at-reminder-tick.sh").read_text()
    blocks = re.findall(r'-c "([^"]*)"', sh)
    blocks += re.findall(r"<<'SQL'[^\n]*\n(.*?)\nSQL$", sh, re.DOTALL | re.MULTILINE)
    hits = [b.strip() for b in blocks if needle in b]
    assert len(hits) == 1, f"{needle!r}: expected exactly 1 shipped SQL block, got {len(hits)}"
    return hits[0]


class _Pg:
    """Thin psql runner: feeds SQL on STDIN (so :'var' binds interpolate, exactly
    as the tick does) and returns stdout."""

    def __init__(self, psql_bin: str, conn: str):
        self._psql, self.conn = psql_bin, conn

    def run(self, sql: str, *, vars=None, field_sep=None, check=True) -> str:
        args = [self._psql, self.conn, "-tA", "--no-psqlrc", "-v", "ON_ERROR_STOP=1"]
        if field_sep is not None:
            args += ["-F", field_sep]
        for k, v in (vars or {}).items():
            args += ["-v", f"{k}={v}"]
        r = subprocess.run(args, input=sql, capture_output=True, text=True)
        if check:
            assert r.returncode == 0, f"psql rc={r.returncode}: {r.stderr}\n--SQL--\n{sql}"
        return r.stdout


@pytest.fixture(scope="class")
def pg(tmp_path_factory):
    assert _PG_BIN is not None
    pgdata = tmp_path_factory.mktemp("pgdata")
    # The unix-socket path has a hard 103-char limit — keep its dir SHORT (/tmp).
    sockdir = Path(tempfile.mkdtemp(prefix="crpg", dir="/tmp"))

    def _b(name):
        return str(_PG_BIN / name)

    started = False
    logfile = pgdata / "server.log"
    try:
        subprocess.run([_b("initdb"), "-D", str(pgdata), "-U", "postgres",
                        "--auth=trust", "-E", "UTF8", "-N"],
                       check=True, capture_output=True, text=True)
        # `-l logfile` sends the postmaster's stdout/stderr to a file, and
        # DEVNULL on this call means the daemon never inherits a captured pipe —
        # capturing pg_ctl's output would hang forever (the daemon holds the pipe
        # open, so subprocess.run never sees EOF even after pg_ctl exits).
        subprocess.run(
            [_b("pg_ctl"), "-D", str(pgdata), "-l", str(logfile), "-w", "-t", "30",
             "-o", f"-c listen_addresses='' -c unix_socket_directories={sockdir} "
             f"-c fsync=off", "start"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        started = True
        handle = _Pg(_b("psql"), f"host={sockdir} dbname=postgres user=postgres")
        # Minimal-but-faithful officer_tasks (038 columns) + the REAL 041 DDL
        # (due_at, reminder_fired_at, the re-arm trigger) so the claim + bump run
        # against ACTUAL re-arm semantics, not a Python model.
        handle.run("CREATE TABLE officer_tasks ("
                   " id BIGSERIAL PRIMARY KEY,"
                   " officer_slug TEXT NOT NULL,"
                   " title TEXT NOT NULL,"
                   " status TEXT NOT NULL"
                   "   CHECK (status IN ('queue','wip','done','cancelled')),"
                   " type TEXT NOT NULL DEFAULT 'task');")
        handle.run((_REPO / "cabinet" / "sql" / "041-tasks-due-at.sql").read_text())
        yield handle
    except Exception as e:  # noqa: BLE001
        if not started:
            shutil.rmtree(sockdir, ignore_errors=True)
            tail = logfile.read_text()[-500:] if logfile.exists() else ""
            pytest.skip(f"could not start ephemeral Postgres: {e}\n{tail}")
        raise
    finally:
        if started:
            subprocess.run([_b("pg_ctl"), "-D", str(pgdata), "-w", "-t", "20",
                            "stop", "-m", "immediate"], capture_output=True)
        shutil.rmtree(sockdir, ignore_errors=True)


@_PG_SKIP
class TestLiveClaimBumpForgery:
    """The claim predicate, the snooze bump guard, the real 041 re-arm, and the
    P2 no-forgery RETURNING — run against a REAL Postgres using the SCRIPT'S OWN
    extracted SQL. Each has a negative control that MUTATES the shipped SQL and
    proves the removed predicate/column was load-bearing."""

    # Seed rows as offsets from NOW() (minutes); '' ⇒ NULL. All binds go through
    # :'var' on STDIN — the untrusted title is never inlined into SQL text.
    def _seed(self, pg, rows):
        # Timestamps stay on the DB clock (NOW()) — no Python/DB skew. NULLIF(…,'')
        # yields NULL for an empty offset, and make_interval(mins => NULL) → NULL,
        # so an empty offset is a NULL column. (A bare :'x'::int would constant-fold
        # ''::int at plan time and error even inside a CASE guard.)
        pg.run("TRUNCATE officer_tasks RESTART IDENTITY;")
        for r in rows:
            pg.run(
                "INSERT INTO officer_tasks"
                " (officer_slug, title, status, type, due_at, reminder_fired_at)"
                " VALUES (:'sl', :'t', :'st', :'ty',"
                "  NOW() + make_interval(mins => NULLIF(:'due','')::int),"
                "  NOW() + make_interval(mins => NULLIF(:'fired','')::int));",
                vars={"sl": r.get("slug", "captain"), "t": r.get("title", "x"),
                      "st": r.get("status", "queue"), "ty": r.get("type", "reminder"),
                      "due": r.get("due_min", ""), "fired": r.get("fired_min", "")})

    @staticmethod
    def _routing_ids(out):
        return sorted(int(l.split("\t")[0]) for l in out.splitlines() if "\t" in l)

    @staticmethod
    def _bump_hit(out, task_id):
        # Mirror the tick's own `grep -qE '^[0-9]+$'` on the bump RETURNING.
        return any(l.strip() == str(task_id) for l in out.splitlines())

    # -- claim predicate -----------------------------------------------------
    def test_claim_only_returns_claimable_and_marks_it_fired(self, pg):
        self._seed(pg, [
            {"title": "A", "status": "queue", "due_min": "-1", "fired_min": ""},   # claimable
            {"title": "B", "status": "queue", "due_min": "-1", "fired_min": "-1"}, # already fired
            {"title": "C", "status": "queue", "due_min": "1440", "fired_min": ""}, # future
            {"title": "D", "status": "done",  "due_min": "-1", "fired_min": ""},   # not queue/wip
        ])
        out = pg.run(_tick_sql("WITH due_tasks"), field_sep="\t")
        assert self._routing_ids(out) == [1]                 # only A
        fired = pg.run("SELECT id FROM officer_tasks"
                       " WHERE reminder_fired_at IS NOT NULL ORDER BY id;")
        assert sorted(fired.split()) == ["1", "2"]           # A newly fired, B already

    def test_negative_control_claim_without_fired_predicate_reclaims(self, pg):
        self._seed(pg, [
            {"title": "A", "status": "queue", "due_min": "-1", "fired_min": ""},
            {"title": "B", "status": "queue", "due_min": "-1", "fired_min": "-1"},  # fired
        ])
        claim = _tick_sql("WITH due_tasks")
        mutated = "\n".join(l for l in claim.splitlines()
                            if "reminder_fired_at IS NULL" not in l)
        assert mutated != claim                              # predicate line existed + removed
        out = pg.run(mutated, field_sep="\t")
        assert self._routing_ids(out) == [1, 2]              # B WRONGLY reclaimed

    # -- snooze bump guard + real 041 re-arm ---------------------------------
    def test_bump_guard_and_real_rearm(self, pg):
        self._seed(pg, [
            {"title": "A", "status": "queue", "due_min": "-1", "fired_min": ""},    # overdue, NOT fired
            {"title": "B", "status": "queue", "due_min": "-1", "fired_min": "-1"},  # overdue + fired
            {"title": "G", "status": "queue", "due_min": "1440", "fired_min": "-1"},# future + fired
        ])
        bump = _tick_sql("make_interval")
        assert not self._bump_hit(pg.run(bump, vars={"id": 1, "days": 7}), 1)  # unfired → guard blocks
        assert not self._bump_hit(pg.run(bump, vars={"id": 3, "days": 7}), 3)  # future → blocked
        assert self._bump_hit(pg.run(bump, vars={"id": 2, "days": 7}), 2)      # overdue+fired → bumps
        # the REAL 041 re-arm cleared reminder_fired_at and pushed due_at future.
        row = pg.run("SELECT (due_at > NOW())::text || '|'"
                     " || (reminder_fired_at IS NULL)::text"
                     " FROM officer_tasks WHERE id = 2;").strip()
        assert row == "true|true"       # bumped into the future + re-arm cleared fired

    def test_negative_control_bump_without_fired_guard_bumps_unfired(self, pg):
        self._seed(pg, [
            {"title": "A", "status": "queue", "due_min": "-1", "fired_min": ""},   # overdue, NOT fired
        ])
        bump = _tick_sql("make_interval")
        mutated = "\n".join(l for l in bump.splitlines()
                            if "reminder_fired_at IS NOT NULL" not in l)
        assert mutated != bump
        assert self._bump_hit(pg.run(mutated, vars={"id": 1, "days": 7}), 1)  # unfired WRONGLY bumped

    # -- P2: the shipped RETURNING cannot forge a routing row ----------------
    _EVIL_TITLE = ("CHASE DG JUST\n999\tvictim-officer\t"
                   "2020-01-01T00:00:00Z\ttask\tFORGED")

    def test_malicious_title_never_forges_via_real_returning(self, pg):
        self._seed(pg, [{"title": self._EVIL_TITLE, "status": "queue",
                         "due_min": "-1", "fired_min": ""}])
        out = pg.run(_tick_sql("WITH due_tasks"), field_sep="\t")
        routing = [l for l in out.splitlines() if "\t" in l]
        assert len(routing) == 1                             # ONE row, not a forged pair
        fields = routing[0].split("\t")
        assert fields[0] == "1" and fields[1] == "captain"   # the genuine captain row
        assert "victim-officer" not in out and "FORGED" not in out   # no title shrapnel at all

    def test_negative_control_title_in_returning_would_forge(self, pg):
        self._seed(pg, [{"title": self._EVIL_TITLE, "status": "queue",
                         "due_min": "-1", "fired_min": ""}])
        claim = _tick_sql("WITH due_tasks")
        mutated = re.sub(r"RETURNING id, officer_slug, due_at, type",
                         "RETURNING id, officer_slug, due_at, type, title", claim)
        assert mutated != claim                              # the removed column re-added
        out = pg.run(mutated, field_sep="\t")
        routing = [l for l in out.splitlines() if "\t" in l]
        # the title's embedded newline splits the row → a SECOND (forged) routing
        # line carrying victim-officer/FORGED: proof the dropped column was the vuln.
        assert len(routing) >= 2
        assert any("victim-officer" in l and "FORGED" in l for l in routing)

    # -- the by-id title re-read works against real psql (heredoc, not -c) ----
    def test_title_reread_interpolates_via_stdin(self, pg):
        self._seed(pg, [{"title": "café ☕ \"quote\" 'apos'", "status": "queue",
                         "due_min": "-1", "fired_min": ""}])
        got = pg.run(_tick_sql("SELECT title FROM officer_tasks"),
                     vars={"id": 1}).strip()
        assert got == "café ☕ \"quote\" 'apos'"             # :'id' bound + returned verbatim

    # -- end-to-end: the ACTUAL tick against real psql files a real-title card --
    def test_end_to_end_tick_files_captain_card_with_real_title(self, pg, tmp_path):
        """Run the SHIPPED tick against real psql: it claims a due captain
        reminder and files ONE card whose body carries the EXACT (multi-line,
        P2-shaped) title. Proves the by-id title re-read interpolates via STDIN
        (a -c string sends :'id' literally → empty title → '(no text)'), and that
        the malicious title lands as card DATA, not a forged officer trigger."""
        title = ("CHASE DG JUST\n999\tvictim-officer\t"
                 "2020-01-01T00:00:00Z\ttask\tFORGED")
        self._seed(pg, [{"title": title, "status": "queue",
                         "due_min": "-1", "fired_min": ""}])
        root = tmp_path / "root"
        (root / "shared" / "interfaces").mkdir(parents=True)
        bind = tmp_path / "bin"
        bind.mkdir()
        (bind / "redis-cli").write_text("#!/bin/bash\nexit 0\n")
        (bind / "redis-cli").chmod(0o755)
        env = {**os.environ, "CONN": pg.conn, "CABINET_ROOT": str(root),
               "CABINET_NEEDS_WIRED": "1", "PYTHON": sys.executable,
               "REDIS_HOST": "127.0.0.1", "PATH": f"{bind}:{os.environ['PATH']}"}
        r = subprocess.run(["bash", str(_SCRIPTS / "due-at-reminder-tick.sh")],
                           capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        assert "carded=1" in r.stdout and "fired=0" in r.stdout   # card, no officer trigger
        cards = [v for v in _ledger_rows(root).values()
                 if str(v.get("action_type", "")).startswith("captain-reminder:")]
        assert len(cards) == 1                     # ONE card — the newline did not forge a pair
        assert title in cards[0]["why"]            # the EXACT multi-line title, re-read by id
