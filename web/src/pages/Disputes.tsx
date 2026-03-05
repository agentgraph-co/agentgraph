import { useState, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import { useToast } from '../components/Toasts'
import { formatDate, timeAgo, formatPrice } from '../lib/formatters'
import { TableRowSkeleton } from '../components/Skeleton'

interface Dispute {
  id: string
  transaction_id: string
  opened_by: string
  reason: string
  status: string
  resolution: string | null
  resolution_amount_cents: number | null
  resolved_by: string | null
  admin_note: string | null
  deadline: string
  created_at: string
  resolved_at: string | null
}

interface DisputeListResponse {
  disputes: Dispute[]
  total: number
}

const PAGE_SIZE = 20

const STATUS_STYLES: Record<string, string> = {
  open: 'bg-warning/20 text-warning',
  negotiating: 'bg-accent/20 text-accent',
  escalated: 'bg-danger/20 text-danger',
  resolved: 'bg-success/20 text-success',
  closed: 'bg-muted/20 text-muted-foreground',
}

const STATUS_LABELS: Record<string, string> = {
  open: 'Open',
  negotiating: 'Negotiating',
  escalated: 'Escalated',
  resolved: 'Resolved',
  closed: 'Closed',
}

const RESOLUTION_LABELS: Record<string, string> = {
  release_funds: 'Funds Released',
  cancel_auth: 'Refunded',
  partial_refund: 'Partial Refund',
}

export default function Disputes() {
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [searchParams, setSearchParams] = useSearchParams()
  const statusFilter = searchParams.get('status') || 'all'
  const [selectedDispute, setSelectedDispute] = useState<Dispute | null>(null)
  const [escalateId, setEscalateId] = useState<string | null>(null)
  const [messageText, setMessageText] = useState('')

  useEffect(() => { document.title = 'Disputes - AgentGraph' }, [])

  const {
    data,
    isLoading,
    isError,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery<DisputeListResponse>({
    queryKey: ['disputes', statusFilter],
    queryFn: async ({ pageParam }) => {
      const params: Record<string, unknown> = {
        limit: PAGE_SIZE,
        offset: pageParam,
      }
      if (statusFilter !== 'all') params.status = statusFilter
      const { data } = await api.get('/disputes', { params })
      return data
    },
    initialPageParam: 0,
    getNextPageParam: (_lastPage, allPages) => {
      const loaded = allPages.reduce((acc, page) => acc + page.disputes.length, 0)
      const total = allPages[0]?.total || 0
      if (loaded >= total) return undefined
      return loaded
    },
    staleTime: 60_000,
  })

  const escalateMutation = useMutation({
    mutationFn: async (disputeId: string) => {
      await api.post(`/disputes/${disputeId}/escalate`)
    },
    onSuccess: () => {
      addToast('Dispute escalated to admin review', 'success')
      queryClient.invalidateQueries({ queryKey: ['disputes'] })
      setEscalateId(null)
    },
    onError: (err: any) => {
      addToast(err?.response?.data?.detail || 'Failed to escalate', 'error')
    },
  })

  const messageMutation = useMutation({
    mutationFn: async ({ disputeId, message }: { disputeId: string; message: string }) => {
      const { data } = await api.post(`/disputes/${disputeId}/message`, { message })
      return data
    },
    onSuccess: () => {
      addToast('Message sent', 'success')
      setMessageText('')
    },
    onError: (err: any) => {
      addToast(err?.response?.data?.detail || 'Failed to send message', 'error')
    },
  })

  const allDisputes = data?.pages.flatMap(p => p.disputes) ?? []
  const total = data?.pages[0]?.total ?? 0

  const filterButtons = ['all', 'open', 'negotiating', 'escalated', 'resolved', 'closed']

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Disputes</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage disputes on your marketplace transactions
          </p>
        </div>
        {total > 0 && (
          <span className="text-sm text-muted-foreground">{total} total</span>
        )}
      </div>

      {/* Status filter tabs */}
      <div className="flex gap-2 flex-wrap">
        {filterButtons.map(s => (
          <button
            key={s}
            onClick={() => {
              const params = new URLSearchParams(searchParams)
              if (s === 'all') params.delete('status')
              else params.set('status', s)
              setSearchParams(params)
            }}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              statusFilter === s
                ? 'bg-primary text-primary-foreground'
                : 'bg-surface/50 text-muted-foreground hover:bg-surface/80'
            }`}
          >
            {s === 'all' ? 'All' : STATUS_LABELS[s] || s}
          </button>
        ))}
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <TableRowSkeleton key={i} />
          ))}
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="glass-card p-6 text-center text-danger">
          Failed to load disputes. Please try again later.
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !isError && allDisputes.length === 0 && (
        <div className="glass-card p-12 text-center">
          <div className="text-4xl mb-3">⚖️</div>
          <h2 className="text-lg font-semibold mb-2">No disputes found</h2>
          <p className="text-sm text-muted-foreground">
            {statusFilter === 'all'
              ? "You don't have any disputes yet."
              : `No ${statusFilter} disputes found.`}
          </p>
        </div>
      )}

      {/* Disputes list */}
      <div className="space-y-3">
        {allDisputes.map(dispute => (
          <div
            key={dispute.id}
            className="glass-card p-4 hover:bg-surface/40 transition-colors cursor-pointer"
            onClick={() => setSelectedDispute(
              selectedDispute?.id === dispute.id ? null : dispute
            )}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                    STATUS_STYLES[dispute.status] || STATUS_STYLES.closed
                  }`}>
                    {STATUS_LABELS[dispute.status] || dispute.status}
                  </span>
                  {dispute.resolution && (
                    <span className="text-xs text-muted-foreground">
                      {RESOLUTION_LABELS[dispute.resolution] || dispute.resolution}
                      {dispute.resolution_amount_cents != null && (
                        <> ({formatPrice(dispute.resolution_amount_cents)})</>
                      )}
                    </span>
                  )}
                </div>
                <p className="text-sm line-clamp-2">{dispute.reason}</p>
                <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                  <span>Opened {timeAgo(dispute.created_at)}</span>
                  <span>Deadline: {formatDate(dispute.deadline)}</span>
                  {dispute.resolved_at && (
                    <span>Resolved {timeAgo(dispute.resolved_at)}</span>
                  )}
                </div>
              </div>
              <div className="text-xs text-muted-foreground whitespace-nowrap">
                {dispute.id.slice(0, 8)}
              </div>
            </div>

            {/* Expanded detail */}
            {selectedDispute?.id === dispute.id && (
              <div className="mt-4 pt-4 border-t border-white/10 space-y-3" onClick={e => e.stopPropagation()}>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">Transaction:</span>{' '}
                    <Link
                      to="/transactions"
                      className="text-primary hover:underline"
                    >
                      {dispute.transaction_id.slice(0, 8)}...
                    </Link>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Opened by:</span>{' '}
                    <Link
                      to={`/profile/${dispute.opened_by}`}
                      className="text-primary hover:underline"
                    >
                      {dispute.opened_by.slice(0, 8)}...
                    </Link>
                  </div>
                  {dispute.admin_note && (
                    <div className="col-span-2">
                      <span className="text-muted-foreground">Admin note:</span>{' '}
                      {dispute.admin_note}
                    </div>
                  )}
                </div>

                {/* Actions for open/negotiating disputes */}
                {!['resolved', 'closed'].includes(dispute.status) && (
                  <div className="flex gap-2 flex-wrap">
                    {/* Send message */}
                    <div className="flex-1 flex gap-2">
                      <input
                        type="text"
                        value={messageText}
                        onChange={e => setMessageText(e.target.value)}
                        placeholder="Send a message..."
                        className="flex-1 px-3 py-1.5 rounded-lg bg-surface/50 border border-white/10 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                        onKeyDown={e => {
                          if (e.key === 'Enter' && messageText.trim()) {
                            messageMutation.mutate({
                              disputeId: dispute.id,
                              message: messageText.trim(),
                            })
                          }
                        }}
                      />
                      <button
                        onClick={() => {
                          if (messageText.trim()) {
                            messageMutation.mutate({
                              disputeId: dispute.id,
                              message: messageText.trim(),
                            })
                          }
                        }}
                        disabled={!messageText.trim() || messageMutation.isPending}
                        className="px-3 py-1.5 rounded-lg bg-primary/20 text-primary text-sm hover:bg-primary/30 disabled:opacity-50"
                      >
                        Send
                      </button>
                    </div>

                    {/* Escalate button */}
                    {dispute.status !== 'escalated' && (
                      <button
                        onClick={() => setEscalateId(dispute.id)}
                        className="px-3 py-1.5 rounded-lg bg-danger/20 text-danger text-sm hover:bg-danger/30"
                      >
                        Escalate
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Load more */}
      {hasNextPage && (
        <div className="flex justify-center">
          <button
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
            className="px-4 py-2 rounded-lg bg-surface/50 text-sm hover:bg-surface/80 disabled:opacity-50"
          >
            {isFetchingNextPage ? 'Loading...' : 'Load More'}
          </button>
        </div>
      )}

      {/* Escalate confirmation */}
      {escalateId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="glass-card p-6 max-w-md w-full mx-4 space-y-4">
            <h3 className="text-lg font-semibold">Escalate Dispute</h3>
            <p className="text-sm text-muted-foreground">
              Are you sure you want to escalate this dispute to admin review?
              This action cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setEscalateId(null)}
                className="px-4 py-2 rounded-lg bg-surface/50 text-sm hover:bg-surface/80"
              >
                Cancel
              </button>
              <button
                onClick={() => escalateMutation.mutate(escalateId)}
                disabled={escalateMutation.isPending}
                className="px-4 py-2 rounded-lg bg-danger text-white text-sm hover:bg-danger/80 disabled:opacity-50"
              >
                {escalateMutation.isPending ? 'Escalating...' : 'Escalate'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
