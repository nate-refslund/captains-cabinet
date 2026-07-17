/**
 * /library/graph — redirect stub since the Library retirement (2026-07-16).
 * The force-directed wiki-link graph went away with the editable UI.
 */

import { redirect } from 'next/navigation'

export default async function GraphRedirect() {
  redirect('/library')
}
