import type { DashboardMode } from '@/hooks/use-dashboard-mode'

export type NavLink = {
  href: string
  label: string
  /** If true, renders as an external anchor with target=_blank. */
  external?: boolean
}

/**
 * Nav link set per dashboard mode (Spec 032).
 *
 * Consumer (6 items, including the canonical post-hatch journey):
 *   Dashboard / Orientation / Cabinets / Costs / Library / Settings
 *
 * Advanced (all items, zero regression from the pre-Spec-032 nav):
 *   Dashboard / Orientation / Needs You / World / Project / Cabinets / Officers / Tasks /
 *   Capability Gaps / Health / Settings / Governance / Receipts /
 *   Integrations / Costs / Crons / Vault / Library / Terminal (external)
 *
 * Vault (read-only filesystem browser over the org vault/ corpus) is an
 * Advanced-only power tool; it is intentionally NOT in CONSUMER_NAV.
 *
 * Receipts (perfect-cabinet Wave B): read-only browser over the undo
 * journal — the what/why/cost/undo receipt surface, next to Governance.
 *
 * Terminal-to-Advanced per CoS plan review 2026-04-17 — a raw-shell utility
 * doesn't fit the consumer "check in" intent.
 *
 * Cabinets nav link is hidden at runtime when CABINETS_PROVISIONING_ENABLED !== 'true'.
 * The nav-config exports the links unconditionally; NavWithMode / NavStatic filter them
 * based on the feature flag so the static config stays declarative.
 */

export const ADVANCED_NAV: NavLink[] = [
  { href: '/', label: 'Dashboard' },
  { href: '/onboarding', label: 'Orientation' },
  { href: '/queue', label: 'Needs You' },
  { href: '/world', label: 'World' },
  { href: '/project', label: 'Project' },
  { href: '/cabinets', label: 'Cabinets' },
  { href: '/officers', label: 'Officers' },
  { href: '/tasks', label: 'Tasks' },
  { href: '/gaps', label: 'Capability Gaps' },
  { href: '/health', label: 'Health' },
  { href: '/settings', label: 'Settings' },
  { href: '/governance', label: 'Governance' },
  { href: '/receipts', label: 'Receipts' },
  { href: '/integrations', label: 'Integrations' },
  { href: '/costs', label: 'Costs' },
  { href: '/crons', label: 'Crons' },
  { href: '/vault', label: 'Vault' },
  { href: '/library', label: 'Library' },
  { href: 'https://terminal.example.com', label: 'Terminal', external: true },
]

export const CONSUMER_NAV: NavLink[] = [
  { href: '/', label: 'Dashboard' },
  { href: '/onboarding', label: 'Orientation' },
  { href: '/cabinets', label: 'Cabinets' },
  { href: '/costs', label: 'Costs' },
  { href: '/library', label: 'Library' },
  { href: '/settings', label: 'Settings' },
]

export function navForMode(mode: DashboardMode, consumerEnabled: boolean): NavLink[] {
  if (!consumerEnabled) return ADVANCED_NAV
  return mode === 'consumer' ? CONSUMER_NAV : ADVANCED_NAV
}
