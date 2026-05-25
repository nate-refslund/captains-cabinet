# C3 conventional-commit hook — FW-029-family bypass corpus (golden-eval spec)

Spec 049 AC#7 point 4. The executable spec for `cabinet/scripts/lib/git-commit-argv.sh` +
`cabinet/scripts/hooks/pre-tool-use-conventional-commit.sh`. The harness (`test-spec-049.sh`
§C3) drives these as pos/neg cases. The parser is authored to satisfy this table, then
adversary-passed (≥2) + Opus-ship-gated before any enforce-mode flip. **Hook default = WARN
mode** (warn + FP-JSONL log, never block) — so an imperfect parser cannot brick commits;
enforce-mode is a separate later decision after the FP rate is validated.

Conventional-commit subject regex (AC#7): `^(feat|fix|refactor|docs|test|chore|perf|style)(\([a-z0-9_-]+\))?: .+$`

## Detection contract (`gca_invokes_git_commit`)
A command "invokes git commit" iff `git ... commit` appears at a SHELL STATEMENT boundary
(line-start OR after `; & | ( ) { } \``), optionally prefixed by command-modifiers
(`env`, `VAR=val`, `nohup/nice/time/exec/stdbuf/...`) and optional `git` global flags
(`-c k=v`, `-C path`, `--git-dir=…`), then the `commit` subcommand. NOT a substring match
(the FW-029 amplification class).

## Extraction contract (`gca_commit_subject`)
Returns the subject (first line of the message) + a status: 0=extracted-validate /
1=no-inline-message-skip (`-c`/`-C`/`--reuse-message` reuse, or editor `-e`) / 2=present-but-
UNEXTRACTABLE → FAIL-CLOSED (warn). Never fail-open (never silently treat an unparseable
commit as compliant).

## --no-verify contract (`gca_has_no_verify`)
Detect `--no-verify` or standalone `-n` token on a `git commit`/`git push` (flag token at a
word boundary, NOT inside a quoted message body) → block-with-surfaced-reason.

---

## POSITIVE — valid conventional commit, must NOT warn (detect=Y, valid=Y, no_verify=N)
| # | command | subject extracted |
|---|---------|-------------------|
| P1 | `git commit -m "feat(auth): add login"` | feat(auth): add login |
| P2 | `git commit -m 'fix: null deref'` | fix: null deref |
| P3 | `git commit -m $'refactor(core): split\n\nbody here'` | refactor(core): split |
| P4 | `git commit --message="docs: update readme"` | docs: update readme |
| P5 | `git -c user.name=ci commit -m "chore(ci): bump"` | chore(ci): bump (global flag tolerated) |
| P6 | `cd /repo && git commit -m "test(api): add case"` | test(api): add case (chain prefix) |
| P7 | `GIT_AUTHOR_NAME=x git commit -m "perf: cache"` | perf: cache (inline VAR= prefix) |

## NEGATIVE — invalid message, must WARN (detect=Y, valid=N)
| # | command | why invalid |
|---|---------|-------------|
| N1 | `git commit -m "added some stuff"` | no type prefix |
| N2 | `git commit -m "WIP"` | no `type: ` |
| N3 | `git commit -m "Fix: capitalized"` | type must be lowercase enum |
| N4 | `git commit -m "feat add login"` | missing colon |
| N5 | `git commit -m 'feature(x): wrong-type'` | `feature` not in enum |

## BYPASS / EDGE — must fail-CLOSED or detect correctly (never fail-open)
| # | command | expected |
|---|---------|----------|
| B1 | `git commit -m "feat: x" --no-verify` | no_verify=Y → block-reason |
| B2 | `git commit -n -m "feat: x"` | no_verify=Y (`-n` standalone) → block |
| B3 | `git commit -F /tmp/msg.txt` | read first line → validate; if unreadable → status 2 fail-closed-warn |
| B4 | `git commit -c HEAD~1` | status 1 (reuse, no inline msg) → skip validation |
| B5 | `bash -c "git commit -m 'badmsg'"` | detect=Y (nested) → warn on `badmsg` |
| B6 | `(git commit -m "bad")` | detect=Y (subshell prefix) → warn |
| B7 | `{ git commit -m "bad"; }` | detect=Y (brace prefix) → warn |
| B8 | `git commit -m "msg with \" escaped quote"` | escape-aware DQ span; subject extracted intact |

## FALSE-POSITIVE GUARDS — must NOT fire (detect=N)
| # | command | why no-fire |
|---|---------|-------------|
| F1 | `echo "git commit -m bad"` | not a real commit invocation (echo arg) |
| F2 | `git commit -m "see 'git commit -m foo' in the docs"` | detect=Y but validate the OUTER subject ("see '...'"), NOT FP on the inner mention (FW-029 substring-amplification guard) |
| F3 | `cat log \| grep "git commit"` | substring in a pipe arg, not an invocation |
| F4 | `git log --grep="git commit -m x"` | `git log`, not `git commit` |

> Authoring note: prefer sequential per-form bash `[[ =~ ]]` extraction (one capture per quote
> form: SQ `'…'`, DQ escape-aware `"([^"\\]|\\.)*"`, ANSI-C `$'…'`, `--message=…`, bare) in
> priority order, returning on first match — not one monster alternation. F2 is the hard FP:
> extract the FIRST `-m`/`--message` value as the subject; the inner mention lives INSIDE that
> value, so validating the outer value (which starts "see '…") correctly yields invalid→warn
> without a separate inner match.
