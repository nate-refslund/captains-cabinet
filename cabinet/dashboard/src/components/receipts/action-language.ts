/**
 * action-language.ts — TS MIRROR of the receipt grammar's plain-language
 * phrase map in `framework/frontdoor/action_language.py` (perfect-cabinet
 * Wave B: slug → human phrase; that module is the SOURCE OF TRUTH).
 *
 * WHY A MIRROR: the dashboard cannot import Python, and runtime-parsing
 * Python source in prod would fail silently on any refactor. Instead the
 * map is mirrored here and `action-language.test.ts` parses the Python
 * `HUMAN_PHRASES` dict at test time and asserts the two maps are IDENTICAL
 * — drift fails CI loudly at build time, never degrades the page quietly.
 *
 * DO NOT extend this map ad hoc: change `action_language.py` first, then
 * mirror the change here — the parity test will hold you to it.
 *
 * Keys cover every classifier `action_type`
 * (framework/authority/classifier.py::ACTION_TYPES + the `ambiguous`
 * backstop) AND every executor step kind (action_exec payload schemas +
 * the proposer's ACTION_TYPE_MAP keys), exactly like the Python source.
 * Unknown slugs fall back to the same visible de-underscore words —
 * never an invented phrase, never a raw `some_new_slug` token.
 */

export const HUMAN_PHRASES: Record<string, string> = {
  // -- classifier action_types: reversible class --
  task_status_move: "moved a task's status",
  label: 'changed a label',
  tier2_note: 'wrote a note',
  draft_only: 'prepared a draft',
  local_edit: 'edited a local file',
  investigation_run: 'ran a read-only investigation',
  // -- pm_write / calendar_write (reversible-with-undo) --
  task_create: 'created a task',
  board_status: 'updated a board column',
  calendar_event_create: 'scheduled a calendar event',
  // -- internal comms --
  internal_message: 'sent an internal message',
  internal_email: 'sent an internal email',
  officer_dispatch: 'dispatched work to an officer',
  // -- external comms (hard ceiling — phrases exist for honest telling only) --
  external_message: 'sent an external message',
  external_email: 'sent an external email',
  // -- deploy --
  vercel_deploy_preview: 'deployed a preview build',
  git_push_nonmain: 'pushed to a non-main branch',
  vercel_deploy_prod: 'deployed to production',
  git_push_main: 'pushed to the main branch',
  // -- spend (ceiling) --
  purchase: 'made a purchase',
  provision_paid: 'provisioned a paid service',
  billing: 'changed a billing setting',
  // -- secrets (ceiling) --
  secret_read: 'read a secret',
  secret_write: 'wrote a secret',
  env_write: 'changed an environment variable',
  // -- network_write (ceiling) --
  mcp_post: 'sent a network write (POST)',
  mcp_put: 'sent a network write (PUT)',
  mcp_delete: 'sent a network delete',
  // -- credentials_grant (ceiling) --
  oauth_grant: 'granted an OAuth authorization',
  token_grant: 'granted a token',
  // -- the visible propose-defaulting backstop --
  ambiguous: 'performed an unclassified action',
  // -- executor step kinds (action_exec._PAYLOAD_KEYS / ACTION_TYPE_MAP keys;
  //    investigation_run doubles as both and is covered above) --
  monday_task_create: 'created a task',
  monday_task_update: 'updated a task',
  reminder_create: 'scheduled an event',
  delegate_work: 'dispatched work to an officer',
  mission_propose: 'proposed a mission',
  // -- the acted-event fallback kind (action_undo.acted_event) --
  action: 'performed an action',
}

function lookup(slug: unknown): string | null {
  if (typeof slug !== 'string' || !slug) return null
  // hasOwnProperty guard: a hostile slug like "__proto__" must never
  // resolve through the prototype chain.
  return Object.prototype.hasOwnProperty.call(HUMAN_PHRASES, slug)
    ? HUMAN_PHRASES[slug]
    : null
}

/** Mirror of action_language.human_phrase's fallback: de-underscore/de-hyphen
 * to lowercase words, marker char (U+00B7) stripped — visible words for an
 * unknown slug, never a raw token; empty ⇒ "acted". */
function deUnderscore(slug: string): string {
  return slug.replace(/[_-]+/g, ' ').trim().toLowerCase().replace(/·/g, '') || 'acted'
}

export interface ActionPhrase {
  text: string
  /** False when no phrase is registered — `text` is then the safe
   * de-underscore fallback, flagged so the page can say so honestly. */
  mapped: boolean
}

/** The plain-language phrase for a journal row. KIND first (the executor
 * step's mechanical identity — "updated a task"), then the classifier
 * action_type (its policy bucket — "updated a board column"); both resolve
 * through the ONE mirrored map. Nothing mapped ⇒ the visible de-underscore
 * fallback, flagged unmapped. */
export function phraseFor(
  actionType: string | null | undefined,
  kind: string | null | undefined
): ActionPhrase {
  const byKind = lookup(kind)
  if (byKind !== null) return { text: byKind, mapped: true }
  const byType = lookup(actionType)
  if (byType !== null) return { text: byType, mapped: true }
  const raw = (typeof kind === 'string' && kind) || (typeof actionType === 'string' && actionType) || ''
  return { text: deUnderscore(raw), mapped: false }
}
