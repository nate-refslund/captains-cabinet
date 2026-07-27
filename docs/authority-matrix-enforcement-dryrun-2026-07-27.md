# Authority-matrix enforcement — dry run and adjudication (2026-07-27)

**Verdict: DO NOT FLIP.** Adding `authority_matrix` to the live enforcing set
would refuse **52,659 of the 69,603 officer tool calls that run today — 75.66%**
— measured by replaying the matrix over five weeks of real recorded calls. The
Captain-facing consequence is not "a stricter cabinet"; it is a cabinet that
cannot run `python3`, `git add`, `git commit`, `gh`, `sed`, `pytest` or `npm`,
and that refuses to send a status message containing the word *billing*.

What landed instead: the instrument that produced these numbers, and the
guardrail path the Captain's ruling actually asks for.

---

## 1. The ruling, and what is true today

> *"cabinet should decide what action is allowed. if captain wants some specific
> actions not allowed, captain can just say so and cabinet should be able to
> adjust, e.g. guardrails through hooks."* — Captain, 2026-07-27

Access inversion (ruled 2026-07-04 for estate writes) applied to the authority
plane: the cabinet's typed policy decides; the Captain names exceptions.

Today the first half is not true. `cabinet/scripts/policy-shadow.py`
`_LEGACY_ENFORCING_TYPES` lists six types and `_engine_decision()` skips
everything else — so the authority matrix computes a verdict on every tool call
and the system discards it, while a cruder pattern-matcher decides. The
enforcing plane itself is armed (`instance/config/authority-enforcing`, flipped
2026-07-03 on the Captain's "flip it"); only the matrix type is excluded.

Everything hardened in the last two days — the hard-ceiling class-mapping pin,
the recipient `all`-quantifier fix, the Bash egress reclassification — lives in
that discarded plane.

The second half did not exist at all. There was no surface on which the Captain
could say "not that". That gap is now closed (§5).

---

## 2. Corpus

| | |
|---|---|
| Source | `org_events` where `event_type='policy.shadow_decision'`, live `cabinet/cache/org-runtime.sqlite3` — the record `pre-tool-use.sh` itself writes |
| Read | read-only (`file:...?mode=ro`); nothing in the live deployment was modified |
| Raw rows | 175,388 |
| After dedup (officer, tool, input, second) | 109,753 |
| After dropping pytest-fixture rows written into the live DB by suite runs | 87,577 |
| After dropping `officer=unknown` (developer/CI sessions, `$OFFICER` unset) | **80,307 — the replay corpus** |
| Window | 2026-05-25 → 2026-07-21, dense 2026-06-18 onward |
| Officers | cto 27,922 · cos 16,611 · stephie-ceo 8,873 · comms-officer 8,030 · polads-ceo 7,569 · cro 5,771 · cpo 5,257 · coo 271 · ghost-officer 2 · ccos 1 |
| Shape | `{tool_name, tool_input}` verbatim as the hook received it, officer-attributed, timestamped |

**Known biases, stated rather than hidden.** (a) Attempt-level: the shadow fires
at the top of the hook, so these are calls officers *tried*, not calls that
succeeded — which is exactly right for blast radius and useless for "did it
run". (b) 85% Bash, so the rarest and most dangerous classes rest on single
digits: `external_comms` 3, `credentials_grant` 6. (c) Officer skew — cto+cos
are 55%. (d) Stale: the last row is 2026-07-21, because the shadow's write
target is `CABINET_ROOT`-relative and ~30 worktrees each write their own DB.
(e) Recorded verdicts are posture-conditioned; only `{tool_name, tool_input,
officer}` was reused as replay input, never the stored verdict.

---

## 3. Method

`cabinet/scripts/authority-matrix-dryrun.py` computes two decisions per record
over the same loaded policy stack, calling the **real**
`policy_engine.evaluate_policy` — no second copy of the verdict logic:

* **baseline** — today's live decision: the types in `_LEGACY_ENFORCING_TYPES`,
  imported *from* `policy-shadow.py` so a stale hand-copy is impossible.
* **candidate** — the same first-match-wins loop with `authority_matrix` added.

**NEWLY BLOCKED = baseline allow AND candidate block.** That delta is the whole
cost: an authority *allow* merely continues into the legacy rules, so the flip
is monotone-narrowing and cannot widen anything.

**Read-only is enforced, not assumed.** The candidate arm calls the GATE path,
which on a ceiling row under a non-guardian posture calls
`standing_grant_resolution(..., act=True)` — the need-FILING, rate-CONSUMING path
§4.7 is about. A measurement that files needs is not a measurement, so the
instrument forces `act=False`, no-ops the gate-tell emitter, and refuses to run
if the posture is not guardian and those guards could not be installed. The run
below reports `gate posture: guardian` and both guards active.

A **timed-out** record has no verdict and is excluded from the denominator
rather than counted as allowed. The bound is wall-clock, so the count moves a
little between runs (53 then 52 on two runs of the same corpus); it is 0.06% of
the corpus either way, and it moves the headline by 0.06pp.

Sensors against a lying measurement: an empty corpus exits 2 rather than
reporting a comfortable zero; an unimportable engine exits 3; the
`read_cell_state` memo is proven exact on a 300-record sample before use
(`--verify-cache`, and it must reproduce the uncached verdicts exactly); every
policy evaluation is wall-clock bounded and a breach is reported as its own
category rather than silently counted as allow.

**Re-running it — one command each, no side scripts.** This number is what
decides when the flip becomes possible, so the corpus filters live in the
instrument rather than in a one-off:

```
# rebuild the corpus from the live shadow record (read-only, mode=ro URI)
python3.12 cabinet/scripts/authority-matrix-dryrun.py --extract corpus.jsonl
# measure
python3.12 cabinet/scripts/authority-matrix-dryrun.py corpus.jsonl \
    --verify-cache 300 --policy-timeout 1.5 --json out.json
```

**BASELINE OF RECORD — 2026-07-27, master `0ab0cc2b`, guardian posture:**
80,307 records · 10,652 blocked today · 52 no-verdict · 69,603 allowed today ·
**52,659 newly blocked = 75.66%**. The same numbers are in the instrument's
docstring. A materially different result means the corpus, the classifier or
the matrix moved — find out which before trusting it.

---

## 4. Results

### 4.1 Headline

| | count | share |
|---|---:|---:|
| records replayed | 80,307 | |
| blocked today by the legacy types | 10,652 | 13.3% |
| no verdict — timed out in one policy (§6.1) | 52 | 0.06% |
| **allowed today** | **69,603** | |
| **NEWLY BLOCKED by the flip** | **52,659** | **75.66% of what runs today** |

### 4.2 By officer

| officer | newly blocked | share of the blast |
|---|---:|---:|
| cto | 18,734 | 35.6% |
| cos | 9,644 | 18.3% |
| comms-officer | 7,659 | 14.5% |
| stephie-ceo | 6,871 | 13.1% |
| polads-ceo | 6,307 | 12.0% |
| cro | 2,326 | 4.4% |
| cpo | 1,056 | 2.0% |
| coo | 59 | 0.1% |
| ghost-officer / ccos | 3 | ~0% |

No officer escapes. This is not one misbehaving lane; it is the whole fleet.

### 4.3 By tool

| tool | newly blocked | share |
|---|---:|---:|
| Bash | 50,294 | 95.5% |
| CronList | 527 | 1.0% |
| ToolSearch | 399 | 0.8% |
| Agent | 174 | 0.3% |
| mcp__claude-in-chrome__computer | 173 | 0.3% |
| mcp__brain__log_reasoning | 165 | 0.3% |
| mcp__brain__record_run | 105 | 0.2% |
| SendMessage / WebFetch / WebSearch / ScheduleWakeup / … | ~820 | 1.6% |

`Read`, `Grep`, `Glob`, `LS`, `Edit`, `Write` are **not** in the blast — they
classify `local_edit`, which resolves `act_with_undo` and allows. Everything
else the fleet uses is.

### 4.4 By risk class — where the blast actually comes from

| risk class | newly blocked | share |
|---|---:|---:|
| **unclassified** (`action_type=ambiguous`) | **37,624** | **71.5%** |
| ceiling: deploy_prod | 6,507 | 12.4% |
| ceiling: secrets | 4,471 | 8.5% |
| below bar: deploy_nonprod | 3,459 | 6.6% |
| ceiling: network_write | 364 | 0.7% |
| ceiling: spend | 219 | 0.4% |
| below bar: internal_comms | 6 | ~0% |
| ceiling: credentials_grant | 6 | ~0% |
| ceiling: external_comms | 3 | ~0% |

### 4.5 Root cause — the classifier, not the matrix

Nearly three quarters of the blast is a single mechanism.
`framework/authority/classifier.py` grants `local_edit` to a Bash command only
when `_is_provably_local` proves every invoked binary can neither open a socket
nor exec another program. That allowlist (`_LOCAL_ONLY_BINARIES`, ~90 entries)
contains **no** `python`/`python3`, `sed`, `awk`, `find`, `xargs`, `gh`, `npm`,
`node`, `make`, `pytest`, `bash`, `sh`, `rg`, `ssh`, and `_GIT_LOCAL_SUBCOMMANDS`
contains **no git write verb** — no `add`, `commit`, `checkout`, `merge`.
Everything else resolves `AMBIGUOUS`, which has no risk class, so
`_eval_authority_matrix` step 1 fail-safes to propose-only ⇒ block.

That fail-safe default is *correct* for a classifier and *catastrophic* as a
gate, because the vocabulary was never built for developer tooling — it was
built for the acting plane's action kinds.

Verified samples (all currently allowed, all newly blocked):

| command | action_type |
|---|---|
| `python3.12 -m pytest framework/tests -q` | ambiguous |
| `git add cabinet/scripts/foo.py` | ambiguous |
| `git commit -m "feat: x"` | ambiguous |
| `gh pr checks 123` | ambiguous |
| `sed -n '1,50p' README.md` | ambiguous |
| `tar -xf /tmp/a.tar` | ambiguous |
| `less framework/frontdoor/action_exec.py` | ambiguous |
| `cabinet/scripts/evidence-read.sh DOGFOOD-001` | ambiguous |

That last row matters on its own: it is the bounded doorway the **observe-only**
emergency mode leaves open. Flipping enforcement would break the Captain's own
"constrain the fleet right now" control.

### 4.5b Decomposition — what actually blocks, ranked, and the smallest fix

The `unclassified` bucket is 71.5% of the blast, so it is worth taking apart.
Of its 42,279 records, 39,797 are Bash commands the shell parser can analyse
(the rest: 2,353 non-Bash tools with no classifier arm at all — `CronList` 527,
`ToolSearch` 399, `Agent` 174, `SendMessage` 74, `WebFetch` 64 …; 126
unparseable; 3 `/dev/tcp` refusals).

For each of those 39,797, the set of tokens that fails `_is_provably_local`:

| why the locality proof fails | records | share |
|---|---:|---:|
| ONLY real binaries — a genuine allowlist gap | 16,741 | 42.1% |
| **includes a token that is not a program at all** — the parser cannot resolve it | **13,691** | **34.4%** |
| ONLY shell builtins / git verbs | 5,505 | 13.8% |
| mixed | 3,860 | 9.7% |

**The single largest cause is not policy and not a short allowlist — it is that
the shell parser cannot tell what a command invokes.** 347 distinct
non-program tokens are being resolved as command words: bare `1`, `)`, `#`,
`##`, `.`, newline fragments, `REDIS_HOST:-localhost`, ` -p $`,
` XLEN cabinet:captain-attention:polads`, and whole sentences out of heredoc
bodies (`COUNTERFACTUAL=Actively pull my lanes…`). The "real binaries" row above
is optimistic for the same reason: its 609 distinct tokens include `A`, `ACK`,
`ALLOW`, `AND`, `API`, `ACTIVE_TASK`, `BLOCKS_CHECK` — heredoc words and shell
variables that merely *look* like program names. So 34.4% is a floor, not an
estimate.

**Allowlist widening has a hard ceiling.** Greedy cover — add the token that
clears the most remaining records, repeat:

| rank | token | clears | cumulative |
|---:|---|---:|---:|
| 1 | `gh` | 5,429 | 13.6% |
| 2 | `tar` | 2,309 | 19.4% |
| 3 | `sudo` | 1,651 | 23.6% |
| 4 | `__unresolved_program__` | 1,442 | 27.2% |
| 6 | `source` | 3,378 | 38.0% |
| 8 | `exit` | 2,124 | 45.9% |
| 12 | `sed` | 1,073 | 58.4% |
| 15 | `python3.12` | 1,052 | 67.0% |
| 30 | `tclsh` | 156 | 84.4% |

Thirty additions reach 84.4% — and the list is unusable. `gh`, `redis-cli`,
`docker` are network clients; `python3`, `perl`, `awk`, `tar`, `find`, `xargs`
execute arbitrary programs; `sudo`, `reboot`, `launchctl` are privilege and
system control; `source` and `.` run another script. Adding any of them would
delete the very property the allowlist exists to prove, which is exactly the
argument `_is_provably_local`'s own docstring makes against a blocklist. The
top-ranked single win, `gh` at 13.6%, is illegitimate on its face.

**What IS legitimately cheap** (each is a strict subset of "cannot reach the
network and cannot exec"):

1. **Pure shell builtins** — `export`, `exit`, `read`, `local`, `declare`,
   `return`, `shift`, `set`, `unset`. They neither exec nor open a socket, and
   they are currently treated as unknown programs.
2. **The local git WRITE verbs** — `add`, `commit`, `checkout`, `switch`,
   `restore`, `merge`, `rebase`, `stash`, `tag`, `apply`, `am`, `cherry-pick`,
   `revert`, `mv`, `rm`, `worktree`. None reaches the network; only `push`,
   `fetch`, `pull`, `clone`, `remote`, `submodule` and `send-email` do, and
   `push` already has its own positive classification.

Together those clear the 13.8% "builtins / git verbs" row outright and part of
the 9.7% mixed row, for two small edits to sets that already exist. Worth doing
on their own merits; nowhere near enough to make the flip viable.

**The smallest change that moves the number most is none of the above.** The
matrix's thirteen risk classes are all about *acting on the world* — comms,
deploy, spend, secrets, PM writes, calendar. **Not one of them describes
"run a command on this machine."** So every build, test, inspect and
housekeeping command an officer runs falls off the edge of the vocabulary into
`AMBIGUOUS`, and the fail-safe does the rest. That is the actual defect: not a
missing allowlist entry, not a wrong verdict, but a *missing risk class*.

The high-leverage fix is therefore one new `action_type` + risk class —
call it `toolchain` — covering local build/inspect/housekeeping execution,
mapped to `act_with_undo` or `notify_after`, with the network-reaching and
privilege-escalating cases explicitly kept out and left to the existing
ceilings. That addresses the whole 71.5% in one place, in the layer where the
question belongs, instead of chasing 609 binary names. Its own gate is that
adding a class is a *widening*: it needs an adversarial pass proving no
`sendmail`/`nc`/`ssh`/`osascript` path lands inside it — the same attack that
produced the current fail-closed default (RES-018).

Second, independently: **give the non-Bash tools a classifier arm.** 2,353
records are tools (`CronList`, `ToolSearch`, `Agent`, `SendMessage`,
`WebFetch`, `ScheduleWakeup`, the `mcp__brain__*` family) that fall through
`classify_action` to `AMBIGUOUS` because nothing matches them — a read-only
`ToolSearch` and a `WebFetch` are not the same action, and today neither is
anything at all.

### 4.6 The ceiling classes are not a safe subset either

The obvious salvage — enforce only the six hard ceilings, which are positively
classified and can never be `AMBIGUOUS` — fails on **precision**. The ceiling
rules are substring searches over the *whole command text*, including message
payloads and grep patterns, so they classify what a command *says*, not what it
*does*:

| real recorded command (truncated) | classified | reality |
|---|---|---|
| `bash cabinet/scripts/notify-officer.sh cos "…billing…"` | `billing` → **spend ceiling** | a status message |
| `bash cabinet/scripts/record-experience.sh cos success "…"` | `token_grant` → **credentials ceiling** | a log write |
| `git commit -m "…subscribe…"` | `purchase` → **spend ceiling** | a commit |
| `ls \| grep -iE 'commit\|deploy\|vercel'` | `vercel_deploy_preview` | a read-only pipeline |
| `echo … && bash -n run-frontdoor-briefing.sh && grep -oE '^VERCEL_API_KEY=' cabinet/.env` | `secret_write` → **secrets ceiling** | a names-only `.env` grep, the *sanctioned* pattern |

`secret_write` alone is 4,391 records, overwhelmingly of this kind: on a
compound `A && B && C`, any `.env` mention anywhere plus any `>` anywhere
(a `>/dev/null` will do) yields the highest ceiling class. `billing` is 195 and
`purchase` 26, almost entirely message text.

Correctly classified, for contrast: `git push origin main` → `deploy_prod`;
`export TOKEN="$(grep '^TELEGRAM_COS_TOKEN=' cabinet/.env …)"` → `secret_read`;
`curl -X DELETE https://api.github.com/…` → `mcp_delete`; `queue_draft` to an
external recipient → `external_email`.

**The finding under the finding:** the classifier's precision has never been
measured, because until now nothing depended on it. A verdict nobody enforces is
a verdict nobody checks.

### 4.7 The flip is not only "block more" — it starts writing

At a hard-ceiling row under a sovereign posture the *gate* path calls
`standing_grant_resolution(..., act=True)`, which **files a NEED** and
**consumes standing-grant rate budget**. The shadow path deliberately probes
with `act=False`. Two existing tests pin exactly this
(`test_sovereign_ceiling_no_grant_records_need_fingerprint`,
`test_sovereign_ceiling_grant_match_records_grant_id` — "shadow NEVER consumes
rate budget"). Enforcement turns a read into a write on ~11,500 ceiling records.

### 4.8 A documented in-repo precondition is unmet

`framework/authority/policy_engine.py`, in `_act_with_undo_gap`:

> ⚠ FLIP PRECONDITION — … A RAW officer tool call — Edit/Write, or a direct
> Monday MCP mutation — that this matrix verdict would apply to is journaled by
> NOTHING and captures no prestate … **Do NOT flip enforcement for the
> act_with_undo classes until raw officer pm_write/calendar_write tool calls are
> routed through (or wrapped by) the journaled lane, or blocked at the hook so
> only lane-executed acts can act.**

Measured: `_act_with_undo_gap` returns `None` (gate allows) for all seven of
`local_edit`, `task_status_move`, `label`, `tier2_note`, `task_create`,
`board_status`, `calendar_event_create`. The precondition is unmet.

### 4.9 Cost beyond the corpus

* **Hook-regression suite:** 115 of 183 ALLOW-expected probes across 17 permanent
  harnesses would newly exit 2 (63%).
* **Unit tests:** 3 of 19 in `test_policy_shadow.py` flip; the whole
  `TestNoLiveBlock` class name becomes a lie.
* **Reason strings:** the matrix loads at index 0, so first-match-wins makes
  *every* typed block report `authority_matrix` instead of its specific rule.
* **Latency:** +17.7 ms per tool call, uncached, on every hook invocation.
* **Ceremony:** `policy-shadow.py` is germline (schg), so the flip also costs a
  Captain unlock/relock.

---

## 5. What landed instead — the guardrail path the ruling names

### 5.1 The surface

`instance/config/authority-exceptions.yml` — **deny-only**, re-read on every
tool call. Same shape the Captain already ruled for
`instance/config/act-first-surfaces.yml`: a `denylist:` he appends to.

Only the **`.example` ships**; the live file is absent by default, which is
behaviourally identical to an empty denylist and avoids two real problems: the
egg export would otherwise delete a file two shipped tests read (no materialize
transform exists for it, unlike `act-first-surfaces`), and a present file makes
the loader reach `import yaml` on every call — so a deployment missing PyYAML
would go from "degrades to the regex fallback" to "every tool call blocked,
including Read".

```yaml
version: 1
denylist:
  - id: no-prod-deploys                 # required; appears in the refusal
    why: "I ship production myself."    # shown to the officer — told why, not just no
    action_type: vercel_deploy_prod     # any of: tool, officer, command_contains,
                                        #         path_contains, action_type
```

A row matches when **every** predicate it declares matches. To narrow, add a
row; to lift, delete it. No deploy, no restart, no code change.

**A row that cannot mean what it looks like is a load ERROR, not a silent
no-op.** A predicate-less row would deny every call — reads like a typo, behaves
like an outage — so it is refused. Review extended the same rule to predicate
VALUES: `command_contains: ["rm -rf"]` is the natural YAML for "any of these",
and `str([...]).lower()` is never a substring of a command, so the row would
have loaded clean, matched nothing, and left the Captain believing the deny was
live. Non-string predicates, empty strings, a non-string `id`, and an
`action_type` outside the classifier's enum are all refused at load, naming the
row and the problem.

### 5.2 Why it can be left unlocked — and what that does NOT buy

It has **no allow direction**: there is no syntax here that permits anything, so
its *content* cannot widen the cabinet by one call, and a malformed row costs a
self-inflicted denial of service rather than an escalation. That is what makes
"the Captain says so, the cabinet adjusts" safe as a writable file rather than a
germline ceremony. `act-first-surfaces.yml` is schg-locked precisely because it
*grants*.

**Stated plainly, and MEASURED — this is not containment.** The path is on
neither of `pre-tool-use.sh`'s protected lists, so an ordinary officer tool call
erases it. Probed through the real hook:

| probe | result |
|---|---|
| `Write` over the file | exit 0 (allowed) |
| `Bash: echo 'denylist: []' > <file>` | exit 0 (allowed) |
| `Bash: rm -f <file>` | exit 0 (allowed) |
| `Bash: truncate the file to 0 bytes` | exit 0 (allowed) |
| *contrast:* `Write` to `instance/config/act-first-surfaces.yml` | **exit 2** (refused) |

Four of those erasures are **SILENT**: an absent, empty, or `denylist: []` file
is legitimately the ruled posture and is indistinguishable from a deliberate
Captain edit. Only a WRONG-SHAPE file (symlink, directory, corrupt YAML) fails
closed. The refusal string also names the row that blocked the call, which helps
a cooperative officer and hands an uncooperative one the string to delete.

So this is a **preference channel**: it holds against drift, mistake, and an
officer that is not trying to defeat it. It is **not a boundary**. An earlier
draft of this section claimed it held against "an officer's ordinary tool calls"
and that erasure was "loud rather than silent" — both were false, caught by
adversarial review, and are corrected here rather than softened. The same probe
table is in the shipped `.example`'s own header, because the person who most
needs to know is the Captain deciding whether to rely on a row.

The fix is the hook half of the Captain's own ruling: one enumerated
`hook_protected` entry in `framework/policies/immutable-core.yml` plus the two
`pre-tool-use.sh` lists, on the `shared/interfaces/captain-vetoes.yml`
precedent (hook-protected, deliberately NOT schg-locked, so the Captain keeps
editing it without root). It is not in this PR because adding a path changes the
Ring-0 **set**, which `immutable-core.yml` reserves to the Captain in its own
header. Proposed in
`docs/proposals/authority-exceptions-hook-protection-2026-07-27.md`; it edits
the same `pre-tool-use.sh` that §6.3 already forces onto the Captain's bench, so
it costs no extra window.

What the shape check *does* buy is narrower and still worth having: a
**wrong-shape** file cannot masquerade as an empty one. The first version used
`path.is_file()`, so `ln -sf /dev/null <path>` read as ABSENT — every exclusion
gone, no error. Found by attacking my own implementation; three arms in each
battery.

### 5.3 Failure semantics

| state | behaviour |
|---|---|
| absent | empty denylist — the ruled posture, and what a fresh hatch gets |
| present, empty | empty denylist |
| present, unreadable | **every call refused until repaired** — an unreadable Captain exclusion list is never ignored (same clause as `act-first-surfaces.yml`) |
| present as a symlink | refused, naming the shape (the enforcement plane's convention: a control surface is a real file or it is broken — cf. the observe-only marker and `killswitch-read.sh`) |
| present but not a regular file (directory, device) | refused, naming the shape |
| a row with no predicate, a non-string predicate value, a non-string `id`, or an `action_type` outside the classifier enum | **load error**, not a silent no-op — a row that cannot mean what it looks like is refused, naming the row and the problem |
| a row that cannot be evaluated | that row refuses |

E-stop unchanged and total: `rm instance/config/authority-enforcing` disarms the
whole typed plane, this surface with it. Proven (probe E17 below).

### 5.4 Proof it is honoured

Two layers, both of which **fail against pre-change code** — verified by
reverting `policy-shadow.py` to HEAD and re-running:

* `cabinet/scripts/lib/tests/test_captain_exceptions.py` — 31 tests. Against
  pre-change code: **16 failed, 3 passed** (measured at the 19 tests that
  existed then). After: 31 passed.
* `cabinet/tests/hook-regression/captain-exceptions.sh` — 19 probes driving the
  **real `pre-tool-use.sh`**. Against pre-change code: **PASS=10 FAIL=7**
  (measured at the 17 probes that existed then). After: PASS=19 FAIL=0. Wired
  into `run-hook-regression.sh`, so CI keeps it.

Both directions, at the hook:

```
row present   →  exit 2: TYPED POLICY BLOCK — captain_exception:no-echo-hello — synthetic harness row
row removed   →  exit 0
```

The harness drives a throwaway `CABINET_ROOT` skeleton, so it never writes a
live control surface — no `authority-exceptions.yml`, no `authority-enforcing`,
no `observe-only` in its write set.

---

### 5.5 It is not live until a Captain relock ceremony

`cabinet/scripts/policy-shadow.py` is germline (schg). Landing to master is the
correct and complete engineering path, but the bytes on the box only change when
the Captain runs one unlock/relock window. Until then the exception surface
exists in the repo and not in the running fleet. Named as a handback, not
worked around.

Checked while confirming that: the live locked `policy-shadow.py` is
byte-identical to master (`daf96a77c492`). **The live locked
`cabinet/scripts/hooks/pre-tool-use.sh` is not** — see §6.3.

---

## 6. Three live findings this dry run surfaced

### 6.1 ReDoS in an already-ENFORCING policy — availability

`no-product-workspace-write` (type `bash_write_to_path`, **in
`_LEGACY_ENFORCING_TYPES` today**) exhibits catastrophic backtracking. Its `sed`
and `perl` patterns in `policy_engine._WRITE_PATTERNS` nest an ambiguous
alternation, `(?:[^;&|]|'[^']*'|"[^"]*")*`, twice in one expression:

```
sed\b(?:[^;&|]|'[^']*'|"[^"]*")*(?:…-i…)(?:[^;&|]|'[^']*'|"[^"]*")*\s["']?{path}
```

`[^;&|]` overlaps both quoted alternatives, so a long command with no `;&|`
separator explodes exponentially. **52 of 80,307 recorded officer calls (0.06%)
exceed 1.5 s in this one policy**; a stack sample shows the process pinned at
99% CPU inside `sre_ucs2_match`. Smallest reproducer found in the corpus is
1,328 bytes — an ordinary multi-line `python3 - <<'PY'` heredoc.

**The live hook has no timeout.** An officer issuing such a command wedges
`pre-tool-use.sh` indefinitely — the officer hangs, and nothing reports it.

Not fixed here, deliberately: every obvious rewrite either narrows what the rule
matches (weakening an enforcing safety rule) or needs atomic groups, which the
system interpreter (3.9.6) does not have. It needs its own wave with an
equivalence proof. Backlogged.

### 6.2 Content-vs-action confusion in the ceiling classifier — precision

§4.6. Harmless while shadow-only; blocking the moment anything enforces. The
fix is to classify the *action*, not the command's text — parse the invocation
rather than substring-search the payload.

### 6.3 GERMLINE DRIFT — the live enforcement hook matches no commit

Found while verifying that a landed change would actually reach the box.
Measured, read-only, on the live deployment:

```
cabinet/scripts/hooks/pre-tool-use.sh   master a6614c7c97fd   live 754412b5fbca
cabinet/scripts/policy-shadow.py        master daf96a77c492   live daf96a77c492
```

The hook differs from master by **230 diff lines — 203 present only in master,
27 present only on the box** — and its content hash matches **none of the 74
commits touching that file** anywhere reachable from master. A germline file is
supposed to change only by landing to master and re-materializing under a
Captain unlock/relock; this one was edited in place inside an unlock window and
the edit never came back through git. (Caveat on the negative: I searched
history reachable from master in a fresh clone; a commit on an unmerged branch
would not be found.)

**What the box is missing.** The 203 master-only lines are, in the main,
commit `1cbeb14d` *"fix(safety): the emergency stop failed OPEN — invert the
default, one reader"*. Master reads the stop through a nonce-fenced probe
(`ECHO n1 / GET cabinet:killswitch / ECHO n2`), defaults `KS_VERDICT=INDETERMINATE`,
adds a second filesystem-marker channel (`instance/config/estop`), and halts
unless it can positively verify CLEAR. The live copy is the predecessor: a bare
`redis-cli GET` whose only evidence of a successful read is `$?`. It does halt
when `redis-cli` exits non-zero — so this is not the naive fail-open — but it
cannot tell a real answer from an exit-0 non-answer, has no filesystem channel,
and is exactly the shape the landed fix exists to replace.

Four other commits touching this file since 2026-07-16 are also not on the box.

**Handback, not a workaround.** Relocking germline needs interactive `sudo`,
which this session cannot take. It also should not be a blind overwrite: the 28
box-only lines must be adjudicated first — either they are stale predecessors of
landed work (discard) or they are unlanded local fixes (land them, then
re-materialize). Recorded in the cabinet-meta handbacks file.

The general lesson is the one this program keeps paying: **a fix that landed is
not a fix that is running.** Nothing measured master-vs-box until something
needed to know.

---

## 7. What would make the flip viable

In dependency order. None of these is a threshold change; all are composition.

1. **Give the matrix a risk class for running commands on this machine** —
   §4.5b decomposes why this, and not allowlist surgery, is the high-leverage
   move: the vocabulary has no row for "run a build tool", 34.4%+ of the
   ambiguous bucket is the shell parser failing to resolve command words at all,
   and greedy allowlist widening tops out at 84.4% using entries
   (`gh`, `sudo`, `python3`, `source`) that would delete the property the
   allowlist exists to prove. Do the two cheap legitimate pieces as well (pure
   shell builtins; the local git write verbs). Adding a class is a *widening*,
   so it needs the adversarial pass that produced the current default.
   Target: the `unclassified` bucket below ~1% of calls, re-measured with this
   instrument.
2. **Fix ceiling precision** (§6.2), re-measured the same way.
3. **Discharge the journaling precondition** (§4.8) — route raw officer
   Edit/Write through the write-ahead lane, or block them at the hook so only
   lane-executed acts can act.
4. **Decide the write-side question** (§4.7): enforcement filing needs and
   consuming grant budget must be intended, not inherited.
5. **Then flip, and soak.** The design doc's own Cycle-2 staging
   (`framework/docs/authority-matrix-design-2026-06-19.md` §7) already specifies
   parity corpus → Captain-approved flip → 48 h soak with instant revert.

Revert remains one command throughout: `rm instance/config/authority-enforcing`.

**Separately, and not gated on any of the above:** promote
`instance/config/authority-exceptions.yml` from a preference channel to a
boundary (§5.2). The right move is the one the Captain's ruling already names —
*guardrails through hooks*: add the path to `pre-tool-use.sh`'s protected-path
case list so officers cannot write it while the Captain still can, exactly as
`instance/config/autonomy.yml` is handled today. That list is kept in lockstep
with the schg set in `germline-lock.sh`, so it is a Captain ceremony (set change
+ amendment doc), not a session change. Until then the honest claim is the one
in §5.2, and it is written into the file's own header.

---

## 8. Provenance

Per the 2026-07-07 full-autonomy grant + the 2026-07-21 ownership-on-GO ruling.
Every number above was produced this session by
`cabinet/scripts/authority-matrix-dryrun.py` over the corpus in §2; the raw
result object is reproducible with the command in §3.
