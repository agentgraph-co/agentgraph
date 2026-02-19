import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'

interface DiscoverProfile {
  id: string
  type: string
  display_name: string
  bio_markdown: string
  avatar_url: string | null
  did_web: string
  privacy_tier: string
  trust_score: number | null
  badges: string[]
  created_at: string
}

export default function Discover() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [entityType, setEntityType] = useState<'all' | 'human' | 'agent'>('all')
  const [offset, setOffset] = useState(0)
  const limit = 20

  useEffect(() => { document.title = 'Discover - AgentGraph' }, [])

  const { data, isLoading, isError } = useQuery<{ profiles: DiscoverProfile[]; total: number; has_more: boolean }>({
    queryKey: ['discover', search, entityType, offset],
    queryFn: async () => {
      const params: Record<string, string | number> = { limit, offset }
      if (search) params.q = search
      if (entityType !== 'all') params.entity_type = entityType
      const { data } = await api.get('/profiles', { params })
      return data
    },
  })

  const followMutation = useMutation({
    mutationFn: async (entityId: string) => {
      await api.post(`/social/follow/${entityId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['discover'] })
    },
  })

  const handleSearch = (value: string) => {
    setSearch(value)
    setOffset(0)
  }

  const handleTypeChange = (t: 'all' | 'human' | 'agent') => {
    setEntityType(t)
    setOffset(0)
  }

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-xl font-bold mb-4">Discover</h1>

      <div className="flex gap-3 mb-4 flex-wrap">
        <input
          type="text"
          value={search}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder="Search profiles..."
          className="flex-1 min-w-[200px] bg-surface border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-primary"
        />
        <div className="flex gap-1">
          {(['all', 'human', 'agent'] as const).map((t) => (
            <button
              key={t}
              onClick={() => handleTypeChange(t)}
              className={`px-3 py-2 rounded-md text-sm transition-colors cursor-pointer ${
                entityType === t
                  ? 'bg-primary/10 text-primary-light border border-primary/30'
                  : 'text-text-muted hover:text-text border border-border'
              }`}
            >
              {t === 'all' ? 'All' : t === 'human' ? 'Humans' : 'Agents'}
            </button>
          ))}
        </div>
      </div>

      {isError && (
        <div className="text-center py-10">
          <p className="text-danger mb-2">Failed to load profiles</p>
          <button onClick={() => window.location.reload()} className="text-sm text-primary-light hover:underline cursor-pointer">Retry</button>
        </div>
      )}

      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-surface border border-border rounded-lg p-4 animate-pulse">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-surface-hover" />
                <div className="flex-1">
                  <div className="h-4 bg-surface-hover rounded w-1/3 mb-2" />
                  <div className="h-3 bg-surface-hover rounded w-2/3" />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {data && (
        <>
          <p className="text-xs text-text-muted mb-3">
            {data.total} {data.total === 1 ? 'profile' : 'profiles'} found
          </p>

          <div className="space-y-3">
            {data.profiles.map((p) => (
              <div
                key={p.id}
                className="bg-surface border border-border rounded-lg p-4 hover:border-border/80 transition-colors"
              >
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-full bg-surface-hover flex items-center justify-center text-sm font-bold text-text-muted shrink-0">
                    {p.display_name.charAt(0).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <Link
                        to={`/profile/${p.id}`}
                        className="text-sm font-medium hover:text-primary-light transition-colors"
                      >
                        {p.display_name}
                      </Link>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${
                        p.type === 'agent' ? 'bg-accent/20 text-accent' : 'bg-success/20 text-success'
                      }`}>
                        {p.type}
                      </span>
                      {p.trust_score !== null && (
                        <span className="text-[10px] text-text-muted">
                          Trust: {(p.trust_score * 100).toFixed(0)}%
                        </span>
                      )}
                      {p.badges.map((badge) => (
                        <span
                          key={badge}
                          className="text-[10px] px-1.5 py-0.5 bg-warning/20 text-warning rounded"
                        >
                          {badge}
                        </span>
                      ))}
                    </div>
                    {p.bio_markdown && (
                      <p className="text-xs text-text-muted line-clamp-2 mb-1">
                        {p.bio_markdown}
                      </p>
                    )}
                    <span className="text-[10px] text-text-muted font-mono">
                      {p.did_web}
                    </span>
                  </div>
                  {user && user.id !== p.id && (
                    <button
                      onClick={() => followMutation.mutate(p.id)}
                      disabled={followMutation.isPending}
                      className="shrink-0 text-xs bg-primary/10 text-primary-light hover:bg-primary/20 px-3 py-1.5 rounded-full transition-colors cursor-pointer disabled:opacity-50"
                    >
                      Follow
                    </button>
                  )}
                </div>
              </div>
            ))}

            {data.profiles.length === 0 && (
              <div className="text-center text-text-muted py-10 text-sm">
                {search ? 'No profiles match your search' : 'No profiles found'}
              </div>
            )}
          </div>

          {/* Pagination */}
          {data.total > limit && (
            <div className="flex items-center justify-between mt-4 pt-3 border-t border-border">
              <span className="text-xs text-text-muted">
                Showing {offset + 1}-{Math.min(offset + limit, data.total)} of {data.total}
              </span>
              <div className="flex gap-2">
                {offset > 0 && (
                  <button
                    onClick={() => setOffset(Math.max(0, offset - limit))}
                    className="text-xs text-primary-light hover:underline cursor-pointer"
                  >
                    Previous
                  </button>
                )}
                {data.has_more && (
                  <button
                    onClick={() => setOffset(offset + limit)}
                    className="text-xs text-primary-light hover:underline cursor-pointer"
                  >
                    Next
                  </button>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
