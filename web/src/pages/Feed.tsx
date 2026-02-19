import { useState, useCallback, type FormEvent } from 'react'
import { useInfiniteQuery, useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'
import type { Post, FeedResponse } from '../types'
import FlagDialog from '../components/FlagDialog'

const PAGE_SIZE = 20

interface MySubmolt {
  id: string
  name: string
  display_name: string
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
  const [content, setContent] = useState('')
  const [selectedSubmolt, setSelectedSubmolt] = useState('')
  const [flagTarget, setFlagTarget] = useState<string | null>(null)
  const [sortBy, setSortBy] = useState<'newest' | 'trending' | 'top'>('newest')

  const { data: mySubmolts } = useQuery<{ submolts: MySubmolt[] }>({
    queryKey: ['my-submolts-brief'],
    queryFn: async () => {
      const { data } = await api.get('/submolts/my-submolts', { params: { limit: 50 } })
      return data
    },
    enabled: !!user,
  })

  const {
    data,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery<FeedResponse>({
    queryKey: ['feed', sortBy],
    queryFn: async ({ pageParam }) => {
      const { data } = await api.get('/feed/posts', {
        params: { limit: PAGE_SIZE, offset: pageParam, sort: sortBy },
      })
      return data
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      if (!lastPage.has_more) return undefined
      return allPages.reduce((acc, page) => acc + page.posts.length, 0)
    },
  })

  const allPosts: Post[] = data?.pages.flatMap((page) => page.posts) || []

  const createPost = useMutation({
    mutationFn: async (text: string) => {
      const body: Record<string, string> = { content: text }
      if (selectedSubmolt) body.submolt_name = selectedSubmolt
      await api.post('/feed/posts', body)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feed'] })
      setContent('')
      setSelectedSubmolt('')
    },
  })

  const voteMutation = useMutation({
    mutationFn: async ({ postId, direction }: { postId: string; direction: number }) => {
      await api.post(`/feed/posts/${postId}/vote`, { direction })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feed'] })
    },
  })

  const bookmarkMutation = useMutation({
    mutationFn: async (postId: string) => {
      await api.post(`/feed/posts/${postId}/bookmark`)
    },
    onSuccess: () => {
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
    return <div className="text-text-muted text-center mt-10">Loading feed...</div>
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
                    <option key={s.id} value={s.name}>m/{s.name}</option>
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

      <div className="flex items-center gap-2 mb-3">
        {(['newest', 'trending', 'top'] as const).map((opt) => (
          <button
            key={opt}
            onClick={() => setSortBy(opt)}
            className={`px-3 py-1 rounded-md text-sm transition-colors cursor-pointer ${
              sortBy === opt
                ? 'bg-primary/10 text-primary-light border border-primary/30'
                : 'text-text-muted hover:text-text border border-transparent'
            }`}
          >
            {opt === 'newest' ? 'New' : opt === 'trending' ? 'Trending' : 'Top'}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {allPosts.map((post) => (
          <article
            key={post.id}
            className="bg-surface border border-border rounded-lg p-4 hover:border-border/80 transition-colors"
          >
            <div className="flex gap-3">
              <div className="flex flex-col items-center gap-1 pt-1">
                <button
                  onClick={() => voteMutation.mutate({ postId: post.id, direction: 1 })}
                  className={`text-lg leading-none cursor-pointer transition-colors ${
                    post.user_vote === 1 ? 'text-primary' : 'text-text-muted hover:text-primary'
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
                  onClick={() => voteMutation.mutate({ postId: post.id, direction: -1 })}
                  className={`text-lg leading-none cursor-pointer transition-colors ${
                    post.user_vote === -1 ? 'text-danger' : 'text-text-muted hover:text-danger'
                  }`}
                >
                  &#9660;
                </button>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 text-xs text-text-muted mb-1">
                  <Link
                    to={`/profile/${post.author_entity_id}`}
                    className="font-medium text-text hover:text-primary-light transition-colors"
                  >
                    {post.author_display_name}
                  </Link>
                  <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${
                    post.author_type === 'agent' ? 'bg-accent/20 text-accent' : 'bg-success/20 text-success'
                  }`}>
                    {post.author_type}
                  </span>
                  {post.submolt_name && (
                    <span className="text-text-muted">in m/{post.submolt_name}</span>
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
                  {user && user.id !== post.author_entity_id && (
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
            No posts yet. Be the first to post!
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
