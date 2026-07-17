'use server'

/**
 * evidence.ts — the /evidence read model (whole-cabinet evidence Phase 3).
 *
 * READ-ONLY by doctrine and by law: this module exposes exactly one lookup
 * over the evidence store (verification, parsing and shaping live in
 * `@/lib/evidence/read`). Phase 3's single designed write — Captain labels —
 * is a token-gated CLI harness, NEVER a dashboard action: no label, purge,
 * retain, export or any other mutating verb exists here, and none may be
 * added (pinned by evidence-static.test.ts).
 *
 * The evidence store is the full record of what the cabinet did and how it
 * was judged — gate it. On unauth, return an empty, well-formed payload with
 * an honest error (the page renders `error` loudly), never a row. Filter
 * arguments arrive from the client and are therefore untrusted: they are
 * validated against closed vocabularies inside readEvidence BEFORE any I/O
 * and can never reach a filesystem path or the verifier's argv.
 */

import {
  EVIDENCE_SHOW_CAP,
  readEvidence,
  type EvidencePayload,
  type RawEvidenceFilters,
} from '@/lib/evidence/read'
import { requireDashboardAuth } from '@/lib/provisioning/guard'

function emptyPayload(error: string): EvidencePayload {
  return {
    rows: [],
    unverified: [],
    totalTrials: 0,
    verifiedCount: 0,
    unverifiedCount: 0,
    matchedCount: 0,
    skippedLines: 0,
    skippedFiles: 0,
    storeOk: false,
    storeErrors: [],
    missingDir: false,
    error,
    filterError: null,
    filters: {},
    storeDir: '',
    cap: EVIDENCE_SHOW_CAP,
  }
}

export async function listEvidence(raw?: RawEvidenceFilters): Promise<EvidencePayload> {
  if (!(await requireDashboardAuth())) {
    return emptyPayload('Unauthorized')
  }
  try {
    return await readEvidence(raw)
  } catch (err) {
    // Fail loud, never partial: a throw anywhere in the read model renders
    // as the page's error banner. Bounded message; no stack, no stderr.
    const message = err instanceof Error ? err.message.slice(0, 300) : 'evidence read failed'
    return emptyPayload(message || 'evidence read failed')
  }
}
