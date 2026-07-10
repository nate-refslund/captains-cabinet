# Living Dashboard — Captain Alignment Record (2026-07-10)

Captain interview completed 2026-07-10 (in-session, orchestrator). This document is the ratified
alignment for the LIVING-DASHBOARD program (connector surface + org-prompting UI + custom
components + chat rail + theming). Design docs must build to THIS; deviations need Captain word.

## The Captain's vision (verbatim substance)
Menu → "Connections": list of connected + possible connectors. Add a custom one by typing
("Apple Notes") + Add → sent AS A PROMPT to the org → UI immediately shows "Building…" —
**true information only**: the status lives in the org's own mission/MCP state so a refresh
still shows Building…; once built, it appears in the list; if a credential is missing, the
captain enters it THERE, which prompts the org to finalize + test — all visible live.
Dashboard actions forward as prompts to the org. Telegram traffic visible in a right sidebar;
captain can write to the org from there (like in the world). Captain can modify everything:
custom components ("everything in Apple Notes, my way"; "my monday.com data in MY interface";
"my own command center gathering reminders + tasks + monday + db + decisions + BI graphs"),
and appearance.

## Interview rulings (binding)
1. **Intent scope = Designated + chat.** Purpose-built surfaces (Connections, component
   builder, decision cards) emit STRUCTURED intents; the chat rail is the ONE free-text door.
   No per-page free-text boxes.
2. **Widget model = Declarative + org-built, two tiers.**
   - Tier 1 declarative: pick data source + layout template → renders instantly, config-only,
     zero new code. (Covers: "monday board, my way", simple mashups.)
   - Tier 2 org-built: complex asks ("my own command center from N sources + BI graphs")
     become missions — CTO builds a real component → PR → gates → lands in BOTH surfaces
     per SURFACE-PARITY-LAW.
   - Explicit Captain examples to serve: replace monday.com's UI with his own view of its
     data; multi-source command centers, completely customizable.
3. **Chat rail = equal-authority door.** Same one-door transport + gate + receipts + feed
   journal as HQ Chair Telegram (WRITE-CLASS-2 pattern extended). Investigate ~/stephie-mcp's
   chatbot app (chat that navigates + builds-pages-on-the-go) as PRIOR ART for
   chat-controls-dashboard; adopt only what survives an over-engineering check — Captain
   himself flags it may be too much; the VALUE hypothesis is "visualization is how humans
   prefer information" (chat answers that can RENDER live components/views, not just text).
4. **Theming = themes + layout.** Preset + custom themes (colors/fonts), drag/resize/hide/
   arrange per captain, persisted per-captain. PROTECTED DECISION CHROME: the verdict/confirm
   UI zone is exempt from theming (spoof-proofing) — non-negotiable rail.

## Standing laws that bind this program
- Truth law: every status shown is org-state-derived (mission rows, MCP registry, doctor
  probes) — never client-side theater. "Building…" survives refresh because it IS the org state.
- WRITE-CLASS-3 (pending Captain ratification as its own decision card): credentials through
  the surface — captain-identity only, config-plane only, write-only fields (never echoed),
  validated at entry, journaled; credential fields appear ONLY when a real mission requests
  them (anti-phish).
- Intelligence lives in the ORG, not the widget: components = live views + intent doors;
  thinking = missions/officers; results stream back as events.
- Connector build pipeline = the EXISTING capability-gap loop (gap → mission → CTO builds MCP
  → validate-extension → install → doctor probes green). The Connections page is a skin over
  that pipeline; the world's switchboard hut renders the same states (scaffolding while
  Building…, humming when green, sparking when auth-missing).
- SURFACE-PARITY-LAW: every capability here ships on both surfaces from one API.
- No auto-merge: org-built components + this program's own build land via PR.

## Sequencing
Queued BEHIND captain-surface-v2 (PR in flight) — same dashboard file surfaces, no racing.
Design workflow may run in parallel (docs only); build starts after the v2 PR lands.
Stage order: S1 Connections page + connector pipeline skin (+ world hut parity), S2 chat rail
(equal door) + Telegram mirror, S3 declarative widgets + layout/theming, S4 org-built
components + WRITE-CLASS-3 (if ratified) + stephie-mcp-style render-in-chat if it survives
the over-engineering check.
