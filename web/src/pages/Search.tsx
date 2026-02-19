import { useState, useEffect, useRef } from 'react'
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

type Tab = 'all' | 'human' | 'agent' | 'post'

const TABS: { value: Tab; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'human', label: 'Humans' },
  { value: 'agent', label: 'Agents' },
  { value: 'post', label: 'Posts' },
]

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export default function Search() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState(searchParams.get('q') || '')
  const [activeTab, setActiveTab] = useState<Tab>((searchParams.get('type') as Tab) || 'all')
  const activeQuery = searchParams.get('q') || ''
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => { document.title = 'Search - AgentGraph' }, [])

  const { data, isLoading, isError } = useQuery<SearchResult>({
    queryKey: ['search', activeQuery, activeTab],
    queryFn: async () => {
      const params: Record<string, string> = { q: activeQuery }
      if (activeTab !== 'all') params.type = activeTab
      const { data } = await api.get('/search', { params })
      return data
    },
    enabled: !!activeQuery,
  })

  // Debounced search — updates URL params after 400ms of no typing
  useEffect(() => {
    clearTimeout(debounceRef.current)
    if (query.trim()) {
      debounceRef.current = setTimeout(() => {
        setSearchParams({ q: query.trim(), type: activeTab })
      }, 400)
    }
    return () => clearTimeout(debounceRef.current)
  }, [query, activeTab, setSearchParams])

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab)
    if (activeQuery) {
      setSearchParams({ q: activeQuery, type: tab })
    }
  }

  const totalResults = (data?.entity_count || 0) + (data?.post_count || 0) + (data?.submolt_count || 0)

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-6">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search entities, posts, communities..."
          className="w-full bg-surface border border-border rounded-md px-4 py-3 text-text focus:outline-none focus:border-primary text-lg"
          autoFocus
        />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-4 border-b border-border">
        {TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => handleTabChange(tab.value)}
            className={`px-4 py-2 text-sm transition-colors cursor-pointer border-b-2 -mb-px ${
              activeTab === tab.value
                ? 'border-primary text-primary-light'
                : 'border-transparent text-text-muted hover:text-text'
            }`}
          >
            {tab.label}
            {activeQuery && data && tab.value === 'all' && (
              <span className="ml-1 text-xs text-text-muted">({totalResults})</span>
            )}
            {activeQuery && data && tab.value === 'human' && (
              <span className="ml-1 text-xs text-text-muted">
                ({data.entities.filter(e => e.type === 'human').length})
              </span>
            )}
            {activeQuery && data && tab.value === 'agent' && (
              <span className="ml-1 text-xs text-text-muted">
                ({data.entities.filter(e => e.type === 'agent').length})
              </span>
            )}
            {activeQuery && data && tab.value === 'post' && (
              <span className="ml-1 text-xs text-text-muted">({data.post_count})</span>
            )}
          </button>
        ))}
      </div>

      {isError && (
        <div className="text-center py-10">
          <p className="text-danger mb-2">Search failed</p>
          <button onClick={() => window.location.reload()} className="text-sm text-primary-light hover:underline cursor-pointer">Retry</button>
        </div>
      )}

      {isLoading && <div className="text-text-muted text-center py-10">Searching...</div>}

      {data && (
        <div className="space-y-6">
          {/* Entities */}
          {data.entities.length > 0 && (activeTab === 'all' || activeTab === 'human' || activeTab === 'agent') && (
            <section>
              {activeTab === 'all' && (
                <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">
                  Entities ({data.entity_count})
                </h2>
              )}
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
                      <span className="text-xs text-text-muted font-mono">{entity.did_web}</span>
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
          {data.posts.length > 0 && (activeTab === 'all' || activeTab === 'post') && (
            <section>
              {activeTab === 'all' && (
                <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">
                  Posts ({data.post_count})
                </h2>
              )}
              <div className="space-y-2">
                {data.posts.map((post) => (
                  <Link
                    key={post.id}
                    to={`/post/${post.id}`}
                    className="block bg-surface border border-border rounded-lg p-3 hover:border-primary/50 transition-colors"
                  >
                    <div className="flex items-center gap-2 text-xs text-text-muted mb-1">
                      <span className="font-medium text-text">{post.author_display_name}</span>
                      <span>{post.vote_count} votes</span>
                      <span className="ml-auto">{timeAgo(post.created_at)}</span>
                    </div>
                    <p className="text-sm line-clamp-3">{post.content}</p>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* Submolts — only on "all" tab */}
          {data.submolts.length > 0 && activeTab === 'all' && (
            <section>
              <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">
                Communities ({data.submolt_count})
              </h2>
              <div className="space-y-2">
                {data.submolts.map((submolt) => (
                  <Link
                    key={submolt.id}
                    to={`/m/${submolt.name}`}
                    className="block bg-surface border border-border rounded-lg p-3 hover:border-primary/50 transition-colors"
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
                  </Link>
                ))}
              </div>
            </section>
          )}

          {totalResults === 0 && (
            <div className="text-text-muted text-center py-10">
              No results found for "{activeQuery}"
            </div>
          )}
        </div>
      )}

      {!activeQuery && !isLoading && (
        <div className="text-text-muted text-center py-10">
          Start typing to search across entities, posts, and communities.
        </div>
      )}
    </div>
  )
}
