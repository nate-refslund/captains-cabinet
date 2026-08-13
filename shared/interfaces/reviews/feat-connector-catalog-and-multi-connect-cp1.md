# Review — feat/connector-catalog-and-multi-connect, checkpoint 1

Self-review of the whole change before it lands. The Captain's two asks on the
live product were "expand this to hundreds of connectors and include HOW to
connect for each" and "I want to connect MANY connectors at once, not just one".

## What changed, and where the risk actually is

| Surface | Change | Risk it carries |
|---|---|---|
| `instance/config/connector-templates.yml.example` | 4 → 55 templates (54 named + the open one), plus `categories:`, and `category` / `how_to_connect` / `key_looks_like` per entry | DATA with no code review path. A wrong shape 401s an operator who has already gone and made a key; a wrong `how_to_connect` gets them to mint a WRITE key |
| `framework/onboarding/research.py` | `fields[].into_format` — the author's URL sentence with one `{value}` hole | An operator value reaching the scheme or the host of a call the credential is about to be sent on |
| `cabinet/dashboard/src/actions/connectors.ts` | `getConnectorTemplates` → `getConnectorCatalog`, projecting shelves + steps + key hint | A malformed pack entry taking onboarding down, or a mis-categorised tool vanishing from the catalog entirely |
| `cabinet/dashboard/src/components/onboarding/journey-card.tsx` | searchable/browsable catalog, setup sheet, connected list, aggregate found-summary; the step no longer closes itself | The gate change (`showDiscoverPanel`) silently hiding sweep results that used to render |
| tests | `test_connector_catalog.py` (new), `connectors.test.ts` (new), multi-connect arms in `test_connector_declare.py`, 12 new card arms | Sensors that cannot fail |

## Class-11: the four questions, per new sensor

**Does the arm FAIL against pre-change code / a bad input?**
- `test_connector_catalog.py::test_the_checker_rejects_a_bad_template` exists
  precisely for this: it feeds `_check_shape`, `_check_custody` and
  `_check_read_scope_honesty` a template broken four ways (a write scope with
  nothing refusing it, a field writing to `identity.url`, an `into_format` on
  `http://`, a one-step instruction list) and asserts each raises. Without it
  the six arms above it could all be vacuous and read identically green.
- The read-scope honesty arm **did** fail on first run, on a real entry
  (`linear`, "an admin has turned member API keys off"). That is the proof it is
  wired to the live prose. It was resolved by rewording the pack, not by
  loosening the matcher — then the matcher was tightened separately (whole-word
  write terms, and only beside a permission word) because "you must be an admin"
  is a precondition, not a scope, and a checker that cries wolf trains the next
  author to reword around it.
- `test_the_shipped_template_builds…` was already green before this branch — but
  it was green for the wrong reason once templates gained required fields: it
  passed `{}` as answers, which would have raised. It now builds each template
  with that template's **own placeholder**, i.e. the string the pack tells the
  operator to type. A placeholder that cannot build is itself the defect.

**What does the check do at the degenerate end?**
- Pack absent, unparseable, `templates:` not a list, an entry with no id, an
  entry with no connector, `how_to_connect` a bare string, `fields` not a list:
  all covered in `connectors.test.ts`. Every one yields a usable catalog or an
  empty one — never an exception, because onboarding must not die of a tool
  nobody asked for.
- A category nobody declared → the tool lands on `other`, not the floor. A shelf
  nothing sits on is not offered (an empty filter is a dead tap).
- `sweepLine` / `plainReason`: zero items, `latest: null`, empty reason, and an
  unrecognised reason code all pinned. An unknown code prints readably rather
  than becoming "something went wrong", which is how a diagnosable failure turns
  into a mystery.
- Multi-connect: a tool declared but not yet swept renders "not read yet", not a
  failure — those are opposite facts.

**What does the test environment guarantee that production does not?**
- The sweep arms inject `fetch`; the ceiling is HTTPS-only so a loopback server
  cannot pass it, and weakening the ceiling for a test is the one thing this lane
  forbids. That limit is pre-existing and documented in the module docstring; the
  socket arm still covers `_http_fetch` separately.
- **The shapes themselves are verified against documentation, not against live
  accounts** — nobody here holds 54 credentials. That is the honest bound on the
  claim, and it is why the count shipped equals the count verified and why
  anything that could not be checked was dropped rather than guessed.

**Is the sensor wired to the live artifact?**
- `test_connector_catalog.py` resolves the repo root from `__file__` and reads
  `instance/config/connector-templates.yml.example` itself — not a fixture, not a
  copy. `test_connector_declare.py::_sandbox` copies the same shipped file.
- `MIN_TEMPLATES = 25` / `MIN_CATEGORIES = 8` are floors on the DATA, so a future
  edit that guts the catalog back to a pick-list fails loudly rather than
  quietly. They are floors, not the shipped numbers, so they do not need editing
  as the pack grows.

## Adversarial pass — can a `how_to_connect` mislead an operator into a WRITE key?

This is the one place prose can do real damage: the card beside it promises the
cabinet only reads, so a step that says "tick Admin" hands over a writer under
cover of that promise.

- **Mechanically fenced.** `_check_read_scope_honesty` refuses any step naming
  `write|admin|administrator|modify|delete|unrestricted|full access|read_write`
  **as a whole word, beside a permission word** (`scope`, `permission`, `role`,
  `tick`, `grant`, `access level`, …) unless that same step also refuses it
  ("do not", "leave every", "unticked", "nothing else") or admits plainly that
  no read-only key exists ("no read-only", "not limited", "only ever lists").
- **Where a read-only scope exists it is named exactly** and the operator is told
  to pick only it: `read_api`, `read:repository`, `crm.objects.companies.read`,
  `forms:read`, `sites:read`, `channels:read`, `list_configuration:read`,
  `customer:read`, `org:read`+`project:read`, `folders:read`, `r_jobs`,
  `public:read`, Stripe restricted keys (Products → Read), Linode/DigitalOcean
  Read Only, Cloudflare "Read All Resources", Klaviyo Read-only, Squarespace Read
  Only, BigCommerce Products read-only, Sanity Viewer, and the Contentful
  Delivery token, which is read-only by construction.
- **Where none exists the last step says so** in the operator's words, e.g.
  "This product has no read-only key — the key you create can also change things
  there. The cabinet only ever lists, but the key itself is not limited."
  That covers monday.com, Vercel, Asana, Shortcut, Todoist, Coda, GitBook,
  Nuclino, Slite, Tally, Intercom, Pipedrive, Mattermost, Lemon Squeezy, Square,
  Netlify, Render, Neon, Heroku, Railway, Supabase, Cal.com, Kit, Brevo,
  Harvest, Fireflies.
- **The residual risk, stated:** the checker reads words, not intent, and a step
  could in principle be honest-looking and wrong. The mitigation is that the
  steps are transcribed from each provider's own documentation with the citation
  recorded in the PR, and that the catalog is data — a wrong step is a one-line
  fix with no release.

## Custody and the ceiling — nothing widened

- **The credential value still never reaches the core.** `declare_connector`
  takes a template id, a label, an env var NAME and at most a field or two; the
  value goes only to `cabinet/.env` through `saveConnectorCredential`. The
  multi-connect path did not change that; the retry path re-runs exactly the same
  writer.
- **`into_format` cannot widen anything.** It is refused unless it starts with a
  literal `https://` and contains `{value}`, so no operator value can choose the
  scheme. Where the format pins the host, `{value}` lands after the authority
  component is closed, so `@`, `?` and `#` inside it cannot move the request.
  Where the value IS the host (a self-hosted install), that is the operator
  naming their own server — the same consent the open `rest` template has always
  taken, and the card says "only to the address you enter above".
  `_check_custody` additionally refuses any field whose `into` leaves
  `inventory.`, so a pack edit can never point an operator answer at `identity`
  or at the entry root.
- **`assert_read_only` still runs on the BUILT call**, before the write, and
  again in the writer. `test_every_shipped_template_builds_a_read_only_connector`
  runs it over all 55.
- **Never-clobber, contents-free summary, and the host consent line** are
  untouched; the consent line gained a machine check
  (`test_a_declared_host_is_the_host_the_credential_actually_reaches`) because it
  is printed at exactly the moment consent is given, so a stale one is a lie.
- **No MCP UI added**, per the standing instruction.
- **No framework vendor literals added.** The specifics ratchet caught one
  (`sentry.io` in a comment I wrote) and it was removed rather than baselined;
  the `into_format` arm now finds its template by SHAPE, not by name, so the arm
  is agnostic and survives a pack edit.

## The gate change, examined rather than assumed

`showDiscoverPanel` moved from `inDiscover && !hasSweepContent` to
`inDiscover && !exploring`, and `showSweep` gained `&& !showDiscoverPanel`. That
is a real behaviour change: twelve existing card arms rendered sweep sections
while nominally in the discover step, and they now need `exploring: true`.

I checked each rather than reflexively patching: every one of them is asserting
what renders AFTER the operator has asked for the look, which is exactly the
state `exploring: true` names. Two new arms pin the change itself in both
directions — the catalog stays open when a sweep has already produced a ranking
and an identity question (previously it would have been replaced), and the
aggregate appears once the look is asked for.

## What I am NOT claiming

- Not that all 54 endpoints were exercised against live accounts. Doc-verified,
  shape by shape, with citations.
- Not "hundreds shipped". 54 verified, growing by data-only edits — the PR body
  says so in those words.
- Not that the register of absent tools is complete: popular tools are missing
  because their list endpoint cannot meet the read-only ceiling, and the `rest`
  template is the answer for all of them.

Verdict: **approve to land.**
