<!-- DRAFT — NOT FOR PUBLICATION. Publishing is CG-7 Captain-gated. -->

**DRAFT — NOT FOR PUBLICATION. Publishing is CG-7 Captain-gated.**

# Honest capability comparison — Captain's Cabinet vs OpenClaw vs Hermes

**Sourcing rule (binding):** Cabinet cells cite this repo's docs and
measured runs. OpenClaw and Hermes cells carry ONLY the qualitative
findings of the program's two category research analyses, as summarized in
[`category-narrative.md`](./category-narrative.md) — no numbers are
invented for competitors, and any cell the analyses cannot support says
**unverified**. Competitor products move fast: every competitor cell must
be re-checked against their current public docs before publication, and
corrections after publication are welcome and will be applied.

| Capability | Captain's Cabinet | OpenClaw | Hermes (Nous) |
|---|---|---|---|
| **Onboarding friction** | One-command hatch (`hatch.sh --defaults`); measured ~8 s clean-room with deps present, TTFR 1–2 s; first receipt in minutes once hatched; full move-in bar ≤90 min — ratified, **not yet timed on a bare Mac** | Messaging-native onboarding; distance from curiosity to a working agent measured in minutes (per analysis — the category's best first-run) | unverified |
| **Memory / self-improvement** | Skill induction + evolution loop; every change admitted by an eval gate the org cannot edit | unverified | Proved the accumulation axis: agent-authored skills persist and compound (per analysis); gating model unverified |
| **Governance / receipts** | Per-act receipt: what / why / cost / undo; authority matrix (risk class × earned confidence); six hard ceilings never lift; propose-first default; vetoes recorded verbatim, no silent expiry | No equivalent receipt/authority system found by our analysis — unverified | No equivalent receipt/authority system found by our analysis — unverified |
| **Undo** | 48-hour undo window; write-ahead journal; deterministic inverse; no registered inverse ⇒ never acted unattended | unverified | unverified |
| **Multi-agent org structure** | Officers (persistent Claude Code sessions) own domains under launchd/tmux; shared durable state; autonomy graduates per action class, never per agent | unverified | unverified |
| **Ecosystem** | None yet — pre-release | Larger — very large community and skill ecosystem (per analysis; size unverified) | Larger than Cabinet's (per analysis; size unverified) |
| **Maturity / stars** | Pre-release; unknown | unverified | unverified |
| **Platform** | macOS-first (Apple silicon); org lives in launchd user agents | Cross-platform messaging reach (per analysis); specifics unverified | unverified |
| **Account / model requirement** | Claude Code + Max subscription; Telegram bot for the Captain interface | unverified | unverified |
| **Verification discipline** | ~4,069-test framework suite + CI proof gates (null-hatch, clean-room ratchets, dry renders); daily falsifier series designed to expose failure | unverified | unverified |
| **Kill switch** | Fail-closed halt enforced in code (unreachable state store ⇒ halt); anyone-can-halt live today (activation unauthenticated); Captain-only resume is design doctrine — code enforcement pending | unverified | unverified |
| **License** | MIT — any use permitted, including commercial hosting by anyone; the "Captain's Cabinet" name and marks are not licensed | unverified | unverified |

## Reading notes

- **Why so many "unverified" cells?** Deliberate policy. The two research
  analyses were positioning studies, not feature audits of competitors'
  current releases. An honest sparse table beats a confident wrong one —
  the same doctrine as our receipts ("cost: unattributed" over an invented
  number).
- **What the table is NOT claiming:** that OpenClaw or Hermes lack these
  capabilities. "Unverified" means exactly that our analyses did not
  establish the cell either way.
- **Where Cabinet is honestly behind:** onboarding instant-gratification
  and ecosystem size — see the differentiation section of
  `category-narrative.md`. We expect to lose those two rows for a long
  time.
- **Before publication (CG-7):** re-verify every competitor cell against
  current public sources, replace "per analysis" hedges with citations or
  keep "unverified", and have the Captain approve the final table.
