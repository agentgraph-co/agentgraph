import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'

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

type Tab = 'overview' | 'users' | 'moderation' | 'appeals' | 'audit' | 'growth'

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

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
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

export default function Admin() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<Tab>('overview')
  const [userSearch, setUserSearch] = useState('')
  const [userTypeFilter, setUserTypeFilter] = useState<string>('')
  const [flagStatusFilter, setFlagStatusFilter] = useState<string>('pending')
  const [resolvingFlagId, setResolvingFlagId] = useState<string | null>(null)
  const [resolutionNote, setResolutionNote] = useState('')
  const [suspendTarget, setSuspendTarget] = useState<string | null>(null)
  const [suspendDays, setSuspendDays] = useState(7)

  useEffect(() => { document.title = 'Admin - AgentGraph' }, [])

  const { data: stats, isLoading: statsLoading } = useQuery<PlatformStats>({
    queryKey: ['admin-stats'],
    queryFn: async () => {
      const { data } = await api.get('/admin/stats')
      return data
    },
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
  })

  const { data: flags } = useQuery<{ flags: ModerationFlag[]; total: number }>({
    queryKey: ['admin-flags', flagStatusFilter],
    queryFn: async () => {
      const { data } = await api.get('/moderation/flags', { params: { status: flagStatusFilter, limit: 50 } })
      return data
    },
    enabled: tab === 'moderation',
  })

  const { data: auditLogs } = useQuery<{ logs: AuditLogEntry[]; total: number }>({
    queryKey: ['admin-audit'],
    queryFn: async () => {
      const { data } = await api.get('/admin/audit-logs', { params: { limit: 50 } })
      return data
    },
    enabled: tab === 'audit',
  })

  const deactivateMutation = useMutation({
    mutationFn: async (entityId: string) => {
      await api.patch(`/admin/entities/${entityId}/deactivate`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-entities'] })
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
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
  })

  const recomputeTrustMutation = useMutation({
    mutationFn: async () => {
      await api.post('/admin/trust/recompute')
    },
  })

  if (!user?.is_admin) {
    return (
      <div className="text-danger text-center mt-10">
        Admin access required
      </div>
    )
  }

  const [growthDays, setGrowthDays] = useState(7)

  interface GrowthData {
    period_days: number
    signups_per_day: { date: string; count: number }[]
    posts_per_day: { date: string; count: number }[]
    notifications_per_day: { date: string; count: number }[]
  }

  const { data: growthData, isLoading: growthLoading } = useQuery<GrowthData>({
    queryKey: ['admin-growth', growthDays],
    queryFn: async () => {
      const { data } = await api.get('/admin/growth', { params: { days: growthDays } })
      return data
    },
    enabled: tab === 'growth',
  })

  interface TopEntity {
    id: string
    display_name: string
    type: string
    metric_value: number
  }

  const [topMetric, setTopMetric] = useState<'trust' | 'posts' | 'followers'>('trust')

  const { data: topEntities } = useQuery<{ entities: TopEntity[] }>({
    queryKey: ['admin-top', topMetric],
    queryFn: async () => {
      const { data } = await api.get('/admin/top-entities', { params: { metric: topMetric, limit: 10 } })
      return data
    },
    enabled: tab === 'growth',
  })

  const tabs: { value: Tab; label: string }[] = [
    { value: 'overview', label: 'Overview' },
    { value: 'users', label: 'Users' },
    { value: 'moderation', label: 'Moderation' },
    { value: 'appeals', label: 'Appeals' },
    { value: 'audit', label: 'Audit Log' },
    { value: 'growth', label: 'Growth' },
  ]

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-xl font-bold mb-4">Admin Dashboard</h1>

      <div className="flex gap-1 mb-6 border-b border-border">
        {tabs.map((t) => (
          <button
            key={t.value}
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
            <div className="text-text-muted text-center py-10">Loading stats...</div>
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
              value={userSearch}
              onChange={(e) => setUserSearch(e.target.value)}
              placeholder="Search by name or email..."
              className="flex-1 bg-surface border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-primary"
            />
            <select
              value={userTypeFilter}
              onChange={(e) => setUserTypeFilter(e.target.value)}
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
          <div className="flex gap-1.5 mb-4 flex-wrap">
            {FLAG_STATUS_FILTERS.map((s) => (
              <button
                key={s}
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
          <div className="flex gap-1.5 mb-4 flex-wrap">
            {(['pending', 'upheld', 'overturned'] as const).map((s) => (
              <button
                key={s}
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
            <div className="text-text-muted text-center py-10">Loading growth data...</div>
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
    </div>
  )
}
