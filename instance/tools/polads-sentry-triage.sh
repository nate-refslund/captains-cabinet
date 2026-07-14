#!/usr/bin/env bash
# polads-sentry-triage.sh — one-call "verified-noise discriminator" for PolAds Sentry.
#
# WHY: when polads-ceo is the prod-eyes for a Sentry-blind Chair, raw error counts must
# never be relayed as incidents. This runs the 4-step discriminator (reflection
# 2026-07-11-absence-prodeyes.md; Library record #11) in one command instead of the 4-5
# ad-hoc curls (with endpoint/timeout gotchas) that each burst triage otherwise needs:
#   1) live-verify current serving state (smoke the prod DOMAIN)
#   2) freshness/delta            (lastSeen advancing=ongoing vs frozen=stopped; count vs baseline)
#   3) attribution                (url tag = prod-domain+resolved-path=REAL-USER
#                                  vs deployment-hash-domain / unresolved route-template=BOT/NOISE)
#   4) emit a per-issue + overall VERDICT (noise|real|inconclusive)
#
# Instance/lane-scoped by design (PolAds smoke URLs + PolAds Sentry project). The
# foundation-generalization to a CRO-owned sentry-triage.sh is a separate (Nate-gated) call.
#
# Usage:  bash instance/tools/polads-sentry-triage.sh [--limit N] [--baseline "SR=2843,FQ=2811"]
#   --limit N     how many top-frequency issues to show (default 6)
#   --baseline S  optional "SHORTID_SUFFIX=count,..." to show a delta vs a known baseline
#                 (suffixes match the trailing char of the Sentry shortId, e.g. SR-> -3? use the
#                  literal suffix: pass "3=2843,2=2811"). Optional; freshness+attribution stand alone.
#
# Reads cabinet/.env for SENTRY_AUTH_TOKEN + CABINET_SENTRY_ORG + CABINET_SENTRY_PROJECT.
# Never prints the token. Exit 0 always (a triage tool reports; it does not gate a pipeline).
set -uo pipefail

CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CURL=/usr/bin/curl
CT=6            # --connect-timeout (a slow Sentry response must not eat the whole tick)
MT=12           # --max-time
LIMIT=6
BASELINE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --limit)    LIMIT="${2:?--limit needs a value}"; shift 2 ;;
    --baseline) BASELINE="${2:?--baseline needs a value}"; shift 2 ;;
    -h|--help)  sed -n '2,25p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 0 ;;
  esac
done

# --- creds (fail-closed; never echo the token) --------------------------------
if [ -f "$CABINET_ROOT/cabinet/.env" ]; then
  set -a; . "$CABINET_ROOT/cabinet/.env" >/dev/null 2>&1; set +a
fi
ORG="${CABINET_SENTRY_ORG:-}"; PROJ="${CABINET_SENTRY_PROJECT:-}"; TOK="${SENTRY_AUTH_TOKEN:-}"
if [ -z "$TOK" ] || [ -z "$ORG" ] || [ -z "$PROJ" ]; then
  echo "FAIL: missing Sentry creds in cabinet/.env (need SENTRY_AUTH_TOKEN + CABINET_SENTRY_ORG + CABINET_SENTRY_PROJECT). Cannot triage." >&2
  exit 0
fi

NOW_UTC="$(/bin/date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "== PolAds Sentry triage @ $NOW_UTC  (org=$ORG project=$PROJ) =="

# --- (1) live-verify prod serving state ---------------------------------------
echo "-- (1) prod smoke (polads.eu) --"
PROD_OK=1
for p in /da/search /en/terms-of-sale; do
  code="$($CURL -s -o /dev/null -w '%{http_code}' --connect-timeout "$CT" --max-time "$MT" "https://polads.eu$p" 2>/dev/null)"
  echo "   $p -> ${code:-TIMEOUT}"
  [ "$code" = "200" ] || PROD_OK=0
done

# --- (2)+(3) issues by freq, freshness, attribution ---------------------------
SCRATCH="$(mktemp -t polads-sentry.XXXXXX 2>/dev/null || echo /tmp/polads-sentry.$$)"
trap 'rm -f "$SCRATCH" "$SCRATCH".ev' EXIT
code="$($CURL -s -o "$SCRATCH" -w '%{http_code}' --connect-timeout "$CT" --max-time "$MT" \
  -H "Authorization: Bearer $TOK" \
  "https://sentry.io/api/0/projects/$ORG/$PROJ/issues/?query=is:unresolved&sort=freq&statsPeriod=24h&limit=$LIMIT" 2>/dev/null)"
echo "-- (2) Sentry issues (freq, 24h)  [HTTP ${code:-TIMEOUT}] --"
if [ "$code" != "200" ]; then
  echo "   Sentry unreachable/non-200 this run — retry; prod smoke above is the fallback signal."
  echo "== VERDICT: INCONCLUSIVE (Sentry read failed); prod smoke $( [ "$PROD_OK" = 1 ] && echo GREEN || echo NON-200 ) =="
  exit 0
fi

# The event fetch (attribution) needs the numeric id; org-scoped endpoint (project-scoped 404s).
# fetch_url <numeric_id> -> prints the failing event's url tag (or empty).
fetch_url() {
  local id="$1"
  [ -n "$id" ] || { echo ""; return; }
  $CURL -s -o "$SCRATCH".ev --connect-timeout "$CT" --max-time "$MT" \
    -H "Authorization: Bearer $TOK" \
    "https://sentry.io/api/0/organizations/$ORG/issues/$id/events/latest/" 2>/dev/null
  python3 - "$SCRATCH".ev <<'PY' 2>/dev/null
import json,sys
try:
    e=json.load(open(sys.argv[1]))
    tags={t.get('key'):t.get('value') for t in e.get('tags',[])}
    print(tags.get('url') or '')
except Exception:
    print('')
PY
}

# Parse issues; classify freshness; for issues active in the last ~2h, attribute via url tag.
# Emits, per issue: shortId | count | lastSeen(age) | freshness | [attribution] | verdict
python3 - "$SCRATCH" "$BASELINE" "$NOW_UTC" <<'PY' > "$SCRATCH".rows
import json,sys,datetime
issues=json.load(open(sys.argv[1]))
baseline={}
if sys.argv[2]:
    for kv in sys.argv[2].split(','):
        if '=' in kv:
            k,v=kv.split('=',1); baseline[k.strip()]=v.strip()
now=datetime.datetime.strptime(sys.argv[3],"%Y-%m-%dT%H:%M:%SZ")
def age_min(ls):
    if not ls: return None
    s=ls[:19]
    try: t=datetime.datetime.strptime(s,"%Y-%m-%dT%H:%M:%S")
    except Exception: return None
    return (now-t).total_seconds()/60.0
for i in issues if isinstance(issues,list) else []:
    sid=i.get('shortId',''); cid=str(i.get('id','')); cnt=i.get('count','?')
    ls=i.get('lastSeen') or ''; am=age_min(ls)
    # freshness: fired in the last 15 min = ongoing; else stopped/frozen
    fresh = 'ongoing' if (am is not None and am<=15) else ('frozen' if am is not None else 'unknown')
    # active-enough to attribute: fired within last 2h
    attribute = (am is not None and am<=120)
    suffix = sid.split('-')[-1] if '-' in sid else ''
    delta=''
    if suffix in baseline:
        try: delta=' Δ=%+d' % (int(cnt)-int(baseline[suffix]))
        except Exception: delta=''
    print('\t'.join([sid,cid,str(cnt),(ls[:19] or '-'),
                     ('%.0fm'%am if am is not None else '-'),
                     fresh,('ATTR' if attribute else 'skip'),delta]))
PY

OVERALL_REAL=0; OVERALL_ONGOING=0; ANY=0
while IFS=$'\t' read -r sid cid cnt lastseen agem fresh attr delta; do
  [ -n "$sid" ] || continue
  ANY=1
  verdict="noise"
  attribution=""
  if [ "$attr" = "ATTR" ]; then
    url="$(fetch_url "$cid")"
    if [ -z "$url" ]; then
      attribution="url=?"; verdict="inconclusive"
    else
      host="$(printf '%s' "$url" | sed -E 's#^https?://([^/]+)/.*#\1#')"
      path="$(printf '%s' "$url" | sed -E 's#^https?://[^/]+##')"
      # bot/noise tells: deployment-hash vercel.app host, OR unresolved next.js route template in path
      if printf '%s' "$host" | grep -qE 'vercel\.app$' || printf '%s' "$path" | grep -qE '\[[a-zA-Z]'; then
        attribution="host=$host path=$path -> BOT/template"; verdict="noise"
      elif printf '%s' "$host" | grep -qE '(^|\.)polads\.eu$'; then
        attribution="host=$host path=$path -> PROD-DOMAIN+resolved"; verdict="real-user-suspect"; OVERALL_REAL=1
      else
        attribution="host=$host path=$path -> unclassified"; verdict="inconclusive"
      fi
    fi
  fi
  [ "$fresh" = "ongoing" ] && OVERALL_ONGOING=1
  printf '   %-20s count=%-6s lastSeen=%s (%s, %s)%s  %s -> %s\n' \
    "$sid" "$cnt" "$lastseen" "$agem" "$fresh" "$delta" "$attribution" "$verdict"
done < "$SCRATCH".rows

echo "-- (3) attribution: bot/template vs prod-domain+resolved-path (only for issues active <2h) --"
echo "-- (4) VERDICT --"
if [ "$ANY" = 0 ]; then
  echo "== VERDICT: NO unresolved issues in 24h. prod smoke $( [ "$PROD_OK" = 1 ] && echo GREEN || echo NON-200 ). =="
elif [ "$OVERALL_REAL" = 1 ]; then
  echo "== VERDICT: REAL-USER-SUSPECT — at least one active issue attributes to polads.eu + a resolved user path. INVESTIGATE + surface to cos with the affected route. prod smoke $( [ "$PROD_OK" = 1 ] && echo GREEN || echo NON-200 ). =="
elif [ "$PROD_OK" != 1 ]; then
  echo "== VERDICT: PROD SMOKE NON-200 — investigate serving state regardless of Sentry attribution. =="
else
  echo "== VERDICT: NOISE — no active issue attributes to polads.eu real users (active issues are bot/route-template; older ones frozen); prod GREEN. $( [ "$OVERALL_ONGOING" = 1 ] && echo 'NOTE: an issue is still ongoing (lastSeen<15m) — re-run to confirm it stops.' || echo 'All bursts frozen/stopped.') Escalate only on recurrence or a shift to real-user/prod-domain tags. =="
fi
exit 0
