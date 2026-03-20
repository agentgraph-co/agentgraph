import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../../lib/api'
import { InlineSkeleton } from '../../components/Skeleton'

export default function AttributionTab() {
  const [attributionDays, setAttributionDays] = useState(30)

  const { data: attributionData, isLoading: attributionLoading } = useQuery<{
    period_days: number
    sources: { source: string; medium: string | null; events: { event_type: string; count: number }[]; total: number }[]
    total_attributed: number
    total_unattributed: number
  }>({
    queryKey: ['admin-attribution', attributionDays],
    queryFn: async () => {
      const { data } = await api.get('/analytics/attribution', { params: { days: attributionDays } })
      return data
    },
    staleTime: 2 * 60_000,
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
          Marketing Attribution
        </h2>
        <div className="flex gap-1">
          {([7, 14, 30] as const).map((d) => (
            <button
              key={d}
              onClick={() => setAttributionDays(d)}
              className={`px-2.5 py-1 rounded text-xs transition-colors cursor-pointer ${
                attributionDays === d
                  ? 'bg-primary/10 text-primary-light border border-primary/30'
                  : 'text-text-muted hover:text-text border border-transparent'
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {attributionLoading ? (
        <div className="py-10"><InlineSkeleton /></div>
      ) : attributionData ? (
        <div className="space-y-6">
          {/* Summary */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-surface border border-border rounded-lg p-4">
              <div className="text-xs text-text-muted uppercase tracking-wider mb-1">Attributed Events</div>
              <div className="text-lg font-bold">{attributionData.total_attributed.toLocaleString()}</div>
            </div>
            <div className="bg-surface border border-border rounded-lg p-4">
              <div className="text-xs text-text-muted uppercase tracking-wider mb-1">Unattributed Events</div>
              <div className="text-lg font-bold">{attributionData.total_unattributed.toLocaleString()}</div>
            </div>
          </div>

          {/* Per-source breakdown */}
          {attributionData.sources.length > 0 ? (
            <div className="bg-surface border border-border rounded-lg p-4">
              <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">By Source</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-2 pr-4 text-text-muted font-medium">Source</th>
                      <th className="text-left py-2 pr-4 text-text-muted font-medium">Medium</th>
                      <th className="text-right py-2 pr-4 text-text-muted font-medium">Page Views</th>
                      <th className="text-right py-2 pr-4 text-text-muted font-medium">CTA Clicks</th>
                      <th className="text-right py-2 pr-4 text-text-muted font-medium">Reg Start</th>
                      <th className="text-right py-2 pr-4 text-text-muted font-medium">Reg Complete</th>
                      <th className="text-right py-2 pr-4 text-text-muted font-medium">First Action</th>
                      <th className="text-right py-2 text-text-muted font-medium">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {attributionData.sources.map((src) => {
                      const eventMap: Record<string, number> = {}
                      for (const e of src.events) {
                        eventMap[e.event_type] = e.count
                      }
                      return (
                        <tr key={`${src.source}-${src.medium}`} className="border-b border-border/50">
                          <td className="py-2 pr-4 font-medium">{src.source}</td>
                          <td className="py-2 pr-4 text-text-muted">{src.medium || '-'}</td>
                          <td className="py-2 pr-4 text-right font-mono">{(eventMap['guest_page_view'] || 0).toLocaleString()}</td>
                          <td className="py-2 pr-4 text-right font-mono">{(eventMap['guest_cta_click'] || 0).toLocaleString()}</td>
                          <td className="py-2 pr-4 text-right font-mono">{(eventMap['register_start'] || 0).toLocaleString()}</td>
                          <td className="py-2 pr-4 text-right font-mono">
                            <span className={eventMap['register_complete'] ? 'text-success' : ''}>
                              {(eventMap['register_complete'] || 0).toLocaleString()}
                            </span>
                          </td>
                          <td className="py-2 pr-4 text-right font-mono">
                            <span className={eventMap['first_action'] ? 'text-primary-light' : ''}>
                              {(eventMap['first_action'] || 0).toLocaleString()}
                            </span>
                          </td>
                          <td className="py-2 text-right font-mono font-medium">{src.total.toLocaleString()}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="bg-surface border border-border rounded-lg p-6 text-center">
              <p className="text-sm text-text-muted">No UTM-attributed events yet.</p>
              <p className="text-xs text-text-muted mt-1">Marketing bot links with utm_source params will appear here.</p>
            </div>
          )}
        </div>
      ) : null}
    </div>
  )
}
