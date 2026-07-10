# Testburg fixture — the fully synthetic demo cabinet

**Everything in this directory is fiction.** It is the licensing-safe,
screenshot-safe demo estate for the Perfect Cabinet demo kit (egg ledger
row PC-B, Captain approval 2026-07-09): a coherent three-day story for the
fictional captain **Ada Testburg** and her two lanes, **bakery-site** and
**newsletter**. No value in here refers to a real person, employer, chat id,
machine path, or deployment. Synthetic e-mail addresses use `example.com`;
synthetic absolute paths use `/opt/testburg-cabinet/…` (a machine that does
not exist); ids are human-readable slugs (`itm-testburg-0042`) rather than
opaque uuids so a demo audience can follow the story.

## Why this exists

Public demos and screenshots must never show captain-personal or employer
data (PC-B scope item 7). This fixture is what the demo dashboard and the
hero-demo runbook point at instead of the live estate:

- `cabinet/scripts/demo-dashboard.sh` serves the dashboard against this
  fixture (see that script's header for the env contract).
- `docs/runbooks/hero-demo-2026-07-10.md` uses it for the public variant of
  the goal-at-night → morning-briefing demo.

## Honesty labeling (binding)

Per the honesty doctrine: **demo artifacts always say they are demo.** This
README is the top-level label; additionally the seeded receipt row in the
undo journal carries `"demo": true` and says in its own `why` that it was
seeded. Nothing in this fixture may ever be presented as a real cabinet's
history. Honest empties beat invented data — the fixture deliberately does
NOT fake surfaces the product would leave empty on a fresh hatch (no fake
Redis state, no fake officer transcripts).

## The leak-audit contract (enforced by CI-shape test)

`cabinet/scripts/tests/test_testburg_fixture.py` walks EVERY file under this
directory (contents and filenames) and fails on any real-value pattern from
its `BANNED_PATTERNS` list (the captain's given/family names, employer and
product domains, colleague first names, home directory prefix — all
case-insensitive — plus any digit run of 9+, which is telegram-chat-id
shaped). The authoritative list lives in the test, deliberately NOT
reprinted here: this directory must never contain those byte sequences,
not even as documentation.

Mind the substring trap when editing prose here: several ordinary English
words (for example the participle of "desig·n·ate", or "coordi·n·ate")
contain a banned name as a plain substring — the test will catch them;
reword. The same test asserts schema parity: chronicle rows parse through
the REAL ingest normalizers (`cabinet/scripts/world-chronicle.py`) and
undo-journal rows load through the REAL product readers
(`framework/frontdoor/action_undo.py` + `framework/attention/acted_overlay.py`).

## Layout

    README.md                      this contract
    generate.py                    deterministic generator for world/ + undo/
    world/chronicle-2026-07-0{7,8,9}.jsonl
                                   3 story days, schema-matched to
                                   shared/interfaces/world/chronicle-*.jsonl
    undo/undo-journal-2026-07-0{8,9}.jsonl
                                   6 logical acted rows (8 physical lines:
                                   one write-ahead+enrichment pair, one
                                   executed+reversal pair) exercising every
                                   receipt field
    drafts/newsletter-issue-1.md   one queued draft artifact (propose-first)
    notes/tier2/cos/…, notes/tier2/cro/…
                                   two tier2-style officer memory notes
    briefing/first-briefing-2026-07-07.md
                                   the hatch-day first briefing (local-first
                                   receipt shape, propose-only cards)
    config/product.yml             minimal Testburg product identity for the
                                   demo dashboard
    config/projects/testburg.yml   the Testburg project card demo-dashboard.sh
                                   stages for the dashboard's env-honoring
                                   file readers (active-project + projects)

## The three-day story (all times UTC; "story now" = 2026-07-10 08:00Z)

- **2026-07-07 (hatch day)** — the cabinet hatches; cos and cto start
  sessions; the bakery-site launch mission is staked; genesis proposes
  outcome cards; the first briefing (in `briefing/`) is written locally.
- **2026-07-08** — cos saves the launch checklist to officer memory
  (acted, undo window later expires); cpo moves the pilot-bake card to
  Done (acted — Ada reverses it next morning); cro stages the newsletter
  draft (propose-first, still queued in `drafts/`).
- **2026-07-09** — coo books the flour-delivery reminder on the calendar
  (acted, undo still active); cro saves audience research (acted, cost
  honestly unattributed); cpo tags the oven-upgrade card supplier-blocked
  (acted, active); Ada undoes the premature Done from her morning receipt
  (the reversal line); a seeded `demo: true` row closes the story — a
  FIXTURE-ONLY journal row (see the `demo` bullet below; the live seeder
  never journals).

## Receipt-field contract exercised by the undo journal (Wave B additive)

Base row schema is `framework/frontdoor/action_undo.py::new_row` (jid, ts,
pid, cid, step, kind, backend, lane, subject, actor, action_type, prestate,
created, inverse, executed_at, reversed_at, ttl_expires_at, status, canary,
payload_sha256). The Wave-B receipt grammar adds, additively:

- `why` (string) — the human reason the act happened; present from the
  write-ahead line on (the card's why is known before the mutation). Per
  `framework/frontdoor/action_language.py::why_of`, an absent why is an
  OMITTED field — the grammar never invents a rationale.
- `cost` (object) — the write-time-stamped per-act spend, appearing on the
  enrichment line (measured after the act), in EXACTLY the
  `action_language._valid_cost` shape: a subset of
  `{"usd", "tokens_in", "tokens_out", "model", "source"}` with at least one
  non-negative numeric, e.g.
  `{"usd": 0.0148, "tokens_in": 1930, "tokens_out": 210, "source": "lane-metered"}`.
  Unknown keys fail closed. An UNATTRIBUTED row simply OMITS the field —
  the receipt renders the honest `cost: unattributed`, never an invented
  or aggregate-apportioned number.
- `demo` (bool) — present and `true` ONLY on seeded demo rows (the
  /receipts page badges them); absent on real rows. Per the
  `cabinet/scripts/emit-demo-receipt.sh` doctrine a demo row also carries
  `inverse.op: "none"` with a demo reason — a receipt never claims an undo
  that is not registered, so `undo` against the seeded row is an honest
  no-op. NOTE the live seeder's final shape differs on WHERE the row
  lives: `emit-demo-receipt.sh` validates its row through the real schema
  but NEVER appends it to the undo journal — its whole artifact is the
  rendered receipt file at `instance/memory/demo-receipt.md`, and a live
  day-one journal (hence live `/receipts`) is honestly empty. The
  journaled `demo: true` row HERE is a fixture-only exercise of the
  receipts page's DEMO-badge defense-in-depth path.

States covered: **active** (executed, ttl in the future at story-now),
**expired** (executed, ttl passed), **undone** (status `reversed` +
`reversed_at`). The write-ahead/enrichment pair and the executed/reversal
pair share a `jid` each, so readers exercise last-write-wins collapse.

## Regenerating

    python3.12 cabinet/fixtures/testburg/generate.py

is deterministic (fixed story timestamps, real sha256 of the shipped note
files) and rewrites `world/` and `undo/` in place. Run the leak-audit test
after any edit:

    python3.12 -m pytest cabinet/scripts/tests/test_testburg_fixture.py -q
