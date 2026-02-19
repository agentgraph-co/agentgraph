import { useState, useEffect, type FormEvent } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'
import type { Post } from '../types'
import FlagDialog from '../components/FlagDialog'
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

export default function PostDetail() {
  const { postId } = useParams<{ postId: string }>()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { addToast } = useToast()
  const [replyContent, setReplyContent] = useState('')
  const [flagTarget, setFlagTarget] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editContent, setEditContent] = useState('')
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [replySort, setReplySort] = useState<'top' | 'newest' | 'oldest'>('top')
  const [replyToId, setReplyToId] = useState<string | null>(null)
  const [nestedReplyContent, setNestedReplyContent] = useState('')
  const [showEdits, setShowEdits] = useState<string | null>(null)

  const { data: post, isLoading, isError, refetch } = useQuery<Post>({
    queryKey: ['post', postId],
    queryFn: async () => {
      const { data } = await api.get(`/feed/posts/${postId}`)
      return data
    },
    enabled: !!postId,
  })

  useEffect(() => {
    document.title = post ? `Post by ${post.author.display_name} - AgentGraph` : 'Post - AgentGraph'
  }, [post])

  const { data: replies } = useQuery<{ posts: Post[] }>({
    queryKey: ['replies', postId, replySort],
    queryFn: async () => {
      const { data } = await api.get(`/feed/posts/${postId}/replies`, {
        params: { limit: 100, sort: replySort },
      })
      return data
    },
    enabled: !!postId,
  })

  interface EditHistoryItem {
    id: string
    previous_content: string
    new_content: string
    edited_at: string
  }

  const { data: editHistory } = useQuery<{ edits: EditHistoryItem[]; edit_count: number }>({
    queryKey: ['post-edits', showEdits],
    queryFn: async () => {
      const { data } = await api.get(`/feed/posts/${showEdits}/edits`)
      return data
    },
    enabled: !!showEdits,
  })

  const applyVoteOptimistic = (p: Post, direction: 'up' | 'down'): Post => {
    const wasVoted = p.user_vote === direction
    let delta = 0
    if (wasVoted) delta = direction === 'up' ? -1 : 1
    else if (p.user_vote === null) delta = direction === 'up' ? 1 : -1
    else delta = direction === 'up' ? 2 : -2
    return { ...p, user_vote: wasVoted ? null : direction, vote_count: p.vote_count + delta }
  }

  const voteMutation = useMutation({
    mutationFn: async ({ pid, direction }: { pid: string; direction: 'up' | 'down' }) => {
      await api.post(`/feed/posts/${pid}/vote`, { direction })
    },
    onMutate: async ({ pid, direction }) => {
      await queryClient.cancelQueries({ queryKey: ['post', postId] })
      await queryClient.cancelQueries({ queryKey: ['replies', postId] })
      const prevPost = queryClient.getQueryData<Post>(['post', postId])
      const prevReplies = queryClient.getQueryData<{ posts: Post[] }>(['replies', postId, replySort])
      if (prevPost && pid === postId) {
        queryClient.setQueryData<Post>(['post', postId], applyVoteOptimistic(prevPost, direction))
      }
      if (prevReplies) {
        queryClient.setQueryData<{ posts: Post[] }>(['replies', postId, replySort], {
          ...prevReplies,
          posts: prevReplies.posts.map((r) => r.id === pid ? applyVoteOptimistic(r, direction) : r),
        })
      }
      return { prevPost, prevReplies }
    },
    onError: (_err, _vars, context) => {
      if (context?.prevPost) queryClient.setQueryData(['post', postId], context.prevPost)
      if (context?.prevReplies) queryClient.setQueryData(['replies', postId, replySort], context.prevReplies)
      addToast('Failed to vote', 'error')
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['post', postId] })
      queryClient.invalidateQueries({ queryKey: ['replies', postId] })
    },
  })

  const bookmarkMutation = useMutation({
    mutationFn: async (pid: string) => {
      await api.post(`/feed/posts/${pid}/bookmark`)
    },
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ['post', postId] })
      const prevPost = queryClient.getQueryData<Post>(['post', postId])
      if (prevPost) {
        queryClient.setQueryData<Post>(['post', postId], { ...prevPost, is_bookmarked: !prevPost.is_bookmarked })
      }
      return { prevPost }
    },
    onError: (_err, _vars, context) => {
      if (context?.prevPost) queryClient.setQueryData(['post', postId], context.prevPost)
      addToast('Failed to save post', 'error')
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['post', postId] })
    },
  })

  const editMutation = useMutation({
    mutationFn: async ({ pid, content }: { pid: string; content: string }) => {
      await api.patch(`/feed/posts/${pid}`, { content })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['post', postId] })
      queryClient.invalidateQueries({ queryKey: ['replies', postId] })
      setEditingId(null)
    },
    onError: () => {
      addToast('Failed to edit post', 'error')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (pid: string) => {
      await api.delete(`/feed/posts/${pid}`)
    },
    onSuccess: (_, pid) => {
      setConfirmDelete(null)
      if (pid === postId) {
        navigate('/feed')
      } else {
        queryClient.invalidateQueries({ queryKey: ['replies', postId] })
        queryClient.invalidateQueries({ queryKey: ['post', postId] })
      }
    },
    onError: () => {
      addToast('Failed to delete post', 'error')
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
    onError: () => {
      addToast('Failed to post reply', 'error')
    },
  })

  const nestedReplyMutation = useMutation({
    mutationFn: async ({ content, parentId }: { content: string; parentId: string }) => {
      await api.post('/feed/posts', {
        content,
        parent_post_id: parentId,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['replies', postId] })
      queryClient.invalidateQueries({ queryKey: ['post', postId] })
      setNestedReplyContent('')
      setReplyToId(null)
    },
    onError: () => {
      addToast('Failed to post reply', 'error')
    },
  })

  const handleReply = (e: FormEvent) => {
    e.preventDefault()
    if (replyContent.trim()) {
      replyMutation.mutate(replyContent)
    }
  }

  const handleNestedReply = (e: FormEvent, parentId: string) => {
    e.preventDefault()
    if (nestedReplyContent.trim()) {
      nestedReplyMutation.mutate({ content: nestedReplyContent, parentId })
    }
  }

  const startEdit = (p: Post) => {
    setEditingId(p.id)
    setEditContent(p.content)
  }

  const submitEdit = (pid: string) => {
    if (editContent.trim()) {
      editMutation.mutate({ pid, content: editContent })
    }
  }

  if (isLoading) {
    return <div className="text-text-muted text-center mt-10">Loading post...</div>
  }

  if (isError) {
    return (
      <div className="text-center py-10">
        <p className="text-danger mb-2">Failed to load post</p>
        <button onClick={() => refetch()} className="text-sm text-primary-light hover:underline cursor-pointer">Retry</button>
      </div>
    )
  }

  if (!post) {
    return <div className="text-danger text-center mt-10">Post not found</div>
  }

  const isPostOwner = user?.id === post.author.id

  return (
    <div className="max-w-2xl mx-auto">
      <Link to="/feed" className="text-xs text-text-muted hover:text-text transition-colors mb-3 inline-block">&larr; Back to Feed</Link>
      {/* Parent post */}
      <article className="bg-surface border border-border rounded-lg p-4 mb-6">
        <div className="flex gap-3">
          <div className="flex flex-col items-center gap-1 pt-1">
            <button
              onClick={() => voteMutation.mutate({ pid: post.id, direction: 'up' })}
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
              onClick={() => voteMutation.mutate({ pid: post.id, direction: 'down' })}
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
            <Avatar name={post.author.display_name} url={post.author.avatar_url} />
          </Link>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 text-xs text-text-muted mb-2">
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
              <span>{timeAgo(post.created_at)}</span>
              {post.is_edited && (
                <button
                  onClick={() => setShowEdits(showEdits === post.id ? null : post.id)}
                  className="italic hover:text-primary-light transition-colors cursor-pointer"
                >
                  (edited)
                </button>
              )}
              {user && user.id !== post.author.id && (
                <button
                  onClick={() => setFlagTarget(post.id)}
                  className="ml-auto text-text-muted hover:text-danger transition-colors cursor-pointer"
                  title="Report"
                >
                  Report
                </button>
              )}
            </div>

            {editingId === post.id ? (
              <div className="space-y-2">
                <textarea
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  rows={4}
                  maxLength={10000}
                  className="w-full bg-background border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary resize-none"
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => submitEdit(post.id)}
                    disabled={editMutation.isPending}
                    className="bg-primary hover:bg-primary-dark text-white px-3 py-1 rounded-md text-sm transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    {editMutation.isPending ? 'Saving...' : 'Save'}
                  </button>
                  <button
                    onClick={() => setEditingId(null)}
                    className="text-sm text-text-muted hover:text-text cursor-pointer"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <p className="whitespace-pre-wrap break-words">{post.content}</p>
            )}

            {/* Edit history */}
            {showEdits === post.id && editHistory && (
              <div className="mt-3 bg-background rounded-md p-3 space-y-3">
                <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                  Edit History ({editHistory.edit_count} edit{editHistory.edit_count !== 1 ? 's' : ''})
                </h4>
                {editHistory.edits.map((edit) => (
                  <div key={edit.id} className="border-l-2 border-border pl-3">
                    <div className="text-[10px] text-text-muted mb-1">{timeAgo(edit.edited_at)}</div>
                    <div className="text-xs">
                      <div className="bg-danger/5 rounded p-1.5 mb-1">
                        <span className="text-[10px] text-danger font-medium">Before:</span>
                        <p className="text-text-muted whitespace-pre-wrap break-words line-clamp-4">{edit.previous_content}</p>
                      </div>
                      <div className="bg-success/5 rounded p-1.5">
                        <span className="text-[10px] text-success font-medium">After:</span>
                        <p className="text-text-muted whitespace-pre-wrap break-words line-clamp-4">{edit.new_content}</p>
                      </div>
                    </div>
                  </div>
                ))}
                {editHistory.edits.length === 0 && (
                  <div className="text-xs text-text-muted">No edit history available</div>
                )}
              </div>
            )}

            {user && editingId !== post.id && (
              <div className="mt-3 flex gap-4 text-xs text-text-muted">
                <button
                  onClick={() => bookmarkMutation.mutate(post.id)}
                  className={`transition-colors cursor-pointer ${
                    post.is_bookmarked ? 'text-warning' : 'hover:text-warning'
                  }`}
                >
                  {post.is_bookmarked ? 'Saved' : 'Save'}
                </button>
                {isPostOwner && (
                  <>
                    <button
                      onClick={() => startEdit(post)}
                      className="hover:text-primary-light transition-colors cursor-pointer"
                    >
                      Edit
                    </button>
                    {confirmDelete === post.id ? (
                      <span className="flex gap-2">
                        <button
                          onClick={() => deleteMutation.mutate(post.id)}
                          className="text-danger cursor-pointer"
                        >
                          Confirm delete
                        </button>
                        <button
                          onClick={() => setConfirmDelete(null)}
                          className="cursor-pointer"
                        >
                          Cancel
                        </button>
                      </span>
                    ) : (
                      <button
                        onClick={() => setConfirmDelete(post.id)}
                        className="hover:text-danger transition-colors cursor-pointer"
                      >
                        Delete
                      </button>
                    )}
                  </>
                )}
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
            onKeyDown={(e) => {
              if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && replyContent.trim()) {
                e.preventDefault()
                replyMutation.mutate(replyContent.trim())
              }
            }}
            placeholder="Write a reply..."
            rows={3}
            maxLength={10000}
            className="w-full bg-surface border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary resize-none"
          />
          <div className="flex justify-between items-center mt-2">
            <span className="text-[10px] text-text-muted">{replyContent.length}/10000</span>
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

      {/* Replies header + sort */}
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
          {post.reply_count} {post.reply_count === 1 ? 'Reply' : 'Replies'}
        </h2>
        <div className="flex gap-1">
          {(['top', 'newest', 'oldest'] as const).map((opt) => (
            <button
              key={opt}
              onClick={() => setReplySort(opt)}
              className={`px-2 py-1 rounded text-xs transition-colors cursor-pointer ${
                replySort === opt
                  ? 'bg-primary/10 text-primary-light'
                  : 'text-text-muted hover:text-text'
              }`}
            >
              {opt === 'top' ? 'Top' : opt === 'newest' ? 'Newest' : 'Oldest'}
            </button>
          ))}
        </div>
      </div>
      <div className="space-y-3">
        {replies?.posts.map((reply) => {
          const isReplyOwner = user?.id === reply.author.id
          return (
            <article
              key={reply.id}
              className="bg-surface border border-border rounded-lg p-4 ml-4 border-l-2 border-l-primary/30"
            >
              <div className="flex gap-3">
                <div className="flex flex-col items-center gap-1">
                  <button
                    onClick={() => voteMutation.mutate({ pid: reply.id, direction: 'up' })}
                    aria-label="Upvote reply"
                    className={`text-sm leading-none cursor-pointer transition-colors ${
                      reply.user_vote === 'up' ? 'text-primary' : 'text-text-muted hover:text-primary'
                    }`}
                  >
                    &#9650;
                  </button>
                  <span className="text-xs text-text-muted">{reply.vote_count}</span>
                  <button
                    onClick={() => voteMutation.mutate({ pid: reply.id, direction: 'down' })}
                    aria-label="Downvote reply"
                    className={`text-sm leading-none cursor-pointer transition-colors ${
                      reply.user_vote === 'down' ? 'text-danger' : 'text-text-muted hover:text-danger'
                    }`}
                  >
                    &#9660;
                  </button>
                </div>
                <Link to={`/profile/${reply.author.id}`}>
                  <Avatar name={reply.author.display_name} url={reply.author.avatar_url} size="sm" />
                </Link>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 text-xs text-text-muted mb-1">
                    <Link
                      to={`/profile/${reply.author.id}`}
                      className="font-medium text-text hover:text-primary-light transition-colors"
                    >
                      {reply.author.display_name}
                    </Link>
                    <span>{timeAgo(reply.created_at)}</span>
                    {reply.is_edited && <span className="italic">(edited)</span>}
                    {user && user.id !== reply.author.id && (
                      <button
                        onClick={() => setFlagTarget(reply.id)}
                        className="ml-auto text-text-muted hover:text-danger transition-colors cursor-pointer text-[10px]"
                        title="Report"
                      >
                        Report
                      </button>
                    )}
                  </div>

                  {editingId === reply.id ? (
                    <div className="space-y-2">
                      <textarea
                        value={editContent}
                        onChange={(e) => setEditContent(e.target.value)}
                        rows={3}
                        maxLength={10000}
                        className="w-full bg-background border border-border rounded-md px-3 py-2 text-text text-sm focus:outline-none focus:border-primary resize-none"
                      />
                      <span className="text-[10px] text-text-muted">{editContent.length}/10000</span>
                      <div className="flex gap-2">
                        <button
                          onClick={() => submitEdit(reply.id)}
                          disabled={editMutation.isPending}
                          className="bg-primary hover:bg-primary-dark text-white px-3 py-1 rounded-md text-xs transition-colors disabled:opacity-50 cursor-pointer"
                        >
                          Save
                        </button>
                        <button
                          onClick={() => setEditingId(null)}
                          className="text-xs text-text-muted hover:text-text cursor-pointer"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm whitespace-pre-wrap break-words">{reply.content}</p>
                  )}

                  <div className="mt-2 flex gap-3 text-xs text-text-muted">
                    {user && (
                      <button
                        onClick={() => {
                          setReplyToId(replyToId === reply.id ? null : reply.id)
                          setNestedReplyContent('')
                        }}
                        className="hover:text-primary-light transition-colors cursor-pointer"
                      >
                        Reply
                      </button>
                    )}
                    {isReplyOwner && editingId !== reply.id && (
                      <>
                        <button
                          onClick={() => startEdit(reply)}
                          className="hover:text-primary-light transition-colors cursor-pointer"
                        >
                          Edit
                        </button>
                        {confirmDelete === reply.id ? (
                          <span className="flex gap-2">
                            <button
                              onClick={() => deleteMutation.mutate(reply.id)}
                              className="text-danger cursor-pointer"
                            >
                              Confirm
                            </button>
                            <button
                              onClick={() => setConfirmDelete(null)}
                              className="cursor-pointer"
                            >
                              Cancel
                            </button>
                          </span>
                        ) : (
                          <button
                            onClick={() => setConfirmDelete(reply.id)}
                            className="hover:text-danger transition-colors cursor-pointer"
                          >
                            Delete
                          </button>
                        )}
                      </>
                    )}
                  </div>

                  {/* Inline nested reply form */}
                  {replyToId === reply.id && (
                    <form
                      onSubmit={(e) => handleNestedReply(e, reply.id)}
                      className="mt-3 space-y-2"
                    >
                      <textarea
                        value={nestedReplyContent}
                        onChange={(e) => setNestedReplyContent(e.target.value)}
                        onKeyDown={(e) => {
                          if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && nestedReplyContent.trim()) {
                            e.preventDefault()
                            nestedReplyMutation.mutate({ content: nestedReplyContent, parentId: reply.id })
                          }
                        }}
                        placeholder={`Replying to ${reply.author.display_name}...`}
                        rows={2}
                        maxLength={10000}
                        autoFocus
                        className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-primary resize-none"
                      />
                      <div className="flex gap-2">
                        <button
                          type="submit"
                          disabled={!nestedReplyContent.trim() || nestedReplyMutation.isPending}
                          className="bg-primary hover:bg-primary-dark text-white px-3 py-1 rounded-md text-xs transition-colors disabled:opacity-50 cursor-pointer"
                        >
                          {nestedReplyMutation.isPending ? 'Replying...' : 'Reply'}
                        </button>
                        <button
                          type="button"
                          onClick={() => setReplyToId(null)}
                          className="text-xs text-text-muted hover:text-text cursor-pointer"
                        >
                          Cancel
                        </button>
                      </div>
                    </form>
                  )}
                </div>
              </div>
            </article>
          )
        })}
        {replies && replies.posts.length === 0 && (
          <div className="text-text-muted text-center py-6 text-sm">No replies yet. Be the first to respond!</div>
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
