# Federation — graduating a lane to its own cabinet (design, propose-first)

**Status:** design (2026-06-22). The highest-autonomy capability in the cabinet —
**the Chair recommends it; Nate approves every instance; nothing auto-spawns.**

## When (the graduation signal)

A product runs as a **portfolio lane** by default (one Chair, an on-demand lane-CEO
mustering functional hats + crew — see `docs/cabinet-architecture-cohesive-2026-06-22.md`).
A lane **graduates to its own federated cabinet** only when it outgrows that:

- sustained **parallel** load — the lane-CEO is continuously maxed, multiple
  concurrent missions that a single on-demand CEO can't hold;
- it needs a **full standing org** (5 functional officers always-on), not summoned;
- **hard isolation** is warranted — separate data/trust/comms boundary (the
  canonical case is **capacity**: a Work cabinet vs a Personal cabinet, not two
  work products);
- Nate explicitly wants it standalone.

Two work products sharing Nate's attention (PolAds + STEPhie) do **not** meet this —
they stay lanes. Federation is the scale lever, not the default.

## What exists (verified 2026-06-22)

Federation is **built**, not theoretical:
- `cabinet/mcp-server/server.py` — the Cabinet MCP: `identify / presence /
  availability / send_message / request_handoff`. **FW-005 HTTP transport is done**
  (stdlib listener, bearer-auth, `/health`, stdio↔http parity tested).
- `instance/config/peers.yml` — peer registry, **consent-gated**
  (`consented_by_captain`), per-peer `allowed_tools`, `shared_secret_ref`. A
  consented **Personal** peer is already provisioned.
- `CABINET_MODE=multi` wired into `load-preset.sh` + `start-officer-mac.sh`;
  `CABINET_ID` + `CABINET_PEER_SECRET_*` in `cabinet/.env`.

So the Chair→peer-CoS path (`send_message` / `request_handoff`) works today.

## How the Chair handles it (Duty E)

1. **Detect + recommend.** When a lane hits the graduation signal, the Chair
   surfaces a **proposal** (one card): "lane X is maxed N days / needs a standing
   org — graduate to its own cabinet?" with the evidence. It does **not** act.
2. **On approval, set up (gated).** Graduation reuses the onboarding research +
   adds instance-creation:
   - a new cabinet **instance** for the product (own `CABINET_ID`, own Redis
     namespace/prefix, own `cabinet/.env`, `work` preset = 5 functional officers);
   - a `peers.yml` entry **on both sides** + a shared `CABINET_PEER_SECRET_*`;
   - the HTTP endpoint (`http://<host>:<port>/mcp`, or localhost:port same-machine);
   - consent (`consented_by_captain: true`) — **Nate sets this**, per peer.
3. **Bridge.** The Chair talks to the new cabinet's CoS via the Cabinet MCP; the
   product's lane-CEO (if it existed) is retired in favor of the standing org.

## Gates (non-negotiable)

- **Spawning a cabinet is propose-only, always.** It creates a new always-on org —
  the single most consequential autonomous act. Captain-approved each time.
- **Consent is Captain-set** (`peers.yml`), never by a loop.
- The **hard ceiling never lifts** (prod deploy / external comms / spend) in any
  cabinet, federated or not (`presets/portfolio/safety-addendum.md`).
- Same-machine resource reality: each federated cabinet is ~5 standing officer
  sessions + a supervisor + Redis. The Chair must budget this in the recommendation.

## Build status / next

- **Now:** the Chair *recommends* federation (Duty E) using the existing Cabinet
  MCP + `peers.yml`; the work↔personal peer is the live example.
- **Future build (not started):** an **instance-generator** (the onboarding
  pipeline extended from "lane in this cabinet" to "a new cabinet instance") so
  graduation is one approved command. Until then, a graduation is a guided manual
  setup the Chair proposes and walks Nate through.
