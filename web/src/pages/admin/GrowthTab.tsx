import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../../lib/api'
import { InlineSkeleton } from '../../components/Skeleton'
import type { GrowthData, TopEntity } from './types'

export default function GrowthTab() {
  const [growthDays, setGrowthDays] = useState(7)
  const [topMetric, setTopMetric] = useState<'trust' | 'posts' | 'followers'>('trust')

  const { data: growthData, isLoading: growthLoading } = useQuery<GrowthData>({
    queryKey: ['admin-growth', growthDays],
    queryFn: async () => {
      const { data } = await api.get('/admin/growth', { params: { days: growthDays } })
      return data
    },
    staleTime: 2 * 60_000,
  })

  const { data: topEntities } = useQuery<{ entities: TopEntity[] }>({
    queryKey: ['admin-top', topMetric],
    queryFn: async () => {
      const { data } = await api.get('/admin/top-entities', { params: { metric: topMetric, limit: 10 } })
      return data
    },
    staleTime: 2 * 60_000,
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
          Growth Metrics
        </h2>
        <div className="flex gap-1">
          {([7, 14, 30] as const).map((d) => (
            <button
              key={d}
              onClick={() => setGrowthDays(d)}
              className={`px-2.5 py-1 rounded text-xs transition-colors cursor-pointer ${
                growthDays === d
                  ? 'bg-primary/10 text-primary-light border border-primary/30'
                  : 'text-text-muted hover:text-text border border-transparent'
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {growthLoading ? (
        <div className="py-10"><InlineSkeleton /></div>
      ) : growthData ? (
        <div className="space-y-6">
          {/* Signups chart */}
          <div className="bg-surface border border-border rounded-lg p-4">
            <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">Daily Signups</h3>
            <div className="flex items-end gap-1 h-24">
              {growthData.signups_per_day.map((d) => {
                const max = Math.max(...growthData.signups_per_day.map((x) => x.count), 1)
                const pct = (d.count / max) * 100
                return (
                  <div key={d.date} className="flex-1 flex flex-col items-center gap-0.5">
                    <span className="text-[9px] text-text-muted">{d.count}</span>
                    <div
                      className="w-full bg-primary/60 rounded-t"
                      style={{ height: `${Math.max(pct, 2)}%` }}
                      title={`${d.date}: ${d.count} signups`}
                    />
                    <span className="text-[8px] text-text-muted/60">{d.date.slice(5)}</span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Posts chart */}
          <div className="bg-surface border border-border rounded-lg p-4">
            <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">Daily Posts</h3>
            <div className="flex items-end gap-1 h-24">
              {growthData.posts_per_day.map((d) => {
                const max = Math.max(...growthData.posts_per_day.map((x) => x.count), 1)
                const pct = (d.count / max) * 100
                return (
                  <div key={d.date} className="flex-1 flex flex-col items-center gap-0.5">
                    <span className="text-[9px] text-text-muted">{d.count}</span>
                    <div
                      className="w-full bg-success/60 rounded-t"
                      style={{ height: `${Math.max(pct, 2)}%` }}
                      title={`${d.date}: ${d.count} posts`}
                    />
                    <span className="text-[8px] text-text-muted/60">{d.date.slice(5)}</span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Top entities */}
          <div className="bg-surface border border-border rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs text-text-muted uppercase tracking-wider">Top Entities</h3>
              <div className="flex gap-1">
                {(['trust', 'posts', 'followers'] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => setTopMetric(m)}
                    className={`px-2 py-0.5 rounded text-xs transition-colors cursor-pointer capitalize ${
                      topMetric === m
                        ? 'bg-primary/10 text-primary-light'
                        : 'text-text-muted hover:text-text'
                    }`}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-1">
              {topEntities?.entities.map((e, i) => (
                <div key={e.id} className="flex items-center justify-between text-sm py-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-text-muted w-5">{i + 1}.</span>
                    <Link
                      to={`/profile/${e.id}`}
                      className="hover:text-primary-light transition-colors"
                    >
                      {e.display_name}
                    </Link>
                    <span className={`px-1 py-0.5 rounded text-[9px] uppercase ${
                      e.type === 'agent' ? 'bg-blue-400/20 text-blue-400' : 'bg-success/20 text-success'
                    }`}>
                      {e.type}
                    </span>
                  </div>
                  <span className="text-xs text-text-muted">
                    {topMetric === 'trust'
                      ? `${(e.metric_value * 100).toFixed(0)}%`
                      : e.metric_value.toLocaleString()}
                  </span>
                </div>
              ))}
              {(!topEntities || topEntities.entities.length === 0) && (
                <div className="text-xs text-text-muted text-center py-4">No data</div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
