"""ONE-DOOR ratchet (attention-gateway P3, spec §4.4/§4.10.3): the ONLY code
allowed to speak to api.telegram.org is the gated front-door channel plus the
inbound poller and a documented, SHRINK-ONLY allowlist. A new raw poster
anywhere else is CI-red, not a review note — every bypass subtracts the
killswitch, token scrub, chunking, and the feed journal (sister ratchet to
the launcher-hardcode and axis linters)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# SHRINK-ONLY. Remove entries as they migrate behind the channel; never add
# without a spec §13 amendment. Paths are repo-relative.
ALLOWED = {
    # THE door (outbound) and its inbound twin:
    "framework/frontdoor/channel.py",
    "cabinet/scripts/officer-inbound-poller.py",
    # Inbound voice download (getFile) for transcription (src + deployed):
    "cabinet/scripts/hooks-src/pre-captain-dm.sh",
    "cabinet/scripts/hooks/pre-captain-dm.sh",
    # Read-only probes, not senders — getMe health check and the wake-race
    # reachability wait (api.telegram.org:443) before composing a briefing:
    "cabinet/scripts/chair-preflight.sh",
    "cabinet/scripts/run-frontdoor-briefing.sh",
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


def _hits():
    out = set()
    for pattern in SCAN_GLOBS:
        for f in ROOT.glob(pattern):
            rel = f.relative_to(ROOT).as_posix()
            if "/tests/" in rel or rel.startswith("framework/tests/"):
                continue
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
