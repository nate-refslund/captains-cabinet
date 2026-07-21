# Germline amendment — KILLSWITCH SEND-PATH golden eval body (EVAL-002) — 2026-07-21

**Status:** staged — awaiting a Captain germline unlock window
**Filed by:** orchestrator build lane (Phase-0 relaunch, LANE A), per the
2026-07-07 full-autonomy grant
**Safety law being pinned:** the Captain's emergency stop halts the front-door
SEND path. When `cabinet:killswitch` == `active` OR the control plane is
unreachable, every front-door Telegram send is refused before any byte leaves
the process, returns a structured refusal (never raises), and reuses the one
SEC-3 killswitch reader. Send-path twin of EVAL-001 (killswitch at the
pre-tool-use HOOK layer).

## What this stages

ONE new golden-eval body file inside `memory/golden-evals/` — a germline
(schg-locked) directory. Per germline etiquette this amendment STAGES the file;
only the Captain applies it in an unlock window. Everything runnable already
landed non-germline in the same change, so the suite enforces the law TODAY
with or without this body file:

- the fix itself: fail-closed killswitch gate in
  `framework/frontdoor/channel.py` (unlocked-content edit; the germline
  `FILES[]` list is untouched — the fresh instance re-locks from master)
- per-method unit proofs (RED→GREEN):
  `framework/frontdoor/tests/test_channel_killswitch.py`
- deterministic harness: `cabinet/evals/killswitch-send/harness.py` (+ README)
  — house pattern of EVAL-024/025/026 (body germline, harness non-germline)
- harness pytest wrapper + teeth + pairing:
  `cabinet/scripts/tests/test_killswitch_send_eval.py`
- runner registration: section `EVAL-002-KILLSWITCH-SEND` in
  `cabinet/scripts/run-golden-evals.sh` (fail-closed: a missing harness is a
  FAIL; only a missing interpreter skips)

## Why this touches germline

The golden-eval BODY series lives in `memory/golden-evals/` by house law (the
evals are Captain-owned acceptance criteria; officers must not be able to
weaken them). That directory is schg-locked on the live checkout, so the body
cannot land as a tree edit from a running fleet — a staged patch plus this
ceremony note is the sanctioned route. In THIS Phase-0 relaunch the fleet is
DEAD, so the body is written directly in the fresh clone and the fresh instance
re-locks from master; this note remains the provenance record.

## Exact ceremony file list

| # | Path | Action |
|---|------|--------|
| 1 | `memory/golden-evals/eval-002-killswitch-send-path.md` | CREATE, byte-verbatim (already written in this change) |

## Live application (Captain, same day — only if relocking a live fleet)

```bash
# 1. open the window (root):
sudo cabinet/scripts/germline-lock.sh unlock
# 2. confirm/write the body file:
$EDITOR memory/golden-evals/eval-002-killswitch-send-path.md
# 3. verify the suite sees it green:
bash cabinet/scripts/run-golden-evals.sh 2>&1 | grep -A1 "EVAL-002-KILLSWITCH-SEND"
# 4. relock the SAME day (root):
sudo cabinet/scripts/germline-lock.sh lock
cabinet/scripts/germline-lock.sh status
```

Rollback: remove the one body file inside another unlock window; the
`EVAL-002-KILLSWITCH-SEND` runner section keys off
`cabinet/evals/killswitch-send/harness.py` (non-germline) and stays green with
or without the body file, so no other surface moves.
