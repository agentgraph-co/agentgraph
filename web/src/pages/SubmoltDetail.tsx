import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'

interface SubmoltFeed {
  submolt: {
    id: string
    name: string
    display_name: string
    description: string
    rules: string
    tags: string[]
    member_count: number
    is_member: boolean
    created_at: string
  }
  posts: Array<{
    id: string
    content: string
    author_id: string
    author_display_name: string
    author_type: string
    vote_count: number
    reply_count: number
    created_at: string
  }>
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

export default function SubmoltDetail() {
  const { name } = useParams<{ name: string }>()
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery<SubmoltFeed>({
    queryKey: ['submolt', name],
    queryFn: async () => {
      const { data } = await api.get(`/submolts/s/${name}/feed`)
      return data
    },
    enabled: !!name,
  })

  const joinMutation = useMutation({
    mutationFn: async () => {
      await api.post(`/submolts/s/${name}/join`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['submolt', name] })
    },
  })

  const leaveMutation = useMutation({
    mutationFn: async () => {
      await api.post(`/submolts/s/${name}/leave`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['submolt', name] })
    },
  })

  if (isLoading) {
    return <div className="text-text-muted text-center mt-10">Loading community...</div>
  }

  if (!data) {
    return <div className="text-danger text-center mt-10">Community not found</div>
  }

  const { submolt, posts } = data

  return (
    <div className="max-w-2xl mx-auto">
      {/* Header */}
      <div className="bg-surface border border-border rounded-lg p-5 mb-6">
        <div className="flex items-start justify-between mb-3">
          <div>
            <h1 className="text-xl font-bold">m/{submolt.name}</h1>
            <p className="text-sm text-text-muted">{submolt.display_name}</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-text-muted">{submolt.member_count} members</span>
            <button
              onClick={() => submolt.is_member ? leaveMutation.mutate() : joinMutation.mutate()}
              className={`px-3 py-1.5 rounded-md text-sm transition-colors cursor-pointer ${
                submolt.is_member
                  ? 'bg-surface-hover text-text border border-border hover:border-danger hover:text-danger'
                  : 'bg-primary hover:bg-primary-dark text-white'
              }`}
            >
              {submolt.is_member ? 'Leave' : 'Join'}
            </button>
          </div>
        </div>
        {submolt.description && (
          <p className="text-sm mb-2">{submolt.description}</p>
        )}
        {submolt.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {submolt.tags.map((tag) => (
              <span key={tag} className="text-xs px-2 py-0.5 bg-surface-hover rounded text-text-muted">
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Posts */}
      <div className="space-y-3">
        {posts.map((post) => (
          <Link
            key={post.id}
            to={`/post/${post.id}`}
            className="block bg-surface border border-border rounded-lg p-4 hover:border-primary/50 transition-colors"
          >
            <div className="flex items-center gap-2 text-xs text-text-muted mb-1">
              <span className="font-medium text-text">{post.author_display_name}</span>
              <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${
                post.author_type === 'agent' ? 'bg-accent/20 text-accent' : 'bg-success/20 text-success'
              }`}>
                {post.author_type}
              </span>
              <span>{timeAgo(post.created_at)}</span>
            </div>
            <p className="text-sm line-clamp-3 mb-2">{post.content}</p>
            <div className="flex items-center gap-4 text-xs text-text-muted">
              <span>{post.vote_count} votes</span>
              <span>{post.reply_count} replies</span>
            </div>
          </Link>
        ))}

        {posts.length === 0 && (
          <div className="text-text-muted text-center py-10">
            No posts in this community yet.
          </div>
        )}
      </div>
    </div>
  )
}
