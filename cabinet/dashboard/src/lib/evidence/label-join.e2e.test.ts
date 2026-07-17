/**
 * label-join.e2e.test.ts — the dashboard half of the Phase-3 label join,
 * END TO END on a scratch store with the REAL Python verifier:
 *
 *   governance-review.py CLI (Captain token, scripted TTY)  — spawned fixture
 *       └─ verdict_human events on the judged trial
 *            └─ readEvidence() (this page's read model, real verifier spawn)
 *                 └─ the trial renders basis 'human-verified'
 *
 * The pytest twin (cabinet/scripts/tests/test_evidence_label_join.py) drives
 * the SAME CLI path into the G1 query plane / officer projection; this file
 * proves the page read-model leg, including:
 *   - fail-closed verification through the real `python3.12 -m
 *     framework.evidence verify` spawn (no injected verifier);
 *   - basis contrast: the labeled trial is human-verified while an unlabeled
 *     producer trial stays persistence-only;
 *   - the read-only law at the page layer: repeated reads leave the store
 *     tree byte-identical (the one sanctioned side effect — the verifier's
 *     anti-rollback watermark advancing on a trial's FIRST verify — settles
 *     after the first pass).
 *
 * Skips (with a loud reason) when python3.12 is unavailable — CI images for
 * the dashboard always carry it; a skip on a dev laptop is honest, not
 * silent. Synthetic Testburg vocabulary only.
 */
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { readEvidence } from './read'

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../../../..'
)
const PYTHON = process.env.CABINET_PYTHON || 'python3.12'

/** Fixture: seeds one producer trial, labels it through the REAL
 * governance-review CLI main() (token gate + scripted Captain), then seeds a
 * second, unlabeled producer trial. argv: <storeDir> <repoRoot>. Fixed
 * string — nothing is interpolated into it. */
const FIXTURE = `
import hashlib, hmac, importlib.util, io, sys
from pathlib import Path

store = Path(sys.argv[1]); repo = Path(sys.argv[2])
sys.path.insert(0, str(repo))
from framework.evidence import __main__ as evidence_cli
from framework.evidence.recorder import EvidenceRecorder

def seed(rec, trial_id):
    ctx = rec.trace(trial_id, surface="system")
    officer = {"kind": "officer", "id": "tb-cos"}
    component = {"name": "testburg-exec", "version": "1"}
    detail = {"action": "write_testburg_note", "jid": "j-tb-9"}
    rec.append(ctx, phase="intent", status="started", actor=officer,
               component=component, detail=detail)
    rec.append(ctx, phase="execution", status="succeeded", actor=officer,
               component=component, detail=detail)

rec = EvidenceRecorder(store)
seed(rec, "trial-tb-page-join-1")

spec = importlib.util.spec_from_file_location(
    "governance_review_fixture", repo / "cabinet" / "scripts" / "governance-review.py")
gr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gr)

key = (store / ".signing-key").read_bytes()
token = hmac.new(key, evidence_cli.CAPTAIN_TOKEN_PURPOSE.encode("utf-8"),
                 hashlib.sha256).hexdigest()
token_file = store.parent / "captain.token"
token_file.write_text(token + "\\n", encoding="utf-8")
token_file.chmod(0o600)

answers = iter(["r", "clean Testburg page join"])
out = io.StringIO()
rc = gr.main(["--store", str(store), "--captain-token-file", str(token_file),
              "--skip-stations", "--seed", "7",
              "--labels-journal", str(store.parent / "labels.jsonl"),
              "--transcript-dir", str(store.parent / "reviews")],
             input_fn=lambda prompt: next(answers, "q"), isatty=True, out=out)
if rc != 0:
    sys.stderr.write(out.getvalue())
    sys.exit(1)

seed(EvidenceRecorder(store), "trial-tb-page-bystander-1")
print("fixture-ok")
`

function treeDigest(root: string): Record<string, string> {
  const digest: Record<string, string> = {}
  const walk = (dir: string) => {
    for (const name of fs.readdirSync(dir).sort()) {
      const full = path.join(dir, name)
      const stat = fs.lstatSync(full)
      if (stat.isDirectory()) walk(full)
      else if (stat.isFile()) {
        digest[path.relative(root, full)] = createHash('sha256')
          .update(fs.readFileSync(full))
          .digest('hex')
      }
    }
  }
  walk(root)
  return digest
}

const pythonPresent = (() => {
  try {
    return spawnSync(PYTHON, ['--version'], { shell: false }).status === 0
  } catch {
    return false
  }
})()

describe.skipIf(!pythonPresent)(
  'label join e2e: CLI label → page read model (real verifier)',
  () => {
    let scratchRoot: string
    let storeDir: string
    const savedCabinetRoot = process.env.CABINET_ROOT
    const savedPythonPath = process.env.PYTHONPATH

    beforeAll(() => {
      scratchRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'ev-p3-label-join-'))
      storeDir = path.join(scratchRoot, 'instance', 'evidence', 'v1')
      fs.mkdirSync(path.dirname(storeDir), { recursive: true })
      const fixture = spawnSync(PYTHON, ['-c', FIXTURE, storeDir, repoRoot], {
        shell: false,
        encoding: 'utf8',
        timeout: 60_000,
      })
      if (fixture.status !== 0 || !fixture.stdout.includes('fixture-ok')) {
        throw new Error(
          `label fixture failed (status ${fixture.status}): ${fixture.stderr}`
        )
      }
      // Point the read model at the scratch root; PYTHONPATH lets the real
      // verifier spawn (cwd = scratch root) resolve framework/ from the
      // actual checkout. Both restored in afterAll.
      process.env.CABINET_ROOT = scratchRoot
      process.env.PYTHONPATH = repoRoot
    })

    afterAll(() => {
      if (savedCabinetRoot === undefined) delete process.env.CABINET_ROOT
      else process.env.CABINET_ROOT = savedCabinetRoot
      if (savedPythonPath === undefined) delete process.env.PYTHONPATH
      else process.env.PYTHONPATH = savedPythonPath
      fs.rmSync(scratchRoot, { recursive: true, force: true })
    })

    it(
      'a Captain label written via the CLI renders basis human-verified; reads stay read-only',
      { timeout: 120_000 },
      async () => {
        // Pass 1 — settles the verifier watermark (a trial's FIRST verify is
        // the one sanctioned read side effect, identical to `evidence verify`).
        const first = await readEvidence()
        expect(first.error).toBeNull()
        expect(first.storeOk).toBe(true)
        expect(first.unverifiedCount).toBe(0)

        const settled = treeDigest(storeDir)

        const payload = await readEvidence()
        expect(payload.error).toBeNull()
        expect(payload.storeOk).toBe(true)

        const labeled = payload.rows.find(
          (row) => row.trialId === 'trial-tb-page-join-1'
        )
        expect(labeled, 'labeled trial must be served verified').toBeDefined()
        expect(labeled?.verified).toBe(true)
        expect(labeled?.basis).toBe('human-verified')
        expect(labeled?.basisReason).toContain('captain')
        expect(labeled?.actors).toContain('captain:captain')
        expect(labeled?.components).toContain('governance-review')

        // Contrast: the unlabeled producer trial stays a weak basis — a
        // label upgrades exactly the judged trial, nothing else.
        const bystander = payload.rows.find(
          (row) => row.trialId === 'trial-tb-page-bystander-1'
        )
        expect(bystander?.basis).toBe('persistence-only')

        // Filters ride the same one-truth grammar end to end.
        const filtered = await readEvidence({ actor: 'captain:captain' })
        expect(filtered.filterError).toBeNull()
        expect(filtered.rows.map((row) => row.trialId)).toEqual([
          'trial-tb-page-join-1',
        ])

        // READ-ONLY at the page layer: every read after settling leaves the
        // store tree byte-identical, watermark sidecar included.
        expect(treeDigest(storeDir)).toEqual(settled)
      }
    )
  }
)
