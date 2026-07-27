# fix/shell-command-word-parser — cp1

Reviewed-Scope-Digest: 0ef33dd1ab744a236581bf8b35e51bb1cc6741c28ca2147e4b080e5f630373a3

## What this is

A defect fix in the shared shell command-word parser
(`framework/authority/policy_engine.py`), found by MEASUREMENT rather than by
attack. Not a widening: no risk class is added, no matrix vocabulary is
touched, no allowlist member is added to `_LOCAL_ONLY_BINARIES` or
`_GIT_LOCAL_SUBCOMMANDS`.

## The finding, reproduced

Corpus rebuilt READ-ONLY from the live event store through the PR-233
instrument's `--extract` mode (`sqlite3` `mode=ro` URI):
80,307 records — identical to that instrument's baseline of record. Its
decomposition reproduces exactly: 42,279 unclassified / 2,353 non-Bash /
126 unparseable / 3 `/dev/tcp` refusals / **39,797 analysable Bash commands**,
and the "only shell builtins / git verbs" row lands on 5,505 to the record.
Over that population the parser resolved **347 distinct tokens that are not
programs** as command words — the same 347 the dry-run reported.

## Root causes, each with the token it manufactured

| cause | manufactured | records |
|---|---|---|
| `&` treated as a separator inside the redirection `2>&1` | the digit `1` | 14,943 |
| comments never stripped (shlex has `comments=False`) | `#`, `##`, `###` | 1,134 |
| `${VAR:-default}` split as a brace group | `REDIS_HOST:-localhost` | 602+ |
| double-quote scanner ended a span at a `"` nested in `$( )` | ` -p $`, `null \| head -1)`, `) :: $(…)` | 1,100+ |
| every heredoc body re-parsed as shell | `##`, `import`, `.get`, whole sentences | — |
| `$(( ))` arithmetic scanned as a command | `(NOW-START)`, `i++` | — |
| `{}` of `find -exec` read as a brace group | `;` | — |
| `case` patterns and `for` loop variables | `$x`, `d`, `f`, `x`, `p`, `i`, `o` | — |
| substitution TEXT left in its containing statement | `3-People`, `%s` | — |

## What changed

`_split_on_statement_seps` is now a quoting-aware lexer: it understands
`$( )` / backtick / `${ }` / `$(( ))` nesting inside double quotes, strips
word-initial comments, keeps `&` inside redirection operators, treats `((` as
arithmetic, only splits a brace GROUP (never `${…}` or `{}`), drops `case`
patterns, and defers a heredoc body until its owner line ends. A heredoc body
is parsed as shell unless a program that provably cannot execute it as shell
reads it. `for`/`select`/`case`/`in`/`function` no longer recurse into their
operands. A leaf command word that cannot name a program is reported as
`UNRESOLVED` rather than invented.

## Direction — proven, not argued

Re-measured over all 67,346 Bash records, master vs this branch:

- **347 distinct non-program tokens → 1** (10,209 records → 1).
- Distinct "real binaries" tokens 607 → 236, so the optimistic bucket the
  dry run flagged shrank by 61%.
- **573 records block → allow**, and every one of them resolves EXCLUSIVELY to
  `_LOCAL_ONLY_BINARIES` members plus `git` at a verb in
  `_GIT_LOCAL_SUBCOMMANDS`. Checked programmatically over the whole set; the
  complete token vocabulary across all 573 is `[ basename cat cd chmod cp date
  diff echo git grep head ls mkdir mv pwd rm sleep stat tail tail test tr true
  wc`.
- **498 records allow → block**: a pre-existing FAIL-OPEN this closes. Master
  could not see a `$( )` inside a double-quoted string, so commands invoking
  `redis-cli` (468), `gh`, `launchctl` and `find` were classified
  provably-local. `echo "$(sendmail -t)"` was provably local on master.
- `is_destructive_rm`: **0 lost, 0 gained** across 67,346 records.

## Anti-regression

The round-1 and round-2 attack corpus re-runs green, plus the shapes this
rewrite could plausibly have re-opened (`cat <<EOF | bash`,
`sudo bash <<EOF`, `ssh host <<EOF`, `${x:-$(curl …)}`, `echo "$(sendmail -t)"`).
83 new arms; 16 behavioural arms + 37 guard arms fail against the pre-change
parser, and the 30 anti-vacuity arms pass on both by design.
`framework/authority/tests/` : 1,254 passed.

## Budget

`framework_production_noncomment_lines` 69,315 → 69,514 (+199), paid as the
`shell-command-word-parser` temporary allowance with the closed key set;
census re-binds to zero headroom in this commit. Zero new modules, zero new
files.
