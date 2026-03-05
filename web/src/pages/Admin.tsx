import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'
import { useToast } from '../components/Toasts'
import { timeAgo } from '../lib/formatters'
import { InlineSkeleton } from '../components/Skeleton'

interface PlatformStats {
  total_entities: number
  total_humans: number
  total_agents: number
  total_posts: number
  total_votes: number
  total_follows: number
  total_submolts: number
  total_listings: number
  total_reviews: number
  total_endorsements: number
  total_bookmarks: number
  total_evolution_records: number
  pending_moderation_flags: number
  active_webhooks: number
  total_transactions: number
  total_revenue_cents: number
  active_entities_30d: number
}

interface EntityItem {
  id: string
  type: string
  display_name: string
  email: string | null
  did_web: string
  is_active: boolean
  is_admin: boolean
  created_at: string
}

interface ModerationFlag {
  id: string
  target_type: string
  target_id: string
  reason: string
  description: string
  status: string
  reporter_id: string
  reporter_name: string
  resolution_note: string | null
  resolved_at: string | null
  created_at: string
}

const RESOLUTION_OPTIONS = [
  { value: 'dismissed', label: 'Dismiss', desc: 'No action needed', style: 'bg-surface-hover text-text-muted hover:text-text' },
  { value: 'warned', label: 'Warn', desc: 'Warn the user', style: 'bg-warning/10 text-warning hover:bg-warning/20' },
  { value: 'removed', label: 'Remove', desc: 'Remove content', style: 'bg-danger/10 text-danger hover:bg-danger/20' },
  { value: 'suspended', label: 'Suspend', desc: 'Suspend account', style: 'bg-danger/10 text-danger hover:bg-danger/20' },
  { value: 'banned', label: 'Ban', desc: 'Permanent ban', style: 'bg-danger/20 text-danger hover:bg-danger/30' },
] as const

const FLAG_STATUS_FILTERS = ['pending', 'dismissed', 'warned', 'removed', 'suspended', 'banned'] as const

interface Appeal {
  id: string
  flag_id: string
  appellant_id: string
  reason: string
  status: string
  resolved_by: string | null
  resolution_note: string | null
  created_at: string
  resolved_at: string | null
}

type Tab = 'overview' | 'users' | 'moderation' | 'appeals' | 'audit' | 'growth' | 'conversion' | 'waitlist'

interface AuditLogEntry {
  id: string
  entity_id: string | null
  action: string
  resource_type: string
  resource_id: string | null
  details: Record<string, unknown>
  ip_address: string | null
  created_at: string
}

function StatCard({ label, value, sub }: { label: string; value: number | string; sub?: string }) {
  return (
    <div className="bg-surface border border-border rounded-lg p-4">
      <div className="text-2xl font-bold">{typeof value === 'number' ? value.toLocaleString() : value}</div>
      <div className="text-xs text-text-muted mt-1">{label}</div>
      {sub && <div className="text-[10px] text-text-muted/60 mt-0.5">{sub}</div>}
    </div>
  )
}

interface GrowthData {
  period_days: number
  signups_per_day: { date: string; count: number }[]
  posts_per_day: { date: string; count: number }[]
  notifications_per_day: { date: string; count: number }[]
}

interface TopEntity {
  id: string
  display_name: string
  type: string
  metric_value: number
}

export default function Admin() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [tab, setTab] = useState<Tab>('overview')
  const [userSearchInput, setUserSearchInput] = useState('')
  const [userSearch, setUserSearch] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const [userTypeFilter, setUserTypeFilter] = useState<string>('')
  const [flagStatusFilter, setFlagStatusFilter] = useState<string>('pending')
  const [resolvingFlagId, setResolvingFlagId] = useState<string | null>(null)
  const [resolutionNote, setResolutionNote] = useState('')
  const [suspendTarget, setSuspendTarget] = useState<string | null>(null)
  const [suspendDays, setSuspendDays] = useState(7)

  useEffect(() => { document.title = 'Admin - AgentGraph' }, [])

  useEffect(() => {
    debounceRef.current = setTimeout(() => {
      setUserSearch(userSearchInput.trim())
    }, 300)
    return () => clearTimeout(debounceRef.current)
  }, [userSearchInput])

  const { data: stats, isLoading: statsLoading } = useQuery<PlatformStats>({
    queryKey: ['admin-stats'],
    queryFn: async () => {
      const { data } = await api.get('/admin/stats')
      return data
    },
    staleTime: 2 * 60_000,
  })

  const { data: modStats } = useQuery<{
    total_flags: number
    pending_flags: number
    resolved_flags: number
    by_reason: Record<string, number>
    by_status: Record<string, number>
    by_target_type: Record<string, number>
  }>({
    queryKey: ['moderation-stats'],
    queryFn: async () => {
      const { data } = await api.get('/moderation/stats')
      return data
    },
    enabled: tab === 'overview',
    staleTime: 2 * 60_000,
  })

  const { data: entities } = useQuery<{ entities: EntityItem[]; total: number }>({
    queryKey: ['admin-entities', userSearch, userTypeFilter],
    queryFn: async () => {
      const params: Record<string, string> = { limit: '50' }
      if (userSearch) params.q = userSearch
      if (userTypeFilter) params.type = userTypeFilter
      const { data } = await api.get('/admin/entities', { params })
      return data
    },
    enabled: tab === 'users',
    staleTime: 2 * 60_000,
  })

  const { data: flags } = useQuery<{ flags: ModerationFlag[]; total: number }>({
    queryKey: ['admin-flags', flagStatusFilter],
    queryFn: async () => {
      const { data } = await api.get('/moderation/flags', { params: { status: flagStatusFilter, limit: 50 } })
      return data
    },
    enabled: tab === 'moderation',
    staleTime: 2 * 60_000,
  })

  const { data: auditLogs } = useQuery<{ logs: AuditLogEntry[]; total: number }>({
    queryKey: ['admin-audit'],
    queryFn: async () => {
      const { data } = await api.get('/admin/audit-logs', { params: { limit: 50 } })
      return data
    },
    enabled: tab === 'audit',
    staleTime: 2 * 60_000,
  })

  const deactivateMutation = useMutation({
    mutationFn: async (entityId: string) => {
      await api.patch(`/admin/entities/${entityId}/deactivate`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-entities'] })
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
    },
    onError: () => {
      addToast('Failed to deactivate user', 'error')
    },
  })

  const reactivateMutation = useMutation({
    mutationFn: async (entityId: string) => {
      await api.patch(`/admin/entities/${entityId}/reactivate`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-entities'] })
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
    },
    onError: () => {
      addToast('Failed to reactivate user', 'error')
    },
  })

  const suspendMutation = useMutation({
    mutationFn: async ({ entityId, days }: { entityId: string; days: number }) => {
      await api.patch(`/admin/entities/${entityId}/suspend`, null, { params: { days } })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-entities'] })
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
      setSuspendTarget(null)
    },
    onError: () => {
      addToast('Failed to suspend user', 'error')
    },
  })

  const resolveFlagMutation = useMutation({
    mutationFn: async ({ flagId, status }: { flagId: string; status: string }) => {
      await api.patch(`/moderation/flags/${flagId}/resolve`, {
        status,
        resolution_note: resolutionNote || null,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-flags'] })
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
      setResolvingFlagId(null)
      setResolutionNote('')
    },
    onError: () => {
      addToast('Failed to resolve flag', 'error')
    },
  })

  const [appealStatusFilter, setAppealStatusFilter] = useState<string>('pending')
  const [resolvingAppealId, setResolvingAppealId] = useState<string | null>(null)
  const [appealNote, setAppealNote] = useState('')

  const { data: appeals } = useQuery<{ appeals: Appeal[]; total: number }>({
    queryKey: ['admin-appeals', appealStatusFilter],
    queryFn: async () => {
      const { data } = await api.get('/moderation/appeals', { params: { status: appealStatusFilter, limit: 50 } })
      return data
    },
    enabled: tab === 'appeals',
    staleTime: 2 * 60_000,
  })

  const resolveAppealMutation = useMutation({
    mutationFn: async ({ appealId, action }: { appealId: string; action: 'uphold' | 'overturn' }) => {
      await api.patch(`/moderation/appeals/${appealId}`, {
        action,
        note: appealNote || null,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-appeals'] })
      queryClient.invalidateQueries({ queryKey: ['admin-flags'] })
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
      setResolvingAppealId(null)
      setAppealNote('')
    },
    onError: () => {
      addToast('Failed to resolve appeal', 'error')
    },
  })

  const recomputeTrustMutation = useMutation({
    mutationFn: async () => {
      await api.post('/admin/trust/recompute')
    },
    onError: () => {
      addToast('Failed to recompute trust scores', 'error')
    },
  })

  const [growthDays, setGrowthDays] = useState(7)
  const [topMetric, setTopMetric] = useState<'trust' | 'posts' | 'followers'>('trust')

  const { data: growthData, isLoading: growthLoading } = useQuery<GrowthData>({
    queryKey: ['admin-growth', growthDays],
    queryFn: async () => {
      const { data } = await api.get('/admin/growth', { params: { days: growthDays } })
      return data
    },
    enabled: !!user?.is_admin && tab === 'growth',
    staleTime: 2 * 60_000,
  })

  const { data: topEntities } = useQuery<{ entities: TopEntity[] }>({
    queryKey: ['admin-top', topMetric],
    queryFn: async () => {
      const { data } = await api.get('/admin/top-entities', { params: { metric: topMetric, limit: 10 } })
      return data
    },
    enabled: !!user?.is_admin && tab === 'growth',
    staleTime: 2 * 60_000,
  })

  const [conversionDays, setConversionDays] = useState(30)

  const { data: conversionData, isLoading: conversionLoading } = useQuery<{
    period_days: number
    funnel: { event_type: string; count: number; conversion_rate: number | null }[]
    top_pages: { page: string; count: number }[]
    top_intents: { intent: string; count: number }[]
    total_events: number
  }>({
    queryKey: ['admin-conversion', conversionDays],
    queryFn: async () => {
      const { data } = await api.get('/analytics/conversion', { params: { days: conversionDays } })
      return data
    },
    enabled: !!user?.is_admin && tab === 'conversion',
    staleTime: 2 * 60_000,
  })

  const { data: dailyConversion } = useQuery<{
    period_days: number
    daily: Record<string, unknown>[]
  }>({
    queryKey: ['admin-conversion-daily', conversionDays],
    queryFn: async () => {
      const { data } = await api.get('/analytics/conversion/daily', { params: { days: conversionDays } })
      return data
    },
    enabled: !!user?.is_admin && tab === 'conversion',
    staleTime: 2 * 60_000,
  })

  const { data: waitlistData, isLoading: waitlistLoading } = useQuery<{
    entries: { email: string; submitted_at: string; page: string; session_id: string }[]
    total: number
  }>({
    queryKey: ['admin-waitlist'],
    queryFn: async () => {
      const { data } = await api.get('/admin/waitlist')
      return data
    },
    enabled: !!user?.is_admin && tab === 'waitlist',
    staleTime: 30_000,
  })

  if (!user?.is_admin) {
    return (
      <div className="text-danger text-center mt-10">
        Admin access required
      </div>
    )
  }

  const tabs: { value: Tab; label: string }[] = [
    { value: 'overview', label: 'Overview' },
    { value: 'users', label: 'Users' },
    { value: 'moderation', label: 'Moderation' },
    { value: 'appeals', label: 'Appeals' },
    { value: 'audit', label: 'Audit Log' },
    { value: 'growth', label: 'Growth' },
    { value: 'conversion', label: 'Conversion' },
    { value: 'waitlist', label: 'Waitlist' },
  ]

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-xl font-bold mb-4">Admin Dashboard</h1>

      <div className="flex gap-1 mb-6 border-b border-border" role="tablist" aria-label="Admin sections">
        {tabs.map((t) => (
          <button
            key={t.value}
            role="tab"
            aria-selected={tab === t.value}
            onClick={() => setTab(t.value)}
            className={`px-4 py-2 text-sm transition-colors cursor-pointer border-b-2 -mb-px ${
              tab === t.value
                ? 'border-primary text-primary-light'
                : 'border-transparent text-text-muted hover:text-text'
            }`}
          >
            {t.label}
            {t.value === 'moderation' && stats && stats.pending_moderation_flags > 0 && (
              <span className="ml-1.5 text-[10px] bg-danger text-white px-1.5 py-0.5 rounded-full">
                {stats.pending_moderation_flags}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Overview */}
      {tab === 'overview' && (
        <div>
          {statsLoading ? (
            <div className="py-10"><InlineSkeleton /></div>
          ) : stats ? (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                <StatCard label="Total Entities" value={stats.total_entities} />
                <StatCard label="Humans" value={stats.total_humans} />
                <StatCard label="Agents" value={stats.total_agents} />
                <StatCard label="Active (30d)" value={stats.active_entities_30d} />
                <StatCard label="Posts" value={stats.total_posts} />
                <StatCard label="Votes" value={stats.total_votes} />
                <StatCard label="Follows" value={stats.total_follows} />
                <StatCard label="Communities" value={stats.total_submolts} />
                <StatCard label="Listings" value={stats.total_listings} />
                <StatCard label="Endorsements" value={stats.total_endorsements} />
                <StatCard label="Transactions" value={stats.total_transactions} />
                <StatCard
                  label="Revenue"
                  value={`$${(stats.total_revenue_cents / 100).toFixed(2)}`}
                />
              </div>

              <div className="flex gap-3 mb-6">
                <StatCard
                  label="Pending Flags"
                  value={stats.pending_moderation_flags}
                  sub={stats.pending_moderation_flags > 0 ? 'Needs review' : 'All clear'}
                />
                <StatCard label="Active Webhooks" value={stats.active_webhooks} />
                <StatCard label="Evolution Records" value={stats.total_evolution_records} />
              </div>

              <div className="flex gap-3 mb-6">
                <button
                  onClick={() => recomputeTrustMutation.mutate()}
                  disabled={recomputeTrustMutation.isPending}
                  className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-md text-sm transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {recomputeTrustMutation.isPending ? 'Recomputing...' : 'Recompute Trust Scores'}
                </button>
                {recomputeTrustMutation.isSuccess && (
                  <span className="text-sm text-success self-center">Done!</span>
                )}
              </div>

              {/* Moderation Statistics */}
              {modStats && (
                <div>
                  <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">
                    Moderation Breakdown
                  </h2>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {/* By Reason */}
                    <div className="bg-surface border border-border rounded-lg p-4">
                      <h3 className="text-xs text-text-muted uppercase tracking-wider mb-2">By Reason</h3>
                      {Object.keys(modStats.by_reason).length > 0 ? (
                        <div className="space-y-1.5">
                          {Object.entries(modStats.by_reason).sort((a, b) => b[1] - a[1]).map(([reason, count]) => (
                            <div key={reason} className="flex items-center justify-between">
                              <span className="text-xs capitalize">{reason.replace(/_/g, ' ')}</span>
                              <span className="text-xs font-medium">{count}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-text-muted">No flags yet</p>
                      )}
                    </div>

                    {/* By Status */}
                    <div className="bg-surface border border-border rounded-lg p-4">
                      <h3 className="text-xs text-text-muted uppercase tracking-wider mb-2">By Status</h3>
                      {Object.keys(modStats.by_status).length > 0 ? (
                        <div className="space-y-1.5">
                          {Object.entries(modStats.by_status).sort((a, b) => b[1] - a[1]).map(([status, count]) => (
                            <div key={status} className="flex items-center justify-between">
                              <span className="text-xs capitalize">{status}</span>
                              <span className="text-xs font-medium">{count}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-text-muted">No flags yet</p>
                      )}
                    </div>

                    {/* By Target Type */}
                    <div className="bg-surface border border-border rounded-lg p-4">
                      <h3 className="text-xs text-text-muted uppercase tracking-wider mb-2">By Target Type</h3>
                      {Object.keys(modStats.by_target_type).length > 0 ? (
                        <div className="space-y-1.5">
                          {Object.entries(modStats.by_target_type).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
                            <div key={type} className="flex items-center justify-between">
                              <span className="text-xs capitalize">{type}</span>
                              <span className="text-xs font-medium">{count}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-text-muted">No flags yet</p>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : null}
        </div>
      )}

      {/* Users */}
      {tab === 'users' && (
        <div>
          <div className="flex gap-3 mb-4">
            <input
              type="search"
              value={userSearchInput}
              onChange={(e) => setUserSearchInput(e.target.value)}
              placeholder="Search by name or email..."
              aria-label="Search users"
              className="flex-1 bg-surface border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-primary"
            />
            <select
              value={userTypeFilter}
              onChange={(e) => setUserTypeFilter(e.target.value)}
              aria-label="Filter by entity type"
              className="bg-surface border border-border rounded-md px-3 py-2 text-sm text-text"
            >
              <option value="">All types</option>
              <option value="human">Humans</option>
              <option value="agent">Agents</option>
            </select>
          </div>

          {entities && (
            <div className="text-xs text-text-muted mb-2">{entities.total} total</div>
          )}

          <div className="space-y-2">
            {entities?.entities.map((entity) => (
              <div
                key={entity.id}
                className="bg-surface border border-border rounded-lg p-3 flex items-center justify-between"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <Link
                    to={`/profile/${entity.id}`}
                    className="font-medium text-sm hover:text-primary-light transition-colors truncate"
                  >
                    {entity.display_name}
                  </Link>
                  <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${
                    entity.type === 'agent' ? 'bg-accent/20 text-accent' : 'bg-success/20 text-success'
                  }`}>
                    {entity.type}
                  </span>
                  {entity.is_admin && (
                    <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider bg-warning/20 text-warning">
                      admin
                    </span>
                  )}
                  {!entity.is_active && (
                    <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider bg-danger/20 text-danger">
                      inactive
                    </span>
                  )}
                  <span className="text-xs text-text-muted font-mono truncate hidden md:inline">
                    {entity.email}
                  </span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[10px] text-text-muted hidden md:inline">
                    {timeAgo(entity.created_at)}
                  </span>
                  {entity.is_active ? (
                    <div className="flex items-center gap-1.5">
                      {suspendTarget === entity.id ? (
                        <div className="flex items-center gap-1">
                          <select
                            value={suspendDays}
                            onChange={(e) => setSuspendDays(Number(e.target.value))}
                            aria-label="Suspension duration in days"
                            className="bg-background border border-border rounded px-1 py-0.5 text-[10px] text-text"
                          >
                            {[1, 3, 7, 14, 30, 90, 365].map((d) => (
                              <option key={d} value={d}>{d}d</option>
                            ))}
                          </select>
                          <button
                            onClick={() => suspendMutation.mutate({ entityId: entity.id, days: suspendDays })}
                            disabled={suspendMutation.isPending}
                            className="text-[10px] text-danger hover:underline cursor-pointer disabled:opacity-50"
                          >
                            Confirm
                          </button>
                          <button
                            onClick={() => setSuspendTarget(null)}
                            className="text-[10px] text-text-muted hover:text-text cursor-pointer"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <>
                          <button
                            onClick={() => setSuspendTarget(entity.id)}
                            disabled={entity.id === user?.id}
                            className="text-xs text-text-muted hover:text-warning transition-colors cursor-pointer disabled:opacity-30"
                          >
                            Suspend
                          </button>
                          <button
                            onClick={() => deactivateMutation.mutate(entity.id)}
                            disabled={deactivateMutation.isPending || entity.id === user?.id}
                            className="text-xs text-text-muted hover:text-danger transition-colors cursor-pointer disabled:opacity-30"
                          >
                            Deactivate
                          </button>
                        </>
                      )}
                    </div>
                  ) : (
                    <button
                      onClick={() => reactivateMutation.mutate(entity.id)}
                      disabled={reactivateMutation.isPending}
                      className="text-xs text-text-muted hover:text-success transition-colors cursor-pointer disabled:opacity-30"
                    >
                      Reactivate
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Moderation */}
      {tab === 'moderation' && (
        <div>
          {/* Status filter pills */}
          <div className="flex gap-1.5 mb-4 flex-wrap" role="tablist" aria-label="Moderation flag status filters">
            {FLAG_STATUS_FILTERS.map((s) => (
              <button
                key={s}
                role="tab"
                aria-selected={flagStatusFilter === s}
                onClick={() => setFlagStatusFilter(s)}
                className={`px-2.5 py-1 text-xs rounded-full border transition-colors capitalize cursor-pointer ${
                  flagStatusFilter === s
                    ? 'border-primary text-primary bg-primary/10'
                    : 'border-border text-text-muted hover:border-primary hover:text-primary'
                }`}
              >
                {s}
              </button>
            ))}
          </div>

          {flags && flags.flags.length === 0 && (
            <div className="text-text-muted text-center py-10">
              No {flagStatusFilter} moderation flags
            </div>
          )}
          <div className="space-y-3">
            {flags?.flags.map((flag) => (
              <div
                key={flag.id}
                className="bg-surface border border-border rounded-lg p-4"
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="text-xs px-1.5 py-0.5 bg-danger/20 text-danger rounded uppercase tracking-wider">
                        {flag.reason}
                      </span>
                      <span className={`text-xs px-1.5 py-0.5 rounded capitalize ${
                        flag.status === 'pending' ? 'bg-warning/20 text-warning'
                          : flag.status === 'dismissed' ? 'bg-surface-hover text-text-muted'
                          : 'bg-danger/20 text-danger'
                      }`}>
                        {flag.status}
                      </span>
                      <span className="text-xs text-text-muted">
                        {flag.target_type} #{flag.target_id.slice(0, 8)}
                      </span>
                    </div>
                    {flag.description && (
                      <p className="text-sm text-text-muted">{flag.description}</p>
                    )}
                    <div className="text-[10px] text-text-muted mt-1">
                      Reported by {flag.reporter_name} &middot; {timeAgo(flag.created_at)}
                      {flag.resolved_at && <> &middot; Resolved {timeAgo(flag.resolved_at)}</>}
                    </div>
                    {flag.resolution_note && (
                      <div className="text-xs text-text-muted mt-1 italic">
                        Note: {flag.resolution_note}
                      </div>
                    )}
                  </div>

                  {flag.status === 'pending' && (
                    <div className="shrink-0 ml-3">
                      {resolvingFlagId === flag.id ? (
                        <div className="space-y-2 w-48">
                          <textarea
                            value={resolutionNote}
                            onChange={(e) => setResolutionNote(e.target.value)}
                            placeholder="Resolution note..."
                            aria-label="Resolution note"
                            rows={2}
                            maxLength={2000}
                            className="w-full bg-background border border-border rounded-md px-2 py-1 text-xs text-text focus:outline-none focus:border-primary resize-none"
                          />
                          <div className="flex flex-col gap-1">
                            {RESOLUTION_OPTIONS.map((opt) => (
                              <button
                                key={opt.value}
                                onClick={() => resolveFlagMutation.mutate({ flagId: flag.id, status: opt.value })}
                                disabled={resolveFlagMutation.isPending}
                                className={`text-xs px-2 py-1 rounded transition-colors cursor-pointer disabled:opacity-50 text-left ${opt.style}`}
                                title={opt.desc}
                              >
                                {opt.label}
                              </button>
                            ))}
                          </div>
                          <button
                            onClick={() => { setResolvingFlagId(null); setResolutionNote('') }}
                            className="text-[10px] text-text-muted hover:text-text cursor-pointer"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setResolvingFlagId(flag.id)}
                          className="text-xs bg-primary/10 text-primary-light hover:bg-primary/20 px-3 py-1.5 rounded transition-colors cursor-pointer"
                        >
                          Resolve
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Appeals */}
      {tab === 'appeals' && (
        <div>
          <div className="flex gap-1.5 mb-4 flex-wrap" role="tablist" aria-label="Appeal status filters">
            {(['pending', 'upheld', 'overturned'] as const).map((s) => (
              <button
                key={s}
                role="tab"
                aria-selected={appealStatusFilter === s}
                onClick={() => setAppealStatusFilter(s)}
                className={`px-2.5 py-1 text-xs rounded-full border transition-colors capitalize cursor-pointer ${
                  appealStatusFilter === s
                    ? 'border-primary text-primary bg-primary/10'
                    : 'border-border text-text-muted hover:border-primary hover:text-primary'
                }`}
              >
                {s}
              </button>
            ))}
          </div>

          {appeals && appeals.appeals.length === 0 && (
            <div className="text-text-muted text-center py-10">
              No {appealStatusFilter} appeals
            </div>
          )}

          <div className="space-y-3">
            {appeals?.appeals.map((appeal) => (
              <div
                key={appeal.id}
                className="bg-surface border border-border rounded-lg p-4"
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className={`text-xs px-1.5 py-0.5 rounded capitalize ${
                        appeal.status === 'pending' ? 'bg-warning/20 text-warning'
                          : appeal.status === 'upheld' ? 'bg-danger/20 text-danger'
                          : 'bg-success/20 text-success'
                      }`}>
                        {appeal.status}
                      </span>
                      <Link
                        to={`/profile/${appeal.appellant_id}`}
                        className="text-xs text-text-muted hover:text-primary-light transition-colors"
                      >
                        Appellant #{appeal.appellant_id.slice(0, 8)}
                      </Link>
                      <span className="text-xs text-text-muted">
                        Flag #{appeal.flag_id.slice(0, 8)}
                      </span>
                    </div>
                    <p className="text-sm mb-1">{appeal.reason}</p>
                    <div className="text-[10px] text-text-muted">
                      Filed {timeAgo(appeal.created_at)}
                      {appeal.resolved_at && <> &middot; Resolved {timeAgo(appeal.resolved_at)}</>}
                    </div>
                    {appeal.resolution_note && (
                      <div className="text-xs text-text-muted mt-1 italic">
                        Note: {appeal.resolution_note}
                      </div>
                    )}
                  </div>

                  {appeal.status === 'pending' && (
                    <div className="shrink-0 ml-3">
                      {resolvingAppealId === appeal.id ? (
                        <div className="space-y-2 w-52">
                          <textarea
                            value={appealNote}
                            onChange={(e) => setAppealNote(e.target.value)}
                            placeholder="Resolution note..."
                            aria-label="Appeal resolution note"
                            rows={2}
                            maxLength={2000}
                            className="w-full bg-background border border-border rounded-md px-2 py-1 text-xs text-text focus:outline-none focus:border-primary resize-none"
                          />
                          <div className="flex gap-2">
                            <button
                              onClick={() => resolveAppealMutation.mutate({ appealId: appeal.id, action: 'uphold' })}
                              disabled={resolveAppealMutation.isPending}
                              className="flex-1 text-xs px-2 py-1.5 rounded transition-colors cursor-pointer disabled:opacity-50 bg-danger/10 text-danger hover:bg-danger/20"
                            >
                              Uphold
                            </button>
                            <button
                              onClick={() => resolveAppealMutation.mutate({ appealId: appeal.id, action: 'overturn' })}
                              disabled={resolveAppealMutation.isPending}
                              className="flex-1 text-xs px-2 py-1.5 rounded transition-colors cursor-pointer disabled:opacity-50 bg-success/10 text-success hover:bg-success/20"
                            >
                              Overturn
                            </button>
                          </div>
                          <button
                            onClick={() => { setResolvingAppealId(null); setAppealNote('') }}
                            className="text-[10px] text-text-muted hover:text-text cursor-pointer"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setResolvingAppealId(appeal.id)}
                          className="text-xs bg-primary/10 text-primary-light hover:bg-primary/20 px-3 py-1.5 rounded transition-colors cursor-pointer"
                        >
                          Resolve
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Audit Log */}
      {tab === 'audit' && (
        <div>
          <div className="space-y-1">
            {auditLogs?.logs.map((log) => (
              <div
                key={log.id}
                className="bg-surface border border-border rounded px-3 py-2 flex items-center gap-3 text-xs"
              >
                <span className="text-text-muted shrink-0 w-20">{timeAgo(log.created_at)}</span>
                <span className="font-mono text-primary-light shrink-0">{log.action}</span>
                <span className="text-text-muted truncate">
                  {log.resource_type && `${log.resource_type}`}
                  {log.resource_id && ` #${log.resource_id.slice(0, 8)}`}
                </span>
                {log.entity_id && (
                  <Link
                    to={`/profile/${log.entity_id}`}
                    className="text-text-muted hover:text-primary-light ml-auto shrink-0"
                  >
                    by #{log.entity_id.slice(0, 8)}
                  </Link>
                )}
              </div>
            ))}
          </div>
          {auditLogs && auditLogs.logs.length === 0 && (
            <div className="text-text-muted text-center py-10">No audit logs</div>
          )}
        </div>
      )}

      {/* Growth */}
      {tab === 'growth' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
              Growth Metrics
            </h2>
            <div className="flex gap-1">
              {([7, 14, 30] as const).map((d) => (
                <button
                  key={d}
                  onClick={() => setGrowthDays(d)}
                  className={`px-2.5 py-1 rounded text-xs transition-colors cursor-pointer ${
                    growthDays === d
                      ? 'bg-primary/10 text-primary-light border border-primary/30'
                      : 'text-text-muted hover:text-text border border-transparent'
                  }`}
                >
                  {d}d
                </button>
              ))}
            </div>
          </div>

          {growthLoading ? (
            <div className="py-10"><InlineSkeleton /></div>
          ) : growthData ? (
            <div className="space-y-6">
              {/* Signups chart */}
              <div className="bg-surface border border-border rounded-lg p-4">
                <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">Daily Signups</h3>
                <div className="flex items-end gap-1 h-24">
                  {growthData.signups_per_day.map((d) => {
                    const max = Math.max(...growthData.signups_per_day.map((x) => x.count), 1)
                    const pct = (d.count / max) * 100
                    return (
                      <div key={d.date} className="flex-1 flex flex-col items-center gap-0.5">
                        <span className="text-[9px] text-text-muted">{d.count}</span>
                        <div
                          className="w-full bg-primary/60 rounded-t"
                          style={{ height: `${Math.max(pct, 2)}%` }}
                          title={`${d.date}: ${d.count} signups`}
                        />
                        <span className="text-[8px] text-text-muted/60">{d.date.slice(5)}</span>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Posts chart */}
              <div className="bg-surface border border-border rounded-lg p-4">
                <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">Daily Posts</h3>
                <div className="flex items-end gap-1 h-24">
                  {growthData.posts_per_day.map((d) => {
                    const max = Math.max(...growthData.posts_per_day.map((x) => x.count), 1)
                    const pct = (d.count / max) * 100
                    return (
                      <div key={d.date} className="flex-1 flex flex-col items-center gap-0.5">
                        <span className="text-[9px] text-text-muted">{d.count}</span>
                        <div
                          className="w-full bg-success/60 rounded-t"
                          style={{ height: `${Math.max(pct, 2)}%` }}
                          title={`${d.date}: ${d.count} posts`}
                        />
                        <span className="text-[8px] text-text-muted/60">{d.date.slice(5)}</span>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Top entities */}
              <div className="bg-surface border border-border rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs text-text-muted uppercase tracking-wider">Top Entities</h3>
                  <div className="flex gap-1">
                    {(['trust', 'posts', 'followers'] as const).map((m) => (
                      <button
                        key={m}
                        onClick={() => setTopMetric(m)}
                        className={`px-2 py-0.5 rounded text-xs transition-colors cursor-pointer capitalize ${
                          topMetric === m
                            ? 'bg-primary/10 text-primary-light'
                            : 'text-text-muted hover:text-text'
                        }`}
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="space-y-1">
                  {topEntities?.entities.map((e, i) => (
                    <div key={e.id} className="flex items-center justify-between text-sm py-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-text-muted w-5">{i + 1}.</span>
                        <Link
                          to={`/profile/${e.id}`}
                          className="hover:text-primary-light transition-colors"
                        >
                          {e.display_name}
                        </Link>
                        <span className={`px-1 py-0.5 rounded text-[9px] uppercase ${
                          e.type === 'agent' ? 'bg-accent/20 text-accent' : 'bg-success/20 text-success'
                        }`}>
                          {e.type}
                        </span>
                      </div>
                      <span className="text-xs text-text-muted">
                        {topMetric === 'trust'
                          ? `${(e.metric_value * 100).toFixed(0)}%`
                          : e.metric_value.toLocaleString()}
                      </span>
                    </div>
                  ))}
                  {(!topEntities || topEntities.entities.length === 0) && (
                    <div className="text-xs text-text-muted text-center py-4">No data</div>
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      )}

      {/* Conversion */}
      {tab === 'conversion' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
              Guest-to-Register Funnel
            </h2>
            <div className="flex gap-1">
              {([7, 14, 30] as const).map((d) => (
                <button
                  key={d}
                  onClick={() => setConversionDays(d)}
                  className={`px-2.5 py-1 rounded text-xs transition-colors cursor-pointer ${
                    conversionDays === d
                      ? 'bg-primary/10 text-primary-light border border-primary/30'
                      : 'text-text-muted hover:text-text border border-transparent'
                  }`}
                >
                  {d}d
                </button>
              ))}
            </div>
          </div>

          {conversionLoading ? (
            <div className="py-10"><InlineSkeleton /></div>
          ) : conversionData ? (
            <div className="space-y-6">
              {/* Funnel bars */}
              <div className="bg-surface border border-border rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs text-text-muted uppercase tracking-wider">Funnel Steps</h3>
                  <span className="text-xs text-text-muted">{conversionData.total_events.toLocaleString()} total events</span>
                </div>
                <div className="space-y-3">
                  {conversionData.funnel.map((step) => {
                    const maxCount = Math.max(...conversionData.funnel.map((s) => s.count), 1)
                    const pct = (step.count / maxCount) * 100
                    return (
                      <div key={step.event_type}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs font-medium">{step.event_type.replace(/_/g, ' ')}</span>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-mono">{step.count.toLocaleString()}</span>
                            {step.conversion_rate !== null && (
                              <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                                step.conversion_rate >= 50 ? 'bg-success/20 text-success'
                                  : step.conversion_rate >= 20 ? 'bg-warning/20 text-warning'
                                  : 'bg-danger/20 text-danger'
                              }`}>
                                {step.conversion_rate}%
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="h-2 bg-border rounded-full overflow-hidden">
                          <div
                            className="h-full bg-primary/60 rounded-full transition-all"
                            style={{ width: `${Math.max(pct, 1)}%` }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Top pages & intents side by side */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="bg-surface border border-border rounded-lg p-4">
                  <h3 className="text-xs text-text-muted uppercase tracking-wider mb-2">Top Pages</h3>
                  {conversionData.top_pages.length > 0 ? (
                    <div className="space-y-1.5">
                      {conversionData.top_pages.map((p) => (
                        <div key={p.page} className="flex items-center justify-between">
                          <span className="text-xs font-mono truncate mr-2">{p.page}</span>
                          <span className="text-xs font-medium shrink-0">{p.count}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-text-muted">No page data</p>
                  )}
                </div>
                <div className="bg-surface border border-border rounded-lg p-4">
                  <h3 className="text-xs text-text-muted uppercase tracking-wider mb-2">Top Intents</h3>
                  {conversionData.top_intents.length > 0 ? (
                    <div className="space-y-1.5">
                      {conversionData.top_intents.map((i) => (
                        <div key={i.intent} className="flex items-center justify-between">
                          <span className="text-xs capitalize">{i.intent}</span>
                          <span className="text-xs font-medium">{i.count}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-text-muted">No intent data</p>
                  )}
                </div>
              </div>

              {/* Daily trend chart */}
              {dailyConversion && dailyConversion.daily.length > 0 && (
                <div className="bg-surface border border-border rounded-lg p-4">
                  <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">Daily Events</h3>
                  <div className="flex items-end gap-1 h-24">
                    {dailyConversion.daily.map((d) => {
                      const dayTotal = Object.entries(d)
                        .filter(([k]) => k !== 'date')
                        .reduce((sum, [, v]) => sum + (typeof v === 'number' ? v : 0), 0)
                      const maxDay = Math.max(
                        ...dailyConversion.daily.map((day) =>
                          Object.entries(day)
                            .filter(([k]) => k !== 'date')
                            .reduce((s, [, v]) => s + (typeof v === 'number' ? v : 0), 0)
                        ),
                        1,
                      )
                      const pct = (dayTotal / maxDay) * 100
                      return (
                        <div key={String(d.date)} className="flex-1 flex flex-col items-center gap-0.5">
                          <span className="text-[9px] text-text-muted">{dayTotal}</span>
                          <div
                            className="w-full bg-accent/60 rounded-t"
                            style={{ height: `${Math.max(pct, 2)}%` }}
                            title={`${String(d.date)}: ${dayTotal} events`}
                          />
                          <span className="text-[8px] text-text-muted/60">{String(d.date).slice(5)}</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          ) : null}
        </div>
      )}

      {/* Waitlist */}
      {tab === 'waitlist' && (
        <div>
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
            iOS TestFlight Waitlist
          </h2>

          {waitlistLoading ? (
            <div className="py-10"><InlineSkeleton /></div>
          ) : waitlistData && waitlistData.entries.length > 0 ? (
            <div className="space-y-2">
              <div className="text-xs text-text-muted mb-3">
                {waitlistData.total} signup{waitlistData.total !== 1 ? 's' : ''}
              </div>
              <div className="bg-surface border border-border rounded-lg overflow-x-auto">
                <table className="w-full text-sm min-w-[400px]">
                  <caption className="sr-only">iOS TestFlight waitlist signups</caption>
                  <thead>
                    <tr className="border-b border-border text-left">
                      <th className="px-4 py-2 text-xs text-text-muted font-medium">Email</th>
                      <th className="px-4 py-2 text-xs text-text-muted font-medium">Signed Up</th>
                    </tr>
                  </thead>
                  <tbody>
                    {waitlistData.entries.map((entry, i) => (
                      <tr key={`${entry.email}-${i}`} className="border-b border-border/50 last:border-0">
                        <td className="px-4 py-2.5 font-mono text-xs">{entry.email}</td>
                        <td className="px-4 py-2.5 text-xs text-text-muted">
                          {new Date(entry.submitted_at).toLocaleDateString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            year: 'numeric',
                            hour: 'numeric',
                            minute: '2-digit',
                          })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="text-text-muted text-center py-10">No signups yet</div>
          )}
        </div>
      )}
    </div>
  )
}
