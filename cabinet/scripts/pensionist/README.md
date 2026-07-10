# Pensionist test harness (captain-surface spec §7)

Scripted screenshots → vision model → rubric. The final plain-language gate
for every captain-facing card: a vision agent must explain each card in
plain words (see `rubric.md`); any card it can only explain with cabinet
vocabulary fails its arm.

## Pieces

| File | Role |
|---|---|
| `gen_fixtures.py` | Synthetic private-census `out/queue.json` (invented review data — no real pids, no secrets). |
| `render_tg.py` | Renders the branch's TG cards through the REAL pipeline (decision_card → charter → gate.render_card) to `out/tg.html` + `out/tg-lint.json` (plain.lint over every visible string — must be `[]`). |
| `shots/` | Committed screenshot fixtures (dashboard /queue faces + the TG card sheet) — the review baseline of 2026-07-10. |
| `run.py` | The harness: each shot → vision model (claude CLI) → the 3 rubric questions → per-card PASS/WARN/FAIL, answers linted against `plain.BANNED`. |
| `rubric.md` | The questions + the fail law. |

## Run

```bash
python3.12 cabinet/scripts/pensionist/gen_fixtures.py     # census fixture
python3.12 cabinet/scripts/pensionist/render_tg.py        # TG html + lint
python3.12 cabinet/scripts/pensionist/run.py              # vision pass
```

`run.py` needs the `claude` CLI on PATH (it reads each PNG with a vision
prompt). This is a **manual/release gate**, not a network-free CI step —
CI carries the deterministic teeth instead (pytest/vitest jargon linters,
`tg-lint.json` empty). Exit codes: 0 all pass · 1 any FAIL · 3 claude CLI
missing.

## Regenerating shots

- TG sheet: open `out/tg.html` in a browser at 420 px column width and
  screenshot.
- Dashboard: point the dashboard at the fixture census
  (`CABINET_ATTENTION_DIR=cabinet/scripts/pensionist/out` after
  `mkdir out/attention && cp out/queue.json out/attention/`), run
  `npm run dev` in `cabinet/dashboard`, and capture `/queue` (desktop +
  390 px mobile), one armed confirm per verb, and an open Details block.

Shots must be re-captured whenever surface copy changes; `render_tg.py`
output going stale is caught by its own lint step, the PNGs by review.
