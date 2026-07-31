import { readFile, writeFile, rename, stat, chmod, unlink } from 'node:fs/promises'
import path from 'node:path'
import { randomBytes } from 'node:crypto'
import yaml from 'js-yaml'

/**
 * EDITING A CONFIG FILE IN THIS PROCESS, BECAUSE `sed -i` NEVER RAN HERE.
 *
 * THE DEFECT THIS REPLACES. Fifteen call sites across `actions/config.ts`,
 * `actions/env.ts`, `actions/project-config.ts` and `actions/officers.ts` edited
 * the cabinet's YAML and `.env` by shelling out to `sed -i '<script>' <file>`.
 * BSD `sed` — the only `sed` on the only machine this system is deployed to —
 * takes the in-place suffix as a MANDATORY argument, so it read the script as
 * the suffix and the filename as the script. Measured on the Captain's Mac
 * (Darwin 25.6.0, arm64), all four shapes the app used:
 *
 *     sed -i 's|^FOO=.*|FOO=new|' env1
 *       exit 1 · sed: 1: "env1\n": invalid command code e · file unchanged
 *     sed -i '/^FOO=/d' env2
 *       exit 1 · sed: 1: "env2\n": invalid command code e · file unchanged
 *     sed -i '/^product:/,/^[a-z]/{s/^  name: .*​/  name: NEW/}' cfg1
 *       exit 1 · sed: 1: "cfg1\n": command c expects \ followed by text · unchanged
 *     sed -i '/^voice:/,/^[a-z]/{/^  officers:/,/^  [a-z]/{/^    cos: /d}}' cfg2
 *       exit 1 · same · file unchanged
 *
 * So settings, config, secrets and officer deletion have never edited anything
 * on this deployment. It stayed invisible because the shell transport used to
 * return `{ stdout: 'mock: command executed' }` for commands it declined to run,
 * so the failure had no way to reach a screen. That sentinel died first
 * (`lib/docker.ts`), which is what exposed this.
 *
 * WHY THE FIX IS NOT `sed -i ''`. Adding the suffix argument would make the
 * command run here and break on GNU, and it would leave the WORSE half of the
 * defect in place: `sed` cannot distinguish "changed the line" from "matched
 * nothing". On GNU it exits 0 for a pattern that matched no line, so
 * `updateProductConfig('mount_path', …)` against a `product.yml` with no
 * `mount_path` key reports success and changes nothing — a write-lie with no
 * shell dialect involved. A config editor has to be able to say "there is no
 * such field", and `sed` structurally cannot.
 *
 * THE SHAPE, following `actions/crons.ts`: read the whole document, transform it
 * in TypeScript, write it back atomically, read it back and compare, restore the
 * pre-image on mismatch. Editing in-process also deletes the entire
 * shell-interpolation surface — every one of those call sites built a shell
 * script out of a value typed into a browser form, and `value.replace(/'/g, …)`
 * was the whole defence.
 *
 * FAILURE IS A THROW, never a returned flag, for the reason `lib/docker.ts`
 * gives: every one of these actions already has
 * `catch (err) { return { success: false, error: err.message } }`, so throwing
 * lands the honest sentence in a branch that already exists and cannot be
 * mistaken for success by a caller that forgets to check. The messages are
 * written to be READ BY THE CAPTAIN — they are rendered verbatim.
 */

/** A refusal or a failed write. Carries the path so the message can name it. */
export class ConfigWriteError extends Error {
  readonly path: string
  constructor(filePath: string, message: string) {
    super(message)
    this.name = 'ConfigWriteError'
    this.path = filePath
  }
}

/**
 * What a write did. `changed: false` is a SUCCESS — the field was found and
 * already held that value — and is deliberately distinct from "found nothing",
 * which throws. Those two being the same outcome is the half of the `sed`
 * defect that has nothing to do with BSD.
 */
export interface WriteResult {
  path: string
  changed: boolean
}

/** A document transform. `matched` is how many target lines it found. */
export interface Transform {
  text: string
  matched: number
}

// ---------------------------------------------------------------------------
// The atomic core.
// ---------------------------------------------------------------------------

/**
 * Read → transform → atomic write → read back → compare → restore on mismatch.
 *
 * `validate` runs on the CANDIDATE text before it is written (YAML parses it) so
 * a corrupting edit is refused rather than landed and then reverted.
 *
 * The temp file is created in the SAME directory as the target: `rename(2)` is
 * atomic only within a filesystem, and `os.tmpdir()` is a different one on a Mac
 * with a data volume. The mode is copied from the original — `cabinet/.env` is
 * 0600 on a configured box and a fresh temp file would be 0644, which would
 * widen the permissions on the file holding every API key in the org.
 */
export async function editDocument(
  filePath: string,
  transform: (text: string) => Transform,
  options: { requireMatch?: boolean; validate?: (text: string) => void; missingHint?: string } = {}
): Promise<WriteResult> {
  const requireMatch = options.requireMatch !== false

  let before: string
  try {
    before = await readFile(filePath, 'utf8')
  } catch (err) {
    const code = (err as NodeJS.ErrnoException)?.code
    if (code === 'ENOENT') {
      throw new ConfigWriteError(
        filePath,
        `there is no file at ${filePath}, so nothing was changed`
      )
    }
    throw new ConfigWriteError(
      filePath,
      `${filePath} could not be read, so nothing was changed — ${
        err instanceof Error ? err.message : String(err)
      }`
    )
  }

  const { text: after, matched } = transform(before)

  if (matched === 0 && requireMatch) {
    // THE HALF `sed` CANNOT EXPRESS. Silence here is what turned a missing key
    // into a green tick on the settings page.
    throw new ConfigWriteError(
      filePath,
      options.missingHint ??
        `nothing in ${path.basename(filePath)} matched what was being edited, so nothing was changed`
    )
  }

  if (after === before) {
    // Found it; it already said that. A real outcome, and not a write.
    return { path: filePath, changed: false }
  }

  if (options.validate) {
    try {
      options.validate(after)
    } catch (err) {
      throw new ConfigWriteError(
        filePath,
        `that value would have made ${path.basename(filePath)} unreadable, so nothing was changed — ${
          err instanceof Error ? err.message : String(err)
        }`
      )
    }
  }

  const dir = path.dirname(filePath)
  const tmp = path.join(dir, `.${path.basename(filePath)}.tmp-${process.pid}-${randomBytes(4).toString('hex')}`)

  let mode: number | undefined
  try {
    mode = (await stat(filePath)).mode & 0o777
  } catch {
    mode = undefined
  }

  try {
    await writeFile(tmp, after, 'utf8')
    if (mode !== undefined) await chmod(tmp, mode)
    await rename(tmp, filePath)
  } catch (err) {
    await unlink(tmp).catch(() => {})
    throw new ConfigWriteError(
      filePath,
      `${path.basename(filePath)} could not be written, so nothing was changed — ${
        err instanceof Error ? err.message : String(err)
      }`
    )
  }

  // THE READ-BACK. Not ceremony: it is the only thing that can tell a write
  // that landed from a write the filesystem accepted and did something else
  // with, and it is what makes `{ success: true }` a measurement rather than a
  // report of intent.
  let verified: string
  try {
    verified = await readFile(filePath, 'utf8')
  } catch (err) {
    throw new ConfigWriteError(
      filePath,
      `${path.basename(filePath)} was written but could not be read back, so the change is unverified — ${
        err instanceof Error ? err.message : String(err)
      }`
    )
  }

  if (verified !== after) {
    // Put back exactly what was there. A half-applied config is worse than a
    // refused one, and the caller has to be told which it got.
    let restored = true
    try {
      await writeFile(filePath, before, 'utf8')
    } catch {
      restored = false
    }
    throw new ConfigWriteError(
      filePath,
      restored
        ? `${path.basename(filePath)} did not contain the change when it was read back, so the previous contents were restored and nothing was changed`
        : `${path.basename(filePath)} did not contain the change when it was read back AND could not be restored — this file needs a human`
    )
  }

  return { path: filePath, changed: true }
}

// ---------------------------------------------------------------------------
// YAML: line transforms, because these documents are hand-and-generator written.
// ---------------------------------------------------------------------------
//
// Deliberately NOT `yaml.load` → mutate → `yaml.dump`. `instance/config/*.yml`
// carries comments, key order and the block structure `assemble-config.sh`
// writes; a round-trip through js-yaml discards every comment in the file and
// reorders nothing predictably. The line walk changes ONE line and leaves every
// other byte alone — the property the `sed` scripts had and the only one worth
// keeping from them. `yaml.load` is still used, on the RESULT, as a validator.

const KEY_LINE = /^(\s*)([A-Za-z0-9_][A-Za-z0-9_.-]*)\s*:(.*)$/

interface KeyLine {
  index: number
  indent: number
}

function indentOf(line: string): number {
  const m = line.match(/^(\s*)/)
  return m ? m[1].length : 0
}

/**
 * Find `key` among the shallowest key-lines in [from, to).
 *
 * "Shallowest" rather than "indent 2 per level" because the range handed in is
 * always a single block, and assuming a fixed indent is how a walker breaks on
 * the first file somebody indents with four spaces.
 */
function findKeyLine(lines: string[], from: number, to: number, key: string): KeyLine | null {
  let base: number | null = null
  for (let i = from; i < to; i++) {
    const line = lines[i]
    if (!line.trim() || line.trim().startsWith('#')) continue
    const m = line.match(KEY_LINE)
    if (!m) continue
    const indent = m[1].length
    if (base === null) base = indent
    if (indent !== base) continue
    if (m[2] === key) return { index: i, indent }
  }
  return null
}

/** The lines belonging to the block opened at `index` (everything more indented). */
function blockRange(lines: string[], index: number, indent: number): [number, number] {
  let end = index + 1
  while (end < lines.length) {
    const line = lines[end]
    if (line.trim() && !line.trim().startsWith('#') && indentOf(line) <= indent) break
    end++
  }
  return [index + 1, end]
}

/** Walk a dotted path down the block structure. Null when any segment is absent. */
function locate(lines: string[], keyPath: string[]): KeyLine | null {
  let from = 0
  let to = lines.length
  let hit: KeyLine | null = null
  for (const key of keyPath) {
    hit = findKeyLine(lines, from, to, key)
    if (!hit) return null
    ;[from, to] = blockRange(lines, hit.index, hit.indent)
  }
  return hit
}

/**
 * The scalar as YAML, quoted only when it has to be.
 *
 * Plain style is preserved wherever it is safe, so `stability: 0.7` stays a
 * float and `enabled: true` stays a boolean — the bytes the working `sed` would
 * have written. Forcing everything through `yaml.dump` would quote them into
 * strings and silently retype half the cabinet's configuration.
 */
const PLAIN_SAFE = /^[A-Za-z0-9_./+][A-Za-z0-9_./+@ -]*$/

export function yamlScalar(value: string): string {
  if (value === '') return "''"
  if (PLAIN_SAFE.test(value) && !value.endsWith(' ')) return value
  const dumped = yaml.dump({ v: value }, { lineWidth: -1 }).trimEnd()
  return dumped.slice(dumped.indexOf(':') + 1).trim()
}

/** A value that cannot be written as a one-line scalar at all. */
function refuseUnwritable(value: string, what: string): void {
  if (/[\r\n]/.test(value)) {
    throw new ConfigWriteError(
      what,
      'a configuration value cannot contain a line break — nothing was changed'
    )
  }
}

/** Replace the scalar at `keyPath`. `matched` is 0 when the field is not there. */
export function setYamlScalar(text: string, keyPath: string[], value: string): Transform {
  refuseUnwritable(value, keyPath.join('.'))
  const lines = text.split('\n')
  const hit = locate(lines, keyPath)
  if (!hit) return { text, matched: 0 }

  const line = lines[hit.index]
  const m = line.match(KEY_LINE)
  if (!m) return { text, matched: 0 }

  const rest = m[3]
  // Keep a trailing comment when the old value is plainly unquoted; a `#` inside
  // a quoted scalar is not a comment and must not be treated as one.
  let comment = ''
  const oldValue = rest.trim()
  if (!/^["']/.test(oldValue)) {
    const c = rest.match(/(\s+#.*)$/)
    if (c) comment = c[1]
  }

  lines[hit.index] = `${m[1]}${m[2]}: ${yamlScalar(value)}${comment}`
  return { text: lines.join('\n'), matched: 1 }
}

/** Remove the key at `keyPath` and anything nested under it. */
export function deleteYamlKey(text: string, keyPath: string[]): Transform {
  const lines = text.split('\n')
  const hit = locate(lines, keyPath)
  if (!hit) return { text, matched: 0 }
  const [, end] = blockRange(lines, hit.index, hit.indent)
  lines.splice(hit.index, end - hit.index)
  return { text: lines.join('\n'), matched: 1 }
}

/**
 * The validator every YAML write runs against the candidate text.
 *
 * A line edit that produces a document YAML cannot read is a corruption, and
 * `sed` had no way to notice it. js-yaml v4 `load` is safe-by-default (no
 * arbitrary type construction).
 *
 * It uses the DEFAULT schema on purpose, because the validator has to accept
 * exactly what the READER accepts and no less: `lib/config.ts:80` loads
 * `product.yml` with a bare `yaml.load`. Pinning a stricter schema here would
 * refuse edits to documents the app reads happily — a gate calibrated against
 * something other than the thing it guards.
 */
export function mustParseAsYaml(text: string): void {
  yaml.load(text)
}

// ---------------------------------------------------------------------------
// .env files
// ---------------------------------------------------------------------------

/**
 * Set `KEY=value`, appending when absent if asked.
 *
 * A line break in the value is REFUSED rather than escaped. `echo 'K=v' >> .env`
 * with a newline in `v` wrote a second, attacker-chosen line into the file that
 * holds every credential the cabinet has; there is no legitimate `.env` value
 * with a newline in it, so the honest answer is no.
 */
export function setEnvValue(
  text: string,
  key: string,
  value: string,
  options: { createIfMissing?: boolean } = {}
): Transform {
  refuseUnwritable(value, key)
  const lines = text.split('\n')
  let matched = 0
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].startsWith(`${key}=`)) {
      lines[i] = `${key}=${value}`
      matched++
    }
  }
  if (matched === 0 && options.createIfMissing) {
    const body = text.length && !text.endsWith('\n') ? `${text}\n` : text
    return { text: `${body}${key}=${value}\n`, matched: 1 }
  }
  return { text: lines.join('\n'), matched }
}

/** Remove every `KEY=` line. */
export function deleteEnvKey(text: string, key: string): Transform {
  const lines = text.split('\n')
  const kept = lines.filter((l) => !l.startsWith(`${key}=`))
  return { text: kept.join('\n'), matched: lines.length - kept.length }
}

/** Parse a `.env` document into a map. Comments and blanks are skipped. */
export function parseEnvDocument(text: string): Record<string, string> {
  const vars: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const eq = line.indexOf('=')
    if (eq > 0) vars[line.slice(0, eq).trim()] = line.slice(eq + 1).trim()
  }
  return vars
}

// ---------------------------------------------------------------------------
// The three operations the actions actually perform.
// ---------------------------------------------------------------------------

/** Set one scalar in a YAML config. Throws when the field is not in the file. */
export async function writeYamlScalar(
  filePath: string,
  keyPath: string[],
  value: string
): Promise<WriteResult> {
  return editDocument(filePath, (text) => setYamlScalar(text, keyPath, value), {
    validate: mustParseAsYaml,
    missingHint: `${path.basename(filePath)} has no ${keyPath.join('.')} field, so nothing was changed`,
  })
}

/**
 * Remove a key from a YAML config.
 *
 * `requireMatch: false` because the callers delete keys that are legitimately
 * absent — an officer with no voice configured has no `voice.voices.<role>`
 * line, and refusing to delete him over it would be a regression dressed as
 * rigour. Every call site that needs the field to exist uses `writeYamlScalar`.
 */
export async function removeYamlKey(filePath: string, keyPath: string[]): Promise<WriteResult> {
  return editDocument(filePath, (text) => deleteYamlKey(text, keyPath), {
    requireMatch: false,
    validate: mustParseAsYaml,
  })
}

/** Set (or append) a key in a `.env` file. */
export async function writeEnvValue(
  filePath: string,
  key: string,
  value: string,
  options: { createIfMissing?: boolean } = {}
): Promise<WriteResult> {
  return editDocument(filePath, (text) => setEnvValue(text, key, value, options), {
    requireMatch: options.createIfMissing !== true,
    missingHint: `${key} is not in ${path.basename(filePath)}, so nothing was changed`,
  })
}

/** Remove a key from a `.env` file. Absent is not an error — it is the goal. */
export async function removeEnvKey(filePath: string, key: string): Promise<WriteResult> {
  return editDocument(filePath, (text) => deleteEnvKey(text, key), { requireMatch: false })
}

/** Read a `.env` file into a map without shelling out. Absent file = no vars. */
export async function readEnvDocument(filePath: string): Promise<Record<string, string>> {
  const text = await readFile(filePath, 'utf8')
  return parseEnvDocument(text)
}
