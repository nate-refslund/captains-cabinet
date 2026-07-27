#!/bin/bash
# cabinet/scripts/meta-cognition/captain-seat-pack.sh — Captain-Seat evidence pack
#
# The deterministic half of the retro's Captain-Seat Review (Part 1c in
# memory/skills/cross-officer-retro.md; Captain-ratified 2026-07-26, recorded in
# captain-decisions.md). Prints, read-only, the evidence a fresh-context
# reviewer needs to relive the window AS the Captain: what he was sent, what he
# wrote back, repetition counts, open-item dwell, and the health of the
# channels he relies on. It does NOT judge, does NOT ping, and never fabricates:
# an absent source is printed as a measured absence, because absence of a
# scoring/consumption loop is itself Captain-seat evidence.
#
# Usage:
#   bash captain-seat-pack.sh                 # last 14 days, human-readable
#   CAPTAIN_SEAT_WINDOW_DAYS=7 bash ...       # custom window
#   bash captain-seat-pack.sh --meta <dir>    # ALSO scan an orchestrator/meta
#                                             # workspace (LESSONS.md, CLAUDE.md
#                                             # git history, HANDBACKS-*.md).
#                                             # No default: the runtime never
#                                             # assumes a meta dir exists.
#   CAPTAIN_SEAT_ROOT=<dir> bash ...          # override repo root (tests)
#
# Secrets: NONE read or printed. Network: none (optional local redis-cli only).
set -u

ROOT="${CAPTAIN_SEAT_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
WINDOW_DAYS="${CAPTAIN_SEAT_WINDOW_DAYS:-14}"
META_DIR=""
if [ "${1:-}" = "--meta" ] && [ -n "${2:-}" ]; then META_DIR="$2"; fi

python3.12 - "$ROOT" "$WINDOW_DAYS" "$META_DIR" <<'PYEOF'
import json, os, re, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

root = Path(sys.argv[1]); window_days = int(sys.argv[2])
meta = Path(sys.argv[3]) if sys.argv[3] else None
now = datetime.now(timezone.utc)
since = now - timedelta(days=window_days)
DATE_RE = re.compile(r"(20\d\d-\d\d-\d\d)")

def in_window(s):
    m = DATE_RE.search(s or "")
    if not m: return False
    try: d = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError: return False
    return d >= since

def age_days(ts):
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return round((now - d).total_seconds() / 86400, 1)
    except Exception: return None

def mtime_age(p):
    try: return round((now.timestamp() - p.stat().st_mtime) / 86400, 1)
    except OSError: return None

def sec(title): print(f"\n=== {title} ===")

def absent(p, what): print(f"ABSENT: {p} — {what}")

print(f"CAPTAIN-SEAT EVIDENCE PACK  window={window_days}d  since={since.date()}  now={now.isoformat(timespec='seconds')}")
print(f"root={root}  meta={meta or '(none)'}")
print("Read-only. Absences are measured facts, not errors.")

si = root / "shared" / "interfaces"

# --- A. WHAT HE WAS SENT ------------------------------------------------
sec("A. WHAT HE WAS SENT (in window)")
bdir = root / "instance" / "memory" / "briefings"
if bdir.is_dir():
    rows = []
    for f in sorted(bdir.iterdir()):
        if f.is_file() and mtime_age(f) is not None and mtime_age(f) <= window_days:
            try:
                text = f.read_text(errors="replace")
                words = len(text.split())
                first = [ln.strip()[:110] for ln in text.splitlines() if ln.strip()][:2]
            except OSError: words, first = -1, []
            rows.append(f"  {f.name}  ({words} words, {mtime_age(f)}d ago)")
            for ln in first: rows.append(f"      | {ln}")
    n_files = len([r for r in rows if not r.startswith("      |")])
    print(f"briefings sent in window: {n_files} (first lines quoted; full contents NOT in this pack)")
    for r in rows[:60]: print(r)
    if len(rows) > 60: print(f"  ... truncated; file count above is complete")
else:
    absent(bdir, "no briefing store on this deployment")
fs = si / "falsifier-series.jsonl"
if fs.is_file():
    print("proactive-card / attention series (rows in window):")
    for line in fs.read_text().splitlines():
        try: row = json.loads(line)
        except json.JSONDecodeError: continue
        if in_window(row.get("date", "")):
            print(f"  {row.get('date')}: cards_7d={row.get('proactive_cards_7d')} approved_7d={row.get('approved_7d')} acted_7d={row.get('acted_7d')}")
else:
    absent(fs, "no attention/card series")

# --- B. WHAT HE WROTE BACK ---------------------------------------------
sec("B. WHAT HE WROTE BACK (in window)")
cd = si / "captain-decisions.md"
if cd.is_file():
    blocks, cur = [], []
    for line in cd.read_text(errors="replace").splitlines():
        if line.startswith("## ") or line.startswith("### "):
            if cur: blocks.append(cur)
            cur = [line]
        elif cur: cur.append(line)
    if cur: blocks.append(cur)
    hits = [b for b in blocks if in_window(" ".join(b[:3]))]
    print(f"captain-decisions entries in window: {len(hits)} (of {len(blocks)} total)")
    for b in hits:
        body = [ln for ln in b if ln.strip()][:40]
        print("  --- entry ---")
        for ln in body: print(f"  {ln}")
        if len([ln for ln in b if ln.strip()]) > 40: print("  [entry truncated at 40 lines]")
else:
    absent(cd, "no decisions ledger")
al = si / "action-lessons.yml"
if al.is_file():
    print(f"\naction-lessons.yml (his machine-facing correction verbs; {mtime_age(al)}d since last write) — raw:")
    for ln in al.read_text(errors="replace").splitlines(): print(f"  {ln}")
else:
    absent(al, "no correction-verb store")
cv = si / "captain-vetoes.yml"
if cv.is_file():
    print(f"\ncaptain-vetoes.yml ({mtime_age(cv)}d since last write) — raw:")
    for ln in cv.read_text(errors="replace").splitlines(): print(f"  {ln}")
else:
    absent(cv, "no veto registry")
pp = si / "preference-pairs.jsonl"
if pp.is_file():
    lines = pp.read_text().splitlines()
    hits = [ln for ln in lines if in_window(ln)]
    print(f"\npreference-pairs rows: {len(lines)} total, {len(hits)} in window (store {mtime_age(pp)}d since last write):")
    for ln in hits[:10]: print(f"  {ln[:300]}")
else:
    absent(pp, "no preference-pair store")

# --- C. REPETITION ------------------------------------------------------
sec("C. REPETITION (mechanical counts; cross-entry judgment belongs to the reviewer)")
if al.is_file():
    tax = {}
    txt = al.read_text(errors="replace")
    for m in re.finditer(r"taxonomy:\s*(\S+)", txt):
        tax[m.group(1)] = tax.get(m.group(1), 0) + 1
    print(f"action-lessons rows per taxonomy: {tax or '(none)'}")
    subj = {}
    for m in re.finditer(r"subject:\s*(.+)", txt):
        s = m.group(1).strip()[:60]
        subj[s] = subj.get(s, 0) + 1
    rep = {k: v for k, v in subj.items() if v > 1}
    print(f"repeated subjects (count>1): {rep or '(none)'}")

# --- D. WHAT WAITED ON HIM / DWELL --------------------------------------
sec("D. OPEN ITEMS WAITING, BY DWELL")
nl = si / "needs-ledger.jsonl"
if nl.is_file():
    rows = []
    for line in nl.read_text().splitlines():
        try: row = json.loads(line)
        except json.JSONDecodeError: continue
        if row.get("status") == "open":
            a = age_days(row.get("first_seen", "")) or 0
            rows.append((a, row))
    rows.sort(reverse=True, key=lambda t: t[0])
    print(f"open rows: {len(rows)}")
    for a, row in rows[:15]:
        why = (row.get("why") or "")[:120]
        print(f"  {a}d open  [{row.get('kind')}] reminders={row.get('count')}  {row.get('id')}: {why}")
else:
    absent(nl, "no needs ledger")

# --- D2. AVAILABILITY (the budget every cost is judged against) ---------
# Read ROOT-RELATIVE and with no PyYAML dependency (this pack imports stdlib
# only, and the eval points CAPTAIN_SEAT_ROOT at a fixture tree — importing
# framework.env here would read the REAL deployment instead). Precedence
# mirrors framework.env.captain_availability(): the adjustment store's LAST
# valid entry, else the platform.yml onboarding stamp, else UNKNOWN. The store
# is machine-written and always emits minutes_per_day, so a line-shaped read is
# sufficient; a hand-mangled or mode-only row reads as absent here (the resolver
# would derive the band's minutes) — the same fail-closed DIRECTION, and it can
# only ever under-claim, never invent a budget.
sec("AVAILABILITY — what he said he has")
avail_store = root / "instance" / "config" / "captain-availability.yml"
declared = None
if avail_store.is_file():
    entry = {}
    for line in avail_store.read_text(errors="replace").splitlines():
        m = re.match(r"\s*-\s*at:\s*(\S+)", line)
        if m:
            entry = {"at": m.group(1)}
            continue
        m = re.match(r"\s*(minutes_per_day|mode|source):\s*(\S+)", line)
        if m and entry:
            entry[m.group(1)] = m.group(2)
        if entry.get("minutes_per_day"):
            declared = dict(entry, origin="adjusted")
if declared is None:
    plat = root / "instance" / "config" / "platform.yml"
    if plat.is_file():
        txt = plat.read_text(errors="replace")
        m = re.search(r"^captain_availability_minutes_per_day:\s*(\d+)", txt, re.MULTILINE)
        if m:
            declared = {"minutes_per_day": m.group(1), "origin": "onboarding"}
            m2 = re.search(r"^captain_availability_mode:\s*(\S+)", txt, re.MULTILINE)
            if m2:
                declared["mode"] = m2.group(1)
if declared:
    print(f"declared: {declared['minutes_per_day']} min/day  "
          f"mode={declared.get('mode', 'unstated')}  source={declared['origin']}")
    if declared.get("at"):
        age = age_days(declared["at"])
        print(f"set_at: {declared['at']}" + (f" ({age}d ago)" if age is not None else ""))
    print("judge every cost below against THIS budget — an ask that is fair at "
          "full_time is friction at minutes-a-day.")
else:
    absent(avail_store, "no declared availability — the org does not know how "
                        "much of the captain it is entitled to")

# --- D3. DATES HE SET (and whether the briefing still carries them) -----
# The AVAILABILITY dial's sibling evidence: availability is how much of him the
# org may spend, this is what he told the org to remember. Read ROOT-RELATIVE and
# stdlib-only for the same reason (the eval points CAPTAIN_SEAT_ROOT at a fixture
# tree; importing framework.env here would read the REAL deployment). Fold
# mirrors framework.env.captain_dates(): rows are append-only, LATEST ROW PER id
# WINS, so `date done` / `date move` append rather than edit.
#
# THE TRACKED COLUMN IS THE WHOLE POINT. The paid case (2026-07-26 dry run,
# finding 1) was a captain-set release date absent from twelve days of briefings,
# and the only way to SEE that is to check his date against what was actually
# sent. tracked_in_latest_briefing=NO on an open row is a cost he paid inside the
# window; a section that printed the dates but never checked delivery would be a
# sensor pointed at the store instead of at the failure.
sec("DATES HE SET — and whether the latest briefing still carries them")
dates_store = root / "instance" / "config" / "captain-dates.yml"
if dates_store.is_file():
    folded, cur = {}, None
    for line in dates_store.read_text(errors="replace").splitlines():
        m = re.match(r"\s*-\s*id:\s*(\S+)\s*$", line)
        if m:
            cur = {"id": m.group(1)}
            continue
        m = re.match(r"\s*(at|date|label|status|source|supersedes):\s*(.+?)\s*$", line)
        if m and cur is not None:
            val = m.group(2)
            if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
                val = val[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            cur[m.group(1)] = val
            if cur.get("date") and cur.get("label") and cur.get("status"):
                folded[cur["id"]] = dict(cur)
    open_rows = sorted((r for r in folded.values() if r.get("status") == "open"),
                       key=lambda r: (r["date"], r["id"]))
    # The latest briefing BODY: names are briefing-<UTC stamp>.md, so a name sort
    # is a time sort. An absent store is reported as such — "cannot check" is a
    # measured absence, never a silent "yes".
    latest_body, latest_name = None, None
    if bdir.is_dir():
        files = sorted(f for f in bdir.iterdir() if f.is_file())
        if files:
            latest_name = files[-1].name
            try: latest_body = files[-1].read_text(errors="replace")
            except OSError: latest_body = None
    print(f"open dates: {len(open_rows)}  (of {len(folded)} rows in the store)")
    if latest_name:
        print(f"latest briefing checked: {latest_name}")
    else:
        print("latest briefing checked: NONE — no briefing body on this "
              "deployment, so tracking cannot be checked (that absence is "
              "itself the finding)")
    for r in open_rows:
        if latest_body is None:
            tracked = "tracked_in_latest_briefing=UNCHECKED"
        elif r["label"] in latest_body:
            tracked = "tracked_in_latest_briefing=yes"
        else:
            tracked = "tracked_in_latest_briefing=NO"
        try:
            delta = (datetime.strptime(r["date"], "%Y-%m-%d")
                     .replace(tzinfo=timezone.utc) - now).days + 1
            when = f"in {delta}d" if delta > 0 else (
                "today" if delta == 0 else f"OVERDUE by {-delta}d")
        except ValueError:
            when = "unreadable date"
        print(f"  {r['date']}  \"{r['label']}\"  {tracked}  [{r['id']}]  ({when})")
    if open_rows:
        print("a date he set that the latest briefing does not carry is a cost "
              "he paid IN WINDOW — he had to hold it himself.")
else:
    absent(dates_store, "no dates on the org's books — nothing is holding a "
                        "date the captain set")

# --- E. CHANNEL HEALTH (the loops he believes are running) --------------
sec("E. CHANNEL HEALTH")
for name, what in [
    ("captain-decisions.md", "his rulings ledger"),
    ("captain-patterns.md", "his standing-preference ledger"),
    ("captain-intents.md", "his inferred-goals ledger"),
    ("action-lessons.yml", "his correction verbs"),
    ("preference-pairs.jsonl", "what-he-preferred pairs"),
]:
    p = si / name
    if p.is_file(): print(f"  {name}: last write {mtime_age(p)}d ago")
    else: absent(p, what)
scores = root / "instance" / "memory" / "briefing-scores.jsonl"
if scores.is_file():
    lines = scores.read_text().splitlines()
    print(f"  briefing-scores.jsonl: {len(lines)} scores recorded, last write {mtime_age(scores)}d ago")
    for ln in lines[-5:]: print(f"    {ln[:200]}")
else:
    print(f"  briefing scoring: ABSENT ({scores}) — briefings are sent with no recorded scoring loop on this deployment")
if fs.is_file():
    try:
        last = json.loads(fs.read_text().splitlines()[-1])
        latest = last.get("memory_ingestion", {}).get("captain_decision", {}).get("latest", "")
        print(f"  memory ingestion of captain decisions: latest ingested {latest} ({age_days(latest)}d ago)")
    except (json.JSONDecodeError, IndexError): pass
try:
    ping = subprocess.run(["redis-cli", "PING"], capture_output=True, text=True, timeout=3)
    if ping.stdout.strip() == "PONG":
        keys = subprocess.run(["redis-cli", "--scan", "--pattern", "cabinet:schedule:last-run:*"],
                              capture_output=True, text=True, timeout=5)
        n = len([k for k in keys.stdout.splitlines() if k.strip()])
        print(f"  scheduled-loop completion stamps in redis: {n}")
    else:
        print("  redis: unavailable (no PING)")
except (FileNotFoundError, subprocess.TimeoutExpired):
    print("  redis: unavailable (no redis-cli)")

# --- F. META WORKSPACE (optional; orchestrator altitude) ----------------
if meta:
    sec("F. ORCHESTRATOR/META SURFACES (his corrections that arrive as session prose)")
    lessons = meta / "LESSONS.md"
    if lessons.is_file():
        hits = [ln for ln in lessons.read_text(errors="replace").splitlines()
                if in_window(ln) and "captain" in ln.lower()]
        print(f"LESSONS.md rows in window mentioning the Captain: {len(hits)}")
        for ln in hits[:30]: print(f"  {ln[:300]}")
    else:
        absent(lessons, "no lessons ledger in meta dir")
    try:
        log = subprocess.run(
            ["git", "-C", str(meta), "log", f"--since={window_days} days ago",
             "--date=short", "--format=%ad %s", "--", "CLAUDE.md"],
            capture_output=True, text=True, timeout=10)
        lines = [ln for ln in log.stdout.splitlines() if ln.strip()]
        print(f"\ndoctrine (CLAUDE.md) commits in window — each is a rule he needed changed: {len(lines)}")
        for ln in lines[:20]: print(f"  {ln[:200]}")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("meta git history: unavailable")
    hb = sorted(meta.glob("HANDBACKS-*.md"))
    for h in hb:
        heads = [ln for ln in h.read_text(errors="replace").splitlines() if ln.startswith("## ")]
        print(f"\n{h.name} — sections (his open decision queue; oldest still open = dwell):")
        for ln in heads[:15]: print(f"  {ln[:200]}")

print("\nEND OF PACK — no judgments included; the reviewer relives this as the Captain.")
PYEOF
