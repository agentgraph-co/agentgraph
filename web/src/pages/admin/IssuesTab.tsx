import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { useToast } from '../../components/Toasts'
import { timeAgo } from '../../lib/formatters'
import type { IssueItem } from './types'

export default function IssuesTab() {
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [issueStatusFilter, setIssueStatusFilter] = useState<string>('')
  const [issueTypeFilter, setIssueTypeFilter] = useState<string>('')
  const [resolvingIssueId, setResolvingIssueId] = useState<string | null>(null)
  const [issueResolutionNote, setIssueResolutionNote] = useState('')

  const { data: issuesData } = useQuery<{ issues: IssueItem[]; total: number }>({
    queryKey: ['admin-issues', issueStatusFilter, issueTypeFilter],
    queryFn: async () => {
      const params: Record<string, string> = { limit: '50' }
      if (issueStatusFilter) params.status = issueStatusFilter
      if (issueTypeFilter) params.issue_type = issueTypeFilter
      return (await api.get('/admin/issues', { params })).data
    },
    staleTime: 2 * 60_000,
  })

  const resolveIssueMutation = useMutation({
    mutationFn: async ({ issueId, status, resolution_note }: { issueId: string; status: string; resolution_note: string }) => {
      return (await api.patch(`/admin/issues/${issueId}/resolve`, { status, resolution_note })).data
    },
    onSuccess: () => {
      addToast('Issue resolved', 'success')
      setResolvingIssueId(null)
      setIssueResolutionNote('')
      queryClient.invalidateQueries({ queryKey: ['admin-issues'] })
    },
    onError: () => { addToast('Failed to resolve issue', 'error') },
  })

  return (
    <div>
      <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
        Bug Reports & Feature Requests
      </h2>

      {/* Filters */}
      <div className="flex gap-3 mb-4">
        <select
          value={issueStatusFilter}
          onChange={e => setIssueStatusFilter(e.target.value)}
          className="text-xs bg-surface border border-border rounded-md px-3 py-1.5"
        >
          <option value="">All Statuses</option>
          <option value="open">Open</option>
          <option value="in_progress">In Progress</option>
          <option value="resolved">Resolved</option>
          <option value="closed">Closed</option>
          <option value="wontfix">Won&apos;t Fix</option>
        </select>
        <select
          value={issueTypeFilter}
          onChange={e => setIssueTypeFilter(e.target.value)}
          className="text-xs bg-surface border border-border rounded-md px-3 py-1.5"
        >
          <option value="">All Types</option>
          <option value="bug">Bug</option>
          <option value="feature">Feature</option>
        </select>
      </div>

      {issuesData && issuesData.issues.length > 0 ? (
        <div className="space-y-2">
          <div className="text-xs text-text-muted mb-3">
            {issuesData.total} issue{issuesData.total !== 1 ? 's' : ''}
          </div>
          <div className="bg-surface border border-border rounded-lg overflow-x-auto">
            <table className="w-full text-sm min-w-[600px]">
              <caption className="sr-only">Issue reports</caption>
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">Title</th>
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">Type</th>
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">Status</th>
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">Reporter</th>
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">Created</th>
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {issuesData.issues.map(issue => (
                  <tr key={issue.id} className="border-b border-border/50 last:border-0">
                    <td className="px-4 py-2.5 text-xs max-w-[200px] truncate" title={issue.title}>
                      <Link to={`/post/${issue.post_id}`} className="hover:text-primary transition-colors hover:underline">
                        {issue.title.slice(0, 80)}{issue.title.length > 80 ? '...' : ''}
                      </Link>
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                        issue.issue_type === 'bug'
                          ? 'bg-danger/10 text-danger'
                          : 'bg-primary/10 text-primary'
                      }`}>
                        {issue.issue_type}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                        issue.status === 'open' ? 'bg-warning/10 text-warning' :
                        issue.status === 'in_progress' ? 'bg-primary/10 text-primary' :
                        issue.status === 'resolved' ? 'bg-success/10 text-success' :
                        'bg-surface-hover text-text-muted'
                      }`}>
                        {issue.status.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-text-muted">
                      {issue.reporter_name || 'Unknown'}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-text-muted">
                      {timeAgo(issue.created_at)}
                    </td>
                    <td className="px-4 py-2.5">
                      {['open', 'in_progress'].includes(issue.status) ? (
                        resolvingIssueId === issue.id ? (
                          <div className="flex flex-col gap-2 min-w-[180px]">
                            <input
                              type="text"
                              placeholder="Resolution note..."
                              value={issueResolutionNote}
                              onChange={e => setIssueResolutionNote(e.target.value)}
                              className="text-xs bg-surface-hover border border-border rounded px-2 py-1"
                            />
                            <div className="flex gap-1">
                              <button
                                onClick={() => resolveIssueMutation.mutate({ issueId: issue.id, status: 'resolved', resolution_note: issueResolutionNote })}
                                disabled={resolveIssueMutation.isPending}
                                className="text-[10px] bg-success/10 text-success hover:bg-success/20 px-2 py-1 rounded cursor-pointer disabled:opacity-50"
                              >
                                Resolve
                              </button>
                              <button
                                onClick={() => resolveIssueMutation.mutate({ issueId: issue.id, status: 'wontfix', resolution_note: issueResolutionNote })}
                                disabled={resolveIssueMutation.isPending}
                                className="text-[10px] bg-surface-hover text-text-muted hover:text-text px-2 py-1 rounded cursor-pointer disabled:opacity-50"
                              >
                                Won&apos;t Fix
                              </button>
                              <button
                                onClick={() => { setResolvingIssueId(null); setIssueResolutionNote('') }}
                                className="text-[10px] text-text-muted hover:text-text px-2 py-1 cursor-pointer"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          <button
                            onClick={() => setResolvingIssueId(issue.id)}
                            className="text-[10px] bg-surface-hover text-text-muted hover:text-text px-2 py-1 rounded cursor-pointer"
                          >
                            Resolve
                          </button>
                        )
                      ) : (
                        <span className="text-[10px] text-text-muted">
                          {issue.resolution_note ? issue.resolution_note.slice(0, 40) : 'Done'}
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
        <div className="text-text-muted text-center py-10">No issues found</div>
      )}
    </div>
  )
}
