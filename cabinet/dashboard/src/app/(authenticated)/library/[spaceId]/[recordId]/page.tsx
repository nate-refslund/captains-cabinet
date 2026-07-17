/**
 * /library/[spaceId]/[recordId] — redirect stub since the Library
 * retirement (2026-07-16). Old record deep-links land on the retirement
 * notice; the record content lives in the vault archive (provenance
 * frontmatter carries library_record:<id> for exact lookup).
 */

import { redirect } from 'next/navigation'

export default async function RecordRedirect() {
  redirect('/library')
}
