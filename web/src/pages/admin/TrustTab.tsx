import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { useToast } from '../../components/Toasts'
import { InlineSkeleton } from '../../components/Skeleton'

export default function TrustTab() {
  const queryClient = useQueryClient()
  const { addToast } = useToast()

  const { data: trustStats } = useQuery<{
    distribution: { range: string; count: number }[]
    avg_by_type: { entity_type: string; avg_score: number; count: number }[]
    total_with_scores: number
  }>({
    queryKey: ['admin-trust-stats'],
    queryFn: async () => (await api.get('/admin/trust/stats')).data,
    staleTime: 2 * 60_000,
  })

  const recomputeTrustMutation = useMutation({
    mutationFn: async () => {
      await api.post('/admin/trust/recompute')
    },
  })

  const recomputeAllMutation = useMutation({
    mutationFn: async () => { await api.post('/admin/trust/recompute-all') },
    onSuccess: () => {
      addToast('Full trust recomputation started', 'success')
      queryClient.invalidateQueries({ queryKey: ['admin-trust-stats'] })
    },
    onError: () => { addToast('Failed to start recomputation', 'error') },
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">Trust Distribution</h2>
        <div className="flex gap-2">
          <button
            onClick={() => recomputeTrustMutation.mutate()}
            disabled={recomputeTrustMutation.isPending}
            className="text-xs bg-surface border border-border hover:border-primary/50 px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-50"
          >
            {recomputeTrustMutation.isPending ? 'Running...' : 'Quick Recompute'}
          </button>
          <button
            onClick={() => recomputeAllMutation.mutate()}
            disabled={recomputeAllMutation.isPending}
            className="text-xs bg-primary hover:bg-primary-dark text-white px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-50"
          >
            {recomputeAllMutation.isPending ? 'Running...' : 'Full Recompute (with decay)'}
          </button>
        </div>
      </div>

      {trustStats ? (
        <>
          <div className="text-xs text-text-muted">{trustStats.total_with_scores} entities scored</div>

          {/* Distribution bar chart */}
          <div className="bg-surface border border-border rounded-lg p-4">
            <h3 className="text-xs font-medium mb-3">Score Distribution</h3>
            <div className="space-y-2">
              {trustStats.distribution.map((bucket) => {
                const maxCount = Math.max(...trustStats.distribution.map((b) => b.count), 1)
                const pct = (bucket.count / maxCount) * 100
                return (
                  <div key={bucket.range} className="flex items-center gap-3">
                    <span className="text-xs text-text-muted w-20 shrink-0">{bucket.range}</span>
                    <div className="flex-1 bg-background rounded-full h-4 relative">
                      <div
                        className="h-4 rounded-full bg-primary/60 transition-all"
                        style={{ width: `${Math.max(pct, 2)}%` }}
                      />
                    </div>
                    <span className="text-xs font-mono w-8 text-right">{bucket.count}</span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* By type */}
          <div className="bg-surface border border-border rounded-lg p-4">
            <h3 className="text-xs font-medium mb-3">Average Score by Type</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {trustStats.avg_by_type.map((entry) => (
                <div key={entry.entity_type} className="text-center">
                  <div className="text-xl font-bold">{entry.avg_score.toFixed(2)}</div>
                  <div className="text-xs text-text-muted capitalize">{entry.entity_type}</div>
                  <div className="text-[10px] text-text-muted/60">{entry.count} entities</div>
                </div>
              ))}
            </div>
          </div>
        </>
      ) : (
        <div className="py-10"><InlineSkeleton /></div>
      )}
    </div>
  )
}
