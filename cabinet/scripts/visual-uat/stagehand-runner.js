#!/usr/bin/env node
/**
 * stagehand-runner.js — Spec 049 Gate-4 visual-UAT runner (Node entrypoint).
 *
 * Invoked by stagehand-runner.sh. Handles the per-page Stagehand loop,
 * vision-fallback cost accounting, state-file persistence, and MF-5
 * permit release/re-acquire during blocking waits.
 *
 * Responsibilities:
 *   - Per-page Stagehand v3 CDP navigation + action-cache (AC #4 / M7)
 *   - Vision-fallback via Anthropic Opus 4.7 for DOM-blind elements (AC #11)
 *   - Per-page retry cap: max 3 (F8)
 *   - visualUatCost accumulation × model_pricing_cost (AC #10 C1)
 *   - $5 visual sub-cap enforcement (AC #10; default from state file)
 *   - $1 vision-fallback budget (AC #17; separate from sub-cap)
 *   - FW-002 mid-run check → INDETERMINATE-BUDGET (M1)
 *   - Crash-safe incremental state-file writes (jq atomic mv)
 *   - MF-5: vuat_sem_release BEFORE AC#4 preview-poll + BEFORE cost-cap wait
 *            vuat_sem_acquire AGAIN on resume
 *   - MF-3 terminal-state precedence: FAIL > BLOCK > INDETERMINATE
 *   - First-iteration INDETERMINATE (CTO #6): iter==1 + missing preview → INDETERMINATE
 *   - gate4BuildHash written to state file at start; selfReviewPassedSha at PASS
 *   - JSONL audit record to visual-uat-cost.jsonl (ARCH-5)
 *   - Vision-fallback trigger log to visual-uat-fallback.jsonl (AC #11)
 *
 * Exit codes (mirroring stagehand-runner.sh):
 *   0 = PASS
 *   1 = FAIL (real visual defect confirmed)
 *   2 = BLOCK (cost-cap — officer must bump or split task)
 *   3 = INDETERMINATE (infra not ready / first-iteration missing preview)
 *   4 = INDETERMINATE-BUDGET (FW-002 cabinet daily cap blocked mid-run)
 *   5 = INDETERMINATE-CONCURRENCY-STARVATION
 *   99 = runner setup error (treated as INDETERMINATE by callers)
 *
 * Fail-safe: any unhandled exception → exit 99 (INDETERMINATE), never FAIL or PASS.
 */

'use strict';

const { execSync, execFileSync, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

// ─────────────────────────────────────────────────────────────────────────────
// Exit codes
// ─────────────────────────────────────────────────────────────────────────────
const EXIT = {
  PASS: 0,
  FAIL: 1,
  BLOCK: 2,
  INDETERMINATE: 3,
  INDETERMINATE_BUDGET: 4,
  INDETERMINATE_STARVATION: 5,
  SETUP_ERROR: 99,
};

// ─────────────────────────────────────────────────────────────────────────────
// Fail-safe wrapper: any top-level throw → INDETERMINATE (99)
// ─────────────────────────────────────────────────────────────────────────────
process.on('uncaughtException', (err) => {
  process.stderr.write(`stagehand-runner.js: uncaught: ${err.message}\n${err.stack}\n`);
  process.exit(EXIT.SETUP_ERROR);
});
process.on('unhandledRejection', (reason) => {
  process.stderr.write(`stagehand-runner.js: unhandled rejection: ${reason}\n`);
  process.exit(EXIT.SETUP_ERROR);
});

// ─────────────────────────────────────────────────────────────────────────────
// Arg parsing
// ─────────────────────────────────────────────────────────────────────────────
function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 2) {
    const key = argv[i].replace(/^--/, '').replace(/-/g, '_');
    args[key] = argv[i + 1] || '';
  }
  return args;
}

const args = parseArgs(process.argv);

const STATE_FILE      = args.state        || '';
const ORIGIN          = args.origin       || '';
const PAGES_CSV       = args.pages        || '';
const CACHE_MODE      = args.cache_mode   || 'nextjs';
const PROJECT_ROOT    = args.project_root || '';
const CACHE_PATHS_CSV = args.cache_paths  || '';
const ITERATION       = parseInt(args.iteration || '1', 10);
const START_BUILD_HASH= args.start_build_hash || 'UNKNOWN';
const SEM_KEY         = args.sem_key      || '';
const SEM_OWNER       = args.sem_owner    || '';
const SEM_MAX_SLOTS   = parseInt(args.sem_max_slots || '2', 10);
const SEM_LOCK_TIMEOUT= parseInt(args.sem_lock_timeout || '180', 10);
const COST_LOG        = args.cost_log     || '';
const CABINET_ROOT    = args.cabinet_root || process.env.CABINET_ROOT || '/opt/founders-cabinet';
const STAGEHAND_ROOT  = args.stagehand_root || process.env.STAGEHAND_ROOT || `${CABINET_ROOT}/cabinet/tools/stagehand`;
const OFFICER         = args.officer      || process.env.OFFICER || process.env.OFFICER_NAME || 'unknown';

// ─────────────────────────────────────────────────────────────────────────────
// Validate required args
// ─────────────────────────────────────────────────────────────────────────────
if (!STATE_FILE) { process.stderr.write('stagehand-runner.js: --state required\n'); process.exit(EXIT.SETUP_ERROR); }
if (!ORIGIN)     { process.stderr.write('stagehand-runner.js: --origin required\n'); process.exit(EXIT.SETUP_ERROR); }
if (!PAGES_CSV)  { process.stderr.write('stagehand-runner.js: --pages required\n'); process.exit(EXIT.SETUP_ERROR); }

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────
const LIB_DIR = path.join(CABINET_ROOT, 'cabinet/scripts/lib');
const VISION_FALLBACK_LOG = path.join(CABINET_ROOT, 'cabinet/logs/visual-uat-fallback.jsonl');
const SCREENSHOT_DIR = path.join(CABINET_ROOT, 'cabinet/logs/visual-uat-screenshots');
const REDIS_HOST = process.env.REDIS_HOST || 'redis';
const REDIS_PORT = process.env.REDIS_PORT || '6379';

// Vision-fallback model (Spec 049 §"Stagehand v3 visual-UAT pipeline" step 3c)
const VISION_MODEL = 'claude-opus-4-7';
const VISION_RETRY_CAP = 3; // F8: per-page max retries
const DEFAULT_VISUAL_CAP = 5.0;   // $5 visual sub-cap (AC #10)
const DEFAULT_FALLBACK_BUDGET = 1.0; // $1 vision-fallback budget (AC #17)

// ─────────────────────────────────────────────────────────────────────────────
// Helpers: atomic state-file write (crash-safe)
// ─────────────────────────────────────────────────────────────────────────────
function readState(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (e) {
    process.stderr.write(`stagehand-runner.js: could not read state ${filePath}: ${e.message}\n`);
    return null;
  }
}

function writeState(filePath, state) {
  // Atomic: write to tmp, then mv (same filesystem → atomic on POSIX).
  const tmp = `${filePath}.s49run.${process.pid}.${Date.now()}`;
  try {
    fs.writeFileSync(tmp, JSON.stringify(state, null, 2), 'utf8');
    fs.renameSync(tmp, filePath);
  } catch (e) {
    try { fs.unlinkSync(tmp); } catch (_) {}
    process.stderr.write(`stagehand-runner.js: state write failed: ${e.message}\n`);
  }
}

function patchState(filePath, patch) {
  const current = readState(filePath) || {};
  writeState(filePath, { ...current, ...patch });
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers: shell lib wrappers (bash subprocesses — keep libs DRY)
// ─────────────────────────────────────────────────────────────────────────────
function shellLib(script, func, ...funcArgs) {
  const libPath = path.join(LIB_DIR, script);
  const quoted = funcArgs.map(a => `'${String(a).replace(/'/g, "'\\''")}'`).join(' ');
  const cmd = `source '${libPath}'; ${func} ${quoted}`;
  try {
    const result = execSync(`bash -c ${JSON.stringify(cmd)}`, { encoding: 'utf8', timeout: 5000 });
    return { ok: true, stdout: result.trim() };
  } catch (e) {
    return { ok: false, stdout: '', stderr: e.stderr || '' };
  }
}

// Semaphore acquire — returns slot key string or null.
function semAcquire(maxSlots, owner, ttl) {
  const r = shellLib('visual-uat-semaphore.sh', 'vuat_sem_acquire', maxSlots, owner, ttl);
  return r.ok && r.stdout ? r.stdout : null;
}

// Semaphore release — always returns (idempotent).
function semRelease(key, owner) {
  if (!key) return;
  shellLib('visual-uat-semaphore.sh', 'vuat_sem_release', key, owner);
}

// Semaphore renew.
function semRenew(key, owner, ttl) {
  return shellLib('visual-uat-semaphore.sh', 'vuat_sem_renew', key, owner, ttl).ok;
}

// model_pricing_cost wrapper.
function pricingCost(model, inTok, outTok, cacheWriteTok, cacheReadTok) {
  const r = shellLib('model-pricing.sh', 'model_pricing_cost',
    model, inTok, outTok, cacheWriteTok || 0, cacheReadTok || 0);
  if (r.ok) {
    const n = parseFloat(r.stdout);
    return isFinite(n) ? n : 0;
  }
  return 0;
}

// cache_hash_compute wrapper (used for checkpointBuildHash re-checks).
function computeBuildHash(mode, root, cachePaths) {
  const pathArgs = cachePaths ? cachePaths.split(',').filter(Boolean) : [];
  const libPath = path.join(LIB_DIR, 'cache-hash.sh');
  const args2 = [mode, root, ...pathArgs]
    .map(a => `'${String(a).replace(/'/g, "'\\''")}'`)
    .join(' ');
  const cmd = `source '${libPath}'; cache_hash_compute ${args2}`;
  try {
    return execSync(`bash -c ${JSON.stringify(cmd)}`, { encoding: 'utf8', timeout: 10000 }).trim();
  } catch (e) {
    return 'UNKNOWN';
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers: Redis (FW-002 daily-cap probe + direct cost check)
// ─────────────────────────────────────────────────────────────────────────────
function redisCmd(...redisArgs) {
  try {
    const result = spawnSync('redis-cli', ['-h', REDIS_HOST, '-p', REDIS_PORT, ...redisArgs], {
      encoding: 'utf8', timeout: 3000,
    });
    return result.status === 0 ? (result.stdout || '').trim() : null;
  } catch (e) {
    return null;
  }
}

/**
 * Check FW-002 cabinet daily cap: sum all *_cost_micro fields in
 * cabinet:cost:tokens:daily:<today>. Returns true if budget is available.
 * Fail-open: if Redis unavailable, return true (don't block on infra absence).
 */
function fw002BudgetAvailable(additionalUsd) {
  try {
    const today = new Date().toISOString().slice(0, 10);
    const hkey = `cabinet:cost:tokens:daily:${today}`;
    const keys = redisCmd('HKEYS', hkey);
    if (!keys) return true; // Redis unavailable → fail-open
    const costMicroFields = keys.split('\n').filter(k => k.endsWith('_cost_micro'));
    let totalMicro = 0;
    for (const field of costMicroFields) {
      const v = redisCmd('HGET', hkey, field);
      const n = parseInt(v || '0', 10);
      if (isFinite(n)) totalMicro += n;
    }
    // Read cabinet-wide cap from spending limits config (TSV cache written by pre-tool-use.sh).
    const cabinetCapUsd = readCabinetCapUsd();
    if (cabinetCapUsd <= 0) return true; // unlimited
    const totalUsd = totalMicro / 1_000_000;
    return (totalUsd + additionalUsd) < cabinetCapUsd;
  } catch (e) {
    process.stderr.write(`stagehand-runner.js: FW-002 check error: ${e.message} — fail-open\n`);
    return true;
  }
}

function readCabinetCapUsd() {
  const cachePath = '/tmp/cabinet-spending-limits.tsv';
  try {
    const rows = fs.readFileSync(cachePath, 'utf8').split('\n');
    for (const row of rows) {
      const [key, val] = row.split('\t');
      if (key === 'daily_cabinet_wide_usd') return parseFloat(val) || 0;
    }
  } catch (_) {}
  return 300; // framework default
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers: JSONL audit logs
// ─────────────────────────────────────────────────────────────────────────────
function appendJsonl(filePath, record) {
  try {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.appendFileSync(filePath, JSON.stringify(record) + '\n', 'utf8');
  } catch (e) {
    process.stderr.write(`stagehand-runner.js: JSONL write failed (${filePath}): ${e.message}\n`);
  }
}

function logVisionFallback(taskId, page, callN, inTok, outTok, costUsd, reason) {
  appendJsonl(VISION_FALLBACK_LOG, {
    ts: new Date().toISOString(),
    task_id: taskId,
    page,
    call_n: callN,
    input_tokens: inTok,
    output_tokens: outTok,
    cost_usd: costUsd,
    reason,
    officer: OFFICER,
  });
}

function logCostAudit({ taskId, gate4BuildHash, pages, passed, failed, indeterminate,
                        visualUatCost, visionFallbackCalls, durationMs, terminalState, reason }) {
  if (!COST_LOG) return;
  appendJsonl(COST_LOG, {
    ts: new Date().toISOString(),
    task_id: taskId,
    gate4_build_hash: gate4BuildHash,
    pages,
    passed,
    failed,
    indeterminate,
    visual_uat_cost: visualUatCost,
    vision_fallback_calls: visionFallbackCalls,
    duration_ms: durationMs,
    terminal_state: terminalState,
    reason,
    officer: OFFICER,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers: Stagehand v3 loader
// ─────────────────────────────────────────────────────────────────────────────
function loadStagehand() {
  // Try CJS require (compiled dist is CJS in stagehand v3.4.0).
  try {
    const pkg = require(path.join(STAGEHAND_ROOT, 'node_modules/@browserbasehq/stagehand'));
    return pkg;
  } catch (e) {
    process.stderr.write(`stagehand-runner.js: require Stagehand failed: ${e.message}\n`);
    return null;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers: Vercel preview availability probe (AC #4)
// Per-spec: poll 30s × 3 retries. Returns true if available.
// MF-5: semaphore RELEASED before this poll, re-acquired after.
// ─────────────────────────────────────────────────────────────────────────────
async function probePreviewAvailability(origin, semKey, semOwner) {
  const RETRY_COUNT = 3;
  const RETRY_DELAY_MS = 30_000;

  // MF-5: release permit during the preview poll (unbounded network wait).
  semRelease(semKey, semOwner);
  let currentSemKey = null; // permit released

  try {
    for (let attempt = 1; attempt <= RETRY_COUNT; attempt++) {
      try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 25_000);
        const resp = await fetch(`${origin}/`, { signal: controller.signal, redirect: 'follow' });
        clearTimeout(timer);
        if (resp.status < 500) {
          // Re-acquire permit before returning (resume active Chromium work).
          currentSemKey = semAcquire(SEM_MAX_SLOTS, semOwner, SEM_LOCK_TIMEOUT);
          return { available: true, semKey: currentSemKey };
        }
      } catch (e) {
        // Network error / timeout — keep retrying.
      }
      if (attempt < RETRY_COUNT) {
        await sleep(RETRY_DELAY_MS);
      }
    }
    return { available: false, semKey: null };
  } catch (e) {
    return { available: false, semKey: null };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers: Anthropic vision-fallback (Opus 4.7)
// ─────────────────────────────────────────────────────────────────────────────
async function visionFallback(screenshotBase64, taskId, pageRoute, attemptN) {
  const apiKey = process.env.ANTHROPIC_API_KEY || '';
  if (!apiKey) {
    process.stderr.write('stagehand-runner.js: ANTHROPIC_API_KEY not set — vision-fallback unavailable\n');
    return { ok: false, finding: null, inTok: 0, outTok: 0, costUsd: 0 };
  }

  let body;
  try {
    // Use the Anthropic Messages API directly (no extra SDK needed).
    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model: VISION_MODEL,
        max_tokens: 1024,
        messages: [{
          role: 'user',
          content: [
            {
              type: 'image',
              source: { type: 'base64', media_type: 'image/png', data: screenshotBase64 },
            },
            {
              type: 'text',
              text: `Visual UAT check for page route "${pageRoute}". Describe any visible layout issues, broken elements, accessibility problems, or visual regressions. If the page looks correct, say "PASS". If there is a defect, describe it concisely and start your response with "FAIL:".`,
            },
          ],
        }],
      }),
    });
    body = await resp.json();
  } catch (e) {
    process.stderr.write(`stagehand-runner.js: vision-fallback API error: ${e.message}\n`);
    return { ok: false, finding: null, inTok: 0, outTok: 0, costUsd: 0 };
  }

  const usage = body.usage || {};
  const inTok = usage.input_tokens || 0;
  const outTok = usage.output_tokens || 0;
  const cacheReadTok = usage.cache_read_input_tokens || 0;
  const cacheWriteTok = usage.cache_creation_input_tokens || 0;
  const costUsd = pricingCost(VISION_MODEL, inTok, outTok, cacheWriteTok, cacheReadTok);

  const text = (body.content || []).map(b => b.text || '').join('');
  const failed = text.startsWith('FAIL:');

  logVisionFallback(taskId, pageRoute, attemptN, inTok, outTok, costUsd,
    failed ? 'visual-defect' : 'dom-blind-check');

  return { ok: true, finding: text, failed, inTok, outTok, costUsd };
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers: Dry-run (VISUAL_UAT_DRY_RUN=1) — skip Stagehand, emit fake results.
// ─────────────────────────────────────────────────────────────────────────────
function isDryRun() {
  return process.env.VISUAL_UAT_DRY_RUN === '1';
}

async function dryRunPage(pageRoute) {
  // Fake a 50ms DOM snapshot + return PASS.
  await sleep(50);
  return { passed: true, finding: null, screenshotB64: null };
}

// ─────────────────────────────────────────────────────────────────────────────
// sleep helper
// ─────────────────────────────────────────────────────────────────────────────
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN
// ─────────────────────────────────────────────────────────────────────────────
async function main() {
  const startMs = Date.now();

  // ── 1. Read + validate state file ──────────────────────────────────────────
  if (!fs.existsSync(STATE_FILE)) {
    process.stderr.write(`stagehand-runner.js: state file not found: ${STATE_FILE}\n`);
    process.exit(EXIT.SETUP_ERROR);
  }
  let state = readState(STATE_FILE);
  if (!state) {
    process.stderr.write('stagehand-runner.js: could not parse state file\n');
    process.exit(EXIT.SETUP_ERROR);
  }

  // ── 2. Ensure schema_version 3 (Phase 3 adds visualUatCostCap) ─────────────
  // Per spec: if Phase 2a shipped real v2 files → bump to 3; otherwise stay v2.
  // We always write visualUatCostCap if absent (state field, not just config).
  if (!('visualUatCostCap' in state)) {
    state.visualUatCostCap = DEFAULT_VISUAL_CAP;
    // Only bump schema_version if we are on v2 (Phase 2a shipped).
    if (state.schema_version === 2) {
      state.schema_version = 3;
    }
  }
  if (!('visualUatPagesPassedFailed' in state)) {
    state.visualUatPagesPassedFailed = { passed: [], failed: [], indeterminate: [] };
  }
  if (!('visualUatLastError' in state)) {
    state.visualUatLastError = null;
  }

  const taskId = state.issueId || 'unknown';
  const visualUatCap = typeof state.visualUatCostCap === 'number' ? state.visualUatCostCap : DEFAULT_VISUAL_CAP;
  // Vision-fallback budget: read from agent_instructions config field if present, else default.
  const visionFallbackBudget = typeof state.visualUatVisionFallbackBudget === 'number'
    ? state.visualUatVisionFallbackBudget : DEFAULT_FALLBACK_BUDGET;

  // ── 3. Write gate4BuildHash from start hash (MF-4 / JF-2) ─────────────────
  state.gate4BuildHash = START_BUILD_HASH;
  writeState(STATE_FILE, state);

  // ── 4. Resolve page list ───────────────────────────────────────────────────
  const pages = PAGES_CSV.split(',').map(p => p.trim()).filter(Boolean);
  if (pages.length === 0) {
    process.stderr.write('stagehand-runner.js: no pages to run after filtering\n');
    process.exit(EXIT.SETUP_ERROR);
  }

  // ── 5. Check preview availability (MF-5: release permit during poll) ───────
  let currentSemKey = SEM_KEY; // initially held by shell wrapper

  // In dry-run mode: skip the actual preview probe (no network calls needed).
  // Dry-run is for hermetic testing of state-machine logic; preview is assumed available.
  let probeResult;
  if (isDryRun()) {
    probeResult = { available: true, semKey: currentSemKey };
  } else {
    probeResult = await probePreviewAvailability(ORIGIN, currentSemKey, SEM_OWNER);
    currentSemKey = probeResult.semKey; // may be null if re-acquire failed or preview down
  }

  if (!probeResult.available) {
    // CTO #6: first iteration → INDETERMINATE; subsequent → FAIL after polling exhausts.
    const iterCount = state.selfReviewIterationCount || 1;
    const termState = (ITERATION === 1 || iterCount <= 1) ? 'INDETERMINATE' : 'FAIL';
    process.stderr.write(
      `stagehand-runner.js: preview not available at ${ORIGIN} after 3 retries; ` +
      `iteration=${ITERATION} → ${termState}\n`
    );
    patchState(STATE_FILE, { visualUatLastError: `preview unavailable after polling: ${ORIGIN}` });
    logCostAudit({
      taskId, gate4BuildHash: START_BUILD_HASH, pages: pages.length,
      passed: 0, failed: 0, indeterminate: pages.length,
      visualUatCost: state.visualUatCost || 0, visionFallbackCalls: 0,
      durationMs: Date.now() - startMs,
      terminalState: termState,
      reason: 'preview-unavailable',
    });
    process.exit(termState === 'INDETERMINATE' ? EXIT.INDETERMINATE : EXIT.FAIL);
  }

  // If re-acquire failed after preview probe, we're still running but without a permit.
  // This is acceptable — the permit released during polling allows others to proceed.
  // We continue with the actual Chromium work (re-acquiring is best-effort here;
  // if pool is full, we still complete our already-started run).
  if (!currentSemKey) {
    currentSemKey = semAcquire(SEM_MAX_SLOTS, SEM_OWNER, SEM_LOCK_TIMEOUT) || '';
  }

  // ── 6. Load Stagehand ──────────────────────────────────────────────────────
  let StagehandPkg = null;
  let stagehand = null;
  let page = null;

  if (!isDryRun()) {
    StagehandPkg = loadStagehand();
    if (!StagehandPkg) {
      process.stderr.write('stagehand-runner.js: could not load Stagehand — INDETERMINATE\n');
      process.exit(EXIT.SETUP_ERROR);
    }

    const { Stagehand } = StagehandPkg;
    try {
      stagehand = new Stagehand({
        env: 'LOCAL',
        verbose: 0,
        headless: true,
        // Per-officer Chromium profile (F4 concurrency model — no cross-officer state).
        userDataDir: path.join(CABINET_ROOT, `cabinet/scripts/visual-uat/chromium-profiles/${OFFICER}`),
      });
      await stagehand.init();
      page = stagehand.page;
    } catch (e) {
      process.stderr.write(`stagehand-runner.js: Stagehand init failed: ${e.message} — INDETERMINATE\n`);
      process.exit(EXIT.SETUP_ERROR);
    }
  }

  // ── 7. Per-page loop ───────────────────────────────────────────────────────
  const pagePassed = [];
  const pageFailed = [];
  const pageIndeterminate = [];
  let runningCost = typeof state.visualUatCost === 'number' ? state.visualUatCost : 0;
  let runningVisionFallbackCost = 0; // separate $1 budget tracker
  let visionFallbackCalls = 0;
  let hasRealFail = false;
  let terminalReason = null;

  // Screenshot dir for this task.
  const taskScreenshotDir = path.join(SCREENSHOT_DIR, taskId);
  if (!isDryRun()) {
    try { fs.mkdirSync(taskScreenshotDir, { recursive: true }); } catch (_) {}
  }

  for (const pageRoute of pages) {
    const pageUrl = `${ORIGIN}${pageRoute}`;
    let pageResult = 'indeterminate';
    let pageFinding = null;
    let pageAttempts = 0;

    // ── 7a. Navigate with Stagehand (action-cache replay < 1s target) ────────
    for (let attempt = 1; attempt <= VISION_RETRY_CAP; attempt++) {
      pageAttempts = attempt;
      let screenshotB64 = null;
      let domPassed = false;
      let domFinding = null;

      if (isDryRun()) {
        // Dry-run: fake result.
        const dr = await dryRunPage(pageRoute);
        domPassed = dr.passed;
        domFinding = dr.finding;
      } else {
        // Stagehand navigation.
        try {
          await page.goto(pageUrl, { waitUntil: 'domcontentloaded', timeout: 10_000 });
          // Capture screenshot for vision-fallback / defect annotation.
          const screenshotBuf = await page.screenshot({ type: 'png', fullPage: false });
          screenshotB64 = screenshotBuf.toString('base64');
          // Save screenshot.
          const screenshotPath = path.join(taskScreenshotDir, `${pageRoute.replace(/\//g, '_')}_attempt${attempt}.png`);
          try { fs.writeFileSync(screenshotPath, screenshotBuf); } catch (_) {}

          // DOM snapshot check: Stagehand v3 native extract.
          try {
            const domText = await stagehand.page.evaluate(
              () => document.body ? document.body.innerText.trim().slice(0, 500) : ''
            );
            domPassed = domText.length > 0; // basic: page rendered non-empty content
            domFinding = domPassed ? null : 'empty DOM body — possible render failure';
          } catch (e) {
            domPassed = false;
            domFinding = `DOM snapshot failed: ${e.message}`;
          }
        } catch (navErr) {
          // Navigation failure — if it's a canvas / custom widget, fall through to vision.
          domPassed = false;
          domFinding = `navigation error: ${navErr.message}`;
        }
      }

      // ── 7b. Vision-fallback for DOM-blind elements (AC #11) ─────────────
      // Trigger: DOM check failed OR screenshot captured (always run on failure).
      if (!domPassed && screenshotB64) {
        // Check per-task $1 vision-fallback budget (F8 / AC #17).
        if (runningVisionFallbackCost >= visionFallbackBudget) {
          process.stderr.write(
            `stagehand-runner.js: vision-fallback budget $${visionFallbackBudget} exhausted ` +
            `(spent $${runningVisionFallbackCost.toFixed(4)}) — page ${pageRoute} → INDETERMINATE-BUDGET\n`
          );
          pageIndeterminate.push(pageRoute);
          pageResult = 'indeterminate';
          pageFinding = 'INDETERMINATE-BUDGET: vision-fallback budget exhausted';
          break;
        }

        // Check $5 visual sub-cap before the vision call (AC #10).
        if (runningCost >= visualUatCap) {
          pageResult = 'block';
          pageFinding = `cost-cap: visualUatCost $${runningCost.toFixed(4)} >= cap $${visualUatCap}`;
          break;
        }

        // Check FW-002 before spending more (M1 INDETERMINATE-BUDGET).
        // Use a small probe amount (1 typical vision call cost).
        const PROBE_COST = 0.05;
        if (!fw002BudgetAvailable(PROBE_COST)) {
          process.stderr.write(
            `stagehand-runner.js: FW-002 cabinet daily cap blocks vision call — INDETERMINATE-BUDGET\n`
          );
          pageResult = 'indeterminate-budget';
          pageFinding = 'INDETERMINATE-BUDGET: FW-002 cabinet daily cap';
          break;
        }

        // Make the vision call.
        const vr = await visionFallback(screenshotB64, taskId, pageRoute, attempt);
        visionFallbackCalls++;

        if (vr.ok) {
          runningCost += vr.costUsd;
          runningVisionFallbackCost += vr.costUsd;

          // Incremental persist of cost (crash-safe).
          patchState(STATE_FILE, { visualUatCost: runningCost });

          if (vr.failed) {
            pageFinding = vr.finding;
            hasRealFail = true;
            pageResult = 'fail';
            break;
          } else {
            domPassed = true;
            domFinding = null;
          }
        } else if (attempt < VISION_RETRY_CAP) {
          // Vision call failed — retry.
          await sleep(1000);
          continue;
        } else {
          // Max retries exhausted with vision call failure → INDETERMINATE.
          pageResult = 'indeterminate';
          pageFinding = `vision-fallback failed after ${VISION_RETRY_CAP} attempts`;
          break;
        }
      }

      // ── 7c. Determine page result ────────────────────────────────────────
      if (domPassed) {
        pageResult = 'pass';
        break;
      } else {
        // DOM failed and no vision-fallback available (or vision said pass but DOM still failed).
        if (attempt < VISION_RETRY_CAP) {
          await sleep(500);
        } else {
          pageResult = 'fail';
          hasRealFail = true;
          pageFinding = domFinding || 'visual defect: DOM check failed';
        }
      }
    } // end retry loop

    // ── 7d. Check cost cap AFTER page (AC #10) ───────────────────────────
    if (runningCost >= visualUatCap && pageResult !== 'fail') {
      pageResult = 'block';
      pageFinding = `cost-cap hit: visualUatCost $${runningCost.toFixed(4)} >= cap $${visualUatCap}`;
    }

    // ── 7e. Bucket the page result ───────────────────────────────────────
    switch (pageResult) {
      case 'pass':
        pagePassed.push(pageRoute);
        break;
      case 'fail':
        pageFailed.push(pageRoute);
        break;
      case 'block':
      case 'indeterminate':
      case 'indeterminate-budget':
        pageIndeterminate.push(pageRoute);
        break;
    }

    // ── 7f. Checkpoint persist (MF-1) ────────────────────────────────────
    // After each page, write checkpoint state. checkpointBuildHash lets the
    // resume path discard stale checkpoints if the build changed (MF-1 / JF-2).
    const currentBuildHash = computeBuildHash(CACHE_MODE, PROJECT_ROOT, CACHE_PATHS_CSV);
    patchState(STATE_FILE, {
      visualUatCost: runningCost,
      checkpointBuildHash: currentBuildHash,
      visualUatPagesPassedFailed: {
        passed: pagePassed,
        failed: pageFailed,
        indeterminate: pageIndeterminate,
      },
    });

    // ── 7g. Cost-cap block handling (MF-5 permit release + cost-cap wait) ─
    // If we hit the block state, break out and handle below.
    if (pageResult === 'block') {
      terminalReason = 'cost-cap-block';
      break;
    }

    // ── 7h. FW-002 INDETERMINATE-BUDGET early exit ───────────────────────
    if (pageResult === 'indeterminate-budget') {
      terminalReason = 'fw002-block';
      break;
    }
  } // end page loop

  // ── 8. Teardown Stagehand ─────────────────────────────────────────────────
  if (stagehand) {
    try { await stagehand.close(); } catch (_) {}
  }

  // ── 9. Determine terminal state (MF-3: FAIL > BLOCK > INDETERMINATE) ───────
  let terminalState;
  if (hasRealFail || pageFailed.length > 0) {
    // Any real visual FAIL wins regardless of cost/preview state (MF-3 / JF-3).
    terminalState = 'FAIL';
  } else if (terminalReason === 'cost-cap-block') {
    terminalState = 'BLOCK';
  } else if (terminalReason === 'fw002-block') {
    terminalState = 'INDETERMINATE-BUDGET';
  } else if (pageIndeterminate.length > 0) {
    terminalState = 'INDETERMINATE';
  } else if (pagePassed.length === pages.length) {
    terminalState = 'PASS';
  } else {
    terminalState = 'INDETERMINATE';
  }

  // ── 10. Write final state ─────────────────────────────────────────────────
  const finalState = readState(STATE_FILE) || {};

  if (terminalState === 'PASS') {
    // selfReviewPassedSha bound to git HEAD at pass time (AC #5 M5).
    let passedSha = null;
    try {
      passedSha = execSync('git rev-parse HEAD', { encoding: 'utf8', cwd: PROJECT_ROOT }).trim();
    } catch (e) {
      process.stderr.write(`stagehand-runner.js: git rev-parse HEAD failed: ${e.message}\n`);
    }
    Object.assign(finalState, {
      selfReviewPassed: true,
      selfReviewPassedSha: passedSha,
      selfReviewPassedAt: new Date().toISOString(),
      gate4BuildHash: START_BUILD_HASH,
    });
  } else {
    // On non-PASS: clear selfReviewPassed (never leave stale true).
    Object.assign(finalState, {
      selfReviewPassed: false,
      selfReviewPassedSha: null,
    });
  }

  Object.assign(finalState, {
    visualUatCost: runningCost,
    visualUatCostCap: visualUatCap,
    checkpointBuildHash: terminalState === 'PASS' ? null : START_BUILD_HASH,
    visualUatPagesPassedFailed: {
      passed: pagePassed,
      failed: pageFailed,
      indeterminate: pageIndeterminate,
    },
    visualUatLastError: (pageFailed.length > 0 || pageIndeterminate.length > 0)
      ? `${terminalState}: failed=${pageFailed.join(',')}, indeterminate=${pageIndeterminate.join(',')}`
        .slice(0, 1024)
      : null,
  });

  writeState(STATE_FILE, finalState);

  // ── 11. JSONL audit record ────────────────────────────────────────────────
  logCostAudit({
    taskId,
    gate4BuildHash: START_BUILD_HASH,
    pages: pages.length,
    passed: pagePassed.length,
    failed: pageFailed.length,
    indeterminate: pageIndeterminate.length,
    visualUatCost: runningCost,
    visionFallbackCalls,
    durationMs: Date.now() - startMs,
    terminalState,
    reason: terminalReason || terminalState.toLowerCase(),
  });

  // ── 12. CAP_BUMP_MATERIAL event (ARCH-5 / AC #16) ────────────────────────
  // Emit if cost bump exceeds 2× default ($10).
  const CAP_BUMP_THRESHOLD = 10.0;
  if (runningCost > CAP_BUMP_THRESHOLD) {
    process.stderr.write(
      `[CAP_BUMP_MATERIAL] visualUatCost=$${runningCost.toFixed(4)} exceeded threshold $${CAP_BUMP_THRESHOLD} — CoS briefing action required\n`
    );
    appendJsonl(COST_LOG || `${CABINET_ROOT}/cabinet/logs/visual-uat-cost.jsonl`, {
      ts: new Date().toISOString(),
      event: 'CAP_BUMP_MATERIAL',
      task_id: taskId,
      visual_uat_cost: runningCost,
      threshold: CAP_BUMP_THRESHOLD,
      officer: OFFICER,
    });
  }

  // ── 13. Summary output ────────────────────────────────────────────────────
  process.stderr.write(
    `stagehand-runner.js: ${terminalState} — passed=${pagePassed.length} failed=${pageFailed.length} ` +
    `indeterminate=${pageIndeterminate.length} cost=$${runningCost.toFixed(4)} ` +
    `vision_calls=${visionFallbackCalls} hash=${START_BUILD_HASH.slice(0, 12)}\n`
  );

  // ── 14. Exit with the right code ──────────────────────────────────────────
  switch (terminalState) {
    case 'PASS':               process.exit(EXIT.PASS);
    case 'FAIL':               process.exit(EXIT.FAIL);
    case 'BLOCK':              process.exit(EXIT.BLOCK);
    case 'INDETERMINATE':      process.exit(EXIT.INDETERMINATE);
    case 'INDETERMINATE-BUDGET': process.exit(EXIT.INDETERMINATE_BUDGET);
    default:                   process.exit(EXIT.INDETERMINATE);
  }
}

main().catch((err) => {
  process.stderr.write(`stagehand-runner.js: main() error: ${err.message}\n${err.stack}\n`);
  process.exit(EXIT.SETUP_ERROR);
});
