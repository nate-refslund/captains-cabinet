Reviewed-Scope-Digest: 92f4c2f655d97148faff9e9718fd235d930c3afebee56ed9d43aea0bbf05d3f8

# feat/onboarding-connect-a-source — checkpoint 1 review

## What landed

The `decide` branch of onboarding ("go find where I am most useful") now
**connects a tool live**, closing the gap the design-of-record named. The
outward READ lane already existed (`research.sweep_connectors` → `who_and_when`
→ salience); the only missing piece was an operator surface that WRITES a
connector and pairs it with a credential. This adds exactly that:

- **A curated, agnostic template pack, shipped as DATA** —
  `instance/config/connector-templates.yml.example` (github, vercel, monday,
  and an open `rest` template). Vendor names live only in this DATA file; the
  framework consumes it generically. It ships in the egg (`.example` twin) and
  is outside the specifics ratchet's `framework/` scan.
- **A new core act `declare_connector`** (`journey.py::_act_core`) that resolves
  a template + the operator's answers into a connector entry
  (`research.build_connector_from_template`), refuses anything that would not be
  a read (`assert_read_only` on the BUILT inventory, before any write), and
  writes it into `instance/config/connectors.yml` never-clobbering
  (`research.write_connector_declaration`). The env var NAME is written; the
  credential VALUE is never an input here.
- **The credential's only path is `cabinet/.env`** via the dashboard's safe
  writer (`actions/env.ts::saveConnectorCredential` → `writeEnvValue`, the
  #350-hardened `envValueLiteral` quoting, 0600, newline-refused). A new
  `ensureEnvFile` creates the file 0600 on a fresh hatch, since the safe writer
  edits an existing file.
- **The dashboard connect UI** (`journey-card.tsx`, discover panel): a pick-list,
  a password credential field, per-template fields, a consent line NAMING the
  host, and a Connect button that stores the credential, declares, then sweeps.

## Class-11 four questions, for the new sensors

**Does the arm FAIL against pre-change code (both directions, cache purged)?**
The WIRE arm (`test_the_connect_path_declares_then_sweeps_to_connected_mode`)
drives `journey.act({"action":"declare_connector"})` — an action that raises
`action_unknown` on pre-change code, so the test cannot pass without the branch.
The dashboard parity arm compares the live `ACTIONS`/`ONBOARDING_ACTIONS`
against the Python dispatch chain parsed from `journey.py`; drop the branch and
the set inequality fails. The driven UI arm asserts the credential reaches
`saveConnectorCredential` and NOT the `declare_connector` fetch body — it fails
if the orchestration routes the value onto the wire.

**What does the check do at the degenerate end (zero / empty / absent / null)?**
Absent template pack ⇒ `{}` and the discover panel falls back to the folder
(`test_every_shipped_template...` covers the loaded case; the loader returns `{}`
on absent/parse-fail by construction). Absent `connectors.yml` ⇒ created fresh
(`test_absent_file_is_created...`). Unknown template, missing-required field,
unknown field, bad env name ⇒ each refused BY NAME with the file untouched
(four degenerate arms). A refused write asserts the file did NOT gain the entry,
not merely that an error was raised.

**What does the test environment guarantee that production does not?**
The full sweep runs on an injected `fetch` (the suite's sanctioned boundary)
because the ceiling is HTTPS-only and a plain-http loopback cannot pass it — so
the SOCKET half is proven separately over a real `127.0.0.1` server via
`_http_fetch` (`test_http_fetch_reads_a_local_server...`), which also proves a
redirect is surfaced as a status, never followed. The dashboard render/driven
tests run in vitest's `node` env with `useEffect` stubbed, so the template
fetch is scripted, not live — the assertions are on structure and orchestration,
which is what those layers own.

**Is the sensor wired to the live artifact?**
`test_every_shipped_template_builds_a_read_only_connector` reads the REAL
shipped `connector-templates.yml.example` (not a fixture) and asserts every
built inventory passes `assert_read_only` — so a future edit that made a shipped
template a write is caught at the pack. The census budget was RE-MEASURED over
this tree (`77414 → 77632`, +218, dated) rather than estimated.

## Adversarial pass

**Can a declared connector be coerced to write or exfil?** No.
1. The connector SHAPE comes from the curated template, not the caller. Only
   paths the template author declared under `fields[].into` ever take an
   operator value (`build_connector_from_template` refuses an undeclared key by
   name), so a surface cannot smuggle an arbitrary connector body through this
   door.
2. `assert_read_only` runs on the BUILT inventory before the write, and AGAIN in
   the writer as a last line of defense — GET or a GraphQL read document only,
   HTTPS only, method-override headers (including the injected auth header)
   refused, `mutation`/`subscription` tokens refused, no redirects at the
   socket. A template or a custom URL that could write is refused at
   declaration, so `connectors.yml` can never gain an entry the sweep would then
   reject (`test_a_write_verb_inventory_is_refused_at_the_writer`,
   `..._refused_before_the_config_gains_it`).
3. The open `rest` template lets the operator name a URL — but it is a GET, over
   their own credential, to a host they chose; the sweep returns contents-free
   rows and sends the credential only to the declared host. When egress
   enforcement is on, the host must be allow-listed or the sweep refuses it
   visibly. No cabinet data is exfiltrated: results carry names/dates/actors/
   counts, never bodies.

**Can the credential leak into connectors.yml or a log?** No.
The credential VALUE is never an input to `declare_connector` or the writer —
only the env var NAME is. `test_the_connect_path...` asserts the value is absent
from `connectors.yml` and from the committed sweep state; the driven UI arm
asserts it is absent from the `declare_connector` request body. On the `.env`
side the value rides the #350-hardened writer, which single-quotes anything not
provably inert and refuses a newline. The value is wiped from React state the
instant the declaration lands.

**Does the egg still ship no live connectors.yml?** Yes.
The export manifest deletes `instance/config/connectors.yml` (live instance
values never ship) and `instance-verify` fails the export if any non-`.example`
instance file survives. This change adds only `.example` twins
(`connector-templates.yml.example`, and the note in `connectors.yml.example`) —
both ship, neither is a live connector. `null-hatch` starts with no
`connectors.yml` and the read lane honest-empties, unchanged.

## Custody model shipped, and the named fork

`connectors.yml` is captain-custody. v1 is **propose-then-activate**: in the
personal hatch the operator IS the captain, so one explicit Connect click both
declares and activates for the sweep, with a consent line naming the host. This
does NOT silently weaken custody for a delegated (operator ≠ captain) future:
that future needs a ratification step between declaration and activation, and it
is named here and in the design-of-record as the follow-up, not built.

## Filed follow-up

**MCP connectors are OUT of v1** (adding an MCP server is a sudo/germline-gated
code-exec grant via `mcp-scope.yml` + `trusted-mcps.json` — a categorically
bigger, unsafe-if-rushed lift). The connect UI shows no MCP option, so nothing
is faked; the follow-up is filed here and in the design-of-record.
