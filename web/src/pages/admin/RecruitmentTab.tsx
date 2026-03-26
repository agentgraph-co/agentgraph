import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { useToast } from '../../components/Toasts'
import { StatCard } from './StatCard'
import type { RecruitmentProspectItem, RecruitmentStatsData } from './types'

type SubTab = 'overview' | 'outreach'

const STATUSES = ['all', 'discovered', 'contacted', 'visited', 'registered', 'onboarded', 'active', 'skipped', 'declined'] as const
const FUNNEL_STAGES = ['discovered', 'contacted', 'visited', 'registered', 'onboarded'] as const

const STATUS_STYLES: Record<string, string> = {
  discovered: 'bg-blue-500/10 text-blue-400',
  contacted: 'bg-warning/10 text-warning',
  visited: 'bg-purple-500/10 text-purple-400',
  registered: 'bg-cyan-500/10 text-cyan-400',
  onboarded: 'bg-success/10 text-success',
  active: 'bg-success/20 text-success',
  skipped: 'bg-surface-hover text-text-muted',
  declined: 'bg-danger/10 text-danger',
}

const FRAMEWORK_STYLES: Record<string, string> = {
  mcp: 'bg-primary/10 text-primary-light',
  'mcp server': 'bg-primary/10 text-primary-light',
  'mcp_server': 'bg-primary/10 text-primary-light',
  langchain: 'bg-green-500/10 text-green-400',
  crewai: 'bg-orange-500/10 text-orange-400',
  autogen: 'bg-blue-500/10 text-blue-400',
  'ai agent': 'bg-purple-500/10 text-purple-400',
  'ai_agent': 'bg-purple-500/10 text-purple-400',
  'ai tool': 'bg-cyan-500/10 text-cyan-400',
  'ai_tool': 'bg-cyan-500/10 text-cyan-400',
}

function formatDate(ts: string | null): string {
  if (!ts) return '-'
  return new Date(ts).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function FunnelBar({ stats }: { stats: RecruitmentStatsData }) {
  const stages = FUNNEL_STAGES.map((key) => ({
    key,
    label: key.charAt(0).toUpperCase() + key.slice(1),
    count: stats[key],
  }))

  const max = Math.max(1, ...stages.map((s) => s.count))

  return (
    <div className="bg-surface border border-border rounded-lg p-4 mb-6">
      <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-4">Recruitment Funnel</h3>
      <div className="flex items-end gap-2">
        {stages.map((stage, i) => {
          const pct = Math.max(8, (stage.count / max) * 100)
          const prev = i > 0 ? stages[i - 1].count : 0
          const convRate = prev > 0 ? ((stage.count / prev) * 100).toFixed(1) : null
          return (
            <div key={stage.key} className="flex-1 flex flex-col items-center gap-1">
              <span className="text-lg font-bold">{stage.count.toLocaleString()}</span>
              <div
                className="w-full rounded-t-md transition-all"
                style={{
                  height: `${pct}px`,
                  minHeight: '8px',
                  backgroundColor: `hsl(${210 + i * 30}, 70%, 50%)`,
                  opacity: 0.8,
                }}
              />
              <span className="text-[10px] text-text-muted font-medium mt-1">{stage.label}</span>
              {convRate && (
                <span className="text-[9px] text-text-muted/60">{convRate}%</span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ProspectRow({
  prospect,
  expanded,
  onToggle,
  onUpdate,
}: {
  prospect: RecruitmentProspectItem
  expanded: boolean
  onToggle: () => void
  onUpdate: (id: string, data: { status?: string; notes?: string }) => void
}) {
  const [editNotes, setEditNotes] = useState(prospect.notes || '')
  const [editStatus, setEditStatus] = useState(prospect.status)

  const ghUrl = `https://github.com/${prospect.platform_id}`
  const statusStyle = STATUS_STYLES[prospect.status] || 'bg-surface-hover text-text-muted'
  const fwStyle = FRAMEWORK_STYLES[(prospect.framework_detected || '').toLowerCase()] || 'bg-surface-hover text-text-muted'

  return (
    <>
      <tr
        className="border-b border-border/50 last:border-0 hover:bg-surface-hover/50 cursor-pointer transition-colors"
        onClick={onToggle}
      >
        <td className="px-3 py-2.5">
          <a
            href={ghUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary-light hover:underline text-xs font-mono"
            onClick={(e) => e.stopPropagation()}
          >
            {prospect.platform_id}
          </a>
          {prospect.description && (
            <div className="text-[10px] text-text-muted/70 truncate max-w-[300px] mt-0.5">
              {prospect.description}
            </div>
          )}
        </td>
        <td className="px-3 py-2.5 text-xs text-text-muted">{prospect.owner_login}</td>
        <td className="px-3 py-2.5 text-xs text-right font-mono">
          {prospect.stars != null ? prospect.stars.toLocaleString() : '-'}
        </td>
        <td className="px-3 py-2.5">
          {prospect.framework_detected && (
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${fwStyle}`}>
              {prospect.framework_detected}
            </span>
          )}
        </td>
        <td className="px-3 py-2.5">
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${statusStyle}`}>
            {prospect.status}
          </span>
        </td>
        <td className="px-3 py-2.5 text-xs text-text-muted">{formatDate(prospect.contacted_at)}</td>
        <td className="px-3 py-2.5">
          {prospect.issue_url ? (
            <a
              href={prospect.issue_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary-light hover:underline text-[10px]"
              onClick={(e) => e.stopPropagation()}
            >
              View
            </a>
          ) : (
            <span className="text-[10px] text-text-muted">-</span>
          )}
        </td>
        <td className="px-3 py-2.5 text-[10px] text-text-muted truncate max-w-[120px]">
          {prospect.notes || '-'}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-surface-hover/30">
          <td colSpan={8} className="px-4 py-3">
            <div className="flex flex-wrap gap-4 items-end">
              <div className="flex-1 min-w-[200px]">
                <label className="text-[10px] text-text-muted uppercase tracking-wider block mb-1">Notes</label>
                <textarea
                  className="w-full bg-surface border border-border rounded px-2 py-1.5 text-xs text-text resize-none"
                  rows={2}
                  value={editNotes}
                  onChange={(e) => setEditNotes(e.target.value)}
                />
              </div>
              <div>
                <label className="text-[10px] text-text-muted uppercase tracking-wider block mb-1">Status</label>
                <select
                  className="bg-surface border border-border rounded px-2 py-1.5 text-xs text-text"
                  value={editStatus}
                  onChange={(e) => setEditStatus(e.target.value)}
                >
                  {STATUSES.filter((s) => s !== 'all').map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
              <button
                className="px-3 py-1.5 bg-primary text-white text-xs rounded hover:bg-primary/80 transition-colors"
                onClick={(e) => {
                  e.stopPropagation()
                  const updates: { status?: string; notes?: string } = {}
                  if (editStatus !== prospect.status) updates.status = editStatus
                  if (editNotes !== (prospect.notes || '')) updates.notes = editNotes
                  if (Object.keys(updates).length > 0) onUpdate(prospect.id, updates)
                }}
              >
                Save
              </button>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

/* ───────── Outreach History ───────── */
function OutreachSection() {
  const [offset, setOffset] = useState(0)
  const limit = 30

  const { data, isLoading } = useQuery<{
    prospects: RecruitmentProspectItem[]
    total: number
    has_more: boolean
  }>({
    queryKey: ['admin-recruitment-outreach', offset],
    queryFn: async () => {
      const { data } = await api.get('/admin/recruitment/prospects', {
        params: { status: 'contacted', limit, offset, sort: 'contacted_at_desc' },
      })
      return data
    },
    staleTime: 30_000,
  })

  const prospects = data?.prospects || []
  const total = data?.total || 0
  const hasMore = data?.has_more || false

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">GitHub Issues Created</h3>
        <span className="text-xs text-text-muted">{total} contacted</span>
      </div>

      {isLoading && <div className="text-text-muted text-sm py-10 text-center">Loading outreach history...</div>}

      {!isLoading && prospects.length === 0 && (
        <div className="text-center text-text-muted py-16">
          <p className="text-lg font-medium mb-1">No outreach yet</p>
          <p className="text-sm">Contacted prospects and their GitHub issues will appear here.</p>
        </div>
      )}

      {prospects.map((p) => {
        const ghUrl = `https://github.com/${p.platform_id}`
        const fwStyle = FRAMEWORK_STYLES[(p.framework_detected || '').toLowerCase()] || 'bg-surface-hover text-text-muted'
        return (
          <div key={p.id} className="bg-surface border border-border rounded-lg p-4">
            <div className="flex gap-3 items-start">
              {/* Left: repo info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <a
                    href={ghUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm font-mono text-primary-light hover:underline truncate"
                  >
                    {p.platform_id}
                  </a>
                  {p.stars != null && (
                    <span className="text-[10px] text-text-muted shrink-0">{p.stars.toLocaleString()} stars</span>
                  )}
                  {p.framework_detected && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full shrink-0 ${fwStyle}`}>
                      {p.framework_detected}
                    </span>
                  )}
                </div>
                {p.description && (
                  <p className="text-xs text-text-muted/70 line-clamp-2 mb-2">{p.description}</p>
                )}
                <div className="flex items-center gap-3 text-xs text-text-muted">
                  <span>by {p.owner_login}</span>
                  {p.contacted_at && <span>Contacted {formatDate(p.contacted_at)}</span>}
                </div>
              </div>

              {/* Right: issue link */}
              <div className="flex flex-col items-end gap-2 shrink-0">
                {p.issue_url ? (
                  <a
                    href={p.issue_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs bg-primary/10 text-primary hover:bg-primary/20 px-3 py-1.5 rounded inline-flex items-center gap-1"
                  >
                    View Issue
                  </a>
                ) : (
                  <span className="text-[10px] text-text-muted">No issue link</span>
                )}
                <a
                  href={ghUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs bg-surface-hover text-text-muted hover:text-text px-3 py-1.5 rounded inline-flex items-center gap-1"
                >
                  View Repo
                </a>
              </div>
            </div>
          </div>
        )
      })}

      {/* Pagination */}
      {(offset > 0 || hasMore) && (
        <div className="flex items-center justify-center gap-3">
          <button
            className="px-3 py-1 text-xs bg-surface border border-border rounded hover:bg-surface-hover disabled:opacity-40 transition-colors"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - limit))}
          >
            Previous
          </button>
          <span className="text-xs text-text-muted">
            {offset + 1}-{Math.min(offset + limit, total)} of {total}
          </span>
          <button
            className="px-3 py-1 text-xs bg-surface border border-border rounded hover:bg-surface-hover disabled:opacity-40 transition-colors"
            disabled={!hasMore}
            onClick={() => setOffset(offset + limit)}
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}

export default function RecruitmentTab() {
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [subTab, setSubTab] = useState<SubTab>('overview')
  const [statusFilter, setStatusFilter] = useState('all')
  const [offset, setOffset] = useState(0)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const limit = 50

  const subTabs: { value: SubTab; label: string }[] = [
    { value: 'overview', label: 'Overview' },
    { value: 'outreach', label: 'Outreach History' },
  ]

  const { data: stats, isLoading: statsLoading } = useQuery<RecruitmentStatsData>({
    queryKey: ['admin-recruitment-stats'],
    queryFn: async () => {
      const { data } = await api.get('/admin/recruitment/stats')
      return data
    },
    staleTime: 30_000,
  })

  const { data: prospectsData, isLoading: prospectsLoading } = useQuery<{
    prospects: RecruitmentProspectItem[]
    total: number
    has_more: boolean
  }>({
    queryKey: ['admin-recruitment-prospects', statusFilter, offset],
    queryFn: async () => {
      const params: Record<string, string | number> = { limit, offset }
      if (statusFilter !== 'all') params.status = statusFilter
      const { data } = await api.get('/admin/recruitment/prospects', { params })
      return data
    },
    staleTime: 15_000,
  })

  const updateMutation = useMutation({
    mutationFn: async ({ id, updates }: { id: string; updates: { status?: string; notes?: string } }) => {
      const { data } = await api.patch(`/admin/recruitment/prospects/${id}`, updates)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-recruitment-prospects'] })
      queryClient.invalidateQueries({ queryKey: ['admin-recruitment-stats'] })
      addToast('Prospect updated', 'success')
    },
    onError: () => {
      addToast('Failed to update prospect', 'error')
    },
  })

  const handleUpdate = (id: string, updates: { status?: string; notes?: string }) => {
    updateMutation.mutate({ id, updates })
  }

  const prospects = prospectsData?.prospects || []
  const total = prospectsData?.total || 0
  const hasMore = prospectsData?.has_more || false

  return (
    <div>
      <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
        Operator Recruitment
      </h2>

      {/* Sub-tab toggle */}
      <div className="flex gap-1 mb-5 bg-surface-hover/50 rounded-lg p-1 w-fit">
        {subTabs.map((t) => (
          <button
            key={t.value}
            onClick={() => setSubTab(t.value)}
            className={`px-4 py-1.5 rounded text-sm cursor-pointer transition-colors ${
              subTab === t.value ? 'bg-surface text-text font-medium shadow-sm' : 'text-text-muted hover:text-text'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {subTab === 'outreach' && <OutreachSection />}

      {subTab === 'overview' && <>
      {/* Stats cards */}
      {statsLoading ? (
        <div className="grid grid-cols-4 gap-3 mb-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-surface border border-border rounded-lg p-4 h-20 animate-pulse" />
          ))}
        </div>
      ) : stats ? (
        <>
          <div className="grid grid-cols-4 gap-3 mb-4">
            <StatCard label="Total Prospects" value={stats.total} />
            <StatCard label="Contacted" value={stats.contacted} sub={stats.total > 0 ? `${((stats.contacted / stats.total) * 100).toFixed(1)}% of total` : undefined} />
            <StatCard label="Onboarded" value={stats.onboarded} sub={stats.contacted > 0 ? `${((stats.onboarded / stats.contacted) * 100).toFixed(1)}% of contacted` : undefined} />
            <StatCard label="Active" value={stats.active} />
          </div>
          <FunnelBar stats={stats} />
        </>
      ) : null}

      {/* Filters */}
      <div className="flex items-center gap-3 mb-4">
        <label className="text-xs text-text-muted">Status:</label>
        <select
          className="bg-surface border border-border rounded px-2 py-1 text-xs text-text"
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setOffset(0) }}
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s === 'all' ? 'All' : s}</option>
          ))}
        </select>
        <span className="text-xs text-text-muted ml-auto">
          {total} prospect{total !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Prospects table */}
      {prospectsLoading ? (
        <div className="py-10 text-center text-text-muted text-sm">Loading prospects...</div>
      ) : prospects.length === 0 ? (
        <div className="py-10 text-center text-text-muted text-sm">
          No prospects found{statusFilter !== 'all' ? ` with status "${statusFilter}"` : ''}
        </div>
      ) : (
        <div className="bg-surface border border-border rounded-lg overflow-x-auto">
          <table className="w-full text-sm min-w-[700px]">
            <caption className="sr-only">Recruitment prospects</caption>
            <thead>
              <tr className="border-b border-border text-left">
                <th className="px-3 py-2 text-xs text-text-muted font-medium">Repo</th>
                <th className="px-3 py-2 text-xs text-text-muted font-medium">Owner</th>
                <th className="px-3 py-2 text-xs text-text-muted font-medium text-right">Stars</th>
                <th className="px-3 py-2 text-xs text-text-muted font-medium">Framework</th>
                <th className="px-3 py-2 text-xs text-text-muted font-medium">Status</th>
                <th className="px-3 py-2 text-xs text-text-muted font-medium">Contacted</th>
                <th className="px-3 py-2 text-xs text-text-muted font-medium">Issue</th>
                <th className="px-3 py-2 text-xs text-text-muted font-medium">Notes</th>
              </tr>
            </thead>
            <tbody>
              {prospects.map((p) => (
                <ProspectRow
                  key={p.id}
                  prospect={p}
                  expanded={expandedId === p.id}
                  onToggle={() => setExpandedId(expandedId === p.id ? null : p.id)}
                  onUpdate={handleUpdate}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {(offset > 0 || hasMore) && (
        <div className="flex items-center justify-center gap-3 mt-4">
          <button
            className="px-3 py-1 text-xs bg-surface border border-border rounded hover:bg-surface-hover disabled:opacity-40 transition-colors"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - limit))}
          >
            Previous
          </button>
          <span className="text-xs text-text-muted">
            {offset + 1}-{Math.min(offset + limit, total)} of {total}
          </span>
          <button
            className="px-3 py-1 text-xs bg-surface border border-border rounded hover:bg-surface-hover disabled:opacity-40 transition-colors"
            disabled={!hasMore}
            onClick={() => setOffset(offset + limit)}
          >
            Next
          </button>
        </div>
      )}
      </>}
    </div>
  )
}
