#!/usr/bin/env bun
/**
 * Redis Trigger Channel — MCP Channel plugin for Captain's Cabinet
 *
 * Subscribes to Redis Streams and pushes triggers into Claude Code
 * sessions instantly via MCP notifications. Replaces /loop polling.
 *
 * ACK CONTRACT (AUD-12, audit #32 — consumer-side ACK): this channel NEVER
 * XACKs. Delivery is not processing — the old ack-on-emit lost any trigger
 * when the session crashed between the notification push and the wake turn.
 * A trigger stays PENDING in the consumer group until the OFFICER processes
 * it and runs trigger_ack (cabinet/scripts/lib/triggers.sh), or the
 * post-tool-use safety net (trigger_read_safety_net, XAUTOCLAIM after the
 * grace window) reclaims + re-surfaces it into the ids_file the officer's
 * ACK pipeline consumes. Net effect: at-least-once delivery; duplicates are
 * possible and expected, silent loss is not.
 *
 * Usage: OFFICER_NAME=cos bun run index.ts
 * Or via .mcp.json as an MCP server with claude/channel capability.
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createClient } from "redis";

const OFFICER = process.env.OFFICER_NAME || "unknown";
const REDIS_URL = process.env.REDIS_URL || "redis://redis:6379";
const OBSERVE_ONLY = process.env.CABINET_OBSERVE_ONLY === "1";

// Guard against a broken launch path. If OFFICER_NAME was never exported into
// this process (or the MCP-config "${OFFICER_NAME}" placeholder was passed
// through un-interpolated), we must NOT silently join a junk consumer group:
// that leaks an orphan bun process on a `cabinet:triggers:${OFFICER_NAME}`
// stream and a stray `channel` consumer that can split a real officer's stream
// (root cause 2026-06-25 — 15 such zombies found). Fail loud and exit so the
// supervisor/launcher relaunches with a valid identity instead of leaking.
if (
  OFFICER === "unknown" ||
  OFFICER.includes("$") ||           // un-interpolated ${OFFICER_NAME}
  !/^[a-z0-9][a-z0-9-]*$/.test(OFFICER)  // mirrors the cabinet slug guard
) {
  process.stderr.write(
    `redis-trigger-channel: refusing to start — invalid OFFICER_NAME=${JSON.stringify(
      process.env.OFFICER_NAME
    )}. Launch with a concrete officer slug (e.g. OFFICER_NAME=cos).\n`
  );
  process.exit(1);
}

const STREAM_KEY = `cabinet:triggers:${OFFICER}`;
const GROUP_NAME = `officer-${OFFICER}`;
const CONSUMER_NAME = "channel";

// Create MCP server with channel capability
const server = new Server(
  { name: "redis-trigger-channel", version: "1.0.0" },
  {
    capabilities: {
      experimental: { "claude/channel": {} },
    },
  }
);

// Create Redis client
const redis = createClient({ url: REDIS_URL });

redis.on("error", (err) => {
  // Silently handle Redis errors — don't crash the channel
  process.stderr.write(`Redis error: ${err.message}\n`);
});

/**
 * Ensure consumer group exists for this officer
 */
async function ensureConsumerGroup(): Promise<void> {
  try {
    await redis.xGroupCreate(STREAM_KEY, GROUP_NAME, "0", { MKSTREAM: true });
  } catch (err: any) {
    // BUSYGROUP = already exists, that's fine
    if (!err.message?.includes("BUSYGROUP")) {
      process.stderr.write(`Consumer group error: ${err.message}\n`);
    }
  }
}

/**
 * Re-surface this consumer's pending (delivered-but-unACK'd) messages from
 * previous sessions. NO ACK here (AUD-12): re-delivery is still delivery,
 * not processing — the entries stay pending until the officer's trigger_ack
 * (or the post-tool-use XAUTOCLAIM safety net claims them for `worker`).
 */
async function processPending(): Promise<void> {
  try {
    const pending = await redis.xReadGroup(GROUP_NAME, CONSUMER_NAME, {
      key: STREAM_KEY,
      id: "0",
    }, { COUNT: 50 });

    if (!pending) return;

    for (const stream of pending) {
      for (const msg of stream.messages) {
        const content = msg.message?.message || JSON.stringify(msg.message);
        await pushToSession(content, msg.id);
      }
    }
  } catch (err: any) {
    process.stderr.write(`Pending processing error: ${err.message}\n`);
  }
}

/**
 * Push a trigger message into the Claude Code session
 */
async function pushToSession(content: string, messageId: string): Promise<void> {
  try {
    const deliveredContent = OBSERVE_ONLY
      ? `${content}\n\n[observe-only receipt: after processing this trigger, run cabinet/scripts/hooks/observe-ack.sh ${messageId}]`
      : content;
    await server.notification({
      method: "notifications/claude/channel",
      params: {
        content: deliveredContent,
        meta: {
          source: "redis",
          stream: STREAM_KEY,
          message_id: messageId,
          officer: OFFICER,
        },
      },
    });
  } catch (err: any) {
    process.stderr.write(`Notification error: ${err.message}\n`);
  }
}

/**
 * Main subscription loop — blocks on XREADGROUP waiting for new triggers
 */
async function subscribeLoop(): Promise<void> {
  while (true) {
    try {
      const results = await redis.xReadGroup(GROUP_NAME, CONSUMER_NAME, {
        key: STREAM_KEY,
        id: ">",
      }, { COUNT: 10, BLOCK: 5000 }); // Block for 5 seconds, then retry

      if (!results) continue; // Timeout, no new messages

      for (const stream of results) {
        for (const msg of stream.messages) {
          const content = msg.message?.message || JSON.stringify(msg.message);
          await pushToSession(content, msg.id);
          // NO ACK on emit (AUD-12, audit #32): delivery != processing. The
          // entry stays pending until the officer's trigger_ack, or the
          // post-tool-use XAUTOCLAIM safety net reclaims it after the grace
          // window. A crash between this push and the officer's wake turn
          // therefore no longer loses the trigger.
        }
      }

      // NOTE: no channel-side XTRIM either — trimming can delete entries that
      // are still pending (unprocessed) under the new contract. Stream trim
      // happens on the ACK side (trigger_ack in lib/triggers.sh), i.e. only
      // after processing.

    } catch (err: any) {
      if (err.message?.includes("NOGROUP")) {
        await ensureConsumerGroup();
      } else {
        process.stderr.write(`Subscribe error: ${err.message}\n`);
        // Back off on errors
        await new Promise((r) => setTimeout(r, 2000));
      }
    }
  }
}

/**
 * Main entry point
 */
async function main(): Promise<void> {
  // Connect to Redis
  await redis.connect();

  // Ensure consumer group exists
  await ensureConsumerGroup();

  // Connect MCP server via stdio
  const transport = new StdioServerTransport();
  await server.connect(transport);

  // Brief delay for MCP handshake to complete before sending notifications
  await new Promise((r) => setTimeout(r, 1000));

  // Process any pending messages from before restart
  await processPending();

  // Graceful shutdown
  const shutdown = async () => {
    try {
      await redis.disconnect();
    } catch {}
    process.exit(0);
  };
  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);

  // Start the subscription loop
  await subscribeLoop();
}

main().catch((err) => {
  process.stderr.write(`Fatal: ${err.message}\n`);
  process.exit(1);
});
