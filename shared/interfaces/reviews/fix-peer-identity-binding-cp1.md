# Checkpoint review — fix/peer-identity-binding cp1

Reviewed-Scope-Digest: 64881dbef1ee2ca71fe56c7fc1b930fd3748afe54237385b16bbd8b18425eb42

Scope: the 5 staged paths of this commit (server, its tests, the two peers.yml
twins, the provisioning runbook). Review performed against `git diff --cached`
on a clean clone of origin/master at 1d1aec53, by the agent that wrote it —
recorded here as the artifact FW-019 requires, not as an independent lens.

## The defect

`verify_bearer()` collected every configured peer secret and returned a bool if
the presented token matched ANY of them. Authentication therefore answered
"is this somebody?" and never "who?". Three consequences, all reachable by any
peer holding a valid token over the HTTP transport:

1. Every authenticated caller could call every tool on the surface. `peers.yml`
   `allowed_tools` was consulted only on the OUTBOUND side (which tools we may
   call on a peer) and by the relay; nothing checked it on receipt.
2. `tool_send_message`'s self-delivery path took the origin from the request
   BODY (`from_cabinet` / `_relay_origin_cabinet`). A peer could write into an
   officer's `cabinet:triggers:<role>` stream wearing another Cabinet's name —
   and an officer reads and acts on that stream.
3. With no origin claimed at all, the bus recorded the literal `unknown` even
   though the transport knew exactly who had called.

## The change

- `authenticate_bearer(header) -> peer_id | None` replaces the bool as the
  primitive. `verify_bearer()` remains as a thin wrapper (two call sites in the
  test suite depend on the bool; the comms server has its own, untouched).
  Fail-closed posture is unchanged: no secrets configured still denies
  everything with the same stderr warning.
- A token matching two DISTINCT peers now authenticates NOBODY. Guessing would
  let either peer speak as the other; this is the one behaviour change that can
  refuse a request that previously succeeded, and it only fires on a
  misconfiguration the peers.yml comment now warns about.
- `handle(req, authenticated_peer=None)` carries the proven id. It STRIPS the
  reserved `_authenticated_peer` argument from every inbound argument dict on
  every transport, then re-injects it only from the transport's auth result, so
  the value cannot arrive over the wire.
- Receiver-side permission: an authenticated peer may call only the tools in
  ITS `allowed_tools`. Unlisted or unknown name -> `tool_not_allowed_for_peer`,
  before tool lookup (so the surface is not enumerable) and before any handler
  runs.
- Self-delivery origin is the authenticated peer id. A body claiming a
  different origin -> `sender_mismatch`, no XADD.
- stdio is untouched: no bearer, no peer id, none of the rules apply.

## Attacks considered

- **Forge the reserved argument.** Covered: stripped before dispatch on both
  transports, and a sensor drives it end to end over the socket (both arms —
  it cannot set the origin, and it cannot bless a forged `from_cabinet`).
- **Refuse-everything permission gate.** A gate that refused all traffic would
  pass every refusal sensor. `test_identity_allows_listed_tool` and
  `test_identity_accepts_matching_claim` are the control arms; both were
  already green pre-change and stay green.
- **Degenerate ends.** No peers configured, no `allowed_tools` key, an empty
  list, a non-list value, an unknown tool name, a missing origin claim, and one
  secret shared by two peers — each resolves to a refusal, never to an allow.
- **Timing.** Every configured secret is still compared after a match
  (`hmac.compare_digest` is the left operand, so no short-circuit).
- **Regression on the legitimate relay.** `cabinet-mcp-relay.py` sends
  `_relay_origin_cabinet = <its own cabinet id>`; the receiver's peers.yml must
  name that same id (the reciprocal-entry rule the file already documents), so
  an honest relay matches and is delivered. Sensor:
  `test_identity_accepts_matching_claim`.

## Residuals (not closed here — reported, not relabelled as covered)

- **Confused deputy on peer->third-party.** An authenticated peer listed for
  `send_message` can still ask us to queue OUTBOUND to a different peer; that
  message is stamped with OUR cabinet id. Consent and the outbound
  `allowed_tools` check still apply to the destination, but the hop is not
  attributed to the original caller. Unchanged by this commit.
- **`GET /health` is unauthenticated** (pre-existing; loopback bind by default).
- **`framework/comms/mcp/server.py` has its own bool `verify_bearer`.** Out of
  scope here; if that transport ever gains per-peer rules it needs the same
  treatment.
- **`peers.yml.example` parses `consented_by_captain: false   # comment` as the
  truthy string `"false   # Captain flips to true..."`** — a pre-existing
  parser quirk in `read_peers()` (inline comments are not stripped from scalar
  values), so a fresh hatch reads its placeholder peer as CONSENTED. Not
  exploitable on its own (no secret env var is set, so the HTTP transport
  denies), but it contradicts the file's own promise that a fresh instance
  never arrives pre-consented. Left for a separate fix rather than widening
  this diff into the shared parser.

## Evidence

Every sensor was run against pre-change `server.py` (stashed, `__pycache__`
purged) with the new tests present, then against the change. RED->GREEN table
and the full local battery, with exit codes, are in the pull request body.
