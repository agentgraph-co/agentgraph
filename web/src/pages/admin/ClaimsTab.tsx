import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import api from '../../lib/api'
import { useToast } from '../../components/Toasts'
import { timeAgo } from '../../lib/formatters'
import type { ClaimItem } from './types'

export default function ClaimsTab() {
  const { addToast } = useToast()
  const [claimStatusFilter, setClaimStatusFilter] = useState<string>('pending')
  const [claimDecisionNote, setClaimDecisionNote] = useState('')
  const [decidingClaimId, setDecidingClaimId] = useState<string | null>(null)

  const { data: claimsData, refetch: refetchClaims } = useQuery<{ claims: ClaimItem[]; total: number }>({
    queryKey: ['admin-claims', claimStatusFilter],
    queryFn: async () => {
      return (await api.get('/admin/claims', { params: { status_filter: claimStatusFilter } })).data
    },
    staleTime: 2 * 60_000,
  })

  const approveClaimMutation = useMutation({
    mutationFn: async ({ agentId, note }: { agentId: string; note: string }) => {
      return (await api.post(`/admin/claims/${agentId}/approve`, { note })).data
    },
    onSuccess: () => {
      addToast('Claim approved', 'success')
      setDecidingClaimId(null)
      setClaimDecisionNote('')
      refetchClaims()
    },
    onError: () => { addToast('Failed to approve claim', 'error') },
  })

  const rejectClaimMutation = useMutation({
    mutationFn: async ({ agentId, note }: { agentId: string; note: string }) => {
      return (await api.post(`/admin/claims/${agentId}/reject`, { note })).data
    },
    onSuccess: () => {
      addToast('Claim rejected', 'success')
      setDecidingClaimId(null)
      setClaimDecisionNote('')
      refetchClaims()
    },
    onError: () => { addToast('Failed to reject claim', 'error') },
  })

  return (
    <div>
      <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
        Bot Ownership Claims
      </h2>

      <div className="flex gap-3 mb-4">
        <select
          value={claimStatusFilter}
          onChange={e => setClaimStatusFilter(e.target.value)}
          className="text-xs bg-surface border border-border rounded-md px-3 py-1.5"
        >
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
      </div>

      {claimsData && claimsData.claims.length > 0 ? (
        <div className="space-y-2">
          <div className="text-xs text-text-muted mb-3">
            {claimsData.total} claim{claimsData.total !== 1 ? 's' : ''}
          </div>
          <div className="bg-surface border border-border rounded-lg overflow-x-auto">
            <table className="w-full text-sm min-w-[600px]">
              <caption className="sr-only">Bot ownership claims</caption>
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">Bot</th>
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">Claimer</th>
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">Source</th>
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">Reason</th>
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">When</th>
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {claimsData.claims.map(claim => (
                  <tr key={claim.agent_id} className="border-b border-border/50 last:border-0">
                    <td className="px-4 py-2.5">
                      <Link to={`/profile/${claim.agent_id}`} className="text-xs hover:text-primary transition-colors hover:underline">
                        {claim.agent_name}
                      </Link>
                    </td>
                    <td className="px-4 py-2.5">
                      <Link to={`/profile/${claim.claimer_id}`} className="text-xs hover:text-primary transition-colors hover:underline">
                        {claim.claimer_name}
                      </Link>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-text-muted">
                      {claim.source_type ? (
                        claim.source_url ? (
                          <a href={claim.source_url} target="_blank" rel="noopener noreferrer" className="text-primary-light hover:underline">
                            {claim.source_type}
                          </a>
                        ) : claim.source_type
                      ) : '-'}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-text-muted max-w-[200px] truncate" title={claim.reason}>
                      {claim.reason || '-'}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-text-muted">
                      {claim.claimed_at ? timeAgo(claim.claimed_at) : '-'}
                    </td>
                    <td className="px-4 py-2.5">
                      {claimStatusFilter === 'pending' ? (
                        decidingClaimId === claim.agent_id ? (
                          <div className="flex flex-col gap-2">
                            <input
                              type="text"
                              value={claimDecisionNote}
                              onChange={e => setClaimDecisionNote(e.target.value)}
                              placeholder="Note (optional)"
                              className="text-xs bg-background border border-border rounded px-2 py-1 w-40"
                            />
                            <div className="flex gap-1">
                              <button
                                onClick={() => approveClaimMutation.mutate({ agentId: claim.agent_id, note: claimDecisionNote })}
                                disabled={approveClaimMutation.isPending}
                                className="text-[10px] px-2 py-0.5 bg-success/20 text-success rounded hover:bg-success/30 cursor-pointer disabled:opacity-50"
                              >
                                Approve
                              </button>
                              <button
                                onClick={() => rejectClaimMutation.mutate({ agentId: claim.agent_id, note: claimDecisionNote })}
                                disabled={rejectClaimMutation.isPending}
                                className="text-[10px] px-2 py-0.5 bg-danger/20 text-danger rounded hover:bg-danger/30 cursor-pointer disabled:opacity-50"
                              >
                                Reject
                              </button>
                              <button
                                onClick={() => { setDecidingClaimId(null); setClaimDecisionNote('') }}
                                className="text-[10px] px-2 py-0.5 text-text-muted hover:text-text cursor-pointer"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          <button
                            onClick={() => setDecidingClaimId(claim.agent_id)}
                            className="text-[10px] px-2 py-0.5 bg-primary/20 text-primary rounded hover:bg-primary/30 cursor-pointer"
                          >
                            Review
                          </button>
                        )
                      ) : (
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                          claimStatusFilter === 'approved' ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger'
                        }`}>
                          {claimStatusFilter}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="text-text-muted text-center py-10">No {claimStatusFilter} claims</div>
      )}
    </div>
  )
}
