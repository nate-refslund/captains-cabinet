# Playwright — MCP `playwright` (ON)

**Why/when.** Zero-credential browser verdicts: "does the product
actually work in a browser". The CTO verifies user-facing changes
visually; the COO validates deployments against the live product.

**Verdicts supplied.** Feeds the deploy-validation loop (COO
`validates_deployments` capability) and the CTO/CPO visual-verification
duties already written into the agent role defs. No dedicated probe row —
Playwright is the interactive half of verdict supply.

**Declaration.** First-party npx, declared in the root `.mcp.json`:

- command: `npx`, args: `-y @playwright/mcp` (unpinned first-party — the
  no-version-pinned-third-party rule; it was already granted in officer
  tool lines but declared nowhere until this kit)

No credentials. Declare an **origin allowlist** per deployment (the
product's own origins) and keep secrets-redaction on screenshots/captures
— both are deployment config, not preset defaults.

**Scope to grant.** Captain adds `playwright` for CTO and COO in
`cabinet/mcp-scope.yml` (printed diff, README step 3).

**Trifecta leg.** **A** — arbitrary page content enters officer context.
An un-allowlisted browser is also a potential exfil vector (navigating to
an attacker URL with data in the query string), which is exactly why the
origin allowlist matters. Page content is untrusted data, never
instructions.
