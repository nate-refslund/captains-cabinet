"""Render the branch's Telegram cards to an HTML fixture (NO live sends).

Uses the REAL pipeline: decision_card.render → the send_card item shape →
charter.resolve → gate.render_card, so the text is byte-what-the-captain-sees.
Buttons come from the same render kwargs. Output: tg.html (Telegram-look
mock) + tg-lint.json (plain.lint over every visible string).
"""
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
WT = Path(sys.argv[1]) if len(sys.argv) > 1 else _HERE.parents[3]
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else _HERE.parent / "out"
sys.path.insert(0, str(WT))

from framework.attention import charter, gate  # noqa: E402
from framework.attention import plain as plainlaw  # noqa: E402
from framework.comms.surface import briefing_card, decision_card, digest, pacing  # noqa: E402

NOW = datetime.now(timezone.utc)
CFG = {"dashboard_url": "https://cabinet.example", "captain_tz": "Europe/Copenhagen"}
CH = charter.load_charter()

fixdoc = json.loads((OUT / "queue.json").read_text())
CARDS = {c["id"]: c for c in fixdoc["decisions"] + fixdoc["directions"]}


def gate_text(kwargs, state="open"):
    """send_card item shape → the gate's final rendered text."""
    item = {"kind": kwargs.get("kind", "action-card"),
            "subject": kwargs.get("subject", ""),
            "situation": kwargs.get("situation", ""),
            "lane": kwargs.get("lane"),
            "evidence": list(kwargs.get("evidence") or []),
            "urgency": kwargs.get("urgency"), "steps": [],
            "state": state, "deadline_iso": kwargs.get("deadline_iso"),
            "pid_marker": kwargs.get("pid_marker"),
            "injection_suspect": False}
    resolved = charter.resolve(item, CH)
    return gate.render_card(item, resolved, state=state)


PANELS = []  # (label, text, buttons rows)


def add(label, kwargs, state="open"):
    PANELS.append((label, gate_text(kwargs, state=state), kwargs.get("buttons")))


# --- paced single-decision cards (open) --------------------------------------
for cid, label in [("sit-d1", "Draft message (external reply)"),
                   ("sit-d3", "Suggestion (spends money)"),
                   ("sit-d2", "Permission request"),
                   ("sit-d4", "Escalated to you"),
                   ("sit-d5", "Rule change — typed sign-off ritual")]:
    add(label, decision_card.render(CARDS[cid], state="open", now=NOW, cfg=CFG))

# --- decided faces (edit-in-place) -------------------------------------------
done = decision_card.render(CARDS["sit-r2"], state="done", now=NOW, cfg=CFG)
add("After approve (reversible → Undo offered)", done, state="done")
skipped = decision_card.render(CARDS["sit-d3"], state="skipped", now=NOW, cfg=CFG)
add("After 'No'", skipped, state="skipped")

# --- briefing as ONE card -----------------------------------------------------
add("Morning briefing card",
    briefing_card.render(
        "Quiet night. The bakery-site support queue is empty; one deploy shipped.",
        {"pending_captain_items": 5}, now=NOW, cfg=CFG))

# --- pacing nudge lifecycle ----------------------------------------------------
add("Nudge (decisions waiting)", pacing._nudge_kwargs(("nudge", 5), CFG))
add("Batch offer (after 3 cards)", pacing._nudge_kwargs(("batch_offer", 2), CFG))
add("All clear", pacing._nudge_kwargs(("all_clear",), CFG))

# --- FYI digest fold (rides the briefing, shown as its summary text) ----------
fyis = [{"what": "Nightly backup finished (14 GB)", "lane": "org", "kind": "fyi"},
        {"what": "Newsletter signup-form test suite green", "lane": "newsletter", "kind": "fyi"},
        {"what": "3 new bread orders on the bakery site yesterday", "lane": "bakery-site", "kind": "fyi"}]
item = digest.fold_fyi(fyis, now=NOW)
PANELS.append(("FYI digest (folded into the briefing)",
               item["payload"]["summary"], None))

# --- lint every visible string -------------------------------------------------
violations = []
for label, text, buttons in PANELS:
    for hit in plainlaw.lint(text):
        violations.append({"panel": label, "in": "body", **hit, "text": text})
    for row in (buttons or []):
        for b in row:
            for hit in plainlaw.lint(b.get("text", "")):
                violations.append({"panel": label, "in": "button", **hit,
                                   "text": b.get("text", "")})
(OUT / "tg-lint.json").write_text(json.dumps(violations, indent=1))

# --- Telegram-look HTML mock ---------------------------------------------------
def btn_html(b):
    return f'<div class="tgbtn">{html.escape(b.get("text", ""))}</div>'


bubbles = []
for label, text, buttons in PANELS:
    rows = ""
    if buttons:
        rows = "".join(
            f'<div class="tgrow">{"".join(btn_html(b) for b in row)}</div>'
            for row in buttons)
    bubbles.append(f"""
  <div class="panel">
    <div class="cap">{html.escape(label)}</div>
    <div class="msg">
      <div class="bubble"><span class="sender">First Mate</span>
        <pre>{html.escape(text)}</pre>
        <span class="time">09:12</span>
      </div>
      {rows}
    </div>
  </div>""")

page = f"""<!doctype html><meta charset="utf-8">
<title>TG card renders — captain-surface-v2</title>
<style>
 body {{ background:#0e1621; color:#fff; font:16px/1.45 -apple-system,'Helvetica Neue',sans-serif;
        margin:0; padding:24px; display:flex; flex-wrap:wrap; gap:28px; }}
 .panel {{ width:420px; }}
 .cap {{ color:#7d8b99; font-size:12px; text-transform:uppercase; letter-spacing:.06em;
        margin:0 0 6px 4px; }}
 .bubble {{ background:#182533; border-radius:12px 12px 12px 4px; padding:8px 12px 6px;
        max-width:400px; box-shadow:0 1px 1px rgba(0,0,0,.35); }}
 .sender {{ color:#6ab3f3; font-size:13px; font-weight:600; display:block; }}
 pre {{ margin:2px 0 0; white-space:pre-wrap; word-wrap:break-word;
        font:15px/1.4 -apple-system,'Helvetica Neue',sans-serif; }}
 .time {{ color:#6d7f8f; font-size:11px; float:right; margin-top:2px; }}
 .tgrow {{ display:flex; gap:2px; margin-top:2px; max-width:400px; }}
 .tgbtn {{ flex:1; background:rgba(32,43,54,.92); color:#7ab4e0; text-align:center;
        border-radius:7px; padding:9px 6px; font-size:14px; white-space:nowrap;
        overflow:hidden; text-overflow:ellipsis; }}
</style>
{''.join(bubbles)}
"""
(OUT / "tg.html").write_text(page, encoding="utf-8")
print(f"panels={len(PANELS)} lint_violations={len(violations)}")
for v in violations:
    print("LINT:", v["panel"], v["in"], v["term"], "→", repr(v["text"][:90]))
