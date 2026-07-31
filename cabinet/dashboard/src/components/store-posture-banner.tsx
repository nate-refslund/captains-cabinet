import {
  storeBannerAttr,
  storeBannerHint,
  storeBannerTitle,
  type StoreReading,
} from '@/lib/store-posture'

/**
 * THE DISCLOSURE. Says what produced every number on the page, or renders
 * nothing at all when the answer is "your cabinet".
 *
 * WHY IT IS A SEPARATE COMPONENT AND NOT A LINE IN THE LAYOUT: it has to be
 * mountable on `/display` too, which sits OUTSIDE `(authenticated)/layout.tsx`
 * and is the surface a kiosk shows all day with nobody reading the console.
 * One dialect, two mount points.
 *
 * VOCABULARY — deliberately identical to the emergency-stop banner on the home
 * page and the census masthead on /queue: a dashed amber border, plain words
 * for the reason, and no green anywhere. A second dialect for "you are not
 * looking at a measurement" is how one of them rots.
 *
 * PROPS, NOT ENV. The posture is read once on the server and passed in, so this
 * file stays free of `process.env` and can be driven directly from a test with
 * every posture including the ones an environment cannot easily produce.
 */
export default function StorePostureBanner({
  reading,
  compact = false,
}: {
  reading: StoreReading
  compact?: boolean
}) {
  const title = storeBannerTitle(reading)
  // `live` renders zero pixels. Disclosure is for the absence of measurement;
  // announcing a healthy store on every page would be the noise that trains
  // the eye to skip the banner in the one posture that matters.
  if (!title) return null

  const hint = storeBannerHint(reading)

  return (
    <div
      data-store-posture={storeBannerAttr(reading)}
      role="status"
      className={`rounded-xl border border-dashed border-amber-400/60 bg-amber-900/10 ${
        compact ? 'px-4 py-2' : 'px-5 py-4'
      }`}
    >
      <p
        className={`font-semibold text-amber-300 ${
          compact ? 'text-xs' : 'text-sm'
        }`}
      >
        {title}
      </p>
      <p
        className={`mt-0.5 text-amber-100/70 ${compact ? 'text-[11px]' : 'text-xs'}`}
      >
        {reading.source}
      </p>
      {hint && (
        <p className={`mt-0.5 text-zinc-500 ${compact ? 'text-[11px]' : 'text-xs'}`}>
          {hint}
        </p>
      )}
    </div>
  )
}
