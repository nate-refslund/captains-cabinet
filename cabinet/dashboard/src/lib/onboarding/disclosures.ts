/**
 * The disclosure rows a surface renders, from any card the core has ever sent.
 *
 * WHY A PROJECTION EXISTS AT ALL. `card.disclosures` is the authored list and
 * every card built by this tree carries it. But a card is a persisted, shared
 * object: a Telegram surface, a queued action, a state file written by an older
 * build or an in-flight request from a page loaded before a deploy can all hand
 * this component a card that predates the field. Rendering NOTHING in that case
 * would turn a version skew into deleted honesty — the exact failure this whole
 * branch is guarded against — so an older card's `headline` + `details` are
 * read back into rows, and a card with only a `body` becomes one row.
 *
 * IT IS THE INVERSE OF THE CORE'S OWN PROJECTION (`journey.py` `_layered`), and
 * `disclosure-render.test.ts` asserts the round trip: rows → card fields → rows
 * returns the same ids and the same text.
 */
import type { OnboardingCard, OnboardingDisclosure } from './types'

/** Every row this card wants rendered, whatever shape it arrived in. */
export function disclosureRows(card: OnboardingCard): OnboardingDisclosure[] {
  if (card.disclosures && card.disclosures.length > 0) return card.disclosures
  const lead: OnboardingDisclosure[] = (card.headline ?? []).map((text, index) => ({
    id: `lead_${index}`,
    layer: 'headline',
    title: '',
    text,
    cites: [],
  }))
  const rest: OnboardingDisclosure[] = (card.details ?? []).map((section) => ({
    id: section.id,
    layer: 'fold',
    title: section.title,
    text: section.text,
    cites: [],
  }))
  if (lead.length === 0 && rest.length === 0) {
    const body = String(card.body ?? '').trim()
    // A LEDGER ROW, NOT A HEADLINE. An old card's body is the whole ledger, and
    // promoting it to the lead would put a paragraph where one sentence goes —
    // which is the defect the layering was introduced to fix.
    return body ? [{ id: 'body', layer: 'fold', title: '', text: card.body, cites: [] }] : []
  }
  return [...lead, ...rest]
}
