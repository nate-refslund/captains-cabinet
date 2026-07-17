/**
 * /library/[spaceId] — redirect stub since the Library retirement
 * (2026-07-16). Old space deep-links land on the retirement notice.
 */

import { redirect } from 'next/navigation'

export default async function SpaceRedirect() {
  redirect('/library')
}
