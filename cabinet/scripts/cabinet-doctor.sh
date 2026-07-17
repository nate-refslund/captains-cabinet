#!/bin/bash
# cabinet-doctor.sh — deterministic config-liveness prober for the whole fleet
# (Claude Code audit 2026-07-07 follow-on; the audit found a CLASS of silently-
# dead config — dead MCP servers, unwired hooks, an unparseable skill, a bare-
# bash statusline — that nothing probed. This script IS that prober.)
#
# WHAT IT CHECKS (all read-only; the only writes are its own log lines on
# stdout and one Redis heartbeat key at the end):
#   1. exact launchd fleet: every enabled cabinet/services.yml row + roster
#      officer ↔ launchd job loaded ↔ fresh log, and no unexpected Cabinet
#      job/plist is present (the separately managed egress proxy is allowed);
#      (freshness window derived from the row's schedule; log paths read from
#      the INSTALLED plist's StandardOutPath/StandardErrorPath — the fleet has
#      two log-name conventions, the installed plist is the truth);
#      officer rows additionally require their tmux session.
#   2. every .claude/settings.json hook entry → the referenced script EXISTS.
#   3. every server in the active MCP base (.mcp.json.mac-native else
#      .mcp.json) + instance/config/extra-mcps.json env-RESOLVES: each ${VAR}
#      without a :-default must be launcher-provided, named in cabinet/.env,
#      or set in the environment. VARIABLE NAMES ONLY — values are never read
#      into this script and never printed.
#   4. every .claude/skills/*/SKILL.md frontmatter parses (and the file STARTS
#      with the `---` fence — no leading bytes; a past skill-registration
#      regression traced to exactly this).
#   5. every cabinet/mcp-scope.yml grant (agents + universal) is registered in
#      some config layer (repo MCP layers, ~/.claude.json user servers,
#      enabled-plugin basenames). claude.ai profile connectors that cannot be
#      probed from disk print UNVERIFIABLE (warn, not dead).
#   6. statusline (cabinet/scripts/statusline.sh) exits 0 on a minimal payload.
#   7. Redis reachable (PING).
#   8. killswitch DRY-check: `kill-switch.sh status` must run; ACTIVE is
#      surfaced as a loud WARN (a deliberate Captain state, not dead config).
#      This script NEVER activates/deactivates anything and never calls
#      launchctl bootstrap/bootout — probe-only, per the generate-plists.py
#      security contract.
#   9. world read-model liveness (Cabinet World E0a/E0b, 2026-07-07):
#      (a) when the world-census manifest row is enabled, the newest keyframe
#      date in shared/interfaces/world-chronicle.jsonl must be ≤2 days old —
#      a dead census writer accrues PERMANENT replay fog (the file-count
#      surfaces have no ledger to backfill from); (b) when the
#      world-chronicle row is enabled, cabinet:world:chronicle:heartbeat must
#      exist (the daemon SETs it EX 900 every tick — absence = daemon dead,
#      distinct from launchd thinking the job is loaded).
#  10. germline exists-without-schg watchdog (G7): every path in
#      germline-lock.sh's FILES/DIRS locked set (parsed out of the arrays —
#      never hardcoded) that EXISTS on disk must carry the schg flag; dirs
#      are verified RECURSIVELY because that is what lock does (chflags -R).
#      Exists-without-schg = boundary gap (DEAD); absent = legal (SKIP —
#      lock itself skips absent paths). Read-only: stat/find only, never
#      chflags, never sudo.
#  11. retrieval-eval nightly verdict (refinement gate, 2026-07-15): latest
#      line of cabinet/logs/retrieval-eval-history.jsonl via
#      retrieval-eval-nightly.sh --probe (pure file+env inspection — no DB,
#      no network). Floor breach or >48h-stale verdict = WARN/AMBER (quality
#      regression ≠ dead config — the services section already DEADs an
#      unloaded row); credless box (clean-room/CI) = SKIP; staleness honors
#      the post-wake grace below, one severity rung lower than stale_verdict.
#  12. evidence-plane health (Evidence program Phase 2 Batch A, 2026-07-17):
#      freshness (newest trial ledger/anchor mtime vs 48h), growth (store
#      size vs the measured ceiling + today's day-bounded trials vs 80% of
#      the per-trial event cap), chain continuity (read-only verifier
#      spot-check of the newest trial via python3.12 -m framework.evidence),
#      and degradation markers (the telemetry-mirror ledger
#      cabinet/logs/evidence-mirror-degradations.jsonl written by
#      framework/evidence_mirror.py, probed even when the store is absent,
#      + the act-class lifecycle sidecar <store>/degradations.jsonl).
#      All probes are AMBER-max: WARN/SKIP, never DEAD, never crash (Phase-2
#      observation-only law; pinned by
#      framework/tests/test_evidence_doctor_probes.py). Absent store = clean
#      SKIP. Caveat to "all read-only": the verifier may advance its own
#      signed anti-rollback watermark sidecar on a clean spot-check —
#      protective and best-effort by design; evidence bytes are never
#      written. Ceilings: docs/runbooks/evidence-recorder-v1.md
#      ("Measured envelope", cabinet/scripts/evidence-bench.py).
#  13. task-sync drift falsifier verdict (adapter kit, 2026-07-17): latest
#      line of cabinet/logs/task-sync-drift.jsonl via the falsifier's
#      --probe (pure file inspection — no DB, no network, no adapter
#      imports). Drift/stale/error = WARN/AMBER with a self-heal hint
#      (re-run one sync cycle); a breach persisting to the next nightly is
#      escalated to a captain card BY THE FALSIFIER organ, never by this
#      read-only probe. Honest no-op deployments (no adapter configured)
#      print OK — the loud-degrade line is the healthy state.
#
# OUTPUT: one line per finding (OK / WARN / WAIVED / SKIP / DEAD), then either
#   CABINET_DOCTOR GREEN (checks=N warn=N waived=N)
# or
#   CABINET_DOCTOR DEAD (n=N) + the repeated DEAD list.
# EXIT: 0 when green, 1 when anything is DEAD (launchd surfaces nonzero).
#
# HEARTBEAT: every completed run (green OR dead) stamps
#   cabinet:doctor:heartbeat = "<iso8601> GREEN|DEAD:<n>"
# so the outcome-watchdog / dead-man can distinguish "doctor found rot" from
# "doctor itself is dead" (heartbeat stale = the doctor is the dead one).
#
# WAIVERS: known, Captain-gated findings the fleet has already filed (germline
# amendments pending an unlock window) print WAIVED and do not fail the run —
# otherwise the doctor would page daily on a finding that deliberately waits
# on the Captain. Each waiver cites its amendment doc. Remove the waiver in
# the same change that lands the amendment (Docs-Must-Track-Code).
#
# Scheduled daily via cabinet/services.yml (`cabinet-doctor` row). Also the
# final acceptance gate of the Mini hatch runbook
# (docs/runbooks/mini-hatch-tonight-2026-07-07.md §Flight recorder).

set -u

REPO_ROOT="${CABINET_SOURCE_REPO:-${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}}"
cd "$REPO_ROOT" || { echo "CABINET_DOCTOR DEAD (n=1)"; echo "DEAD doctor self — cannot cd $REPO_ROOT"; exit 1; }

PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
command -v "$PY" >/dev/null 2>&1 || PY=python3
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
[ "$REDIS_HOST" = "redis" ] && REDIS_HOST=127.0.0.1   # docker-legacy residue guard
REDIS_PORT="${REDIS_PORT:-6379}"
# (launchd plists are read via the embedded Python's own ~/Library/LaunchAgents
# expansion in section 1 — no shell-level copy of that path is needed here)

DEAD=()
N_OK=0; N_WARN=0; N_WAIVED=0; N_SKIP=0

ok()     { echo "OK     $1"; N_OK=$((N_OK+1)); }
warn()   { echo "WARN   $1"; N_WARN=$((N_WARN+1)); }
waived() { echo "WAIVED $1"; N_WAIVED=$((N_WAIVED+1)); }
skip()   { echo "SKIP   $1"; N_SKIP=$((N_SKIP+1)); }
dead()   { echo "DEAD   $1"; DEAD+=("$1"); }

# ---- sleep-aware wake grace -------------------------------------------------
# Log-mtime and redis-TTL staleness windows keep counting through macOS sleep,
# so the first post-wake run called provably-live services DEAD (false DEAD
# n=8 every post-sleep morning; world-chronicle declared dead while its PID
# wrote records 1s later — 2026-07-11 recon). Inside WAKE_GRACE_S of the last
# wake, STALENESS-class verdicts downgrade to WARN; loaded/parse/path checks
# are unaffected. Fresh-hatch acceptance runs are unaffected too: their logs
# are fresh, so they take the OK path, not this one.
WAKE_GRACE_S="${CABINET_DOCTOR_WAKE_GRACE_S:-1800}"
SECS_SINCE_WAKE="$(sysctl -n kern.waketime 2>/dev/null | awk -v now="$(date +%s)" \
  '{ for (i=1; i<=NF; i++) if ($i == "sec") { v=$(i+2); gsub(/[^0-9]/, "", v); if (v != "") print now - v; exit } }')"
case "$SECS_SINCE_WAKE" in ''|*[!0-9]*) SECS_SINCE_WAKE=999999 ;; esac
stale_verdict() { # staleness-class finding: DEAD normally, WARN in wake grace
  if [ "$SECS_SINCE_WAKE" -lt "$WAKE_GRACE_S" ]; then
    warn "$1 (post-wake grace: woke ${SECS_SINCE_WAKE}s ago < ${WAKE_GRACE_S}s)"
  else
    dead "$1"
  fi
}

# ---- known Captain-gated waivers (cite the pending amendment) --------------
# scope grant `cabinet`: universally granted but registered in no config layer
# — filed as finding #3b in
# docs/proposals/germline-addendum-claude-code-audit-2026-07-07.md (descope
# proposed; mcp-scope.yml is schg-locked). Waived until the unlock window.
WAIVED_SCOPE_GRANTS=" cabinet "
# claude.ai profile connectors: registration lives server-side on the
# Captain's claude.ai profile; not probeable from disk.
PROFILE_CONNECTORS=" claude-in-chrome monday "

echo "[cabinet-doctor] $(date -u +%Y-%m-%dT%H:%M:%SZ) repo=$REPO_ROOT"

# ============================================================
# 1. services.yml ↔ launchd ↔ fresh log
# ============================================================
LAUNCHCTL_SNAPSHOT="$(launchctl list 2>/dev/null | awk '$3 ~ /^com\.cabinet\./ {print $1"\t"$3}')"

SVC_TSV="$("$PY" - <<'PYEOF'
import sys, yaml, time, os, plistlib, re
from pathlib import Path
root = os.getcwd()
data = yaml.safe_load(open("cabinet/services.yml"))
# Product/captain-agnostic foundation (2026-07-14): officer rows are no
# longer hardcoded in services.yml -- merge them in from the roster so the
# tmux-session liveness coverage below (kind == "officer") stays unchanged.
# Absent/empty roster.yml (fresh clone) means nothing to merge, same as
# before this file had any officers to check.
sys.path.insert(0, os.path.join(root, "cabinet", "scripts"))
import lib_roster
services = list(data["services"]) + lib_roster.officer_service_rows(Path(root))
now = time.time()
la = os.path.expanduser("~/Library/LaunchAgents")
for s in services:
    name, label, kind = s["name"], s["label"], s.get("kind", "daemon")
    if s.get("disabled"):
        print(f"{name}\t{label}\t{kind}\tdisabled\t-\t-")
        continue
    sched = s.get("schedule")
    if sched == "keepalive":
        stype, window = "keepalive", 0
    elif isinstance(sched, dict) and "interval_s" in sched:
        stype, window = "interval", max(3 * int(sched["interval_s"]), 7200)
    elif isinstance(sched, dict) and "calendar" in sched:
        entries = sched["calendar"]
        if any("day" in e for e in entries):       window = 33 * 86400   # monthly (registry floor)
        elif any("weekday" in e for e in entries): window = 8 * 86400    # weekly
        elif any("hour" in e for e in entries):    window = 26 * 3600    # daily (registry default)
        else:                                       window = 3 * 3600    # minute-only ≈ hourly
        stype = "calendar"
    else:
        stype, window = "unknown", 0
    # log freshness from the INSTALLED plist (two log-name conventions live)
    age = "-"
    plist_path = os.path.join(la, label + ".plist")
    logpaths = []
    if os.path.exists(plist_path):
        try:
            with open(plist_path, "rb") as f:
                d = plistlib.load(f)
            logpaths = [p for p in (d.get("StandardOutPath"), d.get("StandardErrorPath")) if p]
        except Exception:
            txt = open(plist_path, errors="replace").read()
            logpaths = re.findall(r"Standard(?:Out|Error)Path</key>\s*<string>([^<]+)</string>", txt)
    newest = None
    for p in logpaths:
        p = os.path.expanduser(p)
        try:
            m = os.path.getmtime(p)
            newest = m if newest is None else max(newest, m)
        except OSError:
            pass
    if newest is not None:
        age = str(int(now - newest))
    installed = "yes" if os.path.exists(plist_path) else "no"
    print(f"{name}\t{label}\t{kind}\t{stype}:{window}\t{age}\t{installed}")
PYEOF
)" || { dead "services — could not parse cabinet/services.yml (pyyaml under $PY)"; SVC_TSV=""; }

while IFS=$'\t' read -r name label kind sched age installed; do
  [ -z "${name:-}" ] && continue
  if [ "$sched" = "disabled" ]; then skip "service $name — disabled in manifest"; continue; fi
  pid="$(printf '%s\n' "$LAUNCHCTL_SNAPSHOT" | awk -F'\t' -v l="$label" '$2==l {print $1}')"
  if [ -z "$pid" ]; then
    dead "service $name — launchd job $label not loaded"
    continue
  fi
  stype="${sched%%:*}"; window="${sched##*:}"
  if [ "$stype" = "keepalive" ]; then
    if [ "$pid" = "-" ]; then
      dead "service $name — keepalive job $label loaded but not running"
      continue
    fi
    if [ "$kind" = "officer" ]; then
      if tmux has-session -t "=$name" 2>/dev/null; then
        ok "service $name — running (pid $pid) + tmux session"
      else
        dead "service $name — running (pid $pid) but tmux session '$name' missing"
      fi
    else
      ok "service $name — running (pid $pid)"
    fi
  else
    if [ "$age" = "-" ]; then
      dead "service $name — no log file found (installed plist=$installed; StandardOut/ErrorPath missing or never written)"
    elif [ "$age" -gt "$window" ]; then
      stale_verdict "service $name — log stale ${age}s > window ${window}s"
    else
      ok "service $name — loaded, log fresh (${age}s <= ${window}s)"
    fi
  fi
done <<< "$SVC_TSV"

# Exact-set honesty: checking every expected row is not enough — an old loaded
# mission-supervisor or disabled draft-lane can coexist with a green expected
# set and quietly restore retired authority. Treat the union of installed
# plists and loaded com.cabinet jobs as runtime truth. Egress is the sole
# out-of-manifest allowlist because egress-guard.sh independently owns it and
# a fleet deploy must preserve enforcement.
EXPECTED_FLEET_LABELS="$(printf '%s\n' "$SVC_TSV" | awk -F'\t' '$4 != "disabled" {print $2}')"
EXPECTED_FLEET_LABELS="${EXPECTED_FLEET_LABELS}"$'\n'"com.cabinet.egress-proxy"
while IFS= read -r label; do
  [ -n "$label" ] || continue
  if printf '%s\n' "$EXPECTED_FLEET_LABELS" | grep -qxF "$label"; then
    continue
  fi
  loaded="no"
  installed="no"
  printf '%s\n' "$LAUNCHCTL_SNAPSHOT" | awk -F'\t' -v l="$label" '$2==l {found=1} END {exit !found}' \
    && loaded="yes"
  [ ! -f "$HOME/Library/LaunchAgents/$label.plist" ] || installed="yes"
  dead "service-set — unexpected Cabinet launchd label $label (loaded=$loaded installed=$installed); disabled/legacy jobs must be parked"
done < <(
  {
    printf '%s\n' "$LAUNCHCTL_SNAPSHOT" | awk -F'\t' 'NF >= 2 {print $2}'
    for plist in "$HOME"/Library/LaunchAgents/com.cabinet.*.plist; do
      [ -e "$plist" ] || continue
      basename "$plist" .plist
    done
  } | sort -u
)

# ============================================================
# 2. settings hooks → executables exist   (+ statusLine block)
# ============================================================
HOOKS_OUT="$("$PY" - <<'PYEOF'
import json, os
root = os.getcwd()
d = json.load(open(".claude/settings.json"))
for event, groups in (d.get("hooks") or {}).items():
    for g in groups:
        for h in g.get("hooks", []):
            args = h.get("args") or []
            script = next((a for a in args if "/" in a or "${CLAUDE_PROJECT_DIR}" in a), None)
            if script is None:
                print(f"NOSCRIPT\t{event}\t{h.get('command','?')}")
                continue
            resolved = script.replace("${CLAUDE_PROJECT_DIR}", root)
            print(f"{'EXISTS' if os.path.isfile(resolved) else 'MISSING'}\t{event}\t{os.path.relpath(resolved, root)}")
sl = d.get("statusLine") or {}
cmdline = (sl.get("command", "") + " " + " ".join(sl.get("args") or [])).strip()
print(f"STATUSLINE\t{cmdline}")
PYEOF
)" || dead "hooks — could not parse .claude/settings.json"

while IFS=$'\t' read -r state event path; do
  case "$state" in
    EXISTS)   ok "hook $event → $path" ;;
    MISSING)  dead "hook $event → $path does not exist" ;;
    NOSCRIPT) warn "hook $event → no script path in args ($path)" ;;
    STATUSLINE)
      if printf '%s' "$event" | grep -q "statusline.sh"; then
        ok "settings statusLine → points at statusline.sh"
      else
        # audit finding #9 — germline-gated (settings.json is schg-locked)
        waived "settings statusLine is '$event' (does not reference cabinet/scripts/statusline.sh; audit #9, germline fix pending)"
      fi ;;
  esac
done <<< "$HOOKS_OUT"

# ============================================================
# 3. MCP config layers env-resolve (names only, never values)
# ============================================================
MCP_BASE=".mcp.json.mac-native"; [ -f "$MCP_BASE" ] || MCP_BASE=".mcp.json"
MCP_OUT="$("$PY" - "$MCP_BASE" <<'PYEOF'
import json, os, re, sys
layers = [sys.argv[1], "instance/config/extra-mcps.json"]
VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-[^}]*)?\}")
# launcher-provided at boot (start-officer-mac.sh / hooks env), never in .env:
launcher = {"CABINET_SOURCE_REPO", "CLAUDE_PROJECT_DIR", "OFFICER_NAME", "REDIS_URL", "CABINET_ROOT", "HOME"}
envnames = set()
try:
    for line in open("cabinet/.env"):
        m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)=", line)
        if m: envnames.add(m.group(1))   # NAMES only — value never read past '='
except OSError:
    pass
def walk(o, acc):
    if isinstance(o, dict):
        for v in o.values(): walk(v, acc)
    elif isinstance(o, list):
        for v in o: walk(v, acc)
    elif isinstance(o, str):
        for m in VAR.finditer(o):
            acc.append((m.group(1), bool(m.group(2))))
for layer in layers:
    if not os.path.exists(layer):
        continue
    servers = (json.load(open(layer)).get("mcpServers") or {})
    for name, cfg in servers.items():
        if name.startswith("_"): continue
        acc = []
        walk(cfg, acc)
        deadvars = sorted({v for v, has_default in acc
                           if not has_default and v not in launcher
                           and v not in envnames and v not in os.environ})
        print(f"{layer}\t{name}\t{'OK' if not deadvars else 'DEADVARS:' + ','.join(deadvars)}")
PYEOF
)" || dead "mcp — could not parse MCP config layers"

while IFS=$'\t' read -r layer server state; do
  [ -z "${layer:-}" ] && continue
  if [ "$state" = "OK" ]; then
    ok "mcp $server ($layer) — env resolves"
  else
    dead "mcp $server ($layer) — unresolved env: ${state#DEADVARS:} (not in cabinet/.env names, launcher set, or environment)"
  fi
done <<< "$MCP_OUT"

# ============================================================
# 4. skill frontmatter parses (incl. no leading non-frontmatter bytes)
# ============================================================
SKILLS_OUT="$("$PY" - <<'PYEOF'
import glob, yaml
for p in sorted(glob.glob(".claude/skills/*/SKILL.md")):
    try:
        raw = open(p, "rb").read()
        # THE load-bearing check (audit #7): any byte before the fence makes
        # CC register the skill with a junk description.
        if not raw.startswith(b"---\n") and not raw.startswith(b"---\r\n"):
            print(f"{p}\tDEAD\tLEADING-BYTES (file must START with the --- frontmatter fence)")
            continue
        text = raw.decode("utf-8")
        end = text.find("\n---", 3)
        if end < 0:
            print(f"{p}\tDEAD\tNO-CLOSING-FENCE")
            continue
        block = text[4:end]
        fm, lenient = None, False
        try:
            fm = yaml.safe_load(block)
        except yaml.YAMLError:
            # The CC frontmatter parser is MORE LENIENT than strict YAML --
            # an unquoted colon inside a description value registers fine
            # live. Mirror it: first-colon key/value split per line.
            # Lenient hits are WARN, never DEAD.
            lenient = True
            fm = {}
            for line in block.splitlines():
                if ":" in line and not line.lstrip().startswith("#"):
                    k, v = line.split(":", 1)
                    if k.strip() and " " not in k.strip():
                        fm[k.strip()] = v.strip()
        if not isinstance(fm, dict) or not fm.get("name") or not fm.get("description"):
            print(f"{p}\tDEAD\tFRONTMATTER-INCOMPLETE (need name + description)")
            continue
        verdict = "WARN\tnon-strict YAML frontmatter -- unquoted colon in a value; parses live, tidy when next touched" if lenient else "OK\t-"
        print(f"{p}\t{verdict}")
    except Exception as e:
        print(f"{p}\tDEAD\tPARSE-ERROR {type(e).__name__}")
PYEOF
)" || dead "skills — frontmatter scan failed"

while IFS=$'\t' read -r path state detail; do
  [ -z "${path:-}" ] && continue
  case "$state" in
    OK)   ok "skill $path" ;;
    WARN) warn "skill $path — $detail" ;;
    *)    dead "skill $path — $detail" ;;
  esac
done <<< "$SKILLS_OUT"

# ============================================================
# 5. scope-granted servers are registered somewhere
# ============================================================
SCOPE_OUT="$("$PY" - "$MCP_BASE" <<'PYEOF'
import glob, json, os, re, sys, yaml
scope = yaml.safe_load(open("cabinet/mcp-scope.yml"))
granted = set()
for agent, spec in (scope.get("agents") or {}).items():
    for m in (spec or {}).get("mcps") or []:
        granted.add(str(m).lower())
for m in scope.get("universal") or []:
    granted.add(str(m).lower())
registered = set()
layers = [sys.argv[1], ".mcp.json", "instance/config/extra-mcps.json",
          "cabinet/mcp-overlays/cua-driver.mcp.json"] + sorted(glob.glob("instance/agents/*/mcp.json"))
for layer in layers:
    if not os.path.exists(layer): continue
    try:
        for name in (json.load(open(layer)).get("mcpServers") or {}):
            if not name.startswith("_"): registered.add(name.lower())
    except Exception:
        pass
try:  # user-level servers (~/.claude.json)
    u = json.load(open(os.path.expanduser("~/.claude.json")))
    registered |= {n.lower() for n in (u.get("mcpServers") or {})}
    for proj in (u.get("projects") or {}).values():
        registered |= {n.lower() for n in (proj.get("mcpServers") or {})}
except Exception:
    pass
for sfile in (os.path.expanduser("~/.claude/settings.json"), ".claude/settings.json"):
    try:  # enabled plugin basenames (plugin 'telegram@...' serves scope name 'telegram')
        s = json.load(open(sfile))
        registered |= {k.split("@", 1)[0].lower() for k in (s.get("enabledPlugins") or {})}
    except Exception:
        pass
for g in sorted(granted):
    print(f"{g}\t{'REGISTERED' if g in registered else 'UNREGISTERED'}")
PYEOF
)" || dead "scope — could not parse cabinet/mcp-scope.yml"

while IFS=$'\t' read -r grant state; do
  [ -z "${grant:-}" ] && continue
  if [ "$state" = "REGISTERED" ]; then
    ok "scope grant $grant — registered"
  elif printf '%s' "$WAIVED_SCOPE_GRANTS" | grep -q " $grant "; then
    waived "scope grant $grant — unregistered (known finding #3b, germline descope pending in docs/proposals/germline-addendum-claude-code-audit-2026-07-07.md)"
  elif printf '%s' "$PROFILE_CONNECTORS" | grep -q " $grant "; then
    warn "scope grant $grant — UNVERIFIABLE from disk (claude.ai profile connector)"
  else
    dead "scope grant $grant — registered in no config layer (dead grant, same class as audit #3b)"
  fi
done <<< "$SCOPE_OUT"

# ============================================================
# 6. statusline exits 0
# ============================================================
if printf '{"model":{"display_name":"doctor-probe"}}' | bash cabinet/scripts/statusline.sh >/dev/null 2>&1; then
  ok "statusline — cabinet/scripts/statusline.sh exits 0"
else
  dead "statusline — cabinet/scripts/statusline.sh nonzero exit"
fi

# ============================================================
# 7. Redis reachable
# ============================================================
if [ "$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping 2>/dev/null)" = "PONG" ]; then
  ok "redis — PONG ($REDIS_HOST:$REDIS_PORT)"
else
  dead "redis — no PONG from $REDIS_HOST:$REDIS_PORT (trigger bus down)"
fi

# ============================================================
# 8. killswitch dry-check (status only — NEVER activate/deactivate)
# ============================================================
KS_OUT="$(bash cabinet/scripts/kill-switch.sh status 2>&1)"; KS_RC=$?
if [ $KS_RC -ne 0 ]; then
  dead "killswitch — kill-switch.sh status failed (rc=$KS_RC)"
elif printf '%s' "$KS_OUT" | grep -qi "ACTIVE" && ! printf '%s' "$KS_OUT" | grep -qi "INACTIVE\|not active\|NOT ACTIVE"; then
  warn "killswitch — ACTIVE (fleet halted; deliberate Captain state, verify intended)"
else
  ok "killswitch — status readable, inactive"
fi

# ============================================================
# 9. world-chronicle freshness (Cabinet World E0a — replay-fog probe)
# ============================================================
# A dead census writer = PERMANENT replay fog. DEAD when the world-census
# row is enabled and no keyframe ≤2 days old exists. Read-only.
WORLD_STALE="$($PY - <<'PYEOF'
import datetime, json, re, sys
try:
    text = open("cabinet/services.yml").read()
except OSError:
    print("NOROW"); sys.exit(0)
m = re.search(r"^  - name: world-census\n(?:(?!^  - name: ).*\n?)*", text, re.M)
if not m:
    print("NOROW"); sys.exit(0)
if re.search(r"^\s+disabled:\s*true", m.group(0), re.M):
    print("DISABLED"); sys.exit(0)
last = None
try:
    for line in open("shared/interfaces/world-chronicle.jsonl"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line).get("date")
        except Exception:
            continue
        if isinstance(d, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
            last = max(last or d, d)
except OSError:
    print("MISSING"); sys.exit(0)
if not last:
    print("MISSING"); sys.exit(0)
age = (datetime.date.today() - datetime.date.fromisoformat(last)).days
print(f"OK {last}" if age <= 2 else f"STALE last={last} age={age}d")
PYEOF
)"
case "$WORLD_STALE" in
  OK*)      ok "world-chronicle — fresh keyframe (${WORLD_STALE#OK })" ;;
  NOROW)    skip "world-chronicle — no world-census manifest row" ;;
  DISABLED) skip "world-chronicle — world-census row disabled (parked)" ;;
  MISSING)  dead "world-chronicle — world-census enabled but no keyframe ever landed (replay fog accruing)" ;;
  STALE*)   stale_verdict "world-chronicle — ${WORLD_STALE#STALE } — census writer dead, replay fog accruing (E0a)" ;;
  *)        warn "world-chronicle — probe output unparseable: $WORLD_STALE" ;;
esac

# 9b. world-chronicle DAEMON heartbeat (E0b) — key is SET EX 900 per tick,
# so bare existence IS freshness; absence with an enabled row = daemon dead.
if awk '/^  - name: world-chronicle$/{f=1} f&&/^  - name: /&&!/world-chronicle/{f=0} f&&/disabled: true/{d=1} END{exit d?0:1}' cabinet/services.yml 2>/dev/null; then
  skip "world-chronicle-daemon — row disabled (parked)"
elif grep -qE '^  - name: world-chronicle$' cabinet/services.yml 2>/dev/null; then
  WCHB="$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET cabinet:world:chronicle:heartbeat 2>/dev/null)"
  if [ -n "$WCHB" ] && [ "$WCHB" != "(nil)" ]; then
    ok "world-chronicle-daemon — heartbeat live ($WCHB)"
  else
    stale_verdict "world-chronicle-daemon — row enabled but cabinet:world:chronicle:heartbeat absent (daemon dead; E0b — key is SET EX 900, so it also expires during host sleep)"
  fi
else
  skip "world-chronicle-daemon — no manifest row"
fi

# ============================================================
# 10. germline exists-without-schg watchdog (G7)
# ============================================================
# The germline boundary is only real while every MATERIALIZED path in the
# locked set carries schg — a path can sit unlocked after an unlock window
# that never relocked, or land unlocked when a deployment materializes a
# listed config (e.g. instance/config/posture.yml is deployment-created).
# Source of truth: the FILES=( )/DIRS=( ) arrays in germline-lock.sh —
# parsed out of the array literals (regex extraction, NEVER sourced — the
# script executes cd/case logic on load), never hardcoded here.
# DIR SEMANTICS: lock runs `chflags -R schg "$d"` (germline-lock.sh:167),
# i.e. dirs lock RECURSIVELY — every inode under a listed dir must carry
# the flag, not just the dir inode (the lock script's own `status` checks
# only the dir inode, line 197; the -R lock semantics are what we verify).
# Read-only: stat/find/sed only — never chflags, never sudo.
GL_SCRIPT="cabinet/scripts/germline-lock.sh"
gl_array() { # $1 = array name — one repo-relative entry per line, comments stripped
  sed -n "/^$1=(/,/^)/p" "$GL_SCRIPT" | sed -n 's/^[[:space:]]*"\([^"]*\)".*/\1/p'
}
gl_entry_count() { # $1 = array name — entry-LOOKING lines in the same range
  # (everything that is not the array-open line, the bare closing paren, a
  # comment, or a blank line) — denominator for the drift tripwire below
  sed -n "/^$1=(/,/^)/p" "$GL_SCRIPT" \
    | sed -e "/^$1=(/d" -e '/^)/d' -e '/^[[:space:]]*#/d' -e '/^[[:space:]]*$/d' \
    | grep -c .
}
gl_has_schg() { # flags field only (stat %Sf) — no filename false-positives
  case ",$(stat -f '%Sf' "$1" 2>/dev/null)," in *,schg,*) return 0 ;; *) return 1 ;; esac
}
if [ ! -f "$GL_SCRIPT" ]; then
  warn "germline — $GL_SCRIPT missing; exists-without-schg watchdog cannot run"
else
  GL_FILES="$(gl_array FILES)"; GL_DIRS="$(gl_array DIRS)"
  if [ -z "$GL_FILES" ] || [ -z "$GL_DIRS" ]; then
    warn "germline — could not parse FILES/DIRS arrays out of $GL_SCRIPT (files=$(printf '%s' "$GL_FILES" | grep -c .) dirs=$(printf '%s' "$GL_DIRS" | grep -c .)) — watchdog degraded, not silent"
  else
    # ADVISORY-1 tripwire (lane-B review 2026-07-11): PARTIAL parser drift
    # must not be silent — an unquoted/single-quoted entry extracts as
    # nothing while the empty-parse gate above stays green. Compare the
    # extracted count against the entry-looking-line count in the same sed
    # range; any mismatch means the watchdog is checking FEWER paths than
    # the lock script lists.
    GL_F_EXT="$(printf '%s\n' "$GL_FILES" | grep -c .)"
    GL_D_EXT="$(printf '%s\n' "$GL_DIRS" | grep -c .)"
    GL_F_RAW="$(gl_entry_count FILES)"
    GL_D_RAW="$(gl_entry_count DIRS)"
    if [ "$GL_F_EXT" -ne "$GL_F_RAW" ] || [ "$GL_D_EXT" -ne "$GL_D_RAW" ]; then
      warn "germline — parser drift in $GL_SCRIPT: extracted $GL_F_EXT of $GL_F_RAW FILES + $GL_D_EXT of $GL_D_RAW DIRS entry lines (unquoted/single-quoted entries are invisible to this watchdog) — normalize the array style or fix gl_array"
    fi
    GL_LOCKED=0; GL_ABSENT=0; GL_GAPS=0
    while IFS= read -r f; do
      [ -z "$f" ] && continue
      if [ ! -e "$f" ]; then
        skip "germline $f — absent (not yet materialized; lock skips absent paths)"
        GL_ABSENT=$((GL_ABSENT+1))
      elif gl_has_schg "$f"; then
        GL_LOCKED=$((GL_LOCKED+1))
      else
        dead "germline $f — exists but NOT schg-locked (boundary gap; lock ceremony needed)"
        GL_GAPS=$((GL_GAPS+1))
      fi
    done <<< "$GL_FILES"
    while IFS= read -r d; do
      [ -z "$d" ] && continue
      if [ ! -d "$d" ]; then
        skip "germline $d/ — absent (not yet materialized; lock skips absent dirs)"
        GL_ABSENT=$((GL_ABSENT+1))
        continue
      fi
      # recursive check incl. the dir inode itself — chflags -R semantics
      # (germline-lock.sh:167); one line per dir, capped examples (no spam)
      GL_DIRGAPS="$(find "$d" 2>/dev/null | while IFS= read -r p; do
        gl_has_schg "$p" || printf '%s\n' "$p"
      done)"
      if [ -z "$GL_DIRGAPS" ]; then
        GL_LOCKED=$((GL_LOCKED+1))
      else
        GL_N="$(printf '%s\n' "$GL_DIRGAPS" | grep -c .)"
        GL_EX="$(printf '%s\n' "$GL_DIRGAPS" | head -3 | tr '\n' ' ')"
        dead "germline $d/ — exists but NOT schg-locked: $GL_N inode(s) unlocked under recursive lock (chflags -R, germline-lock.sh:167), e.g. ${GL_EX%% }— boundary gap; lock ceremony needed"
        GL_GAPS=$((GL_GAPS+1))
      fi
    done <<< "$GL_DIRS"
    if [ "$GL_GAPS" -eq 0 ]; then
      ok "germline — $GL_LOCKED materialized path(s) schg-verified ($GL_ABSENT absent skipped; boundary armed for everything on disk)"
    fi
  fi
fi

# ============================================================
# N. embed-seam — semantic-search degrade signal (R4, 2026-07-12)
# The LOUD signal the org-memory study (§5-R4) asks for: if no VOYAGE_API_KEY
# is resolvable, memory_search runs keyless LEXICAL-ONLY — conceptual recall of
# law/knowledge is DEGRADED but not dead (a keyless Mini hatch is a valid,
# deliberate state), so this is WARN/AMBER, never DEAD. Also reports the active
# EMBED-SEAM (provider/model/dims) and, best-effort, flags dims drift vs the
# stamped cabinet_embedding_meta row. Keys are regex-extracted, NEVER sourced
# and NEVER printed (same discipline as the mcp env check above).
# ============================================================
# Configured-seam side resolves env > cabinet/.env > compiled default (review
# fix 2026-07-15) — the SAME chain memory.sh uses at stamp/search time. The
# launchd doctor job carries no EMBED_* env, so a seam configured in
# cabinet/.env must resolve here too, or the dims-drift compare below runs
# against the compiled default: a permanent spurious WARN after a legitimate
# switch+re-embed, or default-vs-default masking a real drift. Same
# grep-extract discipline as ES_VKEY/ES_NEON below; these are plain labels,
# never secrets.
ES_PROVIDER="${EMBED_PROVIDER:-}"
ES_MODEL="${EMBED_MODEL:-}"
ES_DIMS="${EMBED_DIMS:-}"
if [ -z "$ES_PROVIDER" ] && [ -f "$REPO_ROOT/cabinet/.env" ]; then
  ES_PROVIDER="$(grep -E '^EMBED_PROVIDER=' "$REPO_ROOT/cabinet/.env" | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
fi
if [ -z "$ES_MODEL" ] && [ -f "$REPO_ROOT/cabinet/.env" ]; then
  ES_MODEL="$(grep -E '^EMBED_MODEL=' "$REPO_ROOT/cabinet/.env" | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
fi
if [ -z "$ES_DIMS" ] && [ -f "$REPO_ROOT/cabinet/.env" ]; then
  ES_DIMS="$(grep -E '^EMBED_DIMS=' "$REPO_ROOT/cabinet/.env" | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
fi
ES_PROVIDER="${ES_PROVIDER:-voyage}"
ES_MODEL="${ES_MODEL:-voyage-4-large}"
ES_DIMS="${ES_DIMS:-1024}"
ES_VKEY="${VOYAGE_API_KEY:-}"
if [ -z "$ES_VKEY" ] && [ -f "$REPO_ROOT/cabinet/.env" ]; then
  ES_VKEY="$(grep -E '^VOYAGE_API_KEY=' "$REPO_ROOT/cabinet/.env" | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
fi
if [ -n "$ES_VKEY" ]; then
  ok "embed-seam — VOYAGE key resolvable; hybrid+rerank search active (provider=$ES_PROVIDER model=$ES_MODEL dims=$ES_DIMS)"
else
  warn "embed-seam — no VOYAGE_API_KEY resolvable: memory_search DEGRADED to keyless LEXICAL-ONLY (conceptual recall of law/knowledge reduced; rerank off). Set VOYAGE_API_KEY to restore hybrid+rerank retrieval."
fi
unset ES_VKEY
# Dims-drift check — tri-state, never fails the doctor (worst = WARN). Since
# the 2026-07-15 R4 follow-up, 046-embedding-meta.sql rides both apply lists
# and load-preset.sh/cabinet-bootstrap.sh stamp-if-absent right after it, so
# a stamped store is the NORM — and because a deploy never overwrites an
# existing row (the first stamp is provenance; re-stamping is reserved for
# the re-embed organ / a captain after a verified full backfill), a config
# flip keeps WARNing here across officer restarts until the store is
# genuinely re-embedded: match -> OK, mismatch -> WARN (a dims change without
# a full re-embed backfill corrupts vector search). An estate that predates
# the wiring reports SKIP "not yet stamped" until its next load-preset run;
# no resolvable store / unreachable store stays a clean SKIP (a DB-less hatch
# is a valid deliberate state — same discipline as the germline absent-path
# skips). The connection string is never printed.
ES_NEON="${NEON_CONNECTION_STRING:-}"
if [ -z "$ES_NEON" ] && [ -f "$REPO_ROOT/cabinet/.env" ]; then
  ES_NEON="$(grep -E '^NEON_CONNECTION_STRING=' "$REPO_ROOT/cabinet/.env" | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
fi
if [ -z "$ES_NEON" ]; then
  skip "embed-seam dims-drift — no NEON_CONNECTION_STRING resolvable (env or cabinet/.env); store provenance not checkable"
elif ! command -v psql >/dev/null 2>&1; then
  skip "embed-seam dims-drift — psql not on PATH; store provenance not checkable"
elif ES_META_RAW="$(PGCONNECT_TIMEOUT=5 psql "$ES_NEON" -tAc "SELECT dims FROM cabinet_embedding_meta WHERE id=1;" 2>/dev/null)"; then
  ES_META_DIMS="$(printf '%s' "$ES_META_RAW" | tr -d '[:space:]')"
  if [ -z "$ES_META_DIMS" ]; then
    skip "embed-seam dims-drift — store reachable but not yet stamped (no cabinet_embedding_meta row); the next load-preset.sh run stamps it"
  elif [ "$ES_META_DIMS" = "$ES_DIMS" ]; then
    ok "embed-seam — store stamped dims=$ES_META_DIMS matches configured EMBED_DIMS"
  else
    warn "embed-seam — DIMS DRIFT: store stamped dims=$ES_META_DIMS but EMBED_DIMS=$ES_DIMS — a full re-embed backfill is required before the switch takes effect"
  fi
else
  skip "embed-seam dims-drift — store unreachable or cabinet_embedding_meta absent (psql probe failed); not checkable this run"
fi
unset ES_NEON ES_META_RAW ES_META_DIMS

# ============================================================
# N2. captain-law-digest freshness (BC boot-pack, 2026-07-15)
# The promoted digest (shared/interfaces/captain-law-digest.md) is
# boot-injected IN FULL by the Captain-gated session-start patch, but the
# source ledgers keep growing — a stale digest silently returns the fleet to
# "older law is boot-invisible", masked by an authoritative-looking section.
# memory-distill.py --check is READ-ONLY: it compares the digest's recorded
# per-ledger sha256s to the live ledgers. Exit 0 fresh / 3 stale / 4 not in
# use (no promoted digest — a sanctioned state incl. the kill switch, so no
# noise) / 2 nothing to distill. Stale is WARN/AMBER, never DEAD: content is
# a deterministic derivation and regeneration is Captain-gated (review +
# --apply, standing handback) — the doctor's job is the loud tell, the
# cross-officer retro's Part 5 owns acting on it.
# ============================================================
MD_SCRIPT="$REPO_ROOT/cabinet/scripts/memory-distill.py"
if [ -f "$MD_SCRIPT" ]; then
  "$PY" "$MD_SCRIPT" --check >/dev/null 2>&1
  MD_RC=$?
  case "$MD_RC" in
    0) ok "captain-law-digest — fresh (recorded ledger hashes match live)" ;;
    3) warn "captain-law-digest — STALE vs live captain-law ledgers: sessions boot an outdated law index. Regenerate: python3.12 cabinet/scripts/memory-distill.py → Captain review → --apply (docs/proposals/germline-session-start-digest-addendum-2026-07-15.md)" ;;
    2|4) : ;;  # not in use / nothing to distill — silent by design
    *) warn "captain-law-digest — --check probe failed rc=$MD_RC (distiller unrunnable?)" ;;
  esac
fi

# ============================================================
# 11. retrieval-eval nightly verdict — the refinement gate (2026-07-15)
# The 03:50 retrieval-eval services row appends one verdict line/night to
# cabinet/logs/retrieval-eval-history.jsonl, running the recall@k + MRR
# floors in BOTH arms (production hybrid+rerank AND --no-rerank blended
# order — rerank rescues pool damage, so only the blended arm catches a
# weight/pool regression). This check reads ONLY that ledger through the
# wrapper's --probe mode: pure file+env inspection, no DB, no network, no
# secret values (creds resolvability is a NAME check, same discipline as
# the mcp env probe above). Verdict ladder: floor breach / unmeasurable /
# stale >48h = WARN (AMBER — retrieval quality regressed or the gate
# stopped running; a consolidation/supersession/ranking wave must HOLD the
# floors), never DEAD (quality regression ≠ dead config; the services
# section above already DEADs an unloaded row). Credless boxes SKIP clean.
# Staleness-class findings honor the same post-wake grace as stale_verdict
# (the sleep-missed nightly coalesces within minutes of wake), one severity
# rung lower: WARN outside the grace window, OK-with-note inside it.
# ============================================================
re_stale_verdict() { # staleness-class finding for the eval verdict ledger
  if [ "$SECS_SINCE_WAKE" -lt "$WAKE_GRACE_S" ]; then
    ok "$1 (post-wake grace: woke ${SECS_SINCE_WAKE}s ago < ${WAKE_GRACE_S}s — coalesced nightly should land shortly)"
  else
    warn "$1"
  fi
}
RE_PROBE="$(bash cabinet/scripts/retrieval-eval-nightly.sh --probe 2>/dev/null)"
case "$RE_PROBE" in
  OK*)      ok "retrieval-eval — latest nightly verdict passed (${RE_PROBE#OK })" ;;
  NOCREDS*) skip "retrieval-eval — no NEON_CONNECTION_STRING resolvable (clean-room/CI box; the gate is store-local by design — CI gates the ranking fingerprint instead)" ;;
  BREACH*)  warn "retrieval-eval — FLOOR BREACH in latest nightly verdict (${RE_PROBE#BREACH }) — retrieval ranking regressed (weights/rerank/consolidation wave?); run bash cabinet/scripts/retrieval-eval-nightly.sh and root-cause before the next memory wave" ;;
  NOTOK*)   warn "retrieval-eval — latest nightly verdict unmeasurable (${RE_PROBE#NOTOK }) — young store or setup error; see cabinet/logs/retrieval-eval-history.jsonl" ;;
  NOFILE*)  re_stale_verdict "retrieval-eval — creds resolvable but no verdict ledger yet (03:50 nightly never ran — services row not installed?)" ;;
  STALE*)   re_stale_verdict "retrieval-eval — latest verdict stale (${RE_PROBE#STALE }) — the nightly gate is not running" ;;
  BADLINE*) warn "retrieval-eval — latest verdict line unparseable (ledger corrupt? see cabinet/logs/retrieval-eval-history.jsonl)" ;;
  *)        warn "retrieval-eval — probe output unparseable: $RE_PROBE" ;;
esac

# ---- EVIDENCE-PLANE SECTION BEGIN ----
# ============================================================
# 12. evidence plane — freshness / growth / chain continuity
# (Evidence program Phase 2 Batch A, 2026-07-17 — observation-only.)
# Read-only probes against the pinned production store
# $REPO_ROOT/instance/evidence/v1 (journey.py EVIDENCE_REL). The store root
# is deliberately NOT read from the CABINET_EVIDENCE_DIR env fallback —
# that is the recorder's untrusted env seam (A10) and a doctor that
# honored it could be pointed at a decoy store. All three probes are
# bounded and degrade to WARN/AMBER or SKIP: they NEVER dead() the doctor
# (Phase-2 observation-only law — a red evidence plane needs a human, not
# a fleet halt; framework/tests/test_evidence_doctor_probes.py pins this)
# and never crash it. Chain continuity verifies ONLY the newest trial
# (single-trial spot-check, measured ~32ms at cap depth; store-wide
# verification is the evidence-anchor job's department). The verifier's
# watermark advance on a clean pass is best-effort and protective by
# design (verifier.py _watermark_check — a read-only store skips it
# silently); the evidence bytes themselves are never written. Ceilings
# come from the measured envelope in docs/runbooks/evidence-recorder-v1.md
# ("Measured envelope", cabinet/scripts/evidence-bench.py): keep
# EV_CAP_DEFAULT in sync with the recorder's enforced per-trial event cap.
# ============================================================
# ---- EVIDENCE-PLANE PURE PROBES BEGIN ----
# Pure helpers: no doctor globals/counters, echo exactly one verdict line
# ("OK ..." | "WARN ..." | "SKIP ...") and always return 0. They are
# extracted verbatim and sourced by
# framework/tests/test_evidence_doctor_probes.py — keep them
# self-contained (standard tools + the interpreter argument only).
evidence_probe_freshness() { # $1=store-root  $2=max-age-secs (default 172800 = 48h)
  local store="$1" max_age="${2:-172800}" newest="" now age
  [ -d "$store" ] || { echo "SKIP no-store ($store absent — evidence plane not activated)"; return 0; }
  [ -d "$store/trials" ] || { echo "SKIP no-trials (store present, no trials dir)"; return 0; }
  newest="$(find "$store/trials" -mindepth 2 -maxdepth 2 \( -name events.jsonl -o -name anchor.json \) -type f -print0 2>/dev/null \
    | xargs -0 stat -f '%m' 2>/dev/null | sort -nr | head -1)"
  if [ -z "$newest" ]; then # GNU stat fallback (Linux CI)
    newest="$(find "$store/trials" -mindepth 2 -maxdepth 2 \( -name events.jsonl -o -name anchor.json \) -type f -print0 2>/dev/null \
      | xargs -0 stat -c '%Y' 2>/dev/null | sort -nr | head -1)"
  fi
  case "$newest" in ''|*[!0-9]*) echo "SKIP no-trials (no trial ledgers yet)"; return 0 ;; esac
  now="$(date +%s)"
  age=$((now - newest))
  if [ "$age" -gt "$max_age" ]; then
    echo "WARN stale age_s=$age limit_s=$max_age (no evidence append in $((age / 3600))h — producers and daily digest-anchor quiet)"
  else
    echo "OK age_s=$age limit_s=$max_age"
  fi
  return 0
}
evidence_probe_growth() { # $1=store-root  $2=max-store-kb (default 262144 = 256MB)  $3=per-trial event cap (default 500 = recorder MAX_TRIAL_EVENTS)
  local store="$1" max_kb="${2:-262144}" cap="${3:-500}" kb warn_at biggest=0 today n t
  [ -d "$store" ] || { echo "SKIP no-store ($store absent)"; return 0; }
  kb="$(du -sk "$store" 2>/dev/null | awk '{print $1}')"
  case "$kb" in ''|*[!0-9]*) kb=0 ;; esac
  today="$(date -u +%Y%m%d)"
  warn_at=$((cap * 8 / 10))
  for t in "$store/trials"/evt-*-"$today"; do
    [ -f "$t/events.jsonl" ] || continue
    n="$(wc -l < "$t/events.jsonl" 2>/dev/null | tr -d '[:space:]')"
    case "$n" in ''|*[!0-9]*) continue ;; esac
    [ "$n" -gt "$biggest" ] && biggest="$n"
  done
  if [ "$kb" -gt "$max_kb" ]; then
    echo "WARN size kb=$kb max_kb=$max_kb biggest_day_trial_events=$biggest (store past the measured ceiling — check retention + anchor job)"
  elif [ "$biggest" -ge "$warn_at" ]; then
    echo "WARN cap-approach biggest_day_trial_events=$biggest cap=$cap warn_at=$warn_at kb=$kb (today's day-bounded trial nearing the per-trial event cap)"
  else
    echo "OK kb=$kb max_kb=$max_kb biggest_day_trial_events=$biggest cap=$cap"
  fi
  return 0
}
evidence_probe_chain() { # $1=store-root  $2=python interpreter (default python3.12); caller cwd must be the repo root
  local store="$1" py="${2:-python3.12}" newest lines out rc count
  [ -d "$store/trials" ] || { echo "SKIP no-store ($store/trials absent)"; return 0; }
  newest="$(ls -1t "$store/trials" 2>/dev/null | head -1)"
  [ -n "$newest" ] || { echo "SKIP no-trials"; return 0; }
  command -v "$py" >/dev/null 2>&1 || { echo "SKIP no-interpreter ($py not on PATH; chain spot-check needs the house python3.12)"; return 0; }
  "$py" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null \
    || { echo "SKIP interpreter-too-old ($py < 3.11 cannot import framework.evidence)"; return 0; }
  if [ ! -f "$store/trials/$newest/events.jsonl" ]; then
    echo "SKIP no-ledger (trial $newest has no events.jsonl yet)"
    return 0
  fi
  lines="$(wc -l < "$store/trials/$newest/events.jsonl" 2>/dev/null | tr -d '[:space:]')"
  case "$lines" in ''|*[!0-9]*) lines=0 ;; esac
  if [ "$lines" -gt 10000 ]; then
    echo "WARN oversized trial=$newest events=$lines (>10000 — spot-check skipped to stay bounded; the growth envelope is breached)"
    return 0
  fi
  out="$("$py" -m framework.evidence --store "$store" verify --trial "$newest" 2>&1)"
  rc=$?
  count="$(printf '%s' "$out" | sed -n 's/.*"event_count": *\([0-9][0-9]*\).*/\1/p' | head -1)"
  case "$rc" in
    0) echo "OK trial=$newest events=${count:-?} (hash chain + signatures + anchor verified)" ;;
    4) echo "WARN verify-failed trial=$newest events=${count:-?} — $(printf '%s' "$out" | head -c 300)" ;;
    *) echo "WARN probe-error rc=$rc trial=$newest — $(printf '%s' "$out" | head -c 200)" ;;
  esac
  return 0
}
evidence_probe_degradations() { # $1=degradation marker ledger (append-only JSONL)  $2=recent window secs (default 86400 = 24h)
  # Reads BOTH marker formats: the telemetry-mirror ledger written by
  # framework/evidence_mirror.py _write_marker ({ts, chokepoint, reason,
  # message}) and the act-class lifecycle sidecar written by
  # framework/evidence/lifecycle.py _note_degradation ({schema, ts,
  # trial_id, component, phase, error_code}). Recency = file mtime (both
  # ledgers are append-only, so mtime IS the last degradation). Absent
  # file = never degraded = OK.
  local marker="$1" window="${2:-86400}" total mtime now age ck rs
  [ -f "$marker" ] || { echo "OK no-marker (no degradations recorded; $marker absent)"; return 0; }
  total="$(wc -l < "$marker" 2>/dev/null | tr -d '[:space:]')"
  case "$total" in ''|*[!0-9]*) total=0 ;; esac
  [ "$total" -gt 0 ] || { echo "OK empty-marker (0 rows in $marker)"; return 0; }
  mtime="$(stat -f '%m' "$marker" 2>/dev/null || stat -c '%Y' "$marker" 2>/dev/null)"
  case "$mtime" in ''|*[!0-9]*) echo "WARN marker-unreadable rows=$total (cannot stat $marker)"; return 0 ;; esac
  now="$(date +%s)"
  age=$((now - mtime))
  ck="$(tail -1 "$marker" 2>/dev/null | sed -n 's/.*"chokepoint": *"\([^"]*\)".*/\1/p' | head -1)"
  rs="$(tail -1 "$marker" 2>/dev/null | sed -n 's/.*"reason": *"\([^"]*\)".*/\1/p' | head -1)"
  [ -n "$ck" ] || ck="$(tail -1 "$marker" 2>/dev/null | sed -n 's/.*"component": *"\([^"]*\)".*/\1/p' | head -1)"
  [ -n "$rs" ] || rs="$(tail -1 "$marker" 2>/dev/null | sed -n 's/.*"error_code": *"\([^"]*\)".*/\1/p' | head -1)"
  if [ "$age" -le "$window" ]; then
    echo "WARN degraded rows=$total age_s=$age window_s=$window last=${ck:-?}/${rs:-?} (recent evidence-recording degradation — see $marker)"
  else
    echo "OK quiet rows=$total age_s=$age window_s=$window last=${ck:-?}/${rs:-?} (historical degradations only)"
  fi
  return 0
}
# ---- EVIDENCE-PLANE PURE PROBES END ----
ev_stale_verdict() { # staleness-class finding, AMBER-max: WARN outside wake grace, OK-note inside
  if [ "$SECS_SINCE_WAKE" -lt "$WAKE_GRACE_S" ]; then
    ok "$1 (post-wake grace: woke ${SECS_SINCE_WAKE}s ago < ${WAKE_GRACE_S}s)"
  else
    warn "$1"
  fi
}
EV_STORE="$REPO_ROOT/instance/evidence/v1"
EV_CAP_DEFAULT=500        # = the recorder's ENFORCED MAX_TRIAL_EVENTS (provisional; the bench's measured recommendation is 512 — both recorded in runbook "Measured envelope"; retuning is a ceremony follow-up, never a silent edit). Sync pinned by framework/tests/test_evidence_doctor_probes.py.
EV_MAX_KB_DEFAULT=262144  # 256 MB ≈ 7x the measured worst-case 90-day projection (36.2 MB); runbook "Measured envelope"
EV_MIRROR_MARKER="$REPO_ROOT/cabinet/logs/evidence-mirror-degradations.jsonl"
# Mirror degradation marker (framework/evidence_mirror.py degrades LOUD by
# appending here — the doctor-readable join). Probed OUTSIDE the store-dir
# guard: a mirror degradation with NO store present is exactly the loud
# case that must surface.
EV_MIRROR_DEG="$(evidence_probe_degradations "$EV_MIRROR_MARKER")"
case "$EV_MIRROR_DEG" in
  OK*)   ok "evidence-plane mirror-degradations — ${EV_MIRROR_DEG#OK }" ;;
  SKIP*) skip "evidence-plane mirror-degradations — ${EV_MIRROR_DEG#SKIP }" ;;
  WARN*) warn "evidence-plane mirror-degradations — ${EV_MIRROR_DEG#WARN }" ;;
  *)     warn "evidence-plane mirror-degradations — probe output unparseable: $EV_MIRROR_DEG" ;;
esac
if [ ! -d "$EV_STORE" ]; then
  skip "evidence-plane — store absent ($EV_STORE; evidence plane not yet activated on this box)"
else
  EV_FRESH="$(evidence_probe_freshness "$EV_STORE")"
  case "$EV_FRESH" in
    OK*)   ok "evidence-plane freshness — ${EV_FRESH#OK }" ;;
    SKIP*) skip "evidence-plane freshness — ${EV_FRESH#SKIP }" ;;
    WARN*) ev_stale_verdict "evidence-plane freshness — ${EV_FRESH#WARN }" ;;
    *)     warn "evidence-plane freshness — probe output unparseable: $EV_FRESH" ;;
  esac
  EV_GROW="$(evidence_probe_growth "$EV_STORE" "$EV_MAX_KB_DEFAULT" "$EV_CAP_DEFAULT")"
  case "$EV_GROW" in
    OK*)   ok "evidence-plane growth — ${EV_GROW#OK }" ;;
    SKIP*) skip "evidence-plane growth — ${EV_GROW#SKIP }" ;;
    WARN*) warn "evidence-plane growth — ${EV_GROW#WARN }" ;;
    *)     warn "evidence-plane growth — probe output unparseable: $EV_GROW" ;;
  esac
  EV_CHAIN="$(evidence_probe_chain "$EV_STORE" "$PY")"
  case "$EV_CHAIN" in
    OK*)   ok "evidence-plane chain — ${EV_CHAIN#OK }" ;;
    SKIP*) skip "evidence-plane chain — ${EV_CHAIN#SKIP }" ;;
    WARN*) warn "evidence-plane chain — ${EV_CHAIN#WARN }" ;;
    *)     warn "evidence-plane chain — probe output unparseable: $EV_CHAIN" ;;
  esac
  # Act-class lifecycle degradation sidecar (framework/evidence/lifecycle.py
  # writes <store-root>/degradations.jsonl at every purge-degradation FLIP).
  EV_ACT_DEG="$(evidence_probe_degradations "$EV_STORE/degradations.jsonl")"
  case "$EV_ACT_DEG" in
    OK*)   ok "evidence-plane act-degradations — ${EV_ACT_DEG#OK }" ;;
    SKIP*) skip "evidence-plane act-degradations — ${EV_ACT_DEG#SKIP }" ;;
    WARN*) warn "evidence-plane act-degradations — ${EV_ACT_DEG#WARN }" ;;
    *)     warn "evidence-plane act-degradations — probe output unparseable: $EV_ACT_DEG" ;;
  esac
fi
# ---- EVIDENCE-PLANE SECTION END ----

# ============================================================
# 13. task-sync drift falsifier verdict (adapter kit, 2026-07-17)
# The 04:20 task-sync-drift services row appends one canonical↔mirror
# verdict line/night to cabinet/logs/task-sync-drift.jsonl (honest
# no-adapters-configured lines while every adapter is NoOp/skeleton —
# today's live shape). This check reads ONLY that ledger via the script's
# --probe mode: pure file inspection — no DB, no network, no adapter
# imports, no secret values. ESCALATION LADDER (documented here, executed
# by the FALSIFIER — the doctor is read-only by contract and never sends):
#   drift verdict #1          → AMBER below with the self-heal hint: run
#                               one sync cycle (bash cabinet/cron/
#                               task-sync.sh) then re-run the falsifier —
#                               a fresh passing line clears the AMBER the
#                               same day;
#   drift again on the NEXT   → self-heal failed: the falsifier itself
#   nightly (distinct date)     files ONE captain card via the attention
#                               gateway (attention-submit.sh; the gate
#                               dedups + quiet-hours it) and stamps
#                               `escalated` on the verdict line — the card
#                               reaches the Captain from that organ, NEVER
#                               from this probe.
# Never DEAD: a drifting mirror is a quality finding, not dead config (the
# services section above already DEADs an unloaded row). Staleness rides
# the same post-wake grace as retrieval-eval (re_stale_verdict).
# NOSYNC sub-cases (2026-07-17 review): canonical-unreadable means NOT
# CONFIGURED only (an adapter exists but this box has no Postgres client/
# conn string and no JSON seam) — a CONFIGURED canonical store that FAILS
# to read (credential rot, dead DB) is status=error → the ERROR/AMBER arm
# below, never a green NOSYNC; the falsifier enforces the split at the
# source. (Prose here says "Postgres client" on purpose: the retrieval-eval
# purity scan asserts the literal client-binary token never appears between
# check 11 and the heartbeat.)
# ============================================================
TSD_PROBE="$("$PY" cabinet/scripts/task-sync-drift-falsifier.py --probe 2>/dev/null)"
case "$TSD_PROBE" in
  OK*)      ok "task-sync-drift — latest nightly verdict passed (${TSD_PROBE#OK })" ;;
  "NOSYNC status=canonical-unreadable"*) ok "task-sync-drift — honest no-op (${TSD_PROBE#NOSYNC }); an adapter is configured but this box has no canonical task store to read (no Postgres client/conn string, no JSON seam) — a configured store that FAILS reads surfaces as ERROR, never here" ;;
  NOSYNC*)  ok "task-sync-drift — honest no-op (${TSD_PROBE#NOSYNC }); no external tracker configured to drift, loud-degrade line fresh" ;;
  "DRIFT n=1 "*) warn "task-sync-drift — MIRROR DRIFT in latest nightly verdict (${TSD_PROBE#DRIFT }) — self-heal: bash cabinet/cron/task-sync.sh, then python3.12 cabinet/scripts/task-sync-drift-falsifier.py (a passing line clears this AMBER); if the NEXT nightly still drifts the falsifier files the captain card" ;;
  DRIFT*)   warn "task-sync-drift — drift PERSISTED across nightly verdicts (${TSD_PROBE#DRIFT }) — self-heal failed; the falsifier files/filed the captain card (see the needs ledger + the escalated stamp in cabinet/logs/task-sync-drift.jsonl); root-cause the adapter before trusting the external board" ;;
  ERROR*)   warn "task-sync-drift — latest falsifier run errored (${TSD_PROBE#ERROR }) — adapter/canonical infrastructure broke; see cabinet/logs/task-sync-drift.jsonl" ;;
  NOFILE*)  re_stale_verdict "task-sync-drift — no verdict ledger yet (04:20 nightly never ran — services row not installed?)" ;;
  STALE*)   re_stale_verdict "task-sync-drift — latest verdict stale (${TSD_PROBE#STALE }) — the nightly falsifier is not running" ;;
  BADLINE*) warn "task-sync-drift — latest verdict line unparseable (ledger corrupt? see cabinet/logs/task-sync-drift.jsonl)" ;;
  *)        warn "task-sync-drift — probe output unparseable: $TSD_PROBE" ;;
esac

# ============================================================
# verdict + heartbeat
# ============================================================
TOTAL=$((N_OK + N_WARN + N_WAIVED + ${#DEAD[@]}))
if [ ${#DEAD[@]} -eq 0 ]; then
  VERDICT="GREEN"
  echo "CABINET_DOCTOR GREEN (checks=$TOTAL warn=$N_WARN waived=$N_WAIVED skip=$N_SKIP)"
else
  VERDICT="DEAD:${#DEAD[@]}"
  echo "CABINET_DOCTOR DEAD (n=${#DEAD[@]} of $TOTAL checks; warn=$N_WARN waived=$N_WAIVED)"
  for d in "${DEAD[@]}"; do echo "  DEAD $d"; done
fi
# Heartbeat proves THE DOCTOR ran (stale heartbeat = doctor dead, not fleet):
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET cabinet:doctor:heartbeat \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ) $VERDICT" >/dev/null 2>&1 || true

# Run history (G8a, hardening loop 2026-07-11): the redis heartbeat holds
# only the LAST run, so "healthy over a rolling 7-day window" was never
# measurable. Append one jsonl line per run to cabinet/logs/ (gitignored
# runtime data, .gitignore `cabinet/logs/*`); self-prunes to 60 days.
# Best-effort — history failure never changes the doctor's verdict.
{
  HIST="cabinet/logs/doctor-history.jsonl"
  printf '{"ts":"%s","verdict":"%s","dead":%d,"warn":%d,"waived":%d,"skip":%d,"total":%d,"secs_since_wake":%s}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$VERDICT" "${#DEAD[@]}" "$N_WARN" "$N_WAIVED" "$N_SKIP" "$TOTAL" "$SECS_SINCE_WAKE" >> "$HIST"
  if [ "$(wc -l < "$HIST" 2>/dev/null || echo 0)" -gt 200 ]; then
    tail -n 120 "$HIST" > "$HIST.tmp" && mv "$HIST.tmp" "$HIST"
  fi
} 2>/dev/null || true

[ ${#DEAD[@]} -eq 0 ] && exit 0 || exit 1
