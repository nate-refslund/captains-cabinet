"""ONE-DOOR ratchet (attention-gateway P3, spec §4.4/§4.10.3): the ONLY code
allowed to speak to api.telegram.org is the gated front-door channel plus the
inbound poller and a documented, SHRINK-ONLY allowlist. A new raw poster
anywhere else is CI-red, not a review note — every bypass subtracts the
killswitch, token scrub, chunking, and the feed journal (sister ratchet to
the launcher-hardcode and axis linters).

DEGENERATE ENDS (added 2026-07-28 by the fixture-shape mutation sweep, which
DELETED every file this ratchet scans and watched both arms stay green). Both
assertions are of the form ``offenders == []``, so a scan that matches NOTHING
reads as perfect compliance: rename ``framework/frontdoor/`` or
``cabinet/scripts/``, move the literal host out of the door into a config
value, or break a glob, and this file goes on passing forever while the
one-door law is unenforced. The sister ratchets
(``test_ovi_never_a_selection_input``, ``test_canonical_tasks_ratchet``,
``test_axes_contract``) each carry the arms this one lacked, and it now
carries them too:

  * every scanned tree must EXIST — a rename that empties the scan is RED;
  * the scan must be NON-EMPTY and must contain the door itself, read out of
    the scanner's own output rather than asserted from a hand-written list;
  * the scanner is proven live by ``test_scanner_flags_a_planted_poster``,
    which plants a raw poster in a synthetic tree and asserts it is reported
    (and that the test-file exclusion still holds, so the proof cannot be had
    by over-reporting);
  * every ALLOWED and KILLED path must exist — a shrink-only allowlist whose
    entries name deleted files is rot, and a kill-list that pins a path
    nothing can occupy cannot detect a resurrection. This found one — the
    path ``cabinet/scripts/hooks-src/pre-captain-dm.sh`` sat in ALLOWED with
    no such file anywhere in the tree and no other reference to it in the
    repo. Removed below; removal is what shrink-only permits;
  * every ALLOWED and KILLED path must also be REACHED by the walk
    (``test_every_listed_path_is_reachable_by_the_scan``, added 2026-07-29 by
    the adversarial pass on the four arms above). EXISTING is not REACHED, and
    the four arms close only the glob breaks that EMPTY the scan. Measured
    forges that passed all four: ``cabinet/scripts/**/*.sh`` narrowed to
    ``cabinet/scripts/*.sh`` (roots exist, scan non-empty, door present,
    planted poster still reported at the top of ``cabinet/scripts`` — while
    ``cabinet/scripts/hooks/pre-captain-dm.sh`` silently left the surface),
    and ``framework/**/*.py`` narrowed to ``framework/frontdoor/**/*.py``
    (the whole P3 kill-list left the surface, so ``resurrected == []`` was
    once again true of nothing). Both are RED now.

RESIDUAL, stated rather than implied. The reachability arm is anchored to the
two lists, so a narrowing that drops only trees NO listed path lives in is
still green — and the opening sentence's "anywhere else is CI-red" is
therefore scoped to SCAN_GLOBS, which are python and shell only. Live
counter-examples in the tree today — all THREE carry the raw host, are on no
list, and this ratchet has never seen them:
  * ``cabinet/dashboard/src/lib/docker.ts``
  * ``cabinet/dashboard/src/app/api/telegram/provisioning-webhook/route.ts``
  * ``cabinet/dashboard/src/lib/telegram/connect.ts`` (added 2026-08-14 by the
    guided Telegram connect: getMe + a no-offset getUpdates + ONE sendMessage,
    the same read-only probe class as the two allowlisted shell errand helpers
    plus the one message that proves the round trip to the operator. It is
    deliberately the flow's ONLY caller — the step components import
    ``lib/telegram/contract.ts``, which has no transport — so a later widening
    of this scan to TypeScript has one file to rule on rather than a scatter.)
Widening the scan to the dashboard's TypeScript is a separate unit with its
own allowlist decision; until it lands, "anywhere else" means anywhere else
SCAN_GLOBS reaches.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# SHRINK-ONLY. Remove entries as they migrate behind the channel; never add
# without a spec §13 amendment. Paths are repo-relative.
ALLOWED = {
    # THE door (outbound) and its inbound twin:
    "framework/frontdoor/channel.py",
    "cabinet/scripts/officer-inbound-poller.py",
    # Inbound voice download (getFile) for transcription (the deployed hook;
    # the hooks-src twin was removed from this list 2026-07-28 — no such file
    # exists, see the module docstring):
    "cabinet/scripts/hooks/pre-captain-dm.sh",
    # Read-only probes, not senders — getMe health check and the wake-race
    # reachability wait (api.telegram.org:443) before composing a briefing:
    "cabinet/scripts/chair-preflight.sh",
    "cabinet/scripts/run-frontdoor-briefing.sh",
    # Pre-boot Captain-run errand helpers (PC-A; spec §13 amendment
    # 2026-07-10 in cabinet-attention-gateway-spec-2026-07-08.md): read-only
    # probes, not senders — getMe token validation and getUpdates chat-id
    # capture (timeout=0, NO offset — never consumes updates, never sends).
    # They run before any instance/.env exists, so they cannot ride
    # channel.py; tokens ride env/.env, never argv.
    "cabinet/scripts/telegram-validate-token.sh",
    "cabinet/scripts/telegram-capture-chat-id.sh",
    # Voice sender — rides on an already-sent text reply; migration TODO:
    "cabinet/scripts/send-voice.sh",
    # Hook pager — rare infra alert; migrate to attention-submit (P4 TODO):
    "cabinet/scripts/hooks-src/model-fallback-pager.sh",
    # Warroom GROUP surface (not the Captain DM; separate channel contract):
    "cabinet/scripts/send-to-warroom.sh",
    # Legacy Docker-era, dormant on mac-native (not in generated launchd);
    # deprecated in place rather than deleted (docs reference them):
    "cabinet/scripts/health-check.sh",
    "cabinet/scripts/cost-dashboard.sh",
    "cabinet/scripts/token-refresh-watch.sh",
    "cabinet/scripts/officer-supervisor.sh",
    "cabinet/scripts/reply-to-captain.sh",
    # Admin bot: separate python-telegram-bot surface with its own token:
    "cabinet/admin-bot",
}

# The three P3 kill-list posters — pinned OUT of the allowlist forever.
KILLED = {
    "framework/acting/run_action_lane.py",
    "framework/acting/run_draft_lane.py",
    "framework/frontdoor/action_exec.py",
}

SCAN_GLOBS = ("framework/**/*.py", "cabinet/scripts/**/*.py",
              "cabinet/scripts/**/*.sh", "cabinet/admin-bot/**/*.py")


# The door's own file, asserted to be IN the scan below. Not a second copy of
# the allowlist: it is the one entry whose absence from the hits means the
# scanner stopped seeing the surface it exists to police.
THE_DOOR = "framework/frontdoor/channel.py"


def _scan_roots():
    """The top directory of each glob — every one must exist, or the scan is
    silently smaller than the law it enforces."""
    return sorted({p.split("/*", 1)[0] for p in SCAN_GLOBS})


def _scanned_files(root: Path = ROOT):
    """{repo-relative path: Path} for every file the globs actually REACH,
    after the test-file exclusion — i.e. the surface both ``offenders == []``
    arms are computed over. ``_hits`` is defined as a content filter over this
    exact mapping ON PURPOSE: the reachability arm must measure the walk the
    ratchet really performs, not a wishful second copy of it that a narrowed
    glob would leave untouched."""
    out = {}
    for pattern in SCAN_GLOBS:
        for f in root.glob(pattern):
            rel = f.relative_to(root).as_posix()
            if "/tests/" in rel or rel.startswith("framework/tests/"):
                continue
            out[rel] = f
    return out


def _hits(root: Path = ROOT):
    out = set()
    for rel, f in _scanned_files(root).items():
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "api.telegram.org" in text:
            out.add(rel)
    return out


def test_only_the_door_talks_to_telegram():
    hits = _hits()
    def allowed(rel):
        return any(rel == a or rel.startswith(a + "/") for a in ALLOWED)
    offenders = sorted(h for h in hits if not allowed(h))
    assert offenders == [], (
        "raw api.telegram.org outside the door — route through "
        f"framework.frontdoor.channel (spec §4.4): {offenders}")


def test_kill_list_stays_killed():
    hits = _hits()
    resurrected = sorted(hits & KILLED)
    assert resurrected == [], (
        f"P3 kill-list poster resurrected a raw telegram call: {resurrected}")
    assert not (KILLED & ALLOWED), "kill-list files must never be allowlisted"


# ---------------------------------------------------------------------------
# DEGENERATE ENDS — a scan of nothing must never read as compliance.
# ---------------------------------------------------------------------------

def test_every_scanned_tree_exists():
    """A rename that empties the scan is RED, not silently green."""
    missing = [d for d in _scan_roots() if not (ROOT / d).is_dir()]
    assert missing == [], (
        f"the one-door scan names trees that do not exist: {missing} — "
        "re-point SCAN_GLOBS at the moved code; an empty scan passes both "
        "arms above while every raw poster in the tree goes unseen")


def test_the_scan_is_not_empty_and_contains_the_door():
    """The scan's own output, not a hand-written list, is the floor: the
    gated door is BY CONSTRUCTION a raw ``api.telegram.org`` caller, so it
    must appear in the hits. If it stops appearing, either the door stopped
    being the door or the scanner stopped reaching it — both of which make
    ``offenders == []`` meaningless."""
    hits = _hits()
    assert hits, (
        "the one-door scan matched NOTHING — every arm in this file passes "
        "vacuously in that state")
    assert THE_DOOR in hits, (
        f"{THE_DOOR} is not among the scanned telegram callers {sorted(hits)} "
        "— the scanner is no longer reading the surface it polices")


def test_every_listed_path_exists():
    """A shrink-only allowlist rots into naming deleted files, and a kill-list
    that pins a path nothing can occupy cannot detect a resurrection."""
    missing = sorted(p for p in (ALLOWED | KILLED) if not (ROOT / p).exists())
    assert missing == [], (
        f"listed paths that do not exist: {missing} — drop them from ALLOWED "
        "(removal is what shrink-only permits) or re-point KILLED at where "
        "the poster moved")


def test_every_listed_path_is_reachable_by_the_scan():
    """EXISTING is not REACHED. The four arms above catch a glob break that
    EMPTIES the scan; they do not catch one that merely SHRINKS it, and both
    natural shrinks were measured green against all four (named in the last
    block of the module docstring). An allowlist entry the walk never visits
    permits nothing, and a kill-list entry the walk never visits cannot detect
    the resurrection it exists to detect — in both states the two
    ``== []`` arms are true of a set that can no longer contain the file."""
    surface = set(_scanned_files())

    def reached(p):
        return p in surface or any(s.startswith(p + "/") for s in surface)

    unreachable = sorted(p for p in (ALLOWED | KILLED) if not reached(p))
    assert unreachable == [], (
        f"SCAN_GLOBS no longer reach listed paths: {unreachable} — the "
        "allowlist and the kill-list only bind files the walk actually "
        "visits; widen SCAN_GLOBS back over them, or drop the entries and "
        "say in the docstring that they are no longer policed")


def test_scanner_flags_a_planted_poster(tmp_path):
    """Proves ``_hits`` is a live sensor rather than a function that returns
    the empty set. Without this arm the file could pass by scanning nothing
    correctly, forever."""
    (tmp_path / "cabinet" / "scripts").mkdir(parents=True)
    (tmp_path / "cabinet" / "scripts" / "rogue.sh").write_text(
        'curl -s "https://api.telegram.org/bot$TOKEN/sendMessage"\n')
    (tmp_path / "framework" / "frontdoor").mkdir(parents=True)
    (tmp_path / "framework" / "frontdoor" / "channel.py").write_text(
        '_URL = "https://api.telegram.org/bot"\n')
    (tmp_path / "framework" / "quiet.py").write_text("x = 1\n")
    (tmp_path / "cabinet" / "scripts" / "tests").mkdir()
    (tmp_path / "cabinet" / "scripts" / "tests" / "test_x.py").write_text(
        'URL = "https://api.telegram.org/bot"\n')

    hits = _hits(tmp_path)
    assert "cabinet/scripts/rogue.sh" in hits, (
        "the scanner did not report a planted raw poster — it cannot report a "
        "real one either")
    assert THE_DOOR in hits
    assert "framework/quiet.py" not in hits, "scanner reports files with no hit"
    assert "cabinet/scripts/tests/test_x.py" not in hits, (
        "the /tests/ exclusion broke — a scanner that reports test files "
        "would 'prove' itself live while missing production posters")
