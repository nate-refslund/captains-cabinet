# Review artifact — feat/inbound-archive-read cp1 (2026-07-17)

Batch: read side of the captain-inbound archive — reader lib
(`cabinet/scripts/lib/captain_inbound.py`), CLI
(`cabinet/scripts/captain-inbound.py`), 20-test suite, doc pointers.
~950 lines → FW-019 artifact.

## What shipped
- Lib: `iter_rows(days)` (tolerant loader, feed-discipline), `latest(n,
  kinds)`, `get(dm_id | bare message_id → ambiguity shape: newest copy +
  `matches` list ONLY when ambiguous)`, `search` (all-terms lexical,
  newest-first), `semantic_search` (shells to the existing
  `search-memory.sh` with `--type telegram_dm`; joins hits back to
  verbatim archive rows via ref == dm_id — capture-captain-dm.sh ingests
  `source_id = tg-<chat>-<mid>`, byte-identical to the archive key).
  Read-only, stdlib-only, py3.9-safe. Dedup last-wins incl. position.
- CLI: `latest / get / search [--semantic]`, `--kind`, `--json`; exit 0 =
  hits, 2 = miss/unavailable (mirrors chair-recent-msgs.py).
- Built by a spec'd builder agent in an isolated worktree; the builder's
  one blocking claim (write side not on master) was FALSE — it compared
  against the stale live checkout's local master; `git merge-base
  --is-ancestor 5d35796d origin/master` confirmed landed.

## Review
Independent adversarial review (fresh-context Fable): **SHIP-WITH-FIXES**
— all applied in this commit:
- P1-1 (the big one): `telegram_dm` memory rows ALSO carry OFFICER
  outbound replies (`tg-out-<ts>-<officer>`, post-reply-memory.sh) and
  id-less inbound fallbacks (`tg-in-…`); the prefix-based dm_id labeling
  would have rendered officer speech as Captain speech — the precise
  failure the archive exists to kill. Fixed: exact-shape
  `tg-<numeric chat>-<numeric mid>` regex (negative group-chat ids kept),
  docstrings corrected, pinned by a dedicated test (officer refs →
  dm_id "", negative-chat ref → real dm_id).
- P1-2: `available: True` overclaimed DB reachability — the entrypoint
  discards psql stderr and prints "No results found." + exit 0 on a dead
  DB. Docstring truthed (available = entrypoint ran, NOT DB reachable);
  `stderr_tail` now surfaced on every available=True result so the
  embedding-degrade WARN is never eaten; honest-zero contract pinned.
- P2-3: output-format drift now degrades LOUDLY — banner present ∧ zero
  parsed hits ∧ no "No results found." → `available: False, reason:
  format drift` (the banner only prints when hits exist). Pinned with a
  reordered-format transcript.
- P2-4: CLI `--kind` with `--semantic` no longer silently ignored —
  filters to hits whose archive join matches; dropped un-joined hits are
  counted to stderr.
- P2-6: runbook §10 row + `archive_captain_dm` docstring now name the
  reader (the write side said "readers dedup by dm_id" without naming the
  tool).
- P2-7 (no change, decision recorded): full-archive RAM dedup per call is
  accepted at captain-DM volume (one human; years ≈ tens of MB).
- P3 notes accepted as-is (flag-shaped query dies visibly in the
  entrypoint's parser; CLI doesn't expose the semantic timeout).

Reviewer-verified sound: read-only holds everywhere; no `shell=True`, no
injection (query is one argv element; entrypoint parameterizes via
`psql -v`); UTC day-window correct by construction; negative-chat dm_ids
round-trip (writer's `_sanitize_id` preserves `-`); exit codes + `--json`
validity consistent; py3.9 verified; conftest fences effective;
Popen-leak guard effective; no personal tokens; egg/layer-sep neutral.

## Verification (post-fixes)
- lib/tests: **236 passed** (incl. 20 reader tests; CI count comment
  updated to 236).
- poller family: 71 passed (docstring edit touched the poller).
- py_compile both new files; CLI smoke (verbatim Danish, bare-mid get,
  semantic degrade exit 2) from the build phase.
