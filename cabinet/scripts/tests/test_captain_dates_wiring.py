"""The dated-commitment store's WIRING — every consumer actually reads it.

Captain-Seat dry run 2026-07-26, finding 1: the Captain set a release date and it
appeared in ZERO of the next twelve days of briefings, because nothing in the org
held it. A store with no reader would be that failure with extra steps, so these
arms pin the CONSUMERS, not the resolver (framework/tests/test_env_captain_dates.py
owns that) and not the writer (cabinet/scripts/lib/tests/test_captain_dates.py):

  * the BRIEFING renders one line per open date, EVERY run — the arm that is red
    against pre-change code, because ``captain_date_items`` did not exist and
    ``gather_items`` had no such source;
  * a PAST-DUE date renders LOUDER and FIRST — the quietest possible version of
    the original failure is a passed date rendered like every other row;
  * ZERO open dates ⇒ ZERO lines and NO placeholder (the degenerate end: a
    placeholder pretending to be an answer is this program's named failure);
  * a done/moved row is HISTORY and never re-surfaces;
  * the Captain-seat evidence pack prints his open dates WITH whether the latest
    briefing carries each, and prints the measured absence when the store is
    absent — both ends, because a sensor that cannot detect the degenerate case
    is not a sensor;
  * the retro's Part 1c (and its byte-parity doctrine-pack twin) carry the clause
    that reads an untracked open date as an in-window paid cost;
  * the inbound poller dispatches the verbs from its own process, gated on the
    Captain's own chat id, archiving the DM, with a fail-open relay.

Hermetic: every pack run points CAPTAIN_SEAT_ROOT at a tmp tree and shadows
`redis-cli` with a stub that connects to nothing; every briefing arm injects its
rows and its ``today``, so no live store, control plane, network or clock is
touched.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PACK = REPO / "cabinet/scripts/meta-cognition/captain-seat-pack.sh"
RETRO_SKILL = REPO / "memory/skills/cross-officer-retro.md"
PACK_TWIN = REPO / "packs/doctrine-pack/skills/cross-officer-retro/SKILL.md"
POLLER = REPO / "cabinet/scripts/officer-inbound-poller.py"

ABSENCE = ("no dates on the org's books — nothing is holding a date the "
           "captain set")

TODAY = "2026-07-27"


def _row(rid, when, label, status="open"):
    return {"id": rid, "date": when, "label": label, "status": status,
            "set_at": "2026-07-01T09:00:00Z", "source": "telegram",
            "supersedes": None}


def _synthesis():
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from framework.frontdoor import morning_synthesis
    return morning_synthesis


def _run_pack(seat_root: Path, scratch: Path) -> str:
    """The pack, read-only, against a tmp root in a rebuilt environment."""
    shim = scratch / "bin"
    shim.mkdir(parents=True, exist_ok=True)
    redis = shim / "redis-cli"
    redis.write_text("#!/bin/sh\nexit 1\n")
    redis.chmod(0o755)
    py = shim / "python3.12"
    py.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    py.chmod(0o755)
    home = scratch / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": f"{shim}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "HOME": str(home),
        "LC_ALL": "C.UTF-8",
        "CAPTAIN_SEAT_ROOT": str(seat_root),
        "CAPTAIN_SEAT_WINDOW_DAYS": "14",
    }
    proc = subprocess.run(["bash", str(PACK)], env=env, cwd=str(scratch),
                          capture_output=True, text=True, timeout=120,
                          check=False)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _dates_section(out: str) -> str:
    """Only the DATES section, so an absence assertion cannot be satisfied by
    text another section happens to print."""
    head = "=== DATES HE SET"
    if head not in out:
        return ""
    return out.split(head, 1)[1].split("\n=== ", 1)[0]


def _seat_root(tmp_path: Path, store_body: str | None = None,
               briefing_body: str | None = None) -> Path:
    root = tmp_path / "seat"
    (root / "instance/config").mkdir(parents=True, exist_ok=True)
    if store_body is not None:
        (root / "instance/config/captain-dates.yml").write_text(
            store_body, encoding="utf-8")
    if briefing_body is not None:
        bdir = root / "instance/memory/briefings"
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / "briefing-20260726-073000Z.md").write_text(
            briefing_body, encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# the BRIEFING consumer — the arm that closes the paid failure
# ---------------------------------------------------------------------------
def test_briefing_renders_one_line_per_open_date():
    """RED AGAINST PRE-CHANGE CODE: neither ``captain_date_items`` nor the
    ``captain-date`` source existed, which is exactly why a captain-set date
    could vanish from twelve days of briefings."""
    ms = _synthesis()
    rows = [_row("d-a1", "2026-08-13", "board review"),
            _row("d-b2", "2026-09-01", "quarterly numbers")]
    items = ms.captain_date_items(dates=rows, today=TODAY)
    assert len(items) == 1, "ONE item, so the composer's per-tier cap can never " \
                            "roll the Nth date into a count line"
    summary = items[0]["payload"]["summary"]
    assert "board review: 2026-08-13 (in 17 days)" in summary, summary
    assert "quarterly numbers: 2026-09-01 (in 36 days)" in summary, summary
    assert summary.count("\n•") == 2, "one line per open date, never capped"
    assert items[0]["source"] == "captain-date"
    assert items[0]["urgency_tier"] == "batch", (
        "a standing reminder, not a new interrupt channel")


def test_the_briefing_composer_actually_renders_the_lines():
    """The item is worthless if the composer drops it: compose the real thing."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from framework.frontdoor import composer
    ms = _synthesis()
    items = ms.captain_date_items(
        dates=[_row("d-a1", "2026-08-13", "board review")], today=TODAY)
    text = composer.compose(items)
    assert "board review: 2026-08-13 (in 17 days)" in text, text


def test_gather_items_carries_the_captain_date_source():
    """The leg has to be IN the enqueued set, not merely available: this is the
    wiring the original failure lacked."""
    ms = _synthesis()
    rows = [_row("d-a1", "2026-08-13", "board review")]
    orig = ms.captain_date_items
    try:
        ms.captain_date_items = lambda: orig(dates=rows, today=TODAY)
        sources = {it.get("source") for it in ms.gather_items(limit=1)}
    finally:
        ms.captain_date_items = orig
    assert "captain-date" in sources, sources


def test_a_past_due_date_renders_louder_and_first():
    """LOUDER, and ABOVE the upcoming rows. A passed date rendered like any
    other row is the quietest possible version of the original failure."""
    ms = _synthesis()
    items = ms.captain_date_items(
        dates=[_row("d-a1", "2026-08-13", "board review"),
               _row("d-b2", "2026-07-20", "quarterly numbers")],
        today=TODAY)
    summary = items[0]["payload"]["summary"]
    assert "OVERDUE by 7 days — quarterly numbers: 2026-07-20" in summary, summary
    lines = [ln for ln in summary.splitlines() if ln.startswith("•")]
    assert "OVERDUE" in lines[0], f"overdue must lead: {lines}"
    assert "OVERDUE" not in lines[1]
    assert items[0]["context"]["overdue"] == 1
    assert "past its date" in items[0]["context"]["why"]


def test_a_date_due_today_is_not_reported_as_overdue():
    """The boundary: the day OF is not late, and must not be shouted at him."""
    ms = _synthesis()
    items = ms.captain_date_items(dates=[_row("d-a1", TODAY, "board review")],
                                 today=TODAY)
    summary = items[0]["payload"]["summary"]
    assert f"board review: {TODAY} (today)" in summary, summary
    assert "OVERDUE" not in summary


def test_zero_open_dates_renders_nothing_at_all():
    """THE DEGENERATE END. No dates ⇒ no item, no header, no 'none today' row —
    a placeholder pretending to be an answer is the named failure."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from framework.frontdoor import composer
    ms = _synthesis()
    assert ms.captain_date_items(dates=[], today=TODAY) == []
    assert composer.compose(ms.captain_date_items(dates=[], today=TODAY)) == ""


def test_closed_and_moved_rows_never_reach_the_briefing():
    """A done/moved row is history. Re-surfacing it would nag him about
    something he already closed — the opposite failure, equally his cost."""
    ms = _synthesis()
    items = ms.captain_date_items(
        dates=[_row("d-a1", "2026-08-13", "board review", status="done"),
               _row("d-b2", "2026-09-01", "quarterly numbers", status="moved")],
        today=TODAY)
    assert items == []


def test_a_broken_resolver_never_blocks_the_briefing():
    """Best-effort: the dates leg may cost the briefing nothing if it fails."""
    ms = _synthesis()
    orig = ms.env_captain_open_dates
    try:
        def _boom():
            raise RuntimeError("store on fire")
        ms.env_captain_open_dates = _boom
        assert ms.captain_date_items(today=TODAY) == []
    finally:
        ms.env_captain_open_dates = orig


# ---------------------------------------------------------------------------
# the Captain-seat pack — both ends
# ---------------------------------------------------------------------------
def test_pack_reports_open_dates_and_whether_the_briefing_carries_them(tmp_path):
    """The TRACKED COLUMN is the finding. One label is in the briefing body and
    one is not, so a pack that assumed tracking prints one value twice."""
    root = _seat_root(
        tmp_path,
        store_body=(
            "entries:\n"
            "  - id: d-aa1\n"
            "    at: 2026-07-01T09:00:00Z\n"
            "    date: 2026-08-13\n"
            '    label: "board review"\n'
            "    status: open\n"
            "    source: telegram\n"
            "  - id: d-bb2\n"
            "    at: 2026-07-02T09:00:00Z\n"
            "    date: 2026-09-01\n"
            '    label: "quarterly numbers"\n'
            "    status: open\n"
            "    source: telegram\n"),
        briefing_body="a briefing that mentions board review and nothing else\n")
    section = _dates_section(_run_pack(root, tmp_path / "scratch"))
    assert section, "the DATES section must run"
    assert "open dates: 2" in section, section
    assert '"board review"  tracked_in_latest_briefing=yes' in section, section
    assert '"quarterly numbers"  tracked_in_latest_briefing=NO' in section, section


def test_pack_folds_latest_row_per_id(tmp_path):
    """Append-only means a later same-id row WINS. A first-row reader would
    report a closed date as still open and nag him about it."""
    root = _seat_root(tmp_path, store_body=(
        "entries:\n"
        "  - id: d-aa1\n"
        "    at: 2026-07-01T09:00:00Z\n"
        "    date: 2026-08-13\n"
        '    label: "board review"\n'
        "    status: open\n"
        "  - id: d-aa1\n"
        "    at: 2026-07-05T09:00:00Z\n"
        "    date: 2026-08-13\n"
        '    label: "board review"\n'
        "    status: done\n"))
    section = _dates_section(_run_pack(root, tmp_path / "scratch"))
    assert "open dates: 0" in section, section
    assert "board review" not in section, section


def test_pack_says_so_when_there_is_no_briefing_to_check_against(tmp_path):
    """An unmeasured column must read UNCHECKED, never 'yes'. Reporting a
    tracked date on a deployment with no briefing store would be the sensor
    certifying something it never looked at."""
    root = _seat_root(tmp_path, store_body=(
        "entries:\n"
        "  - id: d-aa1\n"
        "    at: 2026-07-01T09:00:00Z\n"
        "    date: 2026-08-13\n"
        '    label: "board review"\n'
        "    status: open\n"))
    section = _dates_section(_run_pack(root, tmp_path / "scratch"))
    assert "latest briefing checked: NONE" in section, section
    assert "tracked_in_latest_briefing=UNCHECKED" in section, section
    assert "tracked_in_latest_briefing=yes" not in section


def test_pack_reports_an_absent_store_as_a_measured_absence(tmp_path):
    """THE degenerate end. Nothing holding a date must be said in words — a
    silent section, or an 'open dates: 0' header with no store behind it, would
    read as 'checked, all fine'."""
    root = _seat_root(tmp_path)
    out = _run_pack(root, tmp_path / "scratch")
    section = _dates_section(out)
    assert section, "the section must still run"
    assert ABSENCE in section, section
    assert "open dates:" not in section
    assert "tracked_in_latest_briefing" not in section


def test_pack_does_not_write_into_the_dates_tree_it_reads(tmp_path):
    root = _seat_root(tmp_path, store_body=(
        "entries:\n"
        "  - id: d-aa1\n"
        "    at: 2026-07-01T09:00:00Z\n"
        "    date: 2026-08-13\n"
        '    label: "board review"\n'
        "    status: open\n"))
    store = root / "instance/config/captain-dates.yml"
    before = store.read_bytes()
    _run_pack(root, tmp_path / "scratch")
    assert store.read_bytes() == before


# ---------------------------------------------------------------------------
# the retro contract (and its byte-parity twin)
# ---------------------------------------------------------------------------
def test_part_1c_reads_an_untracked_open_date_as_a_paid_cost():
    text = RETRO_SKILL.read_text(encoding="utf-8")
    assert "tracked_in_latest_briefing" in text
    assert "an open date the latest briefing does not carry means he had to " \
           "hold it himself" in text
    assert "An empty store is not a finding" in text, (
        "the silence half: an empty store must not become a manufactured finding")


def test_doctrine_pack_twin_carries_the_same_clause():
    """The pack copy is what a pack INSTALLER gets; a canonical-only edit ships
    stale doctrine to everyone outside this repo."""
    assert "an open date the latest briefing does not carry" in \
        PACK_TWIN.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# the phone dispatch branch
# ---------------------------------------------------------------------------
def test_poller_dispatches_the_verbs_captain_gated_and_fails_open():
    """Text-scan of the poller's dispatch chain: the branch must exist, be
    gated on the Captain's own id like every sibling branch, archive the DM,
    and relay on failure so a real message is never silently eaten."""
    text = POLLER.read_text(encoding="utf-8")
    assert "def is_dates_command(" in text
    assert "def dates_command_reply(" in text
    assert 'elif frm == str(captain) and is_dates_command(text):' in text
    branch = text.split(
        'elif frm == str(captain) and is_dates_command(text):', 1)[1]
    branch = branch.split("elif frm == str(captain) and text:", 1)[0]
    assert 'kind="dates"' in branch, "the DM must be archived"
    assert '"kind": "dates-command"' in branch, "flight-recorder row"
    assert "if not sent:" in branch and "deliver(text" in branch, (
        "a record-or-send failure must fall OPEN to the Chair relay")


def test_the_dates_branch_cannot_swallow_an_availability_ruling():
    """Two anchored verbs in one chain: the dates grammar must not match the
    availability dial's words (or vice versa), or one control would eat the
    other. Checked against the real libraries, not against the branch order."""
    lib = REPO / "cabinet/scripts/lib"
    if str(lib) not in sys.path:
        sys.path.insert(0, str(lib))
    import captain_availability as ca
    import captain_dates as cd
    assert cd.parse_dates_command("availability 20m") is None
    assert ca.parse_availability_command("date 2026-08-13 board review") is None
    assert ca.parse_availability_command("dates") is None
