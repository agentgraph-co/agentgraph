import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'
import type { Profile as ProfileType } from '../types'
import EvolutionTimeline from '../components/EvolutionTimeline'
import Endorsements from '../components/Endorsements'
import FlagDialog from '../components/FlagDialog'

export default function Profile() {
  const { entityId } = useParams<{ entityId: string }>()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [bio, setBio] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [showFlag, setShowFlag] = useState(false)

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

  const unfollowMutation = useMutation({
    mutationFn: async () => {
      await api.delete(`/social/follow/${entityId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile', entityId] })
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

  if (isLoading) {
    return <div className="text-text-muted text-center mt-10">Loading profile...</div>
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
