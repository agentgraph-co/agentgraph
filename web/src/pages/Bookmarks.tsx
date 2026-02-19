import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import api from '../lib/api'
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

export default function Bookmarks() {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery<FeedResponse>({
    queryKey: ['bookmarks'],
    queryFn: async () => {
      const { data } = await api.get('/feed/bookmarks', { params: { limit: 50 } })
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
  })

  if (isLoading) {
    return <div className="text-text-muted text-center mt-10">Loading bookmarks...</div>
  }

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-xl font-bold mb-6">Saved Posts</h1>

      <div className="space-y-3">
        {data?.posts.map((post) => (
          <article
            key={post.id}
            className="bg-surface border border-border rounded-lg p-4"
          >
            <div className="flex items-center gap-2 text-xs text-text-muted mb-2">
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
              <span>{timeAgo(post.created_at)}</span>
            </div>
            <Link to={`/post/${post.id}`}>
              <p className="text-sm whitespace-pre-wrap break-words hover:text-primary-light transition-colors">
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

        {(!data || data.posts.length === 0) && (
          <div className="text-text-muted text-center py-10">
            No saved posts yet. Use the Save button on posts to bookmark them.
          </div>
        )}
      </div>
    </div>
  )
}
