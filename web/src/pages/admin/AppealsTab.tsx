import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { useToast } from '../../components/Toasts'
import { timeAgo } from '../../lib/formatters'
import type { Appeal } from './types'

export default function AppealsTab() {
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [appealStatusFilter, setAppealStatusFilter] = useState<string>('pending')
  const [resolvingAppealId, setResolvingAppealId] = useState<string | null>(null)
  const [appealNote, setAppealNote] = useState('')

  const { data: appeals } = useQuery<{ appeals: Appeal[]; total: number }>({
    queryKey: ['admin-appeals', appealStatusFilter],
    queryFn: async () => {
      const { data } = await api.get('/moderation/appeals', { params: { status: appealStatusFilter, limit: 50 } })
      return data
    },
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

  return (
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
  )
}
