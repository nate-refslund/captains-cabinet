#!/usr/bin/env node
/**
 * advisor-crew.ts — Anthropic advisor-tool beta wrapper for Cabinet Crew tasks
 *
 * Invoked by advisor-crew.sh. Uses raw fetch() — no SDK dep required.
 * Exits 0 on success (result to stdout, usage summary to stderr).
 * Exits 1 on any failure (structured error to stderr).
 *
 * Environment:
 *   ANTHROPIC_API_KEY        — required
 *   ADVISOR_BETA_VERSION     — default advisor-tool-2026-03-01
 *   ADVISOR_MODEL            — default claude-fable-5
 *   OFFICER_NAME             — for cost attribution (or --officer flag)
 *   REDIS_HOST / REDIS_PORT  — default redis / 6379
 */

// ────────────────────────────────────────────────────────────
// Arg parsing
// ────────────────────────────────────────────────────────────

interface Args {
  task: string;
  contextFile?: string;
  executor: string;
  expectedCalls: number;
  officer: string;
  dryRun: boolean;
  maxTokens: number;
}

function parseArgs(argv: string[]): Args {
  const args: Record<string, string> = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith("--") && i + 1 < argv.length) {
      args[argv[i].slice(2)] = argv[i + 1];
      i++;
    }
  }

  if (!args["task"]) {
    process.stderr.write("ERROR: --task is required\n");
    process.exit(1);
  }

  return {
    task: args["task"],
    contextFile: args["context"],
    executor: args["executor"] || "claude-sonnet-4-6",
    expectedCalls: parseInt(args["expected-calls"] || "1", 10),
    officer: args["officer"] || process.env.OFFICER_NAME || "unknown",
    dryRun: args["dry-run"] === "true" || args["dry-run"] === "1",
    maxTokens: parseInt(args["max-tokens"] || "8192", 10),
  };
}

// ────────────────────────────────────────────────────────────
// Context loading + ceiling check
// ────────────────────────────────────────────────────────────

const MAX_CONTEXT_CHARS = 200_000 * 4; // ~200k tokens at ~4 chars/token

async function loadContext(contextFile: string | undefined): Promise<string> {
  if (!contextFile) return "";
  try {
    const { readFileSync } = await import("fs");
    const content = readFileSync(contextFile, "utf8");
    return content;
  } catch (err) {
    process.stderr.write(`WARNING: Could not read context file ${contextFile}: ${err}\n`);
    return "";
  }
}

function checkContextCeiling(task: string, context: string): void {
  const totalChars = task.length + context.length;
  if (totalChars > MAX_CONTEXT_CHARS) {
    process.stderr.write(
      `ERROR: Context too large for advisor path (${totalChars} chars ≈ ${Math.round(totalChars / 4)} tokens). ` +
      `Advisor path is capped at 200k tokens. Chunk the context or use non-advisor Crew for this task.\n`
    );
    process.exit(1);
  }
}

// ────────────────────────────────────────────────────────────
// System prompt (Anthropic's suggested blocks — verbatim from design doc)
// ────────────────────────────────────────────────────────────

function buildSystemPrompt(task: string, officer: string): string {
  const today = new Date().toISOString().slice(0, 10);
  const officerLine = officer && officer !== "unknown"
    ? `You are assisting the ${officer.toUpperCase()} officer of the Captain's Cabinet. Answer in first person where natural (avoid "your CRO / your team" — it's "I / we").`
    : "";

  // NOTE: a conciseness block directing the advisor to "respond in 100 words
  // or fewer" was tried and REMOVED after CRO's 2026-04-17 re-pilot showed it
  // made advisor output WORSE (1289 → 2278 tokens, +77%). Opus 4.7 appears
  // to ignore word-cap instructions in the system prompt regardless of how
  // strong the wording. Rather than keep a block the model ignores and pay
  // the extra input tokens, we accept ~1500-2500 advisor output tokens per
  // call as the current model-level floor and budget cost accordingly. The
  // officer-identity and today's-date injections below are kept — they both
  // produced measurable behavior change in the pilot.
  return `You are a skilled execution agent completing a focused task.

Today's date: ${today}. If the task involves deadlines, time windows, or
recent events, use this date as the present reference — do not rely on your
training-data estimate.

${officerLine}

## When to consult the advisor
- Before making a non-obvious architectural/strategic choice
- When stuck for more than 1 tool call
- Before any action that is hard to reverse
- Before a commit or publish

## How to weight advice
- Advice is input, not command
- Challenge it if it contradicts strong evidence you already have
- If advice conflicts with explicit user instruction, follow the user

Complete the task thoroughly. Return only your final synthesized result.`;
}

function buildUserMessage(task: string, context: string): string {
  if (!context) return task;
  return `${task}\n\n---\nContext:\n${context}`;
}

// ────────────────────────────────────────────────────────────
// Request builder
// ────────────────────────────────────────────────────────────

interface AdvisorToolDef {
  type: string;
  name: string;
  model: string;
  cache_control?: { type: string; ttl: string };
}

function buildRequestBody(args: Args, context: string): object {
  const advisorModel = process.env.ADVISOR_MODEL || "claude-fable-5";

  const advisorTool: AdvisorToolDef = {
    type: "advisor_20260301",
    name: "advisor",
    model: advisorModel,
  };

  // Add cache_control only when expected calls >= 3
  if (args.expectedCalls >= 3) {
    advisorTool.cache_control = { type: "ephemeral", ttl: "5m" };
  }

  return {
    model: args.executor,
    max_tokens: args.maxTokens,
    system: buildSystemPrompt(args.task, args.officer),
    tools: [advisorTool],
    messages: [
      {
        role: "user",
        content: buildUserMessage(args.task, context),
      },
    ],
  };
}

// ────────────────────────────────────────────────────────────
// Usage parsing — executor vs advisor tokens
// ────────────────────────────────────────────────────────────

interface IterationUsage {
  input_tokens: number;
  output_tokens: number;
  cache_creation_input_tokens?: number;
  cache_read_input_tokens?: number;
}

interface UsageSummary {
  executorInput: number;
  executorOutput: number;
  executorCacheWrite: number;
  executorCacheRead: number;
  advisorInput: number;
  advisorOutput: number;
  advisorCacheWrite: number;
  advisorCacheRead: number;
  totalInput: number;
  totalOutput: number;
  executorCostMicro: number;
  advisorCostMicro: number;
  totalCostMicro: number;
  advisorCallCount: number;
}

// Pricing — microdollars per token, which is the same number as $/MTok.
//
// FIXED 2026-07-26. This table used to carry hand-typed cache rates copied from
// cabinet/scripts/hooks/stop-hook.sh, and it carried that file's bug: opus
// cache_write was written as $3.75/MTok and cache_read as $0.30/MTok, i.e. 0.25x
// and 0.02x of the input rate instead of the published 1.25x and 0.10x — a 5x
// UNDER-report on every cached token. Sonnet had the identical 5x error
// ($0.75 / $0.06). Only the fable row was right, which is how it survived review.
// Unknown models also fell through to Sonnet, the CHEAPEST row, so anything the
// matcher failed to recognise was billed at a fifth of Opus.
//
// Both faults are now structurally unavailable:
//   * cache prices are DERIVED from the input rate by the published
//     multipliers, never typed in, so a 5x error would require editing a
//     multiplier constant;
//   * an unknown model resolves to the most expensive known rate per dimension,
//     never the cheapest — every estimation error must fail toward
//     OVER-reporting, because the cabinet stopped gating on spend
//     (Captain 2026-07-26) and this is a watch, not a cap.
// Rate provenance and the identical constants live in framework/cost/meter.py.
const MULT_CACHE_WRITE_5M = 1.25;  // 5-minute TTL cache write (1-hour is 2.00x)
const MULT_CACHE_READ = 0.10;      // cache hit

// [model-id substring, input $/MTok, output $/MTok]. First match wins, so more
// specific families go first — mirrors meter.RATES key order.
const RATES: Array<[string, number, number]> = [
  ["fable", 10, 50],
  ["opus", 15, 75],
  ["sonnet", 3, 15],
  ["haiku", 1, 5],
];

interface ModelPricing {
  inputMicro: number;
  outputMicro: number;
  matched: string;
}

function pricingFor(model: string): ModelPricing {
  const m = (model || "").toLowerCase();
  for (const row of RATES) {
    if (m.includes(row[0])) {
      return { inputMicro: row[1], outputMicro: row[2], matched: row[0] };
    }
  }
  // PER-DIMENSION max, not the max of (input+output): a future row with a high
  // input rate and a low output rate would otherwise leave unknown models
  // resolving elsewhere and under-billing input.
  return {
    inputMicro: Math.max.apply(null, RATES.map(function (r) { return r[1]; })),
    outputMicro: Math.max.apply(null, RATES.map(function (r) { return r[2]; })),
    matched: "unknown",
  };
}

// One response priced, in microdollars.
//
// Cache writes are charged at the 5m multiplier because this script pins
// `ttl: "5m"` on the only cache_control it ever sets (buildRequestBody). If a
// 1h TTL is ever introduced here, that arm must use MULT_CACHE_WRITE_1H — the
// advisor usage envelope reports a single cache_creation_input_tokens total
// with no TTL split, so the multiplier has to follow the REQUEST, not the
// response.
function costMicro(p: ModelPricing, input: number, output: number,
                   cacheWrite: number, cacheRead: number): number {
  return Math.round(
    input * p.inputMicro +
    output * p.outputMicro +
    cacheWrite * p.inputMicro * MULT_CACHE_WRITE_5M +
    cacheRead * p.inputMicro * MULT_CACHE_READ
  );
}

function parseUsage(usage: any, advisorModel: string, executorModel: string): UsageSummary {
  const summary: UsageSummary = {
    executorInput: 0, executorOutput: 0, executorCacheWrite: 0, executorCacheRead: 0,
    advisorInput: 0, advisorOutput: 0, advisorCacheWrite: 0, advisorCacheRead: 0,
    totalInput: usage?.input_tokens || 0,
    totalOutput: usage?.output_tokens || 0,
    executorCostMicro: 0, advisorCostMicro: 0, totalCostMicro: 0,
    advisorCallCount: 0,
  };

  const iterations: Array<{ type: string } & IterationUsage> = usage?.iterations || [];

  for (const iter of iterations) {
    const inp = iter.input_tokens || 0;
    const out = iter.output_tokens || 0;
    const cw = iter.cache_creation_input_tokens || 0;
    const cr = iter.cache_read_input_tokens || 0;

    if (iter.type === "advisor_message") {
      summary.advisorInput += inp;
      summary.advisorOutput += out;
      summary.advisorCacheWrite += cw;
      summary.advisorCacheRead += cr;
      summary.advisorCallCount++;
    } else {
      // executor_message or any other type
      summary.executorInput += inp;
      summary.executorOutput += out;
      summary.executorCacheWrite += cw;
      summary.executorCacheRead += cr;
    }
  }

  // If no iterations array, attribute all to executor
  if (iterations.length === 0) {
    summary.executorInput = summary.totalInput;
    summary.executorOutput = summary.totalOutput;
  }

  // Cost calculations — rates and cache multipliers from the derived table above.
  const executorPricing = pricingFor(executorModel);
  const advisorPricing = pricingFor(advisorModel);

  summary.executorCostMicro = costMicro(
    executorPricing, summary.executorInput, summary.executorOutput,
    summary.executorCacheWrite, summary.executorCacheRead);

  summary.advisorCostMicro = costMicro(
    advisorPricing, summary.advisorInput, summary.advisorOutput,
    summary.advisorCacheWrite, summary.advisorCacheRead);

  summary.totalCostMicro = summary.executorCostMicro + summary.advisorCostMicro;

  return summary;
}

// A principal becomes a Redis FIELD NAME and reaches an execSync command line,
// and it arrives from argv or the environment. Same charset and same
// `unattributed` fallback as meter.safe_principal — spend we cannot attribute
// is still spend and must still be counted, just never against a wrong officer.
function safePrincipal(name: string): string {
  const slug = (name || "").trim().toLowerCase();
  if (!slug || slug === "unknown" || slug === "none" || slug === "null") {
    return "unattributed";
  }
  return /^(svc:)?[a-z0-9][a-z0-9._-]{0,63}$/.test(slug) ? slug : "unattributed";
}

// ────────────────────────────────────────────────────────────
// Redis cost tracking (mirrors stop-hook.sh pattern exactly)
// ────────────────────────────────────────────────────────────

async function writeAdvisorCosts(rawOfficer: string, usage: UsageSummary, model: string, executorModel: string): Promise<void> {
  const { execSync, execFileSync } = await import("child_process");
  const officer = safePrincipal(rawOfficer);
  const redisHost = process.env.REDIS_HOST || "redis";
  const redisPort = process.env.REDIS_PORT || "6379";
  const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD (UTC, matches meter.utc_date)
  const timestamp = new Date().toISOString();

  const exec = (cmd: string) => {
    try {
      execSync(cmd, { stdio: "ignore" });
    } catch {
      // Best-effort — Redis write failures never abort the task
    }
  };

  // Per-officer last-values (expire 24h).
  // EXECUTOR HALF ADDED 2026-07-26: parseUsage has always computed
  // executorCostMicro, and this function has always thrown it away — every
  // advisor-crew call persisted only the advisor side, so the executor tokens
  // (the larger half on a single-consultation task) were computed, printed to
  // stderr, and then dropped on the floor.
  exec(
    `redis-cli -h ${redisHost} -p ${redisPort} HSET "cabinet:cost:advisor:${officer}" ` +
    `last_input "${usage.advisorInput}" ` +
    `last_output "${usage.advisorOutput}" ` +
    `last_cache_write "${usage.advisorCacheWrite}" ` +
    `last_cache_read "${usage.advisorCacheRead}" ` +
    `last_cost_micro "${usage.advisorCostMicro}" ` +
    `last_model "${model}" ` +
    `last_advisor_calls "${usage.advisorCallCount}" ` +
    `last_executor_input "${usage.executorInput}" ` +
    `last_executor_output "${usage.executorOutput}" ` +
    `last_executor_cache_write "${usage.executorCacheWrite}" ` +
    `last_executor_cache_read "${usage.executorCacheRead}" ` +
    `last_executor_cost_micro "${usage.executorCostMicro}" ` +
    `last_executor_model "${executorModel.replace(/[^A-Za-z0-9._:@-]/g, "")}" ` +
    `last_total_cost_micro "${usage.totalCostMicro}" ` +
    `last_updated "${timestamp}"`
  );
  exec(`redis-cli -h ${redisHost} -p ${redisPort} EXPIRE "cabinet:cost:advisor:${officer}" 86400`);

  // Daily accumulation (expire 48h). `<officer>_cost_micro` stays ADVISOR-only
  // for back-compat (cabinet/scripts/test-advisor-crew.sh reads that exact
  // field); the executor half lands in its own `_executor_cost_micro` field, so
  // a reader that sums `*_cost_micro` across the hash gets the TRUE total
  // rather than half of it. Deliberately no `_total_cost_micro` field here —
  // that would make the same sum count the spend twice.
  exec(`redis-cli -h ${redisHost} -p ${redisPort} HINCRBY "cabinet:cost:advisor:daily:${today}" "${officer}_input" "${usage.advisorInput}"`);
  exec(`redis-cli -h ${redisHost} -p ${redisPort} HINCRBY "cabinet:cost:advisor:daily:${today}" "${officer}_output" "${usage.advisorOutput}"`);
  exec(`redis-cli -h ${redisHost} -p ${redisPort} HINCRBY "cabinet:cost:advisor:daily:${today}" "${officer}_cache_write" "${usage.advisorCacheWrite}"`);
  exec(`redis-cli -h ${redisHost} -p ${redisPort} HINCRBY "cabinet:cost:advisor:daily:${today}" "${officer}_cache_read" "${usage.advisorCacheRead}"`);
  exec(`redis-cli -h ${redisHost} -p ${redisPort} HINCRBY "cabinet:cost:advisor:daily:${today}" "${officer}_cost_micro" "${usage.advisorCostMicro}"`);
  exec(`redis-cli -h ${redisHost} -p ${redisPort} HINCRBY "cabinet:cost:advisor:daily:${today}" "${officer}_executor_input" "${usage.executorInput}"`);
  exec(`redis-cli -h ${redisHost} -p ${redisPort} HINCRBY "cabinet:cost:advisor:daily:${today}" "${officer}_executor_output" "${usage.executorOutput}"`);
  exec(`redis-cli -h ${redisHost} -p ${redisPort} HINCRBY "cabinet:cost:advisor:daily:${today}" "${officer}_executor_cache_write" "${usage.executorCacheWrite}"`);
  exec(`redis-cli -h ${redisHost} -p ${redisPort} HINCRBY "cabinet:cost:advisor:daily:${today}" "${officer}_executor_cache_read" "${usage.executorCacheRead}"`);
  exec(`redis-cli -h ${redisHost} -p ${redisPort} HINCRBY "cabinet:cost:advisor:daily:${today}" "${officer}_executor_cost_micro" "${usage.executorCostMicro}"`);
  exec(`redis-cli -h ${redisHost} -p ${redisPort} EXPIRE "cabinet:cost:advisor:daily:${today}" 172800`);

  // LANE LEDGER (2026-07-26). The two hashes above are an advisor-only surface
  // nothing else reads; `cabinet:cost:lanes:daily:<date>` is the one place every
  // paid non-session call lands. Shelling out to framework.cost.record_lane
  // instead of writing the fields inline keeps the field shape defined ONCE —
  // duplicating a cost contract across files is the exact mistake this commit
  // is undoing. calls=1 because the advisor-tool beta is ONE billed HTTP
  // request whatever its internal iteration count; cost is executor+advisor,
  // the whole request.
  //
  // execFileSync, NOT execSync: this argv carries an interpreter name and a
  // path, both from the environment, and no shell means no metacharacter can
  // be interpreted. (The redis-cli calls above predate this and still build
  // shell strings — same reason `officer` is slug-validated before it is used
  // anywhere in this function.)
  const { fileURLToPath } = await import("node:url");
  const cabinetRoot = process.env.CABINET_ROOT
    || fileURLToPath(new URL("../../..", import.meta.url));
  const python = process.env.CABINET_PYTHON || "python3";
  try {
    execFileSync(
      python,
      ["-m", "framework.cost.record_lane",
       "--lane", "advisor",
       "--principal", officer,
       "--calls", "1",
       "--cost-micro", String(Math.round(usage.totalCostMicro))],
      {
        stdio: "ignore",
        env: Object.assign({}, process.env, {
          PYTHONPATH: process.env.PYTHONPATH
            ? cabinetRoot + ":" + process.env.PYTHONPATH
            : cabinetRoot,
        }),
      }
    );
  } catch {
    // Counting only — a missing python3 or a down Redis never fails the task.
  }
}

// ────────────────────────────────────────────────────────────
// HTTP call with retry on 429
// ────────────────────────────────────────────────────────────

const ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages";
const MAX_RETRIES = 3;
const INITIAL_BACKOFF_MS = 2000;

async function callAdvisorAPI(args: Args, requestBody: object): Promise<any> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    process.stderr.write("ERROR: ANTHROPIC_API_KEY environment variable is not set\n");
    process.exit(1);
  }

  const betaVersion = process.env.ADVISOR_BETA_VERSION || "advisor-tool-2026-03-01";

  const headers: Record<string, string> = {
    "x-api-key": apiKey,
    "anthropic-version": "2023-06-01",
    "anthropic-beta": betaVersion,
    "content-type": "application/json",
  };

  let lastError: string = "";
  let backoffMs = INITIAL_BACKOFF_MS;

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    let response: Response;
    try {
      response = await fetch(ANTHROPIC_API_URL, {
        method: "POST",
        headers,
        body: JSON.stringify(requestBody),
      });
    } catch (networkErr) {
      lastError = `Network error: ${networkErr}`;
      if (attempt === MAX_RETRIES) break;
      process.stderr.write(`WARNING: Network error on attempt ${attempt}/${MAX_RETRIES}: ${networkErr}. Retrying in ${backoffMs}ms...\n`);
      await new Promise(r => setTimeout(r, backoffMs));
      backoffMs *= 2;
      continue;
    }

    if (response.status === 429) {
      lastError = `Rate limited (429)`;
      if (attempt === MAX_RETRIES) break;
      const retryAfter = response.headers.get("retry-after");
      const waitMs = retryAfter ? parseInt(retryAfter, 10) * 1000 : backoffMs;
      process.stderr.write(`WARNING: Rate limited on attempt ${attempt}/${MAX_RETRIES}. Waiting ${waitMs}ms...\n`);
      await new Promise(r => setTimeout(r, waitMs));
      backoffMs *= 2;
      continue;
    }

    if (!response.ok) {
      let body = "";
      try { body = await response.text(); } catch {}
      process.stderr.write(`ERROR: API request failed with status ${response.status}: ${body}\n`);
      process.exit(1);
    }

    let data: any;
    try {
      data = await response.json();
    } catch (parseErr) {
      process.stderr.write(`ERROR: Failed to parse API response as JSON: ${parseErr}\n`);
      process.exit(1);
    }

    return data;
  }

  process.stderr.write(`ERROR: All ${MAX_RETRIES} attempts failed. Last error: ${lastError}\n`);
  process.exit(1);
}

// ────────────────────────────────────────────────────────────
// Response extraction
// ────────────────────────────────────────────────────────────

function extractResult(data: any): string {
  // Validate response shape
  if (!data || typeof data !== "object") {
    process.stderr.write("ERROR: Unexpected response shape — not an object\n");
    process.exit(1);
  }

  if (!Array.isArray(data.content)) {
    process.stderr.write(`ERROR: Unexpected response shape — missing content array. Got: ${JSON.stringify(data).slice(0, 200)}\n`);
    process.exit(1);
  }

  const textBlocks = data.content.filter((b: any) => b.type === "text");
  if (textBlocks.length === 0) {
    process.stderr.write(`ERROR: No text blocks in response. Stop reason: ${data.stop_reason}. Content types: ${data.content.map((b: any) => b.type).join(", ")}\n`);
    process.exit(1);
  }

  return textBlocks.map((b: any) => b.text).join("\n");
}

// ────────────────────────────────────────────────────────────
// Format microdollars for display
// ────────────────────────────────────────────────────────────

function formatMicro(micro: number): string {
  if (micro < 1000) return `${micro}µ$`;
  if (micro < 1_000_000) return `$${(micro / 1_000_000).toFixed(4)}`;
  return `$${(micro / 1_000_000).toFixed(2)}`;
}

// ────────────────────────────────────────────────────────────
// Main
// ────────────────────────────────────────────────────────────

async function main() {
  const args = parseArgs(process.argv.slice(2));

  // Load context file
  const context = await loadContext(args.contextFile);

  // Check context ceiling before making any HTTP call
  checkContextCeiling(args.task, context);

  // Build request body
  const requestBody = buildRequestBody(args, context);

  // Dry-run: dump request and exit
  if (args.dryRun) {
    process.stdout.write(JSON.stringify(requestBody, null, 2) + "\n");
    process.exit(0);
  }

  // Make the API call
  const data = await callAdvisorAPI(args, requestBody);

  // Extract text result
  const result = extractResult(data);

  // Parse usage (cost rates keyed off the actual advisor/executor models)
  const advisorModel = process.env.ADVISOR_MODEL || "claude-fable-5";
  const usage = parseUsage(data.usage, advisorModel, args.executor);

  // Write costs to Redis + the lane ledger (best-effort — never blocks result)
  await writeAdvisorCosts(args.officer, usage, advisorModel, args.executor);

  // Print result to stdout
  process.stdout.write(result + "\n");

  // Print usage summary to stderr
  process.stderr.write(
    `\n--- advisor-crew usage summary ---\n` +
    `executor (${args.executor}): ${usage.executorInput} in / ${usage.executorOutput} out → ${formatMicro(usage.executorCostMicro)}\n` +
    `advisor  (${advisorModel}): ${usage.advisorInput} in / ${usage.advisorOutput} out (${usage.advisorCallCount} calls) → ${formatMicro(usage.advisorCostMicro)}\n` +
    `total: ${usage.totalInput} in / ${usage.totalOutput} out → ${formatMicro(usage.totalCostMicro)}\n` +
    `officer: ${args.officer} | cache_control: ${args.expectedCalls >= 3 ? "on (5m)" : "off"}\n`
  );
}

main().catch((err) => {
  process.stderr.write(`ERROR: Unhandled exception: ${err}\n`);
  process.exit(1);
});
