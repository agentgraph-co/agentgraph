// ─── External Signals Card ───
// Profile card showing all linked sources with live metrics.
// Fetches from GET /linked-accounts/{entityId}/public.

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'

interface LinkedAccountPublic {
  id: string
  provider: string
  provider_username: string
  verification_status: string
  reputation_score: number
  reputation_data: Record<string, unknown> | null
  community_signals: Record<string, unknown> | null
  last_synced_at: string | null
}

const PROVIDER_LABELS: Record<string, string> = {
  github: 'GH',
  npm: 'npm',
  pypi: 'PyPI',
  docker: 'Docker',
  huggingface: 'HF',
  api_health: 'API',
}

const PROVIDER_COLORS: Record<string, string> = {
  github: 'text-text',
  npm: 'text-red-400',
  pypi: 'text-blue-400',
  docker: 'text-blue-300',
  huggingface: 'text-yellow-400',
  api_health: 'text-emerald-400',
}

function formatMetric(value: unknown): string {
  if (typeof value !== 'number') return String(value ?? '')
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1).replace(/\.0$/, '')}k`
  return String(value)
}

function getKeyMetrics(account: LinkedAccountPublic): string {
  const data = account.reputation_data || {}
  const provider = account.provider

  if (provider === 'github') {
    const stars = data.total_stars ?? data.stars
    const forks = data.total_forks ?? data.forks
    const parts: string[] = []
    if (stars != null) parts.push(`★ ${formatMetric(stars)}`)
    if (forks != null) parts.push(`⑂ ${formatMetric(forks)}`)
    return parts.join('  ') || ''
  }
  if (provider === 'npm') {
    const dl = data.downloads
    return dl != null ? `${formatMetric(dl)} dl/mo` : ''
  }
  if (provider === 'pypi') {
    const dl = data.downloads
    const releases = data.release_count
    const parts: string[] = []
    if (dl != null) parts.push(`${formatMetric(dl)} dl`)
    if (releases != null) parts.push(`${releases} releases`)
    return parts.join('  ') || ''
  }
  if (provider === 'docker') {
    const pulls = data.pull_count
    const stars = data.star_count
    const parts: string[] = []
    if (pulls != null) parts.push(`${formatMetric(pulls)} pulls`)
    if (stars != null) parts.push(`★ ${formatMetric(stars)}`)
    return parts.join('  ') || ''
  }
  if (provider === 'huggingface') {
    const dl = data.downloads
    const likes = data.likes
    const parts: string[] = []
    if (dl != null) parts.push(`${formatMetric(dl)} dl`)
    if (likes != null) parts.push(`♥ ${formatMetric(likes)}`)
    return parts.join('  ') || ''
  }
  if (provider === 'api_health') {
    const uptime = data.uptime_pct
    return uptime != null ? `${uptime}% uptime` : ''
  }
  return ''
}

function timeAgoShort(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

interface ExternalSignalsProps {
  entityId: string
  isOwn: boolean
}

export default function ExternalSignals({ entityId, isOwn }: ExternalSignalsProps) {
  const queryClient = useQueryClient()

  const { data: accounts, isLoading } = useQuery<LinkedAccountPublic[]>({
    queryKey: ['linked-accounts-public', entityId],
    queryFn: () => api.get(`/linked-accounts/${entityId}/public`).then(r => r.data),
    staleTime: 60_000,
  })

  const refreshMutation = useMutation({
    mutationFn: () => api.post('/linked-accounts/discover'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['linked-accounts-public', entityId] })
    },
  })

  if (isLoading || !accounts || accounts.length === 0) return null

  return (
    <div className="bg-surface border border-border rounded-lg p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider">
          External Signals ({accounts.length} {accounts.length === 1 ? 'source' : 'sources'})
        </h3>
        {isOwn && (
          <button
            onClick={() => refreshMutation.mutate()}
            disabled={refreshMutation.isPending}
            className="text-[10px] text-primary-light hover:text-primary transition-colors cursor-pointer disabled:opacity-50"
          >
            {refreshMutation.isPending ? 'Refreshing...' : 'Refresh'}
          </button>
        )}
      </div>
      <div className="space-y-2">
        {accounts.map((account) => {
          const label = PROVIDER_LABELS[account.provider] || account.provider
          const color = PROVIDER_COLORS[account.provider] || 'text-text-muted'
          const metrics = getKeyMetrics(account)
          const synced = account.last_synced_at
            ? timeAgoShort(account.last_synced_at)
            : null

          return (
            <div
              key={account.id}
              className="flex items-center gap-2 text-xs"
            >
              <span className={`font-mono font-medium w-10 shrink-0 ${color}`}>
                [{label}]
              </span>
              <span className="truncate flex-1 text-text">
                {account.provider_username}
              </span>
              {metrics && (
                <span className="text-text-muted whitespace-nowrap shrink-0">
                  {metrics}
                </span>
              )}
              {synced && (
                <span className="text-text-muted/50 text-[10px] whitespace-nowrap shrink-0">
                  {synced}
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
