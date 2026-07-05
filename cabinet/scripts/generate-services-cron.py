#!/usr/bin/env python3
"""generate-services-cron.py — render crontab lines for the cabinet fleet from
cabinet/services.yml (AX-4, axes spec 2026-07-05 §3).

ONE manifest, TWO renderers: generate-plists.py renders launchd plists for the
macbook/mac_mini targets; THIS script renders the same daemon/watchdog/cron
rows as a crontab for the docker target (scheduler = container init + cron).
The manifest stays the single fleet truth — a row is never described twice.

Row selection:
  - `platform:` per row — darwin | linux | any, DEFAULT darwin. Only
    linux/any rows render here (a macOS-only row must not thrash inside a
    container); generate-plists.py keeps rendering everything as today. A row
    OPTS IN to container scheduling by declaring `platform: linux` or
    `platform: any` once it is verified container-safe. An unknown platform
    value is a HARD ERROR — same no-silent-skip lesson as unknown kinds.
  - kind: officer rows are skipped with a notice (officers are session
    processes, owned by the container init / start scripts, never cron).
  - `disabled: true` rows are skipped with a notice (manifest-parked truth).
  - `schedule: keepalive` rows cannot be expressed in cron: they are emitted
    as a comment block naming the container init's responsibility.

Schedule translation (fail LOUDLY on anything cron cannot express —
generate-plists.py's silent-skip lesson, lane-ops 2026-07-04):
  - {interval_s: N}   → whole minutes: `*/M * * * *`; whole hours:
                        `0 */H * * *` (`0 * * * *` hourly, `0 0 * * *` daily);
                        anything else (sub-minute, ragged, >daily) hard-errors.
  - {calendar: [...]} → one 5-field line per entry; absent keys stay
                        wildcards (launchd semantics, faithfully); launchd
                        weekday 7 normalizes to cron 0 (both Sunday).

Security contract (Corridor-reviewed, binding — mirrors generate-plists.py):
  - service names validated ^[a-z0-9-]+$ BEFORE any path use (the name forms
    the per-service log filename — a malformed manifest cannot traverse);
  - no shell=True anywhere; git rev-parse runs via an argument list;
  - this script NEVER installs the crontab — rendering only; installation is
    a separate deliberate step (the docker preset's CMD, or `crontab <file>`);
  - no secret VALUES are rendered: lines source cabinet/.env at RUN time
    (same wrapper contract as the plists) plus declared per-service env.

Each rendered line (SHELL=/bin/bash, PATH pinned in the header — the
launchd-minimal-PATH FATAL lesson applies verbatim to cron):
  cd <root> && { set -a; . cabinet/.env 2>/dev/null; set +a; \
    [env] REDIS_HOST=<host> <command>; } >> <log-dir>/<name>.log 2>&1
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

NAME_RE = re.compile(r"^[a-z0-9-]+$")
PATH_ENV = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
RENDERED_KINDS = ("daemon", "watchdog", "cron")
PLATFORMS = ("darwin", "linux", "any")


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


def _int_field(svc, entry, key, lo, hi):
    v = int(entry[key])
    if not lo <= v <= hi:
        raise ValueError(f"{svc['name']}: calendar {key}={v} outside {lo}..{hi}")
    return v


def cron_times(svc):
    """Manifest schedule → list of 5-field cron time specs (no command).
    keepalive returns [] — the container init owns those rows (see main)."""
    sched = svc.get("schedule")
    name = svc["name"]
    if sched == "keepalive":
        return []
    if isinstance(sched, dict) and "interval_s" in sched:
        iv = int(sched["interval_s"])
        if iv <= 0 or iv % 60:
            raise ValueError(
                f"{name}: interval_s={iv} is not cron-expressible (whole "
                f"minutes only) — keep the row platform: darwin or loop it "
                f"under the container init")
        m = iv // 60
        if m < 60:
            return [f"*/{m} * * * *"]
        if m % 60:
            raise ValueError(
                f"{name}: interval_s={iv} is not cron-expressible "
                f"(above 59min it must be whole hours)")
        h = m // 60
        if h == 1:
            return ["0 * * * *"]
        if h < 24:
            return [f"0 */{h} * * *"]
        if h == 24:
            return ["0 0 * * *"]
        raise ValueError(
            f"{name}: interval_s={iv} exceeds daily — express it as a "
            f"calendar schedule instead")
    if isinstance(sched, dict) and "calendar" in sched:
        out = []
        for entry in sched["calendar"]:
            if not any(k in entry for k in ("minute", "hour", "day", "weekday")):
                raise ValueError(f"{name}: empty calendar entry")
            minute = str(_int_field(svc, entry, "minute", 0, 59)) \
                if "minute" in entry else "*"
            hour = str(_int_field(svc, entry, "hour", 0, 23)) \
                if "hour" in entry else "*"
            dom = str(_int_field(svc, entry, "day", 1, 31)) \
                if "day" in entry else "*"
            # launchd weekday 0..6 Sun..Sat, 7 also Sunday; cron 0=Sunday.
            dow = str(_int_field(svc, entry, "weekday", 0, 7) % 7) \
                if "weekday" in entry else "*"
            out.append(f"{minute} {hour} {dom} * {dow}")
        return out
    raise ValueError(f"{name}: unsupported schedule {sched!r}")


def cron_command(svc, root: str, redis_host: str, log_dir: str) -> str:
    """The run-time half of a line — same contract as the plist wrapper:
    cd must SUCCEED (the brace group never runs from a wrong cwd), cabinet/
    .env is sourced at run time (secrets never rendered), declared per-service
    env rides inline, stdout+stderr land in the per-service log."""
    name = svc["name"]
    command = svc.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError(f"{name}: command must be a non-empty string")
    env_pairs = ["REDIS_HOST=" + redis_host]
    for k, v in (svc.get("env") or {}).items():
        env_pairs.append(f"{k}={v}")
    return (
        f"cd {root} && {{ set -a; . cabinet/.env 2>/dev/null; set +a; "
        f"{' '.join(env_pairs)} {command.strip()}; }} "
        f">> {log_dir}/{name}.log 2>&1"
    )


def render(services, root: str, redis_host: str, log_dir: str):
    """→ (crontab_text, stats dict). Validates the WHOLE manifest before
    rendering a single line (a typo'd row must fail the render, not vanish)."""
    unknown = [s.get("name") for s in services
               if s.get("kind") not in RENDERED_KINDS + ("officer",)]
    if unknown:
        raise SystemExit(
            f"generate-services-cron: unknown kind on service(s) {unknown} — "
            f"valid kinds: officer|{'|'.join(RENDERED_KINDS)}")
    bad_names = [s.get("name") for s in services
                 if not NAME_RE.match(str(s.get("name", "")))]
    if bad_names:
        raise SystemExit(
            f"generate-services-cron: invalid service name(s) {bad_names} "
            f"(want ^[a-z0-9-]+$)")
    bad_platform = [s["name"] for s in services
                    if s.get("platform", "darwin") not in PLATFORMS]
    if bad_platform:
        raise SystemExit(
            f"generate-services-cron: unknown platform on service(s) "
            f"{bad_platform} — valid: {'|'.join(PLATFORMS)} (default darwin)")

    stats = {"rendered": [], "keepalive": [], "darwin_only": [],
             "officers": [], "disabled": []}
    lines = []
    keepalive = []
    for svc in services:
        if svc.get("kind") == "officer":
            stats["officers"].append(svc["name"])
            continue
        if svc.get("disabled"):
            stats["disabled"].append(svc["name"])
            continue
        if svc.get("platform", "darwin") == "darwin":
            stats["darwin_only"].append(svc["name"])
            continue
        times = cron_times(svc)
        if not times:  # keepalive
            stats["keepalive"].append(svc["name"])
            keepalive.append(f"#   {svc['name']}: {svc['command'].strip()}")
            continue
        cmd = cron_command(svc, root, redis_host, log_dir)
        for t in times:
            lines.append(f"{t} {cmd}")
        stats["rendered"].append(svc["name"])

    out = [
        "# generated by cabinet/scripts/generate-services-cron.py — DO NOT EDIT",
        "# one manifest, two renderers (axes spec §3): launchd plists via",
        "# generate-plists.py for macbook/mac_mini; THIS crontab for docker.",
        "# source manifest: cabinet/services.yml",
        "SHELL=/bin/bash",
        f"PATH={PATH_ENV}",
        'MAILTO=""',
        "",
    ]
    if lines:
        out.extend(lines)
    else:
        out.append("# no container-schedulable rows yet: every manifest row is")
        out.append("# platform: darwin (the default) — a row opts in with")
        out.append("# `platform: linux` or `platform: any` once container-safe.")
    if keepalive:
        out.append("")
        out.append("# keepalive rows (container init owns these — cron cannot"
                   " supervise):")
        out.extend(keepalive)
    return "\n".join(out) + "\n", stats


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None,
                    help="path rendered into every line's cd (default: the "
                         "manifest's repo root; the docker preset passes "
                         "/opt/cabinet)")
    ap.add_argument("--redis-host", default="localhost",
                    help="REDIS_HOST rendered into every line (the docker "
                         "preset passes the redis sidecar's hostname)")
    ap.add_argument("--log-dir", default="/var/log/cabinet")
    ap.add_argument("--output", default=None,
                    help="write the crontab here instead of stdout")
    args = ap.parse_args()

    repo = repo_root()
    services = load_services(repo)
    text, stats = render(services, args.root or str(repo),
                         args.redis_host, args.log_dir)

    if args.output:
        Path(args.output).write_text(text)
    else:
        sys.stdout.write(text)
    print(
        f"rendered={len(stats['rendered'])} keepalive={len(stats['keepalive'])}"
        f" darwin-only-skipped={len(stats['darwin_only'])}"
        f" officers-skipped={len(stats['officers'])}"
        f" disabled={len(stats['disabled'])}",
        file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
