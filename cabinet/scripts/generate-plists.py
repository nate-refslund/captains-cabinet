#!/opt/homebrew/bin/python3.12
"""generate-plists.py — render launchd plists for the cabinet fleet from
cabinet/services.yml (F0.4, 2026-07-02).

Scope: DAEMON, WATCHDOG and CRON kinds (all render identically — kind is fleet
taxonomy, not a rendering switch). Officers (kind: officer) are rendered
by deploy-mac.sh from cabinet/launchd/com.cabinet.officer.template.plist with
the roster derived from instance/config/roster.yml — one owner per joint.

Kind handling is STRICT (lane-ops 2026-07-04): an unknown kind is a hard
error, never a silent skip. The silent-skip of `kind: cron` is exactly how
the retro-trigger row was never rendered — its hand-made plist shipped
without PATH, launchd's minimal PATH has no /opt/homebrew/bin, and redis-cli
was unfindable (FATAL hourly since ~Jul 3) while every GENERATED plist
carried PATH all along.

`disabled: true` rows are skipped with a printed notice (parked/staged
services stay in the manifest as fleet truth — e.g. draft-lane, superseded by
the 2026-07-03 act-not-draft ruling — without being rendered or installed).

Briefing-time source of truth (silent-defaults audit C, 2026-07-18): the
com.cabinet.frontdoor-briefing row's StartCalendarInterval is stamped from
instance/config/platform.yml `briefing_times` (framework.env.briefing_times;
fleet default 07:30,19:30), NOT from the services.yml calendar row — that row
stays as the documented no-config fallback mirror and loses on divergence
(a provenance line is always printed; parity is pinned by
cabinet/scripts/tests/test_briefing_time_parity.py).

Security contract (Corridor-reviewed, binding):
  - service names validated ^[a-z0-9-]+$ BEFORE any filesystem path use
    (a malformed manifest cannot traverse paths);
  - plutil -lint runs via subprocess argument lists, never shell=True;
  - this script NEVER calls launchctl — rendering only; installation is a
    separate deliberate step (deploy-mac.sh);
  - no secret VALUES are ever rendered: plists carry PATH + declared
    per-service env (non-secret) only; secrets live in cabinet/.env, sourced
    at runtime by the command wrapper.

Modes:
  (default)  render all enabled daemon/watchdog/cron services to
             cabinet/launchd/generated/
             and plutil -lint each output; stale plist outputs are pruned only
             after the complete current set has rendered and linted.
  --output-dir renders to an operator/test staging directory without pruning;
             ~/Library/LaunchAgents is explicitly refused.
  --check    additionally diff generated vs ~/Library/LaunchAgents installed
             copies (functional keys: Label present, schedule match, command
             script referenced). Unparseable installed plists (two live ones
             contain '--' inside XML comments, which launchd tolerates but
             strict parsers reject) degrade to regex extraction — never crash.

Output dir is machine-specific (expanded $HOME/root paths) and gitignored.
"""

import argparse
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

NAME_RE = re.compile(r"^[a-z0-9-]+$")
LABEL_RE = re.compile(r"^[a-z0-9.-]+$")  # L-1 (cp1 review): label forms the output filename
# The launchd EnvironmentVariables PATH: a FIXED, captain-agnostic, ABSOLUTE
# literal. It is cross-pinned to the dependency-radar registry service_path
# (cabinet/config/dependency-radar.yml) + runbook by the tests, and the radar
# validator requires absolute dirs — so a per-user ~/.local/bin (native-
# installer `claude`) must NOT be baked here; it is prepended in the officer
# WRAPPER below, where bash expands $HOME at boot (#60 fresh-hatch fix).
PATH_ENV = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# The briefing service whose StartCalendarInterval is stamped from the ONE
# source of truth — instance/config/platform.yml `briefing_times` (via the
# framework.env resolver; fleet default 07:30,19:30). The calendar row in
# cabinet/services.yml stays as the documented no-config fallback MIRROR;
# platform.yml wins whenever the two disagree (silent-defaults audit C,
# 2026-07-18; parity pinned by cabinet/scripts/tests/test_briefing_time_parity.py).
BRIEFING_LABEL = "com.cabinet.frontdoor-briefing"


def repo_root() -> Path:
    env = os.environ.get("CABINET_ROOT")
    if env:
        return Path(env).resolve()
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
        cwd=Path(__file__).resolve().parent,
    )
    return Path(out.stdout.strip())


def load_services(root: Path):
    data = yaml.safe_load((root / "cabinet" / "services.yml").read_text())
    if not isinstance(data, dict) or not isinstance(data.get("services"), list):
        raise SystemExit("generate-plists: cabinet/services.yml must contain a services list")
    return data["services"]


def validate_services(services) -> None:
    """Validate the whole manifest before writing any output.

    Deployment reconciliation is intentionally fail-before-mutation: duplicate
    labels/names or an unknown kind must not leave a plausible-looking partial
    generated fleet behind for deploy-mac.sh to install.
    """
    rendered_kinds = ("daemon", "watchdog", "cron")
    valid_kinds = rendered_kinds + ("officer",)
    names = []
    labels = []
    for index, svc in enumerate(services):
        if not isinstance(svc, dict):
            raise SystemExit(f"generate-plists: services[{index}] must be a mapping")
        name = svc.get("name")
        label = svc.get("label")
        kind = svc.get("kind")
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            raise SystemExit(
                f"generate-plists: invalid service name {name!r} "
                "(must match ^[a-z0-9-]+$)"
            )
        if (
            not isinstance(label, str)
            or not LABEL_RE.fullmatch(label)
            or not label.startswith("com.cabinet.")
        ):
            raise SystemExit(
                f"generate-plists: invalid label for service {name!r} "
                "(must start com.cabinet. and match ^[a-z0-9.-]+$)"
            )
        if kind not in valid_kinds:
            raise SystemExit(
                f"generate-plists: unknown kind on service {name!r}: {kind!r} — "
                f"valid kinds: officer|{'|'.join(rendered_kinds)} "
                "(unknown kinds hard-error so a row can never be silently "
                "un-rendered again)"
            )
        names.append(name)
        labels.append(label)

    duplicate_names = sorted({name for name in names if names.count(name) > 1})
    duplicate_labels = sorted({label for label in labels if labels.count(label) > 1})
    if duplicate_names or duplicate_labels:
        parts = []
        if duplicate_names:
            parts.append(f"duplicate names={duplicate_names}")
        if duplicate_labels:
            parts.append(f"duplicate labels={duplicate_labels}")
        raise SystemExit("generate-plists: manifest identity collision: " + "; ".join(parts))


def stamp_briefing_schedule(services) -> str:
    """Overwrite the frontdoor-briefing row's calendar with the slots from the
    ONE source of truth — platform.yml ``briefing_times`` via
    ``framework.env.briefing_times()`` (fleet default 07:30,19:30 when the key
    or the file is absent, so a clean-room render is unchanged).

    ``framework`` is imported from THIS script's own repo checkout
    (``parents[2]`` — the code root), while the RESOLVER reads its config
    under ``CABINET_ROOT`` when set (the same root ``repo_root()`` honours),
    so a test can point the manifest+config at a fixture root without needing
    a framework/ copy there. Import/resolve failure falls back to the fleet
    default — rendering must never crash on a half-provisioned box; the
    stamped value is always printed (provenance), never silent.

    Returns the one-line provenance notice ("" when no briefing row exists)."""
    code_root = Path(__file__).resolve().parents[2]
    times = None
    try:
        sys.path.insert(0, str(code_root))
        try:
            from framework.env import briefing_times
            times = briefing_times()
        finally:
            try:
                sys.path.remove(str(code_root))
            except ValueError:
                pass
    except Exception as exc:  # noqa: BLE001 — resolver trouble must not kill rendering
        print(f"generate-plists: briefing_times resolver unavailable ({exc}) — "
              "stamping the fleet default 07:30,19:30", file=sys.stderr)
        times = ("07:30", "19:30")
    cal = []
    for t in times:
        h, m = t.split(":")
        cal.append({"hour": int(h), "minute": int(m)})
    for svc in services:
        if svc.get("label") == BRIEFING_LABEL and not svc.get("disabled"):
            old = (svc.get("schedule") or {}).get("calendar") \
                if isinstance(svc.get("schedule"), dict) else None
            svc["schedule"] = {"calendar": cal}
            note = (f"{svc['name']}: StartCalendarInterval stamped from "
                    f"platform.yml briefing_times → "
                    + ",".join(f"{c['hour']:02d}:{c['minute']:02d}" for c in cal))
            if old is not None and old != cal:
                note += (f" (services.yml fallback row said {old!r} — "
                         "platform.yml is the source of truth; re-sync the mirror)")
            return note
    return ""


def _host_iana_tz() -> "str | None":
    """Best-effort IANA name of the MACHINE clock. launchd fires
    StartCalendarInterval in machine-local time, so a briefing schedule stamped
    as Captain-local only fires at the right wall-clock hour when the two agree.
    Resolves the ``/etc/localtime`` symlink (…/zoneinfo/Europe/Berlin); returns
    None when it can't be read (never raises — this is a warning aid)."""
    try:
        lt = Path("/etc/localtime")
        if lt.is_symlink():
            target = os.readlink(lt)
            marker = "zoneinfo/"
            if marker in target:
                return target.split(marker, 1)[1]
    except Exception:  # noqa: BLE001 — best-effort; never break a render
        return None
    return None


def _machine_tz_mismatch_warn(captain_tz: "str | None", host_tz: "str | None") -> str:
    """The loud line when launchd's machine-local firing would desync the
    Captain-local briefing slots, else "". Compares the two zones' CURRENT UTC
    offset (not just the IANA name), so operationally-identical pairs like
    Europe/Copenhagen and Europe/Berlin (both CET/CEST — the live box's real
    pairing) do NOT false-alarm; only a genuine wall-clock divergence (e.g. a
    UTC machine clock vs a Berlin Captain on a clean-room hatch) warns. Pure
    inputs (both zone names injected) so the branch logic is unit-testable."""
    if not captain_tz or not host_tz or captain_tz == host_tz:
        return ""
    try:
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        now = datetime.now(timezone.utc)
        if now.astimezone(ZoneInfo(host_tz)).utcoffset() == \
                now.astimezone(ZoneInfo(captain_tz)).utcoffset():
            return ""   # same wall clock now (e.g. Copenhagen == Berlin)
    except Exception:  # noqa: BLE001 — can't prove equivalence → warn conservatively
        pass
    return (f"generate-plists: WARNING machine timezone {host_tz!r} != Captain "
            f"timezone {captain_tz!r} — launchd fires briefings in "
            f"machine-local time, so slots stamped Captain-local {captain_tz!r} "
            f"will fire at the wrong wall-clock hour. Set the Mac's timezone "
            f"to {captain_tz!r} (see cabinet/docs/mac-mini-deploy-runbook.md).")


def _framework_captain_tz() -> "str | None":
    """THE resolver's Captain-tz NAME, imported from this script's own code
    checkout (``parents[2]``); None on any import/resolve trouble (the
    machine-tz warning is best-effort and must never break a render)."""
    code_root = Path(__file__).resolve().parents[2]
    try:
        sys.path.insert(0, str(code_root))
        try:
            from framework.env import captain_timezone
            return captain_timezone()
        finally:
            try:
                sys.path.remove(str(code_root))
            except ValueError:
                pass
    except Exception:  # noqa: BLE001 — resolver trouble must not kill rendering
        return None


def _schedule_keys(svc):
    """Normalize the manifest schedule into plist key/value pairs."""
    sched = svc.get("schedule")
    if sched == "keepalive":
        return {"KeepAlive": True, "ThrottleInterval": 30, "RunAtLoad": True}
    if isinstance(sched, dict) and "interval_s" in sched:
        iv = int(sched["interval_s"])
        return {"StartInterval": iv, "RunAtLoad": True}
    if isinstance(sched, dict) and "calendar" in sched:
        cal = []
        for entry in sched["calendar"]:
            e = {}
            if "hour" in entry:
                e["Hour"] = int(entry["hour"])
            if "minute" in entry:
                e["Minute"] = int(entry["minute"])
            if "weekday" in entry:  # 0=Sunday..6=Saturday (launchd convention; 7 also Sunday)
                e["Weekday"] = int(entry["weekday"])
            if "day" in entry:      # 1-31 day-of-month → MONTHLY row (launchd Day;
                # lane-supply 2026-07-05 for fidelity-f1 — the watchdog gives
                # `day`-carrying rows a 33-day floor, registry._floor_for_entry)
                e["Day"] = int(entry["day"])
            if not e:
                raise ValueError(f"{svc['name']}: empty calendar entry")
            cal.append(e)
        return {"StartCalendarInterval": cal, "RunAtLoad": True}
    raise ValueError(f"{svc['name']}: unsupported schedule {sched!r}")


def render(svc, root: Path, home: Path) -> dict:
    name = svc["name"]
    if not LABEL_RE.match(str(svc.get("label",""))):
        raise SystemExit(f"generate-plists: invalid label for service {name!r} (must match ^[a-z0-9.-]+$)")
    if not NAME_RE.match(name):
        raise ValueError(f"invalid service name {name!r} (want ^[a-z0-9-]+$)")
    command = svc["command"]
    if not isinstance(command, str) or not command.strip():
        raise ValueError(f"{name}: command must be a non-empty string")
    wrapper = (
        # #51: a missing/malformed cabinet/.env must NOT abort the service.
        # `;` (not `&&`) so the watchdog/doctor/monitors still boot and can
        # REPORT the fault instead of dying silently before exec (the
        # secret-needing services self-check — healthchecks-drill already
        # guards on missing keys). The `[ -r cabinet/.env ]` guard skips a
        # source that would error on an absent/locked file; the `2>/dev/null`
        # swallows a malformed file's noise. `cd` failure still ABORTS.
        f"cd {root} || exit 1; set -a; [ -r cabinet/.env ] && source cabinet/.env 2>/dev/null; set +a"
        # Native-installer `claude` lives at ~/.local/bin; launchd does not
        # expand $HOME and the baked EnvironmentVariables.PATH (PATH_ENV) stays
        # a captain-agnostic absolute literal (cross-pinned to the dependency-
        # radar registry). Prepend the per-user ~/.local/bin HERE, where bash
        # expands $HOME at officer-boot time, so officers can find `claude`
        # without drifting the radar's absolute service-PATH pin (#60).
        f'; export PATH="$HOME/.local/bin:$PATH"'
        f"; REDIS_HOST=localhost exec {command}"
    )
    env = {"PATH": PATH_ENV}
    for k, v in (svc.get("env") or {}).items():
        env[str(k)] = str(v)
    log_dir = home / "Library" / "Logs" / "cabinet"
    pl = {
        "Label": svc["label"],
        "ProgramArguments": ["/bin/bash", "-lc", wrapper],
        "WorkingDirectory": str(root),
        "EnvironmentVariables": env,
        "StandardOutPath": str(log_dir / f"{name}.log"),
        "StandardErrorPath": str(log_dir / f"{name}.err"),
    }
    pl.update(_schedule_keys(svc))
    return pl


def lint(path: Path) -> bool:
    # plutil is macOS-only; on Linux (CI runners, clean-room hatches) it is
    # absent — treat "no linter available" as a pass so plist generation stays
    # portable. The install path (deploy-mac.sh) runs on macOS where plutil
    # exists and the lint is real.
    if shutil.which("plutil") is None:
        return True
    r = subprocess.run(["plutil", "-lint", str(path)], capture_output=True, text=True)
    return r.returncode == 0


def _installed_facts(path: Path):
    """Parse an installed plist; degrade to regex on invalid XML (never crash)."""
    try:
        with open(path, "rb") as f:
            d = plistlib.load(f)
        args = " ".join(d.get("ProgramArguments", []))
        return {
            "parse": "plistlib",
            "args": args,
            "start_interval": d.get("StartInterval"),
            "keepalive": bool(d.get("KeepAlive")),
            "calendar": d.get("StartCalendarInterval"),
        }
    except Exception:
        txt = path.read_text(errors="replace")
        m = re.search(r"StartInterval</key>\s*<integer>(\d+)</integer>", txt)
        cal = re.findall(r"<key>(Hour|Minute)</key>\s*<integer>(\d+)</integer>", txt)
        return {
            "parse": "regex-fallback",
            "args": txt,
            "start_interval": int(m.group(1)) if m else None,
            "keepalive": "<key>KeepAlive</key>" in txt,
            "calendar": cal or None,
        }


def _cmd_token(command: str) -> str:
    """The most identifying token of a command: first path-ish token, else the
    module name of a `python -m` invocation, else the last token."""
    parts = command.split()
    if "-m" in parts:
        return parts[parts.index("-m") + 1]
    for p in parts:
        if "/" in p:
            return p
    return parts[-1]


def check(svc, generated: dict, la_dir: Path):
    label = svc["label"]
    installed = la_dir / f"{label}.plist"
    if not installed.exists():
        return ("MISSING", "not installed")
    facts = _installed_facts(installed)
    problems = []
    token = _cmd_token(svc["command"])
    if token not in facts["args"]:
        problems.append(f"command token '{token}' not in installed args")
    sched = svc.get("schedule")
    if sched == "keepalive" and not facts["keepalive"]:
        problems.append("installed lacks KeepAlive")
    if isinstance(sched, dict) and "interval_s" in sched:
        if facts["start_interval"] != int(sched["interval_s"]):
            problems.append(
                f"interval {facts['start_interval']} != manifest {sched['interval_s']}"
            )
    if isinstance(sched, dict) and "calendar" in sched:
        if not facts["calendar"]:
            problems.append("installed lacks StartCalendarInterval")
    status = "MATCH" if not problems else "DRIFT"
    note = "; ".join(problems) if problems else facts["parse"]
    return (status, note)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="diff generated vs installed LaunchAgents")
    ap.add_argument("--output-dir", default=None)
    args = ap.parse_args()

    root = repo_root()
    home = Path.home()
    canonical_out_dir = root / "cabinet" / "launchd" / "generated"
    out_dir = Path(args.output_dir) if args.output_dir else canonical_out_dir
    launch_agents_dir = home / "Library" / "LaunchAgents"
    if out_dir.resolve() == launch_agents_dir.resolve():
        raise SystemExit(
            "generate-plists: refusing --output-dir ~/Library/LaunchAgents — "
            "render to cabinet/launchd/generated and install with deploy-mac.sh"
        )
    services = load_services(root)
    validate_services(services)
    briefing_note = stamp_briefing_schedule(services)
    if briefing_note:
        print(briefing_note)
    # launchd fires the stamped calendar in the MACHINE's tz, but briefing_times
    # is Captain-local — warn loudly (never fail) when they differ so a
    # UTC-clocked hatch with a Berlin Captain doesn't fire briefings 2h off.
    tz_warn = _machine_tz_mismatch_warn(_framework_captain_tz(), _host_iana_tz())
    if tz_warn:
        print(tz_warn, file=sys.stderr)
    # STRICT kind gate (lane-ops 2026-07-04): daemon/watchdog/cron render;
    # officer is deploy-mac.sh's; anything ELSE is a manifest typo and must
    # fail LOUDLY — the old `in ("daemon","watchdog")` filter silently dropped
    # the `kind: cron` retro-trigger row, which is how its hand-made plist
    # missed the PATH env and FATAL'd hourly under launchd's minimal PATH.
    RENDERED_KINDS = ("daemon", "watchdog", "cron")
    disabled = [s["name"] for s in services
                if s.get("kind") in RENDERED_KINDS and s.get("disabled")]
    if disabled:
        print(f"disabled (manifest-parked, not rendered): {', '.join(disabled)}")
    daemons = [s for s in services
               if s.get("kind") in RENDERED_KINDS and not s.get("disabled")]
    skipped = [s["name"] for s in services if s.get("kind") == "officer"]
    if skipped:
        print(f"officers (deploy-mac.sh template path owns these): {', '.join(skipped)}")

    out_dir.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    expected_names = {f"{svc['label']}.plist" for svc in daemons}

    # Render and lint the complete fleet in a sibling staging directory. Only
    # after every plist passes do we publish it and prune stale generated
    # outputs. A broken manifest can therefore never leave a partial fleet that
    # looks deployable.
    with tempfile.TemporaryDirectory(prefix=".generate-plists-", dir=out_dir.parent) as tmp:
        staged = Path(tmp)
        rendered = []
        for svc in daemons:
            pl = render(svc, root, home)
            dest = staged / f"{svc['label']}.plist"
            with open(dest, "wb") as f:
                plistlib.dump(pl, f)
            if not lint(dest):
                raise SystemExit(f"generate-plists: plutil lint failed: {dest.name}")
            rendered.append((svc, pl, dest))

        out_dir.mkdir(parents=True, exist_ok=True)
        for svc, pl, staged_path in rendered:
            dest = out_dir / staged_path.name
            staged_path.replace(dest)
            line = f"rendered {dest.name}  lint=OK"
            if args.check:
                status, note = check(svc, pl, home / "Library" / "LaunchAgents")
                line += f"  check={status} ({note})"
                rows.append((svc["name"], status, note))
            print(line)

        # Stale pruning belongs only to this script's canonical generated
        # directory. A custom output may be a fixture or operator-owned staging
        # area; never delete Cabinet plists there.
        if out_dir.resolve() == canonical_out_dir.resolve():
            for stale in sorted(out_dir.glob("com.cabinet.*.plist")):
                if stale.name not in expected_names:
                    stale.unlink()
                    print(f"pruned stale generated plist: {stale.name}")
        elif args.output_dir:
            print("custom output dir: stale-prune skipped")

    if args.check and rows:
        drift = [r for r in rows if r[1] != "MATCH"]
        print(f"\n--check summary: {len(rows) - len(drift)}/{len(rows)} MATCH"
              + (f"; drift/missing: {[r[0] for r in drift]}" if drift else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
