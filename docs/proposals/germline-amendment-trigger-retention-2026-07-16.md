# Germline amendment — retain trigger receipts across officer restart

**Status:** proposed; Captain-gated as `AUD-12-R1`. This is the corrective
follow-up to `AUD-12`, not a rewrite of that completed history. Apply only in
the Captain unlock/relock ceremony, with the kill switch and observe-only
posture still active.

**Provenance:** self-ratified for preparation per the 2026-07-07 full-autonomy
grant and the Captain-approved readiness goal to make `origin/master` safe and
honest for a 72-hour observe-only dogfood, including trigger retention. The
grant does not waive the Captain-only unlock or authorize a runtime change.

## Confirmed P1

`cabinet/scripts/start-officer-mac.sh` kills the old trigger-channel process
and then runs:

```sh
XGROUP DELCONSUMER "cabinet:triggers:$OFFICER" "officer-$OFFICER" channel
```

Killing the stale process is correct. Deleting the stable Redis consumer is
not. Redis deletes every pending-entry-list (PEL) record owned by that consumer.
The stream entries remain, but the group's last-delivered cursor is already
past them. The replacement channel starts with the same consumer name and reads
ID `0`, so after `DELCONSUMER` it has no pending ownership to recover and `>`
will not revisit those entries. A routine officer restart can therefore turn
delivered-but-unacknowledged triggers into retained stream bytes that the normal
delivery path can no longer claim.

The post-tool-use `XAUTOCLAIM` safety net is defeated too: `DELCONSUMER`
removes the group-level PEL records that either consumer would need to claim.

That contradicts `AUD-12`'s consumer-side ACK contract: delivery is not
processing, and only `XACK` after processing may clear the receipt. The channel
already implements the correct restart behavior in
`cabinet/channels/redis-trigger-channel/index.ts`: `processPending()` reads ID
`0` before `processNew()` reads `>`.

## Live read-only evidence

At approximately `2026-07-16T12:45:00Z`, from the halted observe-only live
checkout, these read-only commands were run:

```sh
redis-cli --raw XINFO GROUPS cabinet:triggers:cos
redis-cli --raw XPENDING cabinet:triggers:cos officer-cos
```

They reported:

- group `officer-cos`; `consumers=4`; `pending=16`; `entries-read=936`;
  `last-delivered-id=1784199575321-0`; `lag=8`;
- pending range `1784117039686-0` through `1784199575321-0`;
- all 16 pending receipts owned by consumer `channel`.

Therefore running the current launcher for `cos` would delete all 16 ownership
records. The evidence intentionally records only Redis metadata, not trigger
payloads. No Redis or runtime mutation was used to establish the finding.

The live immutable launcher was also read-only verified as `schg`, clean in the
live worktree, and byte-identical to the proposal base; SHA-256:
`4a7505c9470594e5ea18d99208f417e8c0e009bd6edae15df8469cd79e5ca138`.

## Exact ceremony patch

Apply this source change exactly, then add the tests and runbook leg below in
the same commit. No other launcher behavior is in scope.

```diff
diff --git a/cabinet/scripts/start-officer-mac.sh b/cabinet/scripts/start-officer-mac.sh
--- a/cabinet/scripts/start-officer-mac.sh
+++ b/cabinet/scripts/start-officer-mac.sh
@@
-# Reap orphaned redis-trigger-channel processes + their stale group consumers.
+# Reap orphaned redis-trigger-channel processes while retaining the stable
+# group consumer and its pending-entry list across restarts.
@@
-# invariant we enforce here: exactly ONE live `channel` consumer per officer.
+# invariant we enforce here: exactly ONE live `channel` process per officer,
+# using the stable `channel` consumer identity across restarts.
@@
-# 2) Drop the stale `channel` group consumer so the new MCP registers clean and
-#    inherits no other consumer's pending. Idempotent (no-op if absent). The
-#    `worker` consumer (post-tool-use safety net) is intentionally left intact.
-redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
-  XGROUP DELCONSUMER "cabinet:triggers:$OFFICER" "officer-$OFFICER" channel > /dev/null 2>&1 || true
-# 3) Best-effort cleanup of the junk stream from the unexpanded-variable leak.
+# 2) Keep the `channel` consumer and its PEL intact. The replacement channel
+#    calls processPending() with ID 0 before reading new entries, so the first
+#    50 unACKed receipts are re-delivered at startup; the post-tool-use safety
+#    net drains any overflow. Deleting the consumer would delete those ownership
+#    records and violate AUD-12's consumer-side ACK contract.
+# 3) Best-effort cleanup of the junk stream from the unexpanded-variable leak.
 redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
   DEL 'cabinet:triggers:${OFFICER_NAME}' > /dev/null 2>&1 || true
```

The step number deliberately remains `3`: step `2` is now an explicit
retention invariant rather than a Redis command.

## Required tests in the same commit

Extend `cabinet/scripts/tests/test_channel_ack_readonly_contracts.py` with a
launcher source ratchet:

```diff
@@
 TRIGGERS_LIB = REPO / "cabinet/scripts/lib/triggers.sh"
+MAC_LAUNCHER = REPO / "cabinet/scripts/start-officer-mac.sh"
@@
 class TestConsumerSideAck:
+    def test_mac_restart_never_deletes_channel_consumer_or_its_pel(self):
+        src = MAC_LAUNCHER.read_text()
+        assert "DELCONSUMER" not in src, (
+            "officer restart must preserve every consumer PEL: DELCONSUMER "
+            "deletes unACKed receipts and violates AUD-12"
+        )
+        assert "processPending() with ID 0" in src
+        assert "consumer-side ACK contract" in src
```

Extend `cabinet/scripts/tests/test_triggers_stream_durability.py` with a real,
isolated Redis proof. It must prove both the new path and the old path's teeth:

```diff
@@
+def test_restart_keeps_same_consumer_pending_recoverable_and_delconsumer_has_teeth(
+    redis_port: int,
+):
+    token = uuid.uuid4().hex[:8]
+    stream = f"cabinet:triggers:restart-{token}"
+    group = f"officer-restart-{token}"
+    message_id = _redis_cli(
+        redis_port, "XADD", stream, "*", "message", "survives-restart"
+    ).stdout.strip()
+    assert _redis_cli(redis_port, "XGROUP", "CREATE", stream, group, "0").returncode == 0
+
+    first = _redis_cli(
+        redis_port, "XREADGROUP", "GROUP", group, "channel", "COUNT", "1",
+        "STREAMS", stream, ">",
+    )
+    assert message_id in first.stdout
+    before = _redis_cli(redis_port, "XPENDING", stream, group, "-", "+", "10")
+    assert before.stdout.strip().splitlines()[-1] == "1"
+
+    # Replacement process, same stable consumer: index.ts processPending()
+    # reads ID 0 before new entries. Redis re-delivers the owned receipt.
+    restarted = _redis_cli(
+        redis_port, "XREADGROUP", "GROUP", group, "channel", "COUNT", "1",
+        "STREAMS", stream, "0",
+    )
+    assert message_id in restarted.stdout
+    assert "survives-restart" in restarted.stdout
+    after = _redis_cli(redis_port, "XPENDING", stream, group, "-", "+", "10")
+    assert after.stdout.strip().splitlines()[-1] == "2"
+    assert _redis_cli(redis_port, "XACK", stream, group, message_id).stdout.strip() == "1"
+    assert _redis_cli(redis_port, "XACK", stream, group, message_id).stdout.strip() == "0"
+
+    # Negative control: the retired launcher command destroys ownership.
+    doomed_stream = f"cabinet:triggers:doomed-{token}"
+    doomed_group = f"officer-doomed-{token}"
+    doomed_id = _redis_cli(
+        redis_port, "XADD", doomed_stream, "*", "message", "doomed-by-delete"
+    ).stdout.strip()
+    assert _redis_cli(
+        redis_port, "XGROUP", "CREATE", doomed_stream, doomed_group, "0"
+    ).returncode == 0
+    assert doomed_id in _redis_cli(
+        redis_port, "XREADGROUP", "GROUP", doomed_group, "channel", "COUNT", "1",
+        "STREAMS", doomed_stream, ">",
+    ).stdout
+    assert _redis_cli(
+        redis_port, "XGROUP", "DELCONSUMER", doomed_stream, doomed_group, "channel"
+    ).stdout.strip() == "1"
+    cannot_recover = _redis_cli(
+        redis_port, "XREADGROUP", "GROUP", doomed_group, "channel", "COUNT", "1",
+        "STREAMS", doomed_stream, "0",
+    )
+    assert doomed_id not in cannot_recover.stdout
+    assert _redis_cli(redis_port, "XPENDING", doomed_stream, doomed_group).stdout.splitlines()[0] == "0"
+    assert doomed_id in _redis_cli(
+        redis_port, "XRANGE", doomed_stream, doomed_id, doomed_id
+    ).stdout
```

The negative control is load-bearing: without it the test only proves Redis can
re-deliver, not that the removed launcher command caused the confirmed failure.

## Observe-only runbook leg in the same commit

Append this item under `Verify before starting the clock` in
`docs/runbooks/observe-only-dogfood.md`:

```diff
@@
 - A synthetic trigger is delivered with an observe-only receipt, its exact
   `cabinet/scripts/hooks/observe-ack.sh <id>` command succeeds, pending returns
   to zero, and replaying the same receipt is an idempotent `already_clear`
   success.
+- Restart retention is proved before the soak: with one synthetic trigger left
+  pending under consumer `channel`, restart that officer without widening the
+  kill switch, observe-only posture, spend cap, or egress policy. The same
+  receipt ID must be re-delivered by startup ID-0 recovery, then exact-ID ACK
+  must return 1 and pending must return to zero. Any PEL drop before XACK is a
+  failed gate; never use `XGROUP DELCONSUMER` as restart cleanup.
```

## Ceremony and live acceptance

1. Keep the kill switch active, observe-only enabled, and the 72-hour clock
   stopped. Record the current `cos` PEL ID set and count; do not inspect
   payloads.
2. Captain unlocks with `sudo bash cabinet/scripts/germline-lock.sh unlock`.
3. Apply the exact launcher/test/runbook patch and run:
   `python3.12 -m pytest cabinet/scripts/tests/test_channel_ack_readonly_contracts.py cabinet/scripts/tests/test_triggers_stream_durability.py -q`.
4. Relock in the same session; `germline-lock.sh verify` and `status` must pass.
5. Restart one officer with a synthetic receipt pending. Prove the same receipt
   ID reappears under `channel`, its delivery count increments, `XACK` returns
   `1`, repeat `XACK` returns `0`, and no pre-existing PEL ID disappears before
   its own ACK.
6. Restart the remaining enabled officers only after that proof. Record Doctor,
   trigger, posture, spend, egress, and kill-switch evidence. The soak clock
   stays stopped on any mismatch.

## Safe rollback

The immediate rollback is operational: keep the kill switch active, stop the
affected officer/channel process, preserve Redis and the evidence bundle, and
return to the pre-restart filesystem snapshot. Do **not** restore
`DELCONSUMER` while any PEL entry exists; that would make rollback itself the
data-loss event.

If a source revert is required, first drain only through normal processing and
exact-ID `XACK`, prove `XPENDING ... officer-<role>` is zero, then apply the
amendment reversal in a new Captain unlock/relock ceremony. Re-run both tests
and the live synthetic restart leg. The 72-hour clock remains stopped until the
same retention proof is green again.
