import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { InlineSkeleton } from '../../components/Skeleton'
import { StatCard } from './StatCard'
import type { PlatformStats } from './types'

export default function OverviewTab() {
  const queryClient = useQueryClient()

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
    staleTime: 2 * 60_000,
  })

  const recomputeTrustMutation = useMutation({
    mutationFn: async () => {
      await api.post('/admin/trust/recompute')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
    },
  })

  return (
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
  )
}
