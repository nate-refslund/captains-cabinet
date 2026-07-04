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
  (default)  render all daemon/watchdog services to cabinet/launchd/generated/
             and plutil -lint each output.
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
import subprocess
import sys
from pathlib import Path

import yaml

NAME_RE = re.compile(r"^[a-z0-9-]+$")
LABEL_RE = re.compile(r"^[a-z0-9.-]+$")  # L-1 (cp1 review): label forms the output filename
PATH_ENV = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


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
    return data["services"]


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
        f"cd {root} && set -a && source cabinet/.env 2>/dev/null && set +a"
        f" && REDIS_HOST=localhost exec {command}"
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
    out_dir = Path(args.output_dir) if args.output_dir else root / "cabinet" / "launchd" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)

    services = load_services(root)
    # STRICT kind gate (lane-ops 2026-07-04): daemon/watchdog/cron render;
    # officer is deploy-mac.sh's; anything ELSE is a manifest typo and must
    # fail LOUDLY — the old `in ("daemon","watchdog")` filter silently dropped
    # the `kind: cron` retro-trigger row, which is how its hand-made plist
    # missed the PATH env and FATAL'd hourly under launchd's minimal PATH.
    RENDERED_KINDS = ("daemon", "watchdog", "cron")
    unknown = [s["name"] for s in services
               if s.get("kind") not in RENDERED_KINDS + ("officer",)]
    if unknown:
        raise SystemExit(
            f"generate-plists: unknown kind on service(s) {unknown} — "
            f"valid kinds: officer|{'|'.join(RENDERED_KINDS)} (unknown kinds "
            f"hard-error so a row can never be silently un-rendered again)")
    disabled = [s["name"] for s in services
                if s.get("kind") in RENDERED_KINDS and s.get("disabled")]
    if disabled:
        print(f"disabled (manifest-parked, not rendered): {', '.join(disabled)}")
    daemons = [s for s in services
               if s.get("kind") in RENDERED_KINDS and not s.get("disabled")]
    skipped = [s["name"] for s in services if s.get("kind") == "officer"]
    if skipped:
        print(f"officers (deploy-mac.sh template path owns these): {', '.join(skipped)}")

    failures = 0
    rows = []
    for svc in daemons:
        pl = render(svc, root, home)
        dest = out_dir / f"{svc['label']}.plist"
        with open(dest, "wb") as f:
            plistlib.dump(pl, f)
        ok = lint(dest)
        if not ok:
            failures += 1
        line = f"rendered {dest.name}  lint={'OK' if ok else 'FAIL'}"
        if args.check:
            status, note = check(svc, pl, home / "Library" / "LaunchAgents")
            line += f"  check={status} ({note})"
            rows.append((svc["name"], status, note))
        print(line)

    if args.check and rows:
        drift = [r for r in rows if r[1] != "MATCH"]
        print(f"\n--check summary: {len(rows) - len(drift)}/{len(rows)} MATCH"
              + (f"; drift/missing: {[r[0] for r in drift]}" if drift else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
