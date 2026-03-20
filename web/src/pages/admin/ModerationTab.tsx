import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { useToast } from '../../components/Toasts'
import { timeAgo } from '../../lib/formatters'
import { FLAG_STATUS_FILTERS, RESOLUTION_OPTIONS } from './types'
import type { ModerationFlag } from './types'

export default function ModerationTab() {
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [flagStatusFilter, setFlagStatusFilter] = useState<string>('pending')
  const [resolvingFlagId, setResolvingFlagId] = useState<string | null>(null)
  const [resolutionNote, setResolutionNote] = useState('')

  const { data: flags } = useQuery<{ flags: ModerationFlag[]; total: number }>({
    queryKey: ['admin-flags', flagStatusFilter],
    queryFn: async () => {
      const { data } = await api.get('/moderation/flags', { params: { status: flagStatusFilter, limit: 50 } })
      return data
    },
    staleTime: 2 * 60_000,
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

  return (
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
  )
}
