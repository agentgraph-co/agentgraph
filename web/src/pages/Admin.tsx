import { useState } from 'react'
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
  created_at: string
}

type Tab = 'overview' | 'users' | 'moderation' | 'audit' | 'growth'

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

  const { data: stats, isLoading: statsLoading } = useQuery<PlatformStats>({
    queryKey: ['admin-stats'],
    queryFn: async () => {
      const { data } = await api.get('/admin/stats')
      return data
    },
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
    queryKey: ['admin-flags'],
    queryFn: async () => {
      const { data } = await api.get('/moderation/flags', { params: { status: 'pending', limit: 50 } })
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

  const resolveFlagMutation = useMutation({
    mutationFn: async ({ flagId, resolution }: { flagId: string; resolution: string }) => {
      await api.patch(`/moderation/flags/${flagId}/resolve`, { resolution, notes: '' })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-flags'] })
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
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

              <div className="flex gap-3">
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
                    <button
                      onClick={() => deactivateMutation.mutate(entity.id)}
                      disabled={deactivateMutation.isPending || entity.id === user?.id}
                      className="text-xs text-text-muted hover:text-danger transition-colors cursor-pointer disabled:opacity-30"
                    >
                      Deactivate
                    </button>
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
          {flags && flags.flags.length === 0 && (
            <div className="text-text-muted text-center py-10">
              No pending moderation flags
            </div>
          )}
          <div className="space-y-3">
            {flags?.flags.map((flag) => (
              <div
                key={flag.id}
                className="bg-surface border border-border rounded-lg p-4"
              >
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs px-1.5 py-0.5 bg-danger/20 text-danger rounded uppercase tracking-wider">
                        {flag.reason}
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
                    </div>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <button
                      onClick={() => resolveFlagMutation.mutate({ flagId: flag.id, resolution: 'action_taken' })}
                      disabled={resolveFlagMutation.isPending}
                      className="text-xs bg-danger/10 text-danger hover:bg-danger/20 px-2 py-1 rounded transition-colors cursor-pointer disabled:opacity-50"
                    >
                      Action
                    </button>
                    <button
                      onClick={() => resolveFlagMutation.mutate({ flagId: flag.id, resolution: 'dismissed' })}
                      disabled={resolveFlagMutation.isPending}
                      className="text-xs bg-surface-hover text-text-muted hover:text-text px-2 py-1 rounded transition-colors cursor-pointer disabled:opacity-50"
                    >
                      Dismiss
                    </button>
                  </div>
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
