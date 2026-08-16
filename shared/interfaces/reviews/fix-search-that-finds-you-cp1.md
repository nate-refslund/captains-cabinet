# fix-search-that-finds-you — checkpoint 1

**What.** The onboarding look-up composes its queries from what the operator NAMED,
judges what comes back against those same words, says so when it found nothing, asks
one earned follow-up, and re-fires itself when an answer changes what would be
searched. `framework/onboarding/journey.py`, `framework/onboarding/research.py`, the
three surfaces that render it (dashboard card, Telegram, the bridge/type vocabulary),
and their tests.

## The measured failure — the Captain's own run, 2026-08-15

His name and his organisation were both on the journey. Three probes went out:

| # | query sent | what came back |
|---|---|---|
| 1 | `<Role words> <half the org name>` | generic articles about that job title |
| 2 | `… how it works` | the same |
| 3 | `… common problems` | the same |

Four defects in one screen: the role words diluted the query and an engine ranks the
common half; the organisation was SPLIT by the four-term cap (its first word survived,
its second did not), so it was searched for under half its name; his NAME — which the
cabinet had, from the first question it asks — was never used at all; and nothing
judged the answers, so fifteen irrelevant results were listed as though that were an
answer. His verdict: *"none of the searches found me… we should improve it somehow."*
He also had to press a button to make the looking happen ("should be automatic").

## What changed

**1. The query hierarchy** (`_search_queries`, `_search_phrase`, `_ROLE_WORDS`).
`"<name>" "<organization>"` · `"<organization>"` · `"<name>" <salience target>`, then
the seed's own terms fill what is left. Multi-word values are phrase-quoted, so no cap
can split one; the tokenizer is for MATCHING and never builds a query. A query composed
entirely of job titles is not sent. A lone personal name is never a query in any
arrangement of the function — every form pairs it with something else the operator
gave. Deterministic, no model, script-agnostic (an operator with none of the three
answered gets exactly the composition that shipped before).

**2. The judgment** (`research.judge_search_results` / `result_mentions` /
`text_mentions`). Verbatim over tokens: ALL of a term's tokens or none (half a name is
not a match), plus the glued form an address spells without a space. Matches lead and
carry the operator's own string back as the reason; misses are FOLDED, never deleted —
a result that matched nothing is still the web's answer to the operator's own query.
`_discovery_note` leads with the miss instead of a count.

**3. One earned follow-up, never two.** A miss asks for a page (`answer_org_link`) and
actually READS it (`read_operator_link`: https only, no credential, one page, byte- and
time-capped, egress ceiling first, private/loopback hosts refused by name, redirects
refused by the shared opener, re-read on every later look-up). A hit offers a confirm
chip (`confirm_organization_domain`) whose candidate is re-derived from the committed
run, so no surface can record an address a search never returned.

**4. It re-fires itself.** `answer_organization` and `answer_salience` change WHAT IS
SEARCHED FOR, and nothing re-ran on them. Gated on a search tool existing rather than on
the last run having failed — a run that succeeded at searching for the wrong thing is
the case this closes.

## Verified

| gate | result |
|---|---|
| `python3.12 -m pytest framework/onboarding/tests -q` | 1098 passed, 1 skipped |
| `python3.12 -m pytest framework/ -q` | 8202 passed (1 pre-existing local-only red, below) |
| `npm ci && npx vitest run` (dashboard) | 3711 passed, 1 skipped |
| `npx tsc --noEmit` | clean |
| `check-layer-separation.sh` | OK — 0 new |
| `cognitive-architecture-census.py` | PASS after the +458 raise, zero headroom |
| `docs-track-code-sweep.sh` | GREEN (65 files, 0 findings) |
| `ledger-status-parity.sh` | GREEN (353 ids) |

**The live drive.** A fresh cabinet, a real CLI process per action, and a real TLS socket
to a stand-in provider (self-signed, `SSL_CERT_FILE`) — no pytest, no monkeypatch. One
answer to the first question and the probes had already gone out; naming the
organisation re-fired them with **no button pressed**, sending
`"<name>" "<org>"` / `"<org>"` / the seed's terms, with the organisation whole in every
query that carried it. The confirm chip recorded the returned address, and an address no
search returned was refused `organization_domain_not_offered`.

## Three defects this build found in itself

1. **The judgment was silently disabled.** `run_search_probes` already had a local
   named `wanted` for its filtered probe list, so the new keyword argument was
   overwritten before it reached the judge: every real run came back UNJUDGED while the
   unit arms over the pure function stayed green. Found by driving the action, not by
   reading. `test_the_executor_really_applies_the_judgment` is the sensor pointed at the
   live artifact rather than at the function beside it.
2. **A false claim in the honest sentence.** The headline said "I searched for
   \<their name\>" for an operator who had given only a name — and a lone name is never
   sent as a query. Found by the live drive. It now says "I searched for X" only when X
   really was a query, and "I did not find anything clearly about X" otherwise.
3. **The test suite wrote a name into the repo.** Recording an operator name resolves
   its path through `framework.env`, so a test that records one lands it in the real
   `instance/config/cabinet-init.answers.yml` — and the person-literal ratchet derives
   its vocabulary from that file, which makes the whole tree red on the next run. The
   new arms redirect `CABINET_INIT_ANSWERS` into their sandbox, as every other
   name-recording test already does.

## Stated limits

- `_ROLE_WORDS` is English-only and lists exactly the titles it names. Both of its
  effects are harmless when wrong: one query not sent (there is always another), or one
  extra optional question. An operator writing in another script loses both effects and
  gets the behaviour everyone had before.
- The judgment is verbatim. A page that calls the organisation something else — an
  abbreviation, a former name, a translation — does not match, and is FOLDED rather than
  dropped, with the operator one tap from correcting it. Fuzzy matching would trade a
  visible miss for an invisible false claim, which is the wrong direction here.
- `read_operator_link` reads ONE page and reports its `<title>` (or its host, when there
  is none). It parses no further and claims nothing about the contents. It refuses
  loopback and private-range hosts, so a pasted address cannot make the cabinet knock on
  a door only it can reach.
- The pre-existing red in `framework/fidelity/tests/test_retro_shim.py` is local-only:
  the constant it pins is re-exported from the operator's own screenpipe pipe, and CI is
  the lib-less install where that branch is not taken. It fails identically on a clean
  checkout of origin/master and is untouched by this unit.

**Census.** `framework_production_noncomment_lines` 64282 → 64740 (+458, measured
against origin/master a209e4d1: journey.py +319, research.py +139, nothing else in
`framework/` moved). Raised visibly rather than paid by a temporary allowance: a search
that can tell "I found you" from "I found something" is a permanent organ, and an
allowance would promise a deletion gate that will never fire.
