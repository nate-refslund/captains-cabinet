#!/bin/bash
# cabinet-doctor.sh — deterministic config-liveness prober for the whole fleet
# (Claude Code audit 2026-07-07 follow-on; the audit found a CLASS of silently-
# dead config — dead MCP servers, unwired hooks, an unparseable skill, a bare-
# bash statusline — that nothing probed. This script IS that prober.)
#
# WHAT IT CHECKS (all read-only; the only writes are its own log lines on
# stdout and one Redis heartbeat key at the end):
#   1. every cabinet/services.yml row  ↔ launchd job loaded ↔ fresh log
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
#      with the `---` fence — no leading bytes; the brain-audit regression).
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
LA_DIR="$HOME/Library/LaunchAgents"

DEAD=()
N_OK=0; N_WARN=0; N_WAIVED=0; N_SKIP=0

ok()     { echo "OK     $1"; N_OK=$((N_OK+1)); }
warn()   { echo "WARN   $1"; N_WARN=$((N_WARN+1)); }
waived() { echo "WAIVED $1"; N_WAIVED=$((N_WAIVED+1)); }
skip()   { echo "SKIP   $1"; N_SKIP=$((N_SKIP+1)); }
dead()   { echo "DEAD   $1"; DEAD+=("$1"); }

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
root = os.getcwd()
data = yaml.safe_load(open("cabinet/services.yml"))
now = time.time()
la = os.path.expanduser("~/Library/LaunchAgents")
for s in data["services"]:
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
      dead "service $name — log stale ${age}s > window ${window}s"
    else
      ok "service $name — loaded, log fresh (${age}s <= ${window}s)"
    fi
  fi
done <<< "$SVC_TSV"

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
        # THE load-bearing check (brain-audit regression, audit #7): any byte
        # before the fence makes CC register the skill with a junk description.
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

[ ${#DEAD[@]} -eq 0 ] && exit 0 || exit 1
