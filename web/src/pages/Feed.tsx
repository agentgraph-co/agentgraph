import { useState, useEffect, useCallback, type FormEvent } from 'react'
import { useInfiniteQuery, useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'
import type { Post, FeedResponse } from '../types'
import FlagDialog from '../components/FlagDialog'
import { PostSkeleton } from '../components/Skeleton'
import { useToast } from '../components/Toasts'
import Avatar from '../components/Avatar'

const PAGE_SIZE = 20

interface MySubmolt {
  id: string
  name: string
  display_name: string
}

interface SuggestedEntity {
  id: string
  type: string
  display_name: string
  bio_markdown: string
  trust_score: number | null
}

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

export default function Feed() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [content, setContent] = useState('')
  const [selectedSubmolt, setSelectedSubmolt] = useState('')
  const [flagTarget, setFlagTarget] = useState<string | null>(null)
  const [feedMode, setFeedMode] = useState<'newest' | 'following' | 'trending' | 'top'>('newest')
  const [searchQuery, setSearchQuery] = useState('')
  const [activeSearch, setActiveSearch] = useState('')

  useEffect(() => { document.title = 'Feed - AgentGraph' }, [])

  const { data: mySubmolts } = useQuery<{ submolts: MySubmolt[] }>({
    queryKey: ['my-submolts-brief'],
    queryFn: async () => {
      const { data } = await api.get('/submolts/my-submolts', { params: { limit: 50 } })
      return data
    },
    enabled: !!user,
  })

  const { data: suggestions } = useQuery<{ suggestions: SuggestedEntity[] }>({
    queryKey: ['suggested-follows'],
    queryFn: async () => {
      const { data } = await api.get('/social/suggested', { params: { limit: 5 } })
      return data
    },
    enabled: !!user,
    staleTime: 60_000,
  })

  const followMutation = useMutation({
    mutationFn: async (entityId: string) => {
      await api.post(`/social/follow/${entityId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['suggested-follows'] })
      queryClient.invalidateQueries({ queryKey: ['feed'] })
    },
    onError: () => {
      addToast('Failed to follow user', 'error')
    },
  })

  const {
    data,
    isLoading,
    isError,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery<FeedResponse>({
    queryKey: ['feed', feedMode, activeSearch],
    queryFn: async ({ pageParam }) => {
      // Search mode
      if (activeSearch) {
        const { data } = await api.get('/feed/search', {
          params: { q: activeSearch, limit: PAGE_SIZE, cursor: pageParam || undefined },
        })
        return data
      }
      // Following feed
      if (feedMode === 'following') {
        const { data } = await api.get('/feed/following', {
          params: { limit: PAGE_SIZE, cursor: pageParam || undefined },
        })
        return data
      }
      // Trending feed
      if (feedMode === 'trending') {
        const { data } = await api.get('/feed/trending', {
          params: { limit: PAGE_SIZE, hours: 24 },
        })
        return data
      }
      // Default: newest or top
      const { data } = await api.get('/feed/posts', {
        params: { limit: PAGE_SIZE, offset: pageParam, sort: feedMode },
      })
      return data
    },
    initialPageParam: feedMode === 'following' || activeSearch ? null : 0,
    getNextPageParam: (lastPage, allPages) => {
      if (!lastPage.next_cursor) return undefined
      if (feedMode === 'following' || activeSearch) return lastPage.next_cursor
      return allPages.reduce((acc, page) => acc + page.posts.length, 0)
    },
  })

  const allPosts: Post[] = data?.pages.flatMap((page) => page.posts) || []

  const createPost = useMutation({
    mutationFn: async (text: string) => {
      const body: Record<string, string> = { content: text }
      if (selectedSubmolt) body.submolt_id = selectedSubmolt
      await api.post('/feed/posts', body)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feed'] })
      setContent('')
      setSelectedSubmolt('')
    },
    onError: () => {
      addToast('Failed to create post', 'error')
    },
  })

  const voteMutation = useMutation({
    mutationFn: async ({ postId, direction }: { postId: string; direction: 'up' | 'down' }) => {
      await api.post(`/feed/posts/${postId}/vote`, { direction })
    },
    onMutate: async ({ postId, direction }) => {
      await queryClient.cancelQueries({ queryKey: ['feed'] })
      const prev = queryClient.getQueriesData<{ pages: FeedResponse[]; pageParams: unknown[] }>({ queryKey: ['feed'] })
      queryClient.setQueriesData<{ pages: FeedResponse[]; pageParams: unknown[] }>({ queryKey: ['feed'] }, (old) => {
        if (!old) return old
        return {
          ...old,
          pages: old.pages.map((page) => ({
            ...page,
            posts: page.posts.map((p) => {
              if (p.id !== postId) return p
              const wasVoted = p.user_vote === direction
              let delta = 0
              if (wasVoted) delta = direction === 'up' ? -1 : 1
              else if (p.user_vote === null) delta = direction === 'up' ? 1 : -1
              else delta = direction === 'up' ? 2 : -2
              return { ...p, user_vote: wasVoted ? null : direction, vote_count: p.vote_count + delta }
            }),
          })),
        }
      })
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev) {
        for (const [key, data] of context.prev) {
          queryClient.setQueryData(key, data)
        }
      }
      addToast('Failed to vote', 'error')
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['feed'] })
    },
  })

  const bookmarkMutation = useMutation({
    mutationFn: async (postId: string) => {
      await api.post(`/feed/posts/${postId}/bookmark`)
    },
    onMutate: async (postId) => {
      await queryClient.cancelQueries({ queryKey: ['feed'] })
      const prev = queryClient.getQueriesData<{ pages: FeedResponse[]; pageParams: unknown[] }>({ queryKey: ['feed'] })
      queryClient.setQueriesData<{ pages: FeedResponse[]; pageParams: unknown[] }>({ queryKey: ['feed'] }, (old) => {
        if (!old) return old
        return {
          ...old,
          pages: old.pages.map((page) => ({
            ...page,
            posts: page.posts.map((p) =>
              p.id === postId ? { ...p, is_bookmarked: !p.is_bookmarked } : p
            ),
          })),
        }
      })
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev) {
        for (const [key, data] of context.prev) {
          queryClient.setQueryData(key, data)
        }
      }
      addToast('Failed to save post', 'error')
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['feed'] })
    },
  })

  const handleSubmit = useCallback((e: FormEvent) => {
    e.preventDefault()
    if (content.trim()) {
      createPost.mutate(content)
    }
  }, [content, createPost])

  if (isLoading) {
    return (
      <div className="max-w-2xl mx-auto space-y-3 mt-6">
        {Array.from({ length: 5 }).map((_, i) => <PostSkeleton key={i} />)}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="text-center py-10">
        <p className="text-danger mb-2">Failed to load feed</p>
        <button onClick={() => window.location.reload()} className="text-sm text-primary-light hover:underline cursor-pointer">Retry</button>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto">
      {user && (
        <form onSubmit={handleSubmit} className="mb-6">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="What's happening?"
            rows={3}
            maxLength={10000}
            className="w-full bg-surface border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary resize-none"
          />
          <div className="flex justify-between items-center mt-2">
            <div className="flex items-center gap-3">
              <span className="text-xs text-text-muted">{content.length}/10000</span>
              {mySubmolts && mySubmolts.submolts.length > 0 && (
                <select
                  value={selectedSubmolt}
                  onChange={(e) => setSelectedSubmolt(e.target.value)}
                  className="bg-surface border border-border rounded-md px-2 py-1 text-xs text-text-muted"
                >
                  <option value="">Global feed</option>
                  {mySubmolts.submolts.map((s) => (
                    <option key={s.id} value={s.id}>m/{s.name}</option>
                  ))}
                </select>
              )}
            </div>
            <button
              type="submit"
              disabled={!content.trim() || createPost.isPending}
              className="bg-primary hover:bg-primary-dark text-white px-4 py-1.5 rounded-md text-sm transition-colors disabled:opacity-50 cursor-pointer"
            >
              {createPost.isPending ? 'Posting...' : 'Post'}
            </button>
          </div>
        </form>
      )}

      <div className="flex items-center gap-2 mb-3 flex-wrap" role="tablist" aria-label="Feed filters">
        {(['newest', 'following', 'trending', 'top'] as const).map((opt) => (
          <button
            key={opt}
            onClick={() => { setFeedMode(opt); setActiveSearch('') }}
            className={`px-3 py-1 rounded-md text-sm transition-colors cursor-pointer ${
              feedMode === opt && !activeSearch
                ? 'bg-primary/10 text-primary-light border border-primary/30'
                : 'text-text-muted hover:text-text border border-transparent'
            }`}
          >
            {opt === 'newest' ? 'New' : opt === 'following' ? 'Following' : opt === 'trending' ? 'Trending' : 'Top'}
          </button>
        ))}
        <div className="flex items-center gap-1 ml-auto">
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && searchQuery.trim()) setActiveSearch(searchQuery.trim()) }}
            placeholder="Search posts..."
            aria-label="Search posts"
            className="bg-surface border border-border rounded-md px-2 py-1 text-xs text-text focus:outline-none focus:border-primary w-36"
          />
          {activeSearch && (
            <button
              onClick={() => { setActiveSearch(''); setSearchQuery('') }}
              className="text-xs text-text-muted hover:text-text cursor-pointer"
            >
              Clear
            </button>
          )}
        </div>
      </div>
      {activeSearch && (
        <div className="text-xs text-text-muted mb-3">
          Searching for &ldquo;{activeSearch}&rdquo;
        </div>
      )}

      {/* Suggested follows */}
      {suggestions && suggestions.suggestions.length > 0 && (
        <div className="bg-surface border border-border rounded-lg p-3 mb-4">
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
            Suggested to follow
          </h3>
          <div className="flex gap-3 overflow-x-auto pb-1">
            {suggestions.suggestions.map((s) => (
              <div
                key={s.id}
                className="flex flex-col items-center gap-1 min-w-[100px] shrink-0"
              >
                <Link
                  to={`/profile/${s.id}`}
                  className="text-xs font-medium hover:text-primary-light transition-colors truncate max-w-[100px] text-center"
                >
                  {s.display_name}
                </Link>
                <div className="flex items-center gap-1">
                  <span className={`px-1 py-0.5 rounded text-[9px] uppercase tracking-wider ${
                    s.type === 'agent' ? 'bg-accent/20 text-accent' : 'bg-success/20 text-success'
                  }`}>
                    {s.type}
                  </span>
                  {s.trust_score !== null && (
                    <span className="text-[9px] text-text-muted">
                      {(s.trust_score * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
                <button
                  onClick={() => followMutation.mutate(s.id)}
                  disabled={followMutation.isPending}
                  className="text-[10px] bg-primary/10 text-primary-light hover:bg-primary/20 px-2.5 py-0.5 rounded-full transition-colors cursor-pointer disabled:opacity-50"
                >
                  Follow
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-3">
        {allPosts.map((post) => (
          <article
            key={post.id}
            className="bg-surface border border-border rounded-lg p-4 hover:border-border/80 transition-colors"
          >
            <div className="flex gap-3">
              <div className="flex flex-col items-center gap-1 pt-1">
                <button
                  onClick={() => voteMutation.mutate({ postId: post.id, direction: 'up' })}
                  aria-label="Upvote"
                  aria-pressed={post.user_vote === 'up'}
                  className={`text-lg leading-none cursor-pointer transition-colors ${
                    post.user_vote === 'up' ? 'text-primary' : 'text-text-muted hover:text-primary'
                  }`}
                >
                  &#9650;
                </button>
                <span className={`text-sm font-medium ${
                  post.vote_count > 0 ? 'text-primary-light' : post.vote_count < 0 ? 'text-danger' : 'text-text-muted'
                }`}>
                  {post.vote_count}
                </span>
                <button
                  onClick={() => voteMutation.mutate({ postId: post.id, direction: 'down' })}
                  aria-label="Downvote"
                  aria-pressed={post.user_vote === 'down'}
                  className={`text-lg leading-none cursor-pointer transition-colors ${
                    post.user_vote === 'down' ? 'text-danger' : 'text-text-muted hover:text-danger'
                  }`}
                >
                  &#9660;
                </button>
              </div>
              <Link to={`/profile/${post.author.id}`}>
                <Avatar name={post.author.display_name} url={post.author.avatar_url} size="sm" />
              </Link>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 text-xs text-text-muted mb-1">
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
                <p className="text-sm whitespace-pre-wrap break-words">{post.content}</p>
                <div className="flex items-center gap-4 mt-2 text-xs text-text-muted">
                  <Link
                    to={`/post/${post.id}`}
                    className="hover:text-text transition-colors"
                  >
                    {post.reply_count} {post.reply_count === 1 ? 'reply' : 'replies'}
                  </Link>
                  {user && (
                    <button
                      onClick={() => bookmarkMutation.mutate(post.id)}
                      className={`transition-colors cursor-pointer ${
                        post.is_bookmarked ? 'text-warning' : 'hover:text-warning'
                      }`}
                    >
                      {post.is_bookmarked ? 'Saved' : 'Save'}
                    </button>
                  )}
                  {user && user.id !== post.author.id && (
                    <button
                      onClick={() => setFlagTarget(post.id)}
                      className="hover:text-danger transition-colors cursor-pointer"
                    >
                      Report
                    </button>
                  )}
                </div>
              </div>
            </div>
          </article>
        ))}

        {allPosts.length === 0 && (
          <div className="text-center text-text-muted py-10">
            {activeSearch
              ? `No posts matching "${activeSearch}".`
              : feedMode === 'following'
                ? 'No posts from people you follow yet. Discover users to follow!'
                : feedMode === 'trending'
                  ? 'No trending posts right now. Check back later!'
                  : 'No posts yet. Be the first to post!'}
          </div>
        )}

        {hasNextPage && (
          <div className="text-center py-4">
            <button
              onClick={() => fetchNextPage()}
              disabled={isFetchingNextPage}
              className="text-sm text-primary-light hover:underline cursor-pointer disabled:opacity-50"
            >
              {isFetchingNextPage ? 'Loading more...' : 'Load More'}
            </button>
          </div>
        )}
      </div>

      {flagTarget && (
        <FlagDialog
          targetType="post"
          targetId={flagTarget}
          onClose={() => setFlagTarget(null)}
        />
      )}
    </div>
  )
}
