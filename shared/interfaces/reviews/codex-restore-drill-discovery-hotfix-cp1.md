# Fable 5 checkpoint — PostgreSQL restore-tool discovery

**Reviewer:** Claude Fable 5, max-effort, isolated tool-less review

**Date:** 2026-07-16

**Scope:** `restore-drill.sh` candidate exit status and focused regressions

## Incident evidence

The first production restore drill successfully restored and exactly verified
Redis, but failed before PostgreSQL validation with `pg_restore is missing`.
The deployed trace showed that `postgres_bin_candidates` emitted valid
directories, inherited status 1 from its final absent optional-directory probe,
and was consumed by `candidates=$(postgres_bin_candidates) || return 1`. The
caller therefore returned before inspecting any emitted candidate. No
`CABINET_POSTGRES_BIN_DIR` override was active, and two complete local server
toolchains were present.

The patch makes the optional-location generator return success explicitly. It
also pins the negative missing-tool test to its deliberately empty directory
and adds a PATH-discovery integration regression. With the fix temporarily
removed, that regression failed because the drill returned 1; with the fix
restored, it passed. The complete focused file passed 39 tests, and `bash -n`
plus `git diff --check` were clean.

## Review disposition

An initial tool-less reviewer response was discarded because it claimed tool
use and described process-substitution code absent from the supplied source.
A fresh session received the exact deployed functions, patch, trace facts, host
candidate matrix, and fix-removed/fix-restored evidence. It made no tool claims.

The fresh review confirmed that the generator's implicit final status was the
root cause; the explicit `return 0` is the minimal correct fix; configured-path
fail-fast behavior is unchanged; empty discovery output still fails closed in
the callers; the negative test is now host-independent; and the positive test
proves that the fake PATH toolchain completed the disposable restore.

**VERDICT: APPROVE — no remaining P0–P2.**

Non-blocking P3 notes were limited to host sensitivity of the pre-fix
reproduction and a possible future review of independently selected client and
server toolchain versions.

`CHECKPOINT VERDICT: PASS`
