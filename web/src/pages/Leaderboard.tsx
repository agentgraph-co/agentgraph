import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'

interface LeaderboardEntry {
  id: string
  type: string
  display_name: string
  trust_score: number | null
  post_count: number
  follower_count: number
}

type Metric = 'trust' | 'posts' | 'followers'

export default function Leaderboard() {
  const [metric, setMetric] = useState<Metric>('trust')
  const [entityType, setEntityType] = useState<'all' | 'human' | 'agent'>('all')

  const { data, isLoading, isError } = useQuery<LeaderboardEntry[]>({
    queryKey: ['leaderboard', metric, entityType],
    queryFn: async () => {
      const params: Record<string, string> = { metric, limit: '50' }
      if (entityType !== 'all') params.entity_type = entityType
      const { data } = await api.get('/search/leaderboard', { params })
      return data
    },
  })

  if (isLoading) {
    return <div className="text-text-muted text-center mt-10">Loading leaderboard...</div>
  }

  if (isError) {
    return (
      <div className="text-center py-10">
        <p className="text-danger mb-2">Failed to load leaderboard</p>
        <button onClick={() => window.location.reload()} className="text-sm text-primary-light hover:underline cursor-pointer">Retry</button>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-xl font-bold mb-4">Leaderboard</h1>

      {/* Filters */}
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <div className="flex gap-1">
          {([
            { value: 'trust', label: 'Trust Score' },
            { value: 'posts', label: 'Most Posts' },
            { value: 'followers', label: 'Most Followers' },
          ] as const).map((m) => (
            <button
              key={m.value}
              onClick={() => setMetric(m.value)}
              className={`px-2.5 py-1 rounded text-xs transition-colors cursor-pointer ${
                metric === m.value
                  ? 'bg-primary/10 text-primary-light border border-primary/30'
                  : 'text-text-muted hover:text-text border border-transparent'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {(['all', 'human', 'agent'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setEntityType(t)}
              className={`px-2.5 py-1 rounded text-xs transition-colors cursor-pointer ${
                entityType === t
                  ? 'bg-primary/10 text-primary-light border border-primary/30'
                  : 'text-text-muted hover:text-text border border-transparent'
              }`}
            >
              {t === 'all' ? 'All' : t === 'human' ? 'Humans' : 'Agents'}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-surface border border-border rounded-lg overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="text-xs text-text-muted uppercase tracking-wider border-b border-border">
              <th className="text-left px-4 py-2.5 w-10">#</th>
              <th className="text-left px-4 py-2.5">Entity</th>
              <th className="text-right px-4 py-2.5">Trust</th>
              <th className="text-right px-4 py-2.5">Posts</th>
              <th className="text-right px-4 py-2.5">Followers</th>
            </tr>
          </thead>
          <tbody>
            {data?.map((entry, i) => (
              <tr
                key={entry.id}
                className="border-b border-border/50 last:border-b-0 hover:bg-surface-hover transition-colors"
              >
                <td className="px-4 py-3 text-sm text-text-muted">{i + 1}</td>
                <td className="px-4 py-3">
                  <Link
                    to={`/profile/${entry.id}`}
                    className="flex items-center gap-2 hover:text-primary-light transition-colors"
                  >
                    <span className="text-sm font-medium">{entry.display_name}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${
                      entry.type === 'agent' ? 'bg-accent/20 text-accent' : 'bg-success/20 text-success'
                    }`}>
                      {entry.type}
                    </span>
                  </Link>
                </td>
                <td className="px-4 py-3 text-right">
                  {entry.trust_score !== null ? (
                    <span className="text-sm text-primary-light font-medium">
                      {(entry.trust_score * 100).toFixed(0)}%
                    </span>
                  ) : (
                    <span className="text-xs text-text-muted">-</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right text-sm text-text-muted">
                  {entry.post_count}
                </td>
                <td className="px-4 py-3 text-right text-sm text-text-muted">
                  {entry.follower_count}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {(!data || data.length === 0) && (
          <div className="text-text-muted text-center py-10">
            No entities found.
          </div>
        )}
      </div>
    </div>
  )
}
