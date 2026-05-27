'use client'

import { useState, useTransition } from 'react'
import { EditableField, MaskedField } from '@/components/editable-field'
import { updateNotionConfig, updateLinearConfig } from '@/actions/config'
import { updateEnvVar, deleteEnvVar, addEnvVar } from '@/actions/env'

interface TelegramSectionProps {
  envVars: Record<string, string>
}

export function TelegramSection({ envVars }: TelegramSectionProps) {
  const hqChatId = envVars['TELEGRAM_HQ_CHAT_ID'] || ''
  const captainId = envVars['CAPTAIN_TELEGRAM_ID'] || ''
  const botTokenKeys = Object.keys(envVars).filter((k) => k.startsWith('TELEGRAM_') && k.endsWith('_TOKEN'))

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900" style={{ padding: '24px' }}>
      <h2 className="text-lg font-semibold text-white">Telegram</h2>
      <div className="mt-4 space-y-4">
        <MaskedField
          label="HQ Chat ID"
          value={hqChatId}
          onSave={(v) => updateEnvVar('TELEGRAM_HQ_CHAT_ID', v)}
        />
        <MaskedField
          label="Captain Telegram ID"
          value={captainId}
          onSave={(v) => updateEnvVar('CAPTAIN_TELEGRAM_ID', v)}
        />
        {botTokenKeys.length > 0 && (
          <>
            <div className="border-t border-zinc-800 pt-3">
              <span className="text-sm font-medium text-zinc-400">Bot Tokens</span>
            </div>
            {botTokenKeys.map((key) => {
              const role = key.replace('TELEGRAM_', '').replace('_TOKEN', '').toLowerCase()
              return (
                <MaskedField
                  key={key}
                  label={`${role.toUpperCase()} Bot Token`}
                  value={envVars[key] || ''}
                  onSave={(v) => updateEnvVar(key, v)}
                />
              )
            })}
          </>
        )}
      </div>
    </div>
  )
}

interface NotionSectionProps {
  notionConfig: Record<string, string>
}

export function NotionSection({ notionConfig }: NotionSectionProps) {
  const entries = Object.entries(notionConfig)

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900" style={{ padding: '24px' }}>
      <h2 className="text-lg font-semibold text-white">Notion</h2>
      {entries.length === 0 ? (
        <p className="mt-4 text-sm text-zinc-600">No Notion IDs configured.</p>
      ) : (
        <div className="mt-4 space-y-4">
          {entries.map(([key, value]) => (
            <EditableField
              key={key}
              label={key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
              value={value}
              onSave={(v) => updateNotionConfig(key, v)}
              mono
            />
          ))}
        </div>
      )}
    </div>
  )
}

interface LinearSectionProps {
  linearConfig: { team_key: string; workspace_url: string }
}

export function LinearSection({ linearConfig }: LinearSectionProps) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900" style={{ padding: '24px' }}>
      <h2 className="text-lg font-semibold text-white">Linear</h2>
      <div className="mt-4 space-y-4">
        <EditableField
          label="Team Key"
          value={linearConfig.team_key}
          onSave={(v) => updateLinearConfig('team_key', v)}
          mono
        />
        <EditableField
          label="Workspace URL"
          value={linearConfig.workspace_url}
          onSave={(v) => updateLinearConfig('workspace_url', v)}
          mono
        />
      </div>
    </div>
  )
}

interface ApiKeysSectionProps {
  envVars: Record<string, string>
}

// Per-key metadata mirrors cabinet/scripts/setup-env.sh so the dashboard
// and the CLI wizard tell the same story. Updating one without the other
// will drift the Captain UX.
//
// tier: 'critical' (Cabinet won't boot) | 'recommended' (degraded) | 'optional'
// section: groups the key under a heading in the UI
// signup: URL to open in a new tab for the Captain to acquire a fresh key
// description: shown beneath the field
// usedBy: which officer(s) the key powers
type KeyTier = 'critical' | 'recommended' | 'optional'
interface KeyMeta {
  tier: KeyTier
  section: string
  signup?: string
  description: string
  usedBy: string
}
const KEY_META: Record<string, KeyMeta> = {
  // Critical — Cabinet won't boot without these
  GITHUB_PAT: {
    tier: 'critical', section: 'Critical',
    signup: 'https://github.com/settings/tokens/new?scopes=repo,workflow,read:org&description=captains-cabinet',
    description: 'GitHub PAT — drives the github-issues task adapter (cabinet default backlog) + gh CLI for repo ops.',
    usedBy: 'CTO (repo), CPO (issues)',
  },
  NEON_CONNECTION_STRING: {
    tier: 'critical', section: 'Critical',
    signup: 'https://console.neon.tech/',
    description: 'Postgres connection string. Drives org_events ledger, cabinet_memory (pgvector), mission/role state.',
    usedBy: 'all officers (durable state)',
  },
  // Recommended — Cabinet runs without but degraded
  ANTHROPIC_API_KEY: {
    tier: 'recommended', section: 'Models & Memory',
    signup: 'https://console.anthropic.com/settings/keys',
    description: 'Anthropic API key. Drives the cua MCP server (native Mac GUI control) when CUA_MODEL_BACKEND=anthropic. Skip if using Max OAuth + no native Mac apps.',
    usedBy: 'cua (Mac GUI), officer fallback',
  },
  VOYAGE_API_KEY: {
    tier: 'recommended', section: 'Models & Memory',
    signup: 'https://dash.voyageai.com/',
    description: 'Voyage AI key for cabinet_memory embeddings (voyage-4-large, 1024d). Without this the semantic recall layer is dark — keyword retrieval still works.',
    usedBy: 'CoS (Captain DM recall), CRO (research)',
  },
  NOTION_API_KEY: {
    tier: 'recommended', section: 'Models & Memory',
    signup: 'https://www.notion.so/my-integrations',
    description: 'Notion internal integration token. Cabinet reads strategy/brand/vision + writes research briefs + specs here.',
    usedBy: 'CoS (briefings), CRO (research), CPO (specs)',
  },
  // Task systems — pick one
  LINEAR_API_KEY: {
    tier: 'recommended', section: 'Task system (pick one)',
    signup: 'https://linear.app/settings/api',
    description: 'Linear API key. Cabinet default task system.',
    usedBy: 'CPO (backlog), CTO (issues)',
  },
  MONDAY_API_KEY: {
    tier: 'optional', section: 'Task system (pick one)',
    signup: 'https://developer.monday.com/api-reference/docs/authentication',
    description: 'Monday.com API key — if your team uses monday.com instead of Linear.',
    usedBy: 'CPO',
  },
  JIRA_API_KEY: {
    tier: 'optional', section: 'Task system (pick one)',
    signup: 'https://id.atlassian.com/manage-profile/security/api-tokens',
    description: 'Jira API key.',
    usedBy: 'CPO',
  },
  ASANA_API_KEY: {
    tier: 'optional', section: 'Task system (pick one)',
    signup: 'https://app.asana.com/0/my-apps',
    description: 'Asana API key.',
    usedBy: 'CPO',
  },
  // Research APIs — CRO only
  PERPLEXITY_API_KEY: {
    tier: 'optional', section: 'Research APIs (CRO)',
    signup: 'https://www.perplexity.ai/settings/api',
    description: 'Perplexity API. Best general-purpose web research.',
    usedBy: 'CRO research sweep',
  },
  EXA_API_KEY: {
    tier: 'optional', section: 'Research APIs (CRO)',
    signup: 'https://dashboard.exa.ai/',
    description: 'Exa (formerly Metaphor). Semantic search across the web.',
    usedBy: 'CRO competitive intel',
  },
  BRAVE_SEARCH_API_KEY: {
    tier: 'optional', section: 'Research APIs (CRO)',
    signup: 'https://api.search.brave.com/',
    description: 'Brave Search API. Privacy-respecting backup search.',
    usedBy: 'CRO (search fallback)',
  },
  GOOGLE_API_KEY: {
    tier: 'optional', section: 'Research APIs (CRO)',
    signup: 'https://aistudio.google.com/apikey',
    description: 'Google AI Studio key — drives Gemini text/vision API + Nano Banana (Gemini 2.5 Flash Image generation). Single key for both.',
    usedBy: 'CRO (Gemini), any officer (Nano Banana image gen)',
  },
  // Product integrations — defer until outcome demands
  VERCEL_TOKEN: {
    tier: 'optional', section: 'Product integrations',
    signup: 'https://vercel.com/account/tokens',
    description: 'Vercel API token. Cabinet uses it to verify deploys + read build logs.',
    usedBy: 'CTO (deploy), COO (validate)',
  },
  SENTRY_DSN: {
    tier: 'optional', section: 'Product integrations',
    signup: 'https://docs.sentry.io/concepts/key-terms/dsn-explainer/',
    description: 'Sentry DSN (project-level).',
    usedBy: 'COO error triage',
  },
  SENTRY_AUTH_TOKEN: {
    tier: 'optional', section: 'Product integrations',
    signup: 'https://docs.sentry.io/api/auth/',
    description: 'Sentry auth token (for API queries). Same project as DSN.',
    usedBy: 'COO error triage',
  },
  POSTHOG_API_KEY: {
    tier: 'optional', section: 'Product integrations',
    signup: 'https://app.posthog.com/settings/project-details#variables',
    description: 'PostHog API key. Connect when the product has real users to analyze.',
    usedBy: 'CRO (analytics), CPO (usage)',
  },
  POSTHOG_HOST: {
    tier: 'optional', section: 'Product integrations',
    description: 'PostHog host URL (default: https://app.posthog.com). Override for self-hosted PostHog.',
    usedBy: 'CRO, CPO',
  },
  MAPBOX_TOKEN: {
    tier: 'optional', section: 'Product integrations',
    signup: 'https://account.mapbox.com/access-tokens/',
    description: 'Mapbox token. Only needed if the product uses maps.',
    usedBy: '(product-specific)',
  },
  // Alternate model providers + media
  OPENAI_API_KEY: {
    tier: 'optional', section: 'Alternates',
    signup: 'https://platform.openai.com/api-keys',
    description: 'OpenAI API. Alternate cua backend (CUA_MODEL_BACKEND=openai) or Stagehand model. Skip if fully on Anthropic.',
    usedBy: 'cua (alt backend)',
  },
  ELEVENLABS_API_KEY: {
    tier: 'optional', section: 'Alternates',
    signup: 'https://elevenlabs.io/app/settings/api-keys',
    description: 'ElevenLabs voice generation. Powers post-reply-voice.sh — Captain DM voice replies. Skip if text-only.',
    usedBy: 'all officers (voice replies)',
  },
  // Captain-layer runtime config (not strictly secrets — but worth surfacing)
  CUA_MODEL_BACKEND: {
    tier: 'optional', section: 'Captain-layer runtime',
    description: 'cua MCP model backend: anthropic (default) | openai | local-ui-tars-7b. Switch to local-ui-tars-7b for sovereignty/cost.',
    usedBy: 'cua',
  },
  CABINET_CHROME_DEBUG_PORT: {
    tier: 'optional', section: 'Captain-layer runtime',
    description: 'Cabinet Chrome debug port (default 9222). Always bound to 127.0.0.1 only.',
    usedBy: 'chrome_devtools MCP',
  },
  // Cabinet runtime
  DASHBOARD_PASSWORD: {
    tier: 'critical', section: 'Cabinet runtime',
    description: 'Dashboard login password. Auto-generated by setup-env.sh wizard if blank — DO NOT ship "changeme" to production.',
    usedBy: 'dashboard auth',
  },
}

const KNOWN_API_KEYS = Object.keys(KEY_META)

const TELEGRAM_KEYS = ['TELEGRAM_HQ_CHAT_ID', 'CAPTAIN_TELEGRAM_ID']

function DeleteKeyButton({ envKey }: { envKey: string }) {
  const [confirming, setConfirming] = useState(false)
  const [isPending, startTransition] = useTransition()

  if (confirming) {
    return (
      <div className="flex gap-1">
        <button
          onClick={() => startTransition(async () => { await deleteEnvVar(envKey); setConfirming(false) })}
          disabled={isPending}
          className="rounded bg-red-600 px-2 py-0.5 text-xs text-white hover:bg-red-700 disabled:opacity-50"
        >
          {isPending ? '...' : 'Confirm'}
        </button>
        <button onClick={() => setConfirming(false)}
          className="rounded border border-zinc-700 px-2 py-0.5 text-xs text-zinc-400 hover:bg-zinc-800">
          No
        </button>
      </div>
    )
  }

  return (
    <button onClick={() => setConfirming(true)}
      className="rounded border border-red-800 px-2 py-0.5 text-xs text-red-400 hover:bg-red-900/30">
      Delete
    </button>
  )
}

function AddKeyForm() {
  const [open, setOpen] = useState(false)
  const [error, setError] = useState('')
  const [isPending, startTransition] = useTransition()

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
        className="mt-3 rounded border border-zinc-700 px-3 py-1.5 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-white">
        + Add Variable
      </button>
    )
  }

  return (
    <div className="mt-4 rounded-lg border border-zinc-700 bg-zinc-800" style={{ padding: '16px' }}>
      <form onSubmit={(e) => {
        e.preventDefault()
        const fd = new FormData(e.currentTarget)
        const key = (fd.get('key') as string).trim()
        const value = (fd.get('value') as string).trim()
        if (!key || !value) { setError('Both fields required'); return }
        setError('')
        startTransition(async () => {
          const result = await addEnvVar(key, value)
          if (result.success) setOpen(false)
          else setError(result.error || 'Failed')
        })
      }}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1">
            <label className="text-xs text-zinc-500">Variable Name</label>
            <input name="key" placeholder="MY_API_KEY" required
              className="mt-1 block w-full rounded border border-zinc-600 bg-zinc-700 px-2 py-1.5 text-xs text-white font-mono placeholder-zinc-500 focus:border-zinc-500 focus:outline-none" />
          </div>
          <div className="flex-1">
            <label className="text-xs text-zinc-500">Value</label>
            <input name="value" type="password" placeholder="sk-..." required
              className="mt-1 block w-full rounded border border-zinc-600 bg-zinc-700 px-2 py-1.5 text-xs text-white font-mono placeholder-zinc-500 focus:border-zinc-500 focus:outline-none" />
          </div>
          <div className="flex gap-2">
            <button type="submit" disabled={isPending}
              className="rounded bg-white px-3 py-1.5 text-xs font-semibold text-zinc-900 hover:bg-zinc-200 disabled:opacity-50">
              {isPending ? 'Adding...' : 'Add'}
            </button>
            <button type="button" onClick={() => setOpen(false)}
              className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-400 hover:bg-zinc-700">
              Cancel
            </button>
          </div>
        </div>
        {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
      </form>
    </div>
  )
}

function TierBadge({ tier }: { tier: KeyTier }) {
  const styles: Record<KeyTier, string> = {
    critical: 'bg-red-900/30 text-red-400 border-red-800',
    recommended: 'bg-amber-900/30 text-amber-400 border-amber-800',
    optional: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  }
  return (
    <span className={`ml-2 rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase ${styles[tier]}`}>
      {tier}
    </span>
  )
}

function KeyRow({ envKey, value, meta }: { envKey: string; value: string; meta?: KeyMeta }) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-900/40" style={{ padding: '12px' }}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <div className="flex items-center gap-1 mb-1">
            <span className="font-mono text-sm text-white">{envKey}</span>
            {meta && <TierBadge tier={meta.tier} />}
            {value
              ? <span className="ml-2 text-[10px] uppercase text-green-400">● set</span>
              : <span className="ml-2 text-[10px] uppercase text-zinc-500">○ unset</span>
            }
          </div>
          {meta?.description && (
            <p className="mt-1 text-xs text-zinc-400">{meta.description}</p>
          )}
          {meta?.usedBy && (
            <p className="mt-0.5 text-[11px] text-zinc-500">Used by: {meta.usedBy}</p>
          )}
          <div className="mt-2">
            <MaskedField
              label=""
              value={value}
              onSave={(v) => updateEnvVar(envKey, v)}
            />
          </div>
          {meta?.signup && (
            <a
              href={meta.signup}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-block text-[11px] text-blue-400 hover:text-blue-300 hover:underline"
            >
              Get key →
            </a>
          )}
        </div>
        {value && (
          <div className="mt-1 shrink-0"><DeleteKeyButton envKey={envKey} /></div>
        )}
      </div>
    </div>
  )
}

// Stable section ordering (mirrors setup-env.sh wizard sections)
const SECTION_ORDER = [
  'Critical',
  'Models & Memory',
  'Task system (pick one)',
  'Research APIs (CRO)',
  'Product integrations',
  'Alternates',
  'Captain-layer runtime',
  'Cabinet runtime',
] as const

export function ApiKeysSection({ envVars }: ApiKeysSectionProps) {
  // Group known keys by section
  const grouped: Record<string, string[]> = {}
  for (const key of KNOWN_API_KEYS) {
    const section = KEY_META[key]?.section || 'Other'
    if (!grouped[section]) grouped[section] = []
    grouped[section].push(key)
  }
  const orderedSections = SECTION_ORDER.filter((s) => grouped[s]?.length)

  // Show extra keys (in .env but not in KEY_META, not Telegram, not Cabinet runtime)
  const extraKeys = Object.keys(envVars).filter(
    (k) =>
      !KNOWN_API_KEYS.includes(k) &&
      !k.startsWith('TELEGRAM_') &&
      !TELEGRAM_KEYS.includes(k) &&
      !k.startsWith('POSTGRES_') &&
      !k.startsWith('CABINET_'),
  )

  // Critical-keys-missing count for the header banner
  const missingCritical = KNOWN_API_KEYS.filter(
    (k) => KEY_META[k]?.tier === 'critical' && !envVars[k],
  )

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900" style={{ padding: '24px' }}>
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">API Keys &amp; Configuration</h2>
        {missingCritical.length > 0 ? (
          <span className="rounded border border-red-800 bg-red-900/30 px-2 py-0.5 text-xs text-red-400">
            {missingCritical.length} critical key{missingCritical.length === 1 ? '' : 's'} unset
          </span>
        ) : (
          <span className="rounded border border-green-800 bg-green-900/20 px-2 py-0.5 text-xs text-green-400">
            All critical keys set
          </span>
        )}
      </div>
      <p className="mt-1 text-xs text-zinc-500">
        Same tiered layout as <code className="text-zinc-400">cabinet/scripts/setup-env.sh</code>.
        Click <span className="text-blue-400">Get key →</span> to open the provider&apos;s signup page in a new tab.
      </p>

      {orderedSections.map((section) => (
        <div key={section} className="mt-6">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-400">{section}</h3>
          <div className="space-y-3">
            {grouped[section].map((key) => (
              <KeyRow key={key} envKey={key} value={envVars[key] || ''} meta={KEY_META[key]} />
            ))}
          </div>
        </div>
      ))}

      {extraKeys.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-400">
            Custom Variables
          </h3>
          <div className="space-y-3">
            {extraKeys.map((key) => (
              <KeyRow key={key} envKey={key} value={envVars[key] || ''} />
            ))}
          </div>
        </div>
      )}

      <AddKeyForm />
    </div>
  )
}
