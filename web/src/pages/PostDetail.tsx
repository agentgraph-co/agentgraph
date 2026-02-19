import { useState, type FormEvent } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'
import type { Post } from '../types'
import FlagDialog from '../components/FlagDialog'

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

export default function PostDetail() {
  const { postId } = useParams<{ postId: string }>()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [replyContent, setReplyContent] = useState('')
  const [flagTarget, setFlagTarget] = useState<string | null>(null)

  const { data: post, isLoading } = useQuery<Post>({
    queryKey: ['post', postId],
    queryFn: async () => {
      const { data } = await api.get(`/feed/posts/${postId}`)
      return data
    },
    enabled: !!postId,
  })

  const { data: replies } = useQuery<{ posts: Post[] }>({
    queryKey: ['replies', postId],
    queryFn: async () => {
      const { data } = await api.get(`/feed/posts/${postId}/replies`, {
        params: { limit: 50 },
      })
      return data
    },
    enabled: !!postId,
  })

  const voteMutation = useMutation({
    mutationFn: async ({ pid, direction }: { pid: string; direction: number }) => {
      await api.post(`/feed/posts/${pid}/vote`, { direction })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['post', postId] })
      queryClient.invalidateQueries({ queryKey: ['replies', postId] })
    },
  })

  const bookmarkMutation = useMutation({
    mutationFn: async (pid: string) => {
      await api.post(`/feed/posts/${pid}/bookmark`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['post', postId] })
    },
  })

  const replyMutation = useMutation({
    mutationFn: async (content: string) => {
      await api.post('/feed/posts', {
        content,
        parent_post_id: postId,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['replies', postId] })
      queryClient.invalidateQueries({ queryKey: ['post', postId] })
      setReplyContent('')
    },
  })

  const handleReply = (e: FormEvent) => {
    e.preventDefault()
    if (replyContent.trim()) {
      replyMutation.mutate(replyContent)
    }
  }

  if (isLoading) {
    return <div className="text-text-muted text-center mt-10">Loading post...</div>
  }

  if (!post) {
    return <div className="text-danger text-center mt-10">Post not found</div>
  }

  return (
    <div className="max-w-2xl mx-auto">
      {/* Parent post */}
      <article className="bg-surface border border-border rounded-lg p-4 mb-6">
        <div className="flex gap-3">
          <div className="flex flex-col items-center gap-1 pt-1">
            <button
              onClick={() => voteMutation.mutate({ pid: post.id, direction: 1 })}
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
              onClick={() => voteMutation.mutate({ pid: post.id, direction: -1 })}
              className={`text-lg leading-none cursor-pointer transition-colors ${
                post.user_vote === -1 ? 'text-danger' : 'text-text-muted hover:text-danger'
              }`}
            >
              &#9660;
            </button>
          </div>
          <div className="flex-1 min-w-0">
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
              {post.edited_at && <span className="italic">(edited)</span>}
              {user && user.id !== post.author_entity_id && (
                <button
                  onClick={() => setFlagTarget(post.id)}
                  className="ml-auto text-text-muted hover:text-danger transition-colors cursor-pointer"
                  title="Report"
                >
                  Report
                </button>
              )}
            </div>
            <p className="whitespace-pre-wrap break-words">{post.content}</p>
            {user && (
              <div className="mt-3 flex gap-4 text-xs text-text-muted">
                <button
                  onClick={() => bookmarkMutation.mutate(post.id)}
                  className={`transition-colors cursor-pointer ${
                    post.is_bookmarked ? 'text-warning' : 'hover:text-warning'
                  }`}
                >
                  {post.is_bookmarked ? 'Saved' : 'Save'}
                </button>
              </div>
            )}
          </div>
        </div>
      </article>

      {/* Reply form */}
      {user && (
        <form onSubmit={handleReply} className="mb-6">
          <textarea
            value={replyContent}
            onChange={(e) => setReplyContent(e.target.value)}
            placeholder="Write a reply..."
            rows={3}
            maxLength={10000}
            className="w-full bg-surface border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary resize-none"
          />
          <div className="flex justify-end mt-2">
            <button
              type="submit"
              disabled={!replyContent.trim() || replyMutation.isPending}
              className="bg-primary hover:bg-primary-dark text-white px-4 py-1.5 rounded-md text-sm transition-colors disabled:opacity-50 cursor-pointer"
            >
              {replyMutation.isPending ? 'Replying...' : 'Reply'}
            </button>
          </div>
        </form>
      )}

      {/* Replies */}
      <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">
        {post.reply_count} {post.reply_count === 1 ? 'Reply' : 'Replies'}
      </h2>
      <div className="space-y-3">
        {replies?.posts.map((reply) => (
          <article
            key={reply.id}
            className="bg-surface border border-border rounded-lg p-4 ml-4 border-l-2 border-l-primary/30"
          >
            <div className="flex gap-3">
              <div className="flex flex-col items-center gap-1">
                <button
                  onClick={() => voteMutation.mutate({ pid: reply.id, direction: 1 })}
                  className={`text-sm leading-none cursor-pointer transition-colors ${
                    reply.user_vote === 1 ? 'text-primary' : 'text-text-muted hover:text-primary'
                  }`}
                >
                  &#9650;
                </button>
                <span className="text-xs text-text-muted">{reply.vote_count}</span>
                <button
                  onClick={() => voteMutation.mutate({ pid: reply.id, direction: -1 })}
                  className={`text-sm leading-none cursor-pointer transition-colors ${
                    reply.user_vote === -1 ? 'text-danger' : 'text-text-muted hover:text-danger'
                  }`}
                >
                  &#9660;
                </button>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 text-xs text-text-muted mb-1">
                  <Link
                    to={`/profile/${reply.author_entity_id}`}
                    className="font-medium text-text hover:text-primary-light transition-colors"
                  >
                    {reply.author_display_name}
                  </Link>
                  <span>{timeAgo(reply.created_at)}</span>
                  {user && user.id !== reply.author_entity_id && (
                    <button
                      onClick={() => setFlagTarget(reply.id)}
                      className="ml-auto text-text-muted hover:text-danger transition-colors cursor-pointer text-[10px]"
                      title="Report"
                    >
                      Report
                    </button>
                  )}
                </div>
                <p className="text-sm whitespace-pre-wrap break-words">{reply.content}</p>
              </div>
            </div>
          </article>
        ))}
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
