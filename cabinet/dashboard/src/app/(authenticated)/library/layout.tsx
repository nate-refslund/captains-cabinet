/**
 * Library layout — passthrough since the Library retirement (2026-07-16).
 * The Spec 037 A4 sidebar (spaces + per-space record tree) is gone with the
 * editable UI; /library/* now renders only the retirement notice and
 * redirect stubs, so the layout does no data fetching.
 */

import type { ReactNode } from 'react'

export default function LibraryLayout({
  children,
}: {
  children: ReactNode
}) {
  return <>{children}</>
}
