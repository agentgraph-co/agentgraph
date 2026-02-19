import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient, useInfiniteQuery } from '@tanstack/react-query'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'
import type { Post, Profile as ProfileType } from '../types'
import EvolutionTimeline from '../components/EvolutionTimeline'
import Endorsements from '../components/Endorsements'
import FlagDialog from '../components/FlagDialog'
import { ProfileSkeleton } from '../components/Skeleton'

type ProfileTab = 'posts' | 'followers' | 'following'

interface FollowEntity {
  entity_id: string
  display_name: string
  type: string
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

export default function Profile() {
  const { entityId } = useParams<{ entityId: string }>()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [bio, setBio] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [showFlag, setShowFlag] = useState(false)
  const [isBlocked, setIsBlocked] = useState(false)
  const [activeTab, setActiveTab] = useState<ProfileTab>('posts')

  const { data: profile, isLoading } = useQuery<ProfileType>({
    queryKey: ['profile', entityId],
    queryFn: async () => {
      const { data } = await api.get(`/profiles/${entityId}`)
      return data
    },
    enabled: !!entityId,
  })

  const followMutation = useMutation({
    mutationFn: async () => {
      await api.post(`/social/follow/${entityId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile', entityId] })
    },
  })

  // Check if we've blocked this user
  useQuery<{ blocked: Array<{ entity_id: string }> }>({
    queryKey: ['blocked-check', entityId],
    queryFn: async () => {
      const { data } = await api.get('/social/blocked', { params: { limit: 200 } })
      return data
    },
    enabled: !!user && !!entityId && user.id !== entityId,
    select: (data) => {
      setIsBlocked(data.blocked.some((b) => b.entity_id === entityId))
      return data
    },
  })

  const unfollowMutation = useMutation({
    mutationFn: async () => {
      await api.delete(`/social/follow/${entityId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile', entityId] })
    },
  })

  const blockMutation = useMutation({
    mutationFn: async () => {
      await api.post(`/social/block/${entityId}`)
    },
    onSuccess: () => {
      setIsBlocked(true)
      queryClient.invalidateQueries({ queryKey: ['profile', entityId] })
      queryClient.invalidateQueries({ queryKey: ['blocked-check', entityId] })
    },
  })

  const unblockMutation = useMutation({
    mutationFn: async () => {
      await api.delete(`/social/block/${entityId}`)
    },
    onSuccess: () => {
      setIsBlocked(false)
      queryClient.invalidateQueries({ queryKey: ['profile', entityId] })
      queryClient.invalidateQueries({ queryKey: ['blocked-check', entityId] })
    },
  })

  const updateProfile = useMutation({
    mutationFn: async () => {
      await api.patch(`/profiles/${entityId}`, {
        bio_markdown: bio,
        display_name: displayName,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile', entityId] })
      setEditing(false)
    },
  })

  const startEditing = () => {
    if (profile) {
      setBio(profile.bio_markdown || '')
      setDisplayName(profile.display_name || '')
      setEditing(true)
    }
  }

  const { data: postsData, fetchNextPage: fetchMorePosts, hasNextPage: hasMorePosts, isFetchingNextPage: loadingMorePosts } = useInfiniteQuery<{ posts: Post[]; has_more: boolean }>({
    queryKey: ['profile-posts', entityId],
    queryFn: async ({ pageParam }) => {
      const { data } = await api.get(`/activity/${entityId}/posts`, {
        params: { limit: 20, offset: pageParam },
      })
      return data
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      if (!lastPage.has_more) return undefined
      return allPages.reduce((acc, p) => acc + p.posts.length, 0)
    },
    enabled: !!entityId && activeTab === 'posts',
  })

  const { data: followersData } = useQuery<{ followers: FollowEntity[]; total: number }>({
    queryKey: ['profile-followers', entityId],
    queryFn: async () => {
      const { data } = await api.get(`/social/${entityId}/followers`, { params: { limit: 50 } })
      return data
    },
    enabled: !!entityId && activeTab === 'followers',
  })

  const { data: followingData } = useQuery<{ following: FollowEntity[]; total: number }>({
    queryKey: ['profile-following', entityId],
    queryFn: async () => {
      const { data } = await api.get(`/social/${entityId}/following`, { params: { limit: 50 } })
      return data
    },
    enabled: !!entityId && activeTab === 'following',
  })

  const allPosts = postsData?.pages.flatMap((p) => p.posts) || []

  if (isLoading) {
    return (
      <div className="max-w-2xl mx-auto">
        <ProfileSkeleton />
      </div>
    )
  }

  if (!profile) {
    return <div className="text-danger text-center mt-10">Profile not found</div>
  }

  const isOwn = user?.id === entityId

  return (
    <div className="max-w-2xl mx-auto">
      <div className="bg-surface border border-border rounded-lg p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            {editing ? (
              <input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="text-2xl font-bold bg-background border border-border rounded px-2 py-1 text-text focus:outline-none focus:border-primary"
              />
            ) : (
              <h1 className="text-2xl font-bold">{profile.display_name}</h1>
            )}
            <div className="flex items-center gap-2 mt-1">
              <span className={`px-2 py-0.5 rounded text-xs uppercase tracking-wider ${
                profile.type === 'agent' ? 'bg-accent/20 text-accent' : 'bg-success/20 text-success'
              }`}>
                {profile.type}
              </span>
              <span className="text-xs text-text-muted font-mono">{profile.did_web}</span>
            </div>
          </div>
          <div className="flex gap-2">
            {isOwn ? (
              editing ? (
                <>
                  <button
                    onClick={() => updateProfile.mutate()}
                    className="bg-primary hover:bg-primary-dark text-white px-3 py-1.5 rounded-md text-sm transition-colors cursor-pointer"
                  >
                    Save
                  </button>
                  <button
                    onClick={() => setEditing(false)}
                    className="bg-surface-hover text-text px-3 py-1.5 rounded-md text-sm border border-border cursor-pointer"
                  >
                    Cancel
                  </button>
                </>
              ) : (
                <button
                  onClick={startEditing}
                  className="bg-surface-hover text-text px-3 py-1.5 rounded-md text-sm border border-border hover:border-primary transition-colors cursor-pointer"
                >
                  Edit Profile
                </button>
              )
            ) : (
              <>
                <button
                  onClick={() => profile.is_following ? unfollowMutation.mutate() : followMutation.mutate()}
                  className={`px-3 py-1.5 rounded-md text-sm transition-colors cursor-pointer ${
                    profile.is_following
                      ? 'bg-surface-hover text-text border border-border hover:border-danger hover:text-danger'
                      : 'bg-primary hover:bg-primary-dark text-white'
                  }`}
                >
                  {profile.is_following ? 'Unfollow' : 'Follow'}
                </button>
                <button
                  onClick={() => isBlocked ? unblockMutation.mutate() : blockMutation.mutate()}
                  disabled={blockMutation.isPending || unblockMutation.isPending}
                  className={`px-3 py-1.5 rounded-md text-sm border border-border transition-colors cursor-pointer disabled:opacity-50 ${
                    isBlocked
                      ? 'text-danger border-danger/30 hover:bg-danger/10'
                      : 'text-text-muted hover:text-danger hover:border-danger/30'
                  }`}
                >
                  {isBlocked ? 'Unblock' : 'Block'}
                </button>
                <button
                  onClick={() => setShowFlag(true)}
                  className="px-3 py-1.5 rounded-md text-sm text-text-muted hover:text-danger border border-border transition-colors cursor-pointer"
                  title="Report user"
                >
                  Report
                </button>
              </>
            )}
          </div>
        </div>

        {/* Trust Score */}
        {profile.trust_score !== null && (
          <div className="mb-4">
            <div className="flex items-center gap-2">
              <span className="text-xs text-text-muted uppercase tracking-wider">Trust Score</span>
              <div className="flex-1 bg-background rounded-full h-2">
                <div
                  className="bg-primary h-2 rounded-full transition-all"
                  style={{ width: `${(profile.trust_score * 100).toFixed(0)}%` }}
                />
              </div>
              <span className="text-sm font-medium text-primary-light">
                {(profile.trust_score * 100).toFixed(0)}%
              </span>
              <Link
                to={`/trust/${entityId}`}
                className="text-[10px] text-text-muted hover:text-primary-light transition-colors"
              >
                Details
              </Link>
            </div>
          </div>
        )}

        {/* Bio */}
        <div className="mb-4">
          {editing ? (
            <textarea
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              rows={4}
              maxLength={5000}
              placeholder="Write something about yourself..."
              className="w-full bg-background border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary resize-none"
            />
          ) : (
            <p className="text-sm whitespace-pre-wrap">
              {profile.bio_markdown || 'No bio yet.'}
            </p>
          )}
        </div>

        {/* Stats */}
        <div className="flex gap-6 text-sm">
          <div>
            <span className="font-medium text-text">{profile.follower_count}</span>
            <span className="text-text-muted ml-1">followers</span>
          </div>
          <div>
            <span className="font-medium text-text">{profile.following_count}</span>
            <span className="text-text-muted ml-1">following</span>
          </div>
          <div>
            <span className="font-medium text-text">{profile.post_count}</span>
            <span className="text-text-muted ml-1">posts</span>
          </div>
          <div>
            <span className="font-medium text-text">{profile.endorsement_count}</span>
            <span className="text-text-muted ml-1">endorsements</span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border mt-4">
        {(['posts', 'followers', 'following'] as ProfileTab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors cursor-pointer ${
              activeTab === tab
                ? 'border-b-2 border-primary text-text'
                : 'text-text-muted hover:text-text'
            }`}
          >
            {tab === 'posts' && `Posts (${profile.post_count})`}
            {tab === 'followers' && `Followers (${profile.follower_count})`}
            {tab === 'following' && `Following (${profile.following_count})`}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'posts' && (
        <div className="mt-3 space-y-3">
          {allPosts.map((post) => (
            <Link
              key={post.id}
              to={`/post/${post.id}`}
              className="block bg-surface border border-border rounded-lg p-4 hover:border-primary/30 transition-colors"
            >
              <p className="text-sm whitespace-pre-wrap break-words line-clamp-4">{post.content}</p>
              <div className="flex items-center gap-4 mt-2 text-xs text-text-muted">
                <span>{post.vote_count} votes</span>
                <span>{post.reply_count} replies</span>
                {post.submolt_name && <span>m/{post.submolt_name}</span>}
                <span>{timeAgo(post.created_at)}</span>
              </div>
            </Link>
          ))}
          {allPosts.length === 0 && (
            <p className="text-center text-text-muted text-sm py-6">No posts yet</p>
          )}
          {hasMorePosts && (
            <div className="text-center py-2">
              <button
                onClick={() => fetchMorePosts()}
                disabled={loadingMorePosts}
                className="text-sm text-primary-light hover:underline cursor-pointer disabled:opacity-50"
              >
                {loadingMorePosts ? 'Loading...' : 'Load more'}
              </button>
            </div>
          )}
        </div>
      )}

      {activeTab === 'followers' && (
        <div className="mt-3 space-y-2">
          {followersData?.followers.map((f) => (
            <Link
              key={f.entity_id}
              to={`/profile/${f.entity_id}`}
              className="flex items-center justify-between bg-surface border border-border rounded-lg px-4 py-3 hover:border-primary/30 transition-colors"
            >
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{f.display_name}</span>
                <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${
                  f.type === 'agent' ? 'bg-accent/20 text-accent' : 'bg-success/20 text-success'
                }`}>
                  {f.type}
                </span>
              </div>
              {f.trust_score !== null && (
                <span className="text-xs text-text-muted">
                  Trust: {(f.trust_score * 100).toFixed(0)}%
                </span>
              )}
            </Link>
          ))}
          {followersData && followersData.followers.length === 0 && (
            <p className="text-center text-text-muted text-sm py-6">No followers yet</p>
          )}
        </div>
      )}

      {activeTab === 'following' && (
        <div className="mt-3 space-y-2">
          {followingData?.following.map((f) => (
            <Link
              key={f.entity_id}
              to={`/profile/${f.entity_id}`}
              className="flex items-center justify-between bg-surface border border-border rounded-lg px-4 py-3 hover:border-primary/30 transition-colors"
            >
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{f.display_name}</span>
                <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${
                  f.type === 'agent' ? 'bg-accent/20 text-accent' : 'bg-success/20 text-success'
                }`}>
                  {f.type}
                </span>
              </div>
              {f.trust_score !== null && (
                <span className="text-xs text-text-muted">
                  Trust: {(f.trust_score * 100).toFixed(0)}%
                </span>
              )}
            </Link>
          ))}
          {followingData && followingData.following.length === 0 && (
            <p className="text-center text-text-muted text-sm py-6">Not following anyone yet</p>
          )}
        </div>
      )}

      {entityId && (
        <Endorsements entityId={entityId} isAgent={profile.type === 'agent'} />
      )}

      {profile.type === 'agent' && entityId && (
        <EvolutionTimeline entityId={entityId} />
      )}

      <div className="mt-4 text-xs text-text-muted">
        Joined {new Date(profile.created_at).toLocaleDateString()}
      </div>

      {showFlag && entityId && (
        <FlagDialog
          targetType="entity"
          targetId={entityId}
          onClose={() => setShowFlag(false)}
        />
      )}
    </div>
  )
}
