# Resend — declared-OFF

**Why OFF.** Outbound email is the **cheapest exfiltration leg** (trifecta
leg C): any injected instruction that can compose an email can move data
out. Keeping it undeclared removes that leg entirely from the standing
attack surface — and external communications are **per-item Captain
approval regardless** of any connector state, so an email connector never
grants send authority anyway.

**When enabled (the known path, not shipped).**

- Env name: `RESEND_API_KEY`.
- Use case that justifies it: transactional product email (signup
  verification, receipts) built INTO the product — in which case the key
  usually belongs to the product's own env, not the Cabinet's. An
  officer-facing send surface is a separate, later decision with its own
  approval flow.
- If officer-facing send is ever wanted: Captain applies the scope grant,
  the safety addendum gains a row, and every send stays inside the
  external-comms approval gate (per-item Captain approval — the framework
  base, which no preset can relax).

**Verdicts.** Inbound-email probes (probe-support) exist in the services
manifest as import-only until their config lands — unrelated to outbound
send and not unlocked by this connector.

**Trifecta leg.** **C** — the exfil leg itself. The kit's posture: the
best mitigation for the cheapest exfil leg is its absence.
