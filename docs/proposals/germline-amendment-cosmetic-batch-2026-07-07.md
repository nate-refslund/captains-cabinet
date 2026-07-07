# Germline amendment — cosmetic batch, germline window 2 (2026-07-07, egg row CG-13)

**Status:** STAGED on branch `feat/germline-window-2` (worktree-staged — the
live checkout's schg boundary was never opened; relock discipline: one
window, relock same day — D3). Reply **"revert cosmetic batch"** to drop the
branch commit (one-revert rollback below).

**Ratification chain (already-ruled — reference only, do NOT re-paste):**

- **Egg plan row CG-13** — `docs/plans/operative-egg-plan-2026-07-07.md`:
  "Batch for the next scheduled unlock window: NATE-DECISION →
  CAPTAIN-RULING comment scrubs (authority-matrix.yml, matrix.py);
  settings.json permissions-block audit (R151); act-first-surfaces.yml
  example-split (R126); CG-8 host-grant removal; CG-15 pre-tool-use
  write-protect entry. One window, one amendment doc."
- **Germline-window-2 order (2026-07-07)** — executed under the 2026-07-07
  standing full-autonomy grant.

**Batch composition note:** CG-8 (mcp-scope.yml host-grant removal) shipped
EARLIER with its own record
(`germline-amendment-host-grant-removal-2026-07-07.md`) and is NOT re-done
here; CG-15 ships in this window paired with R104 under
`germline-amendment-constitution-retirement-2026-07-07.md` (it is a
functional retirement, not a cosmetic). This doc covers the three cosmetic
items.

**What (the germline edit set):**

1. **Comment scrubs — `framework/policies/authority-matrix.yml` (6 sites) +
   `framework/authority/matrix.py` (7 sites):** every `NATE-DECISION` token
   → `CAPTAIN-RULING`. COMMENT/PROSE ONLY — zero verdict-table, ladder,
   posture, or code-path change (`yaml.safe_load` clean; full authority
   suite green; the de-nate doctrine is why: framework text names the ROLE,
   never the person). Test-file comments that cite the old ruling name are
   left as historical citations (out of the row's named scope).
2. **`.claude/settings.json` permissions-block AUDIT (R151 — verify +
   minimal prune, no restructure):** VERIFIED, ZERO PRUNE —
   - every `permissions.allow` MCP entry maps to a live server in
     `.mcp.json` (notion / neon / linear / vercel / redis-trigger-channel /
     library / make) or an enabled plugin (`telegram@claude-plugins-official`
     for `mcp__plugin_telegram_telegram`); no dead grants (the CG-8 class)
     found;
   - `permissions.deny` (rm -rf / shutdown / reboot / dd / mkfs) verified
     present and unchanged — defense-in-depth under the hook, which remains
     the real floor;
   - FINDING (recorded, deliberately NOT changed under the prune-only
     mandate): the allow entries `mcp__redis_trigger_channel` and the
     server name `redis-trigger-channel` differ underscore-vs-dash; if
     permission matching is verbatim this entry is inert (the hook + auto
     defaultMode mask it). Candidate for the NEXT window after a live
     matching check — flagged, not fixed, because a wrong "fix" could widen
     or break a working grant. The file's BYTES are therefore untouched by
     this batch.
3. **`instance/config/act-first-surfaces.yml.example` (NEW, unlocked — the
   R126 example split):** the framework-shippable twin with EMPTY
   `denylist`/`cascade_gated`, the corruption-honesty contract spelled out
   (absent ⇒ empty denylist; present-but-unparseable ⇒ every board gated),
   the executor obligations, and a pointer that ruling provenance lives in
   the Captain ledger. The LIVE `instance/config/act-first-surfaces.yml`
   (the Captain's 2026-07-04 access-inversion ruling + cascade enumeration)
   is BYTE-UNTOUCHED — it stays the deployment's ruling and stays
   germline-locked (immutable-core files entry unchanged; its `.example`
   sibling stays unlocked exactly like the other `.example` twins).

**Gates (run in the staging worktree, 2026-07-07):**

- `python3.12 -m pytest framework/authority framework/tests -q` → green
  (matrix loader/validator + lockstep + amendment lint over the scrubbed
  files).
- `python3.12 -c "yaml.safe_load(authority-matrix.yml)"` → clean.
- `grep -c NATE-DECISION framework/policies/authority-matrix.yml
  framework/authority/matrix.py` → 0 + 0.
- `ls -lO instance/config/act-first-surfaces.yml` (live checkout, after
  merge + relock) → schg re-applied; example twin exists.

**One-revert rollback:** `git revert` of the CG-13 commit on
`feat/germline-window-2` restores the `NATE-DECISION` comment tokens in
`authority-matrix.yml` + `matrix.py` and removes
`act-first-surfaces.yml.example`; `.claude/settings.json` needs no rollback
(audit made no byte changes). Then `sudo bash
cabinet/scripts/germline-lock.sh lock` on the live checkout.
