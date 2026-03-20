import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../../lib/api'
import { InlineSkeleton } from '../../components/Skeleton'

export default function ConversionTab() {
  const [conversionDays, setConversionDays] = useState(30)

  const { data: conversionData, isLoading: conversionLoading } = useQuery<{
    period_days: number
    funnel: { event_type: string; count: number; conversion_rate: number | null }[]
    top_pages: { page: string; count: number }[]
    top_intents: { intent: string; count: number }[]
    total_events: number
  }>({
    queryKey: ['admin-conversion', conversionDays],
    queryFn: async () => {
      const { data } = await api.get('/analytics/conversion', { params: { days: conversionDays } })
      return data
    },
    staleTime: 2 * 60_000,
  })

  const { data: dailyConversion } = useQuery<{
    period_days: number
    daily: Record<string, unknown>[]
  }>({
    queryKey: ['admin-conversion-daily', conversionDays],
    queryFn: async () => {
      const { data } = await api.get('/analytics/conversion/daily', { params: { days: conversionDays } })
      return data
    },
    staleTime: 2 * 60_000,
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
          Guest-to-Register Funnel
        </h2>
        <div className="flex gap-1">
          {([7, 14, 30] as const).map((d) => (
            <button
              key={d}
              onClick={() => setConversionDays(d)}
              className={`px-2.5 py-1 rounded text-xs transition-colors cursor-pointer ${
                conversionDays === d
                  ? 'bg-primary/10 text-primary-light border border-primary/30'
                  : 'text-text-muted hover:text-text border border-transparent'
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {conversionLoading ? (
        <div className="py-10"><InlineSkeleton /></div>
      ) : conversionData ? (
        <div className="space-y-6">
          {/* Funnel bars */}
          <div className="bg-surface border border-border rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs text-text-muted uppercase tracking-wider">Funnel Steps</h3>
              <span className="text-xs text-text-muted">{conversionData.total_events.toLocaleString()} total events</span>
            </div>
            <div className="space-y-3">
              {conversionData.funnel.map((step) => {
                const maxCount = Math.max(...conversionData.funnel.map((s) => s.count), 1)
                const pct = (step.count / maxCount) * 100
                return (
                  <div key={step.event_type}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium">{step.event_type.replace(/_/g, ' ')}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono">{step.count.toLocaleString()}</span>
                        {step.conversion_rate !== null && (
                          <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                            step.conversion_rate >= 50 ? 'bg-success/20 text-success'
                              : step.conversion_rate >= 20 ? 'bg-warning/20 text-warning'
                              : 'bg-danger/20 text-danger'
                          }`}>
                            {step.conversion_rate}%
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="h-2 bg-border rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary/60 rounded-full transition-all"
                        style={{ width: `${Math.max(pct, 1)}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Top pages & intents side by side */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="bg-surface border border-border rounded-lg p-4">
              <h3 className="text-xs text-text-muted uppercase tracking-wider mb-2">Top Pages</h3>
              {conversionData.top_pages.length > 0 ? (
                <div className="space-y-1.5">
                  {conversionData.top_pages.map((p) => (
                    <div key={p.page} className="flex items-center justify-between">
                      <span className="text-xs font-mono truncate mr-2">{p.page}</span>
                      <span className="text-xs font-medium shrink-0">{p.count}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-text-muted">No page data</p>
              )}
            </div>
            <div className="bg-surface border border-border rounded-lg p-4">
              <h3 className="text-xs text-text-muted uppercase tracking-wider mb-2">Top Intents</h3>
              {conversionData.top_intents.length > 0 ? (
                <div className="space-y-1.5">
                  {conversionData.top_intents.map((i) => (
                    <div key={i.intent} className="flex items-center justify-between">
                      <span className="text-xs capitalize">{i.intent}</span>
                      <span className="text-xs font-medium">{i.count}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-text-muted">No intent data</p>
              )}
            </div>
          </div>

          {/* Daily trend chart */}
          {dailyConversion && dailyConversion.daily.length > 0 && (
            <div className="bg-surface border border-border rounded-lg p-4">
              <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">Daily Events</h3>
              <div className="flex items-end gap-1 h-24">
                {dailyConversion.daily.map((d) => {
                  const dayTotal = Object.entries(d)
                    .filter(([k]) => k !== 'date')
                    .reduce((sum, [, v]) => sum + (typeof v === 'number' ? v : 0), 0)
                  const maxDay = Math.max(
                    ...dailyConversion.daily.map((day) =>
                      Object.entries(day)
                        .filter(([k]) => k !== 'date')
                        .reduce((s, [, v]) => s + (typeof v === 'number' ? v : 0), 0)
                    ),
                    1,
                  )
                  const pct = (dayTotal / maxDay) * 100
                  return (
                    <div key={String(d.date)} className="flex-1 flex flex-col items-center gap-0.5">
                      <span className="text-[9px] text-text-muted">{dayTotal}</span>
                      <div
                        className="w-full bg-accent/60 rounded-t"
                        style={{ height: `${Math.max(pct, 2)}%` }}
                        title={`${String(d.date)}: ${dayTotal} events`}
                      />
                      <span className="text-[8px] text-text-muted/60">{String(d.date).slice(5)}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      ) : null}
    </div>
  )
}
