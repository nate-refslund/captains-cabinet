import {
  getGlobalConfig,
  getDashboardConfig,
  getConfig,
  getCaptainAvailability,
} from '@/lib/config'
import {
  ProductSection,
  VoiceSection,
  ImageGenSection,
  EmbeddingsSection,
} from '@/components/settings-forms'
import SettingsModeSwitch from '@/components/consumer/settings-mode-switch'
import { AvailabilityField } from '@/components/consumer/availability-field'
import type { CaptainAvailability } from '@/lib/config'

export const dynamic = 'force-dynamic'

function AdvancedSettings({
  config,
  availability,
}: {
  config: ReturnType<typeof getGlobalConfig>
  availability: CaptainAvailability
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Global configuration for the Cabinet
        </p>
      </div>

      {/* The dial lives on BOTH surfaces on purpose: a deployment with
          consumer mode switched off renders Advanced directly, and if the row
          were consumer-only that deployment would have no dashboard control at
          all — which is the phone-only hole this change exists to close. */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900" style={{ padding: '24px' }}>
        <h2 className="text-lg font-semibold text-white">Captain</h2>
        <div className="mt-4 space-y-4">
          <AvailabilityField availability={availability} />
        </div>
      </div>

      <ProductSection config={config.product} />
      <VoiceSection config={config.voice} />
      <ImageGenSection config={config.image_generation} />
      <EmbeddingsSection config={config.embeddings} />
    </div>
  )
}

export default function SettingsPage() {
  const config = getGlobalConfig()
  const { consumerModeEnabled } = getDashboardConfig()

  // Availability is the Captain's declared time budget (ruling 2026-07-26),
  // editable on both surfaces since 2026-07-27 — the write path is
  // updateCaptainAvailability, which runs the store's own recorder (the same
  // append the phone verb makes), never a platform.yml edit.
  const availability = getCaptainAvailability()

  // Feature-flag-off: render Advanced directly, never mount the mode switch.
  if (!consumerModeEnabled) {
    return <AdvancedSettings config={config} availability={availability} />
  }

  // Timezone is a platform-level setting on instance/config/platform.yml —
  // read directly from getConfig() since the current typed GlobalConfig
  // doesn't surface it yet. Displayed read-only in Consumer for now: its only
  // writer is the generator, so a settings action for it needs the
  // marker-managed-file question answered first (tech-debt, unchanged).
  const rawConfig = getConfig() as Record<string, unknown>
  const timezone = (rawConfig.captain_timezone as string) || 'UTC'

  // Officer roles from the telegram.officers map — we show a read-only chip
  // roster in Consumer mode. Editing moves to Advanced.
  const telegram = (rawConfig.telegram as Record<string, unknown>) || {}
  const officers = (telegram.officers as Record<string, unknown>) || {}
  const officerRoles = Object.keys(officers)

  return (
    <SettingsModeSwitch
      consumerProps={{ config, officerRoles, timezone, availability }}
    >
      <AdvancedSettings config={config} availability={availability} />
    </SettingsModeSwitch>
  )
}
