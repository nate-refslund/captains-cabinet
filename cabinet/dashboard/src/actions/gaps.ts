'use server'

/**
 * Server actions for the capability-gap loop — the Captain's one-click
 * Approve / Decline on a pending proposal, straight from /gaps.
 *
 * These shell to the org-runtime CLI (the single source of truth for gap
 * state). The CLI's approve emits a `capability_gap_approved` event, which is
 * the ONLY thing that unlocks the fail-closed install gate
 * (capability_gaps.can_install). So a Captain tap here is what lets CTO build
 * the proposed MCP — nothing installs without it.
 */

import { dockerExec } from '@/lib/docker'
import { revalidatePath } from 'next/cache'

// gap ids are `gap-<8 hex>` — validate before interpolating into a shell cmd.
const GAP_ID_RE = /^gap-[0-9a-f]{8}$/

export async function approveGap(gapId: string): Promise<{ ok: boolean; error?: string }> {
  if (!GAP_ID_RE.test(gapId)) return { ok: false, error: 'invalid gap id' }
  try {
    await dockerExec(
      `python3 cabinet/scripts/org-runtime.py gaps approve '${gapId}' --actor captain --note 'approved via dashboard'`
    )
    revalidatePath('/gaps')
    return { ok: true }
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'approve failed' }
  }
}

export async function declineGap(gapId: string, reason: string): Promise<{ ok: boolean; error?: string }> {
  if (!GAP_ID_RE.test(gapId)) return { ok: false, error: 'invalid gap id' }
  // Sanitize the reason for safe single-quote shell embedding.
  const safeReason = (reason || 'declined via dashboard').replace(/'/g, "'\\''").slice(0, 400)
  try {
    await dockerExec(
      `python3 cabinet/scripts/org-runtime.py gaps decline '${gapId}' --actor captain --reason '${safeReason}'`
    )
    revalidatePath('/gaps')
    return { ok: true }
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'decline failed' }
  }
}
