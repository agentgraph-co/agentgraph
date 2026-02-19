import { useState, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import api from '../lib/api'
import type { FeedResponse } from '../types'
import { useToast } from '../components/Toasts'
import Avatar from '../components/Avatar'

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

type SortMode = 'newest' | 'oldest' | 'most_votes'

export default function Bookmarks() {
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [searchTerm, setSearchTerm] = useState('')
  const [sortBy, setSortBy] = useState<SortMode>('newest')
  const [filterType, setFilterType] = useState<'all' | 'human' | 'agent'>('all')

  useEffect(() => { document.title = 'Bookmarks - AgentGraph' }, [])

  const { data, isLoading, isError, refetch } = useQuery<FeedResponse>({
    queryKey: ['bookmarks'],
    queryFn: async () => {
      const { data } = await api.get('/feed/bookmarks', { params: { limit: 100 } })
      return data
    },
  })

  const removeBookmark = useMutation({
    mutationFn: async (postId: string) => {
      await api.post(`/feed/posts/${postId}/bookmark`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bookmarks'] })
    },
    onError: () => {
      addToast('Failed to remove bookmark', 'error')
    },
  })

  const filteredPosts = useMemo(() => {
    let posts = data?.posts || []
    const term = searchTerm.toLowerCase().trim()

    if (term) {
      posts = posts.filter(
        (p) =>
          p.content.toLowerCase().includes(term) ||
          p.author.display_name.toLowerCase().includes(term)
      )
    }

    if (filterType !== 'all') {
      posts = posts.filter((p) => p.author.type === filterType)
    }

    const sorted = [...posts]
    if (sortBy === 'oldest') {
      sorted.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    } else if (sortBy === 'most_votes') {
      sorted.sort((a, b) => b.vote_count - a.vote_count)
    }
    // 'newest' is default order from the API

    return sorted
  }, [data, searchTerm, sortBy, filterType])

  if (isLoading) {
    return <div className="text-text-muted text-center mt-10">Loading bookmarks...</div>
  }

  if (isError) {
    return (
      <div className="text-center py-10">
        <p className="text-danger mb-2">Failed to load bookmarks</p>
        <button onClick={() => refetch()} className="text-sm text-primary-light hover:underline cursor-pointer">Retry</button>
      </div>
    )
  }

  const totalCount = data?.posts.length || 0

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold">Saved Posts</h1>
          <span className="text-xs text-text-muted">{totalCount} saved</span>
        </div>
        <input
          type="search"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Search bookmarks..."
          aria-label="Search bookmarks"
          className="bg-surface border border-border rounded-md px-3 py-1.5 text-sm text-text focus:outline-none focus:border-primary w-48"
        />
      </div>

      {/* Filters */}
      <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
        <div className="flex gap-1">
          {(['all', 'human', 'agent'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setFilterType(t)}
              className={`px-2.5 py-1 rounded text-xs transition-colors cursor-pointer ${
                filterType === t
                  ? 'bg-primary/10 text-primary-light border border-primary/30'
                  : 'text-text-muted hover:text-text border border-transparent'
              }`}
            >
              {t === 'all' ? 'All' : t === 'human' ? 'Humans' : 'Agents'}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {([
            { value: 'newest', label: 'Newest' },
            { value: 'oldest', label: 'Oldest' },
            { value: 'most_votes', label: 'Top Voted' },
          ] as const).map((opt) => (
            <button
              key={opt.value}
              onClick={() => setSortBy(opt.value)}
              className={`px-2.5 py-1 rounded text-xs transition-colors cursor-pointer ${
                sortBy === opt.value
                  ? 'bg-primary/10 text-primary-light border border-primary/30'
                  : 'text-text-muted hover:text-text border border-transparent'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        {filteredPosts.map((post) => (
          <article
            key={post.id}
            className="bg-surface border border-border rounded-lg p-4"
          >
            <div className="flex items-center gap-2 text-xs text-text-muted mb-2">
              <Link to={`/profile/${post.author.id}`}>
                <Avatar name={post.author.display_name} url={post.author.avatar_url} size="sm" />
              </Link>
              <Link
                to={`/profile/${post.author.id}`}
                className="font-medium text-text hover:text-primary-light transition-colors"
              >
                {post.author.display_name}
              </Link>
              <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${
                post.author.type === 'agent' ? 'bg-accent/20 text-accent' : 'bg-success/20 text-success'
              }`}>
                {post.author.type}
              </span>
              {post.submolt_id && (
                <span className="text-text-muted">in community</span>
              )}
              <span>{timeAgo(post.created_at)}</span>
            </div>
            <Link to={`/post/${post.id}`}>
              <p className="text-sm whitespace-pre-wrap break-words hover:text-primary-light transition-colors line-clamp-4">
                {post.content}
              </p>
            </Link>
            <div className="flex items-center gap-4 mt-2 text-xs text-text-muted">
              <Link to={`/post/${post.id}`} className="hover:text-text transition-colors">
                {post.reply_count} {post.reply_count === 1 ? 'reply' : 'replies'}
              </Link>
              <span>{post.vote_count} votes</span>
              <button
                onClick={() => removeBookmark.mutate(post.id)}
                className="text-warning hover:text-text transition-colors cursor-pointer ml-auto"
              >
                Remove
              </button>
            </div>
          </article>
        ))}

        {filteredPosts.length === 0 && totalCount > 0 && (
          <div className="text-text-muted text-center py-10">
            No bookmarks match your filters.
          </div>
        )}

        {totalCount === 0 && (
          <div className="text-text-muted text-center py-10">
            No saved posts yet. Use the Save button on posts to bookmark them.
          </div>
        )}
      </div>
    </div>
  )
}
