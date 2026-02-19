import { useState, type FormEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'
import type { FeedResponse } from '../types'

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

  const { data, isLoading } = useQuery<FeedResponse>({
    queryKey: ['feed'],
    queryFn: async () => {
      const { data } = await api.get('/feed/posts', { params: { limit: 50 } })
      return data
    },
  })

  const createPost = useMutation({
    mutationFn: async (content: string) => {
      await api.post('/feed/posts', { content })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feed'] })
      setContent('')
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

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (content.trim()) {
      createPost.mutate(content)
    }
  }

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
            <span className="text-xs text-text-muted">{content.length}/10000</span>
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

      <div className="space-y-3">
        {data?.posts.map((post) => (
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
                </div>
              </div>
            </div>
          </article>
        ))}

        {data?.posts.length === 0 && (
          <div className="text-center text-text-muted py-10">
            No posts yet. Be the first to post!
          </div>
        )}
      </div>
    </div>
  )
}
