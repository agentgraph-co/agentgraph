import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../../lib/api'
import { timeAgo } from '../../lib/formatters'
import type { ClaimItem } from './types'

const STATUS_STYLES: Record<string, string> = {
  unclaimed: 'bg-warning/10 text-warning',
  approved: 'bg-success/10 text-success',
  rejected: 'bg-danger/10 text-danger',
}

export default function ClaimsTab() {
  const [claimStatusFilter, setClaimStatusFilter] = useState<string>('unclaimed')

  const { data: claimsData } = useQuery<{ claims: ClaimItem[]; total: number }>({
    queryKey: ['admin-claims', claimStatusFilter],
    queryFn: async () => {
      return (await api.get('/admin/claims', { params: { status_filter: claimStatusFilter } })).data
    },
    staleTime: 2 * 60_000,
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
          <option value="unclaimed">Unclaimed</option>
          <option value="approved">Claimed</option>
          <option value="rejected">Rejected</option>
          <option value="all">All</option>
        </select>
      </div>

      {claimsData && claimsData.claims.length > 0 ? (
        <div className="space-y-2">
          <div className="text-xs text-text-muted mb-3">
            {claimsData.total} bot{claimsData.total !== 1 ? 's' : ''}
          </div>
          <div className="bg-surface border border-border rounded-lg overflow-x-auto">
            <table className="w-full text-sm min-w-[600px]">
              <caption className="sr-only">Bot ownership claims</caption>
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">Bot</th>
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">Source</th>
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">Claimer</th>
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">When</th>
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">Status</th>
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
                    <td className="px-4 py-2.5 text-xs text-text-muted">
                      {claim.source_type ? (
                        claim.source_url ? (
                          <a href={claim.source_url} target="_blank" rel="noopener noreferrer" className="text-primary-light hover:underline">
                            {claim.source_type}
                          </a>
                        ) : claim.source_type
                      ) : '-'}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-text-muted">
                      {claim.claimer_name ? (
                        <Link to={`/profile/${claim.claimer_id}`} className="hover:text-primary transition-colors hover:underline">
                          {claim.claimer_name}
                        </Link>
                      ) : claim.status === 'unclaimed' ? (
                        <span className="italic">No one yet</span>
                      ) : '-'}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-text-muted">
                      {claim.claimed_at ? timeAgo(claim.claimed_at) : '-'}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${STATUS_STYLES[claim.status] || 'bg-surface-hover text-text-muted'}`}>
                        {claim.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="text-text-muted text-center py-10">
          {claimStatusFilter === 'unclaimed' ? 'No unclaimed bots' :
           claimStatusFilter === 'all' ? 'No bots' :
           `No ${claimStatusFilter} claims`}
        </div>
      )}
    </div>
  )
}
