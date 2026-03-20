import { useQuery, useMutation } from '@tanstack/react-query'
import api from '../../lib/api'
import { useToast } from '../../components/Toasts'
import { InlineSkeleton } from '../../components/Skeleton'
import { StatCard } from './StatCard'

export default function InfraTab() {
  const { addToast } = useToast()

  const { data: emailStats } = useQuery<{
    unverified_count: number
    registered_last_24h: number
    verified_last_24h: number
  }>({
    queryKey: ['admin-email-stats'],
    queryFn: async () => (await api.get('/admin/email-stats')).data,
    staleTime: 2 * 60_000,
  })

  const { data: rateLimits } = useQuery<{
    total_tracked_keys: number
    active_keys: { key: string; requests_last_60s: number; oldest_request_age_s: number }[]
  }>({
    queryKey: ['admin-rate-limits'],
    queryFn: async () => (await api.get('/admin/rate-limits')).data,
    staleTime: 30_000,
  })

  const cleanupTokenMutation = useMutation({
    mutationFn: async () => { await api.post('/admin/cleanup/token-blacklist') },
    onSuccess: (data: unknown) => {
      const d = data as { cleaned: number } | undefined
      addToast(`Cleaned ${d?.cleaned ?? 0} expired tokens`, 'success')
    },
    onError: () => { addToast('Failed to clean token blacklist', 'error') },
  })

  const expireProvMutation = useMutation({
    mutationFn: async () => (await api.post('/admin/jobs/expire-provisional')).data,
    onSuccess: (data: unknown) => {
      const d = data as { expired_count: number } | undefined
      addToast(`Expired ${d?.expired_count ?? 0} provisional agents`, 'success')
    },
    onError: () => { addToast('Failed to run expiry job', 'error') },
  })

  return (
    <div className="space-y-6">
      {/* Email verification stats */}
      <div>
        <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">Email Verification</h2>
        {emailStats ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <StatCard label="Unverified" value={emailStats.unverified_count} />
            <StatCard label="Registered (24h)" value={emailStats.registered_last_24h} />
            <StatCard label="Verified (24h)" value={emailStats.verified_last_24h} />
          </div>
        ) : (
          <div className="py-6"><InlineSkeleton /></div>
        )}
      </div>

      {/* Rate limits */}
      <div>
        <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">Rate Limiting</h2>
        {rateLimits ? (
          <div className="bg-surface border border-border rounded-lg p-4">
            <div className="text-sm mb-2">
              <span className="font-medium">{rateLimits.total_tracked_keys}</span>{' '}
              <span className="text-text-muted">active rate limit keys in Redis</span>
            </div>
            {rateLimits.active_keys.length > 0 && (
              <div className="mt-2 space-y-1">
                {rateLimits.active_keys.map((entry) => (
                  <div key={entry.key} className="flex items-center justify-between text-xs">
                    <span className="font-mono text-text-muted/80 truncate mr-3">{entry.key}</span>
                    <span className="text-text-muted shrink-0">{entry.requests_last_60s} req/min</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="py-6"><InlineSkeleton /></div>
        )}
      </div>

      {/* Admin actions */}
      <div>
        <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">Maintenance Actions</h2>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => cleanupTokenMutation.mutate()}
            disabled={cleanupTokenMutation.isPending}
            className="text-xs bg-surface border border-border hover:border-primary/50 px-4 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50"
          >
            {cleanupTokenMutation.isPending ? 'Cleaning...' : 'Cleanup Expired Tokens'}
          </button>
          <button
            onClick={() => expireProvMutation.mutate()}
            disabled={expireProvMutation.isPending}
            className="text-xs bg-surface border border-border hover:border-primary/50 px-4 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50"
          >
            {expireProvMutation.isPending ? 'Running...' : 'Expire Provisional Agents'}
          </button>
        </div>
      </div>
    </div>
  )
}
