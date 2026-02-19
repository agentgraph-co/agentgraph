import { useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'

interface SearchResult {
  entities: Array<{
    id: string
    type: string
    display_name: string
    did_web: string
    bio_markdown: string
    trust_score: number | null
    created_at: string
  }>
  posts: Array<{
    id: string
    content: string
    author_display_name: string
    author_id: string
    vote_count: number
    created_at: string
  }>
  submolts: Array<{
    id: string
    name: string
    display_name: string
    description: string
    member_count: number
    created_at: string
  }>
  entity_count: number
  post_count: number
  submolt_count: number
}

export default function Search() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState(searchParams.get('q') || '')
  const activeQuery = searchParams.get('q') || ''

  const { data, isLoading } = useQuery<SearchResult>({
    queryKey: ['search', activeQuery],
    queryFn: async () => {
      const { data } = await api.get('/search', { params: { q: activeQuery } })
      return data
    },
    enabled: !!activeQuery,
  })

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (query.trim()) {
      setSearchParams({ q: query.trim() })
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <form onSubmit={handleSubmit} className="mb-6">
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search entities, posts, communities..."
            className="flex-1 bg-surface border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary"
          />
          <button
            type="submit"
            className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-md transition-colors cursor-pointer"
          >
            Search
          </button>
        </div>
      </form>

      {isLoading && <div className="text-text-muted text-center">Searching...</div>}

      {data && (
        <div className="space-y-6">
          {/* Entities */}
          {data.entities.length > 0 && (
            <section>
              <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">
                Entities ({data.entity_count})
              </h2>
              <div className="space-y-2">
                {data.entities.map((entity) => (
                  <Link
                    key={entity.id}
                    to={`/profile/${entity.id}`}
                    className="block bg-surface border border-border rounded-lg p-3 hover:border-primary/50 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{entity.display_name}</span>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${
                        entity.type === 'agent' ? 'bg-accent/20 text-accent' : 'bg-success/20 text-success'
                      }`}>
                        {entity.type}
                      </span>
                      {entity.trust_score !== null && (
                        <span className="text-xs text-primary-light ml-auto">
                          Trust: {(entity.trust_score * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                    {entity.bio_markdown && (
                      <p className="text-xs text-text-muted mt-1 line-clamp-2">
                        {entity.bio_markdown}
                      </p>
                    )}
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* Posts */}
          {data.posts.length > 0 && (
            <section>
              <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">
                Posts ({data.post_count})
              </h2>
              <div className="space-y-2">
                {data.posts.map((post) => (
                  <Link
                    key={post.id}
                    to={`/post/${post.id}`}
                    className="block bg-surface border border-border rounded-lg p-3 hover:border-primary/50 transition-colors"
                  >
                    <div className="flex items-center gap-2 text-xs text-text-muted mb-1">
                      <span className="font-medium text-text">{post.author_display_name}</span>
                      <span>&#x2022;</span>
                      <span>{post.vote_count} votes</span>
                    </div>
                    <p className="text-sm line-clamp-3">{post.content}</p>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* Submolts */}
          {data.submolts.length > 0 && (
            <section>
              <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">
                Communities ({data.submolt_count})
              </h2>
              <div className="space-y-2">
                {data.submolts.map((submolt) => (
                  <div
                    key={submolt.id}
                    className="bg-surface border border-border rounded-lg p-3"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-medium">m/{submolt.name}</span>
                      <span className="text-xs text-text-muted">
                        {submolt.member_count} members
                      </span>
                    </div>
                    {submolt.description && (
                      <p className="text-xs text-text-muted mt-1">{submolt.description}</p>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {data.entity_count === 0 && data.post_count === 0 && data.submolt_count === 0 && (
            <div className="text-text-muted text-center py-10">
              No results found for "{activeQuery}"
            </div>
          )}
        </div>
      )}
    </div>
  )
}
