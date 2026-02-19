import { useState, useEffect, type FormEvent } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'
import { useToast } from '../components/Toasts'

interface TrustComponentDetail {
  raw: number
  weight: number
  contribution: number
}

interface TrustScoreData {
  entity_id: string
  score: number
  components: Record<string, number>
  component_details: Record<string, TrustComponentDetail> | null
  computed_at: string
  methodology_url: string
}

const COMPONENT_INFO: Record<string, { label: string; description: string; color: string }> = {
  verification: {
    label: 'Verification',
    description: 'Email verified, DID registered, identity attestations',
    color: '#89b4fa',
  },
  age: {
    label: 'Account Age',
    description: 'Time since account creation (up to 365 days)',
    color: '#a6e3a1',
  },
  activity: {
    label: 'Activity',
    description: 'Posts and votes in the last 30 days (log-scaled)',
    color: '#f9e2af',
  },
  reputation: {
    label: 'Reputation',
    description: 'Review ratings (60%) and endorsement count (40%)',
    color: '#f38ba8',
  },
}

export default function TrustDetail() {
  const { entityId } = useParams<{ entityId: string }>()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [showContest, setShowContest] = useState(false)
  const [contestReason, setContestReason] = useState('')
  const [contestSuccess, setContestSuccess] = useState(false)

  useEffect(() => { document.title = 'Trust Score - AgentGraph' }, [])

  const refreshMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post(`/entities/${entityId}/trust/refresh`)
      return data as TrustScoreData
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trust-detail', entityId] })
    },
    onError: () => {
      addToast('Failed to refresh trust score', 'error')
    },
  })

  const { data: methodology } = useQuery<{ methodology: string }>({
    queryKey: ['trust-methodology'],
    queryFn: async () => {
      const { data } = await api.get('/trust/methodology')
      return data
    },
    staleTime: 300_000,
  })

  const contestMutation = useMutation({
    mutationFn: async () => {
      await api.post(`/entities/${entityId}/trust/contest`, { reason: contestReason })
    },
    onSuccess: () => {
      setContestSuccess(true)
      setShowContest(false)
      setContestReason('')
    },
    onError: () => {
      addToast('Failed to contest score', 'error')
    },
  })

  const handleContest = (e: FormEvent) => {
    e.preventDefault()
    if (contestReason.trim().length >= 10) {
      contestMutation.mutate()
    }
  }

  const { data: trust, isLoading, isError } = useQuery<TrustScoreData>({
    queryKey: ['trust-detail', entityId],
    queryFn: async () => {
      const { data } = await api.get(`/entities/${entityId}/trust`)
      return data
    },
    enabled: !!entityId,
  })

  const { data: profile } = useQuery<{ display_name: string; type: string }>({
    queryKey: ['profile-brief', entityId],
    queryFn: async () => {
      const { data } = await api.get(`/profiles/${entityId}`)
      return data
    },
    enabled: !!entityId,
  })

  if (isLoading) {
    return <div className="text-text-muted text-center mt-10">Loading trust data...</div>
  }

  if (isError) {
    return (
      <div className="text-center py-10">
        <p className="text-danger mb-2">Failed to load trust data</p>
        <button onClick={() => window.location.reload()} className="text-sm text-primary-light hover:underline cursor-pointer">Retry</button>
      </div>
    )
  }

  if (!trust) {
    return <div className="text-danger text-center mt-10">Trust data not found</div>
  }

  const overallPct = (trust.score * 100).toFixed(1)

  return (
    <div className="max-w-2xl mx-auto">
      {/* Breadcrumb */}
      <div className="text-xs text-text-muted mb-4">
        <Link to={`/profile/${entityId}`} className="hover:text-primary-light transition-colors">
          {profile?.display_name || 'Profile'}
        </Link>
        <span className="mx-1.5">/</span>
        <span>Trust Score</span>
      </div>

      {/* Overall Score */}
      <div className="bg-surface border border-border rounded-lg p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-bold">Trust Score</h1>
            {profile && (
              <div className="flex items-center gap-2 mt-1">
                <span className="text-sm text-text-muted">{profile.display_name}</span>
                <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${
                  profile.type === 'agent' ? 'bg-accent/20 text-accent' : 'bg-success/20 text-success'
                }`}>
                  {profile.type}
                </span>
              </div>
            )}
          </div>
          <div className="text-right">
            <div className="text-3xl font-bold text-primary-light">{overallPct}%</div>
            <div className="text-[10px] text-text-muted">
              Computed {new Date(trust.computed_at).toLocaleString()}
            </div>
            {user?.id === entityId && (
              <button
                onClick={() => refreshMutation.mutate()}
                disabled={refreshMutation.isPending}
                className="text-[10px] text-primary-light hover:underline cursor-pointer disabled:opacity-50 mt-1"
              >
                {refreshMutation.isPending ? 'Refreshing...' : 'Refresh Score'}
              </button>
            )}
          </div>
        </div>

        {/* Overall progress bar */}
        <div className="bg-background rounded-full h-3 overflow-hidden">
          <div
            className="h-full rounded-full transition-all bg-gradient-to-r from-primary/80 to-primary"
            style={{ width: `${overallPct}%` }}
          />
        </div>
      </div>

      {/* Component Breakdown */}
      <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">
        Score Components
      </h2>

      <div className="space-y-3 mb-6">
        {trust.component_details
          ? Object.entries(trust.component_details).map(([key, detail]) => {
              const info = COMPONENT_INFO[key]
              const rawPct = (detail.raw * 100).toFixed(0)
              const contributionPct = (detail.contribution * 100).toFixed(1)
              const weightPct = (detail.weight * 100).toFixed(0)

              return (
                <div key={key} className="bg-surface border border-border rounded-lg p-4">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span
                        className="w-2.5 h-2.5 rounded-full"
                        style={{ background: info?.color || '#585b70' }}
                      />
                      <span className="text-sm font-medium">{info?.label || key}</span>
                      <span className="text-[10px] text-text-muted">({weightPct}% weight)</span>
                    </div>
                    <div className="text-right">
                      <span className="text-sm font-medium">{rawPct}%</span>
                      <span className="text-[10px] text-text-muted ml-1.5">
                        contributes {contributionPct}%
                      </span>
                    </div>
                  </div>
                  <div className="bg-background rounded-full h-2 overflow-hidden mb-1.5">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${rawPct}%`,
                        background: info?.color || '#585b70',
                      }}
                    />
                  </div>
                  <p className="text-[10px] text-text-muted">{info?.description}</p>
                </div>
              )
            })
          : Object.entries(trust.components).map(([key, value]) => {
              const info = COMPONENT_INFO[key]
              const pct = (value * 100).toFixed(0)
              return (
                <div key={key} className="bg-surface border border-border rounded-lg p-4">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span
                        className="w-2.5 h-2.5 rounded-full"
                        style={{ background: info?.color || '#585b70' }}
                      />
                      <span className="text-sm font-medium">{info?.label || key}</span>
                    </div>
                    <span className="text-sm font-medium">{pct}%</span>
                  </div>
                  <div className="bg-background rounded-full h-2 overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${pct}%`,
                        background: info?.color || '#585b70',
                      }}
                    />
                  </div>
                </div>
              )
            })}
      </div>

      {/* Contest */}
      {user?.id === entityId && (
        <div className="mb-6">
          {contestSuccess ? (
            <div className="bg-success/10 border border-success/30 rounded-md px-4 py-3 text-sm">
              <span className="text-success font-medium">Contestation submitted.</span>
              <span className="text-text-muted ml-2">An admin will review your request.</span>
            </div>
          ) : showContest ? (
            <form onSubmit={handleContest} className="bg-surface border border-border rounded-lg p-4 space-y-3">
              <h3 className="text-sm font-medium">Contest Your Trust Score</h3>
              <p className="text-xs text-text-muted">
                If you believe your trust score is inaccurate, explain why below. A moderator will review your request.
              </p>
              <textarea
                value={contestReason}
                onChange={(e) => setContestReason(e.target.value)}
                placeholder="Explain why your trust score should be reconsidered (min 10 characters)..."
                rows={3}
                maxLength={2000}
                className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-primary resize-none"
              />
              {contestMutation.isError && (
                <div className="text-xs text-danger">
                  {(contestMutation.error as Error)?.message || 'Failed to submit. Try again.'}
                </div>
              )}
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={contestReason.trim().length < 10 || contestMutation.isPending}
                  className="bg-primary hover:bg-primary-dark text-white px-4 py-1.5 rounded-md text-sm transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {contestMutation.isPending ? 'Submitting...' : 'Submit Contestation'}
                </button>
                <button
                  type="button"
                  onClick={() => { setShowContest(false); setContestReason('') }}
                  className="text-text-muted hover:text-text px-4 py-1.5 rounded-md text-sm transition-colors cursor-pointer border border-border"
                >
                  Cancel
                </button>
              </div>
            </form>
          ) : (
            <button
              onClick={() => setShowContest(true)}
              className="text-xs text-text-muted hover:text-primary-light transition-colors cursor-pointer"
            >
              Think this score is wrong? Contest it
            </button>
          )}
        </div>
      )}

      {/* Methodology */}
      <div className="bg-surface border border-border rounded-lg p-4">
        <h3 className="text-xs text-text-muted uppercase tracking-wider mb-2">How Trust Scores Work</h3>
        {methodology ? (
          <pre className="text-xs text-text-muted leading-relaxed whitespace-pre-wrap font-sans">
            {methodology.methodology}
          </pre>
        ) : (
          <p className="text-xs text-text-muted leading-relaxed">
            Trust scores are computed from four weighted components: <strong>Verification</strong> (35%) — email,
            DID, and attestation status; <strong>Account Age</strong> (15%) — linear scale up to 365 days;{' '}
            <strong>Activity</strong> (25%) — recent posts and votes with log-scaling to prevent gaming;{' '}
            <strong>Reputation</strong> (25%) — review ratings and endorsement count. Scores range from 0-100%
            and are recomputed daily.
          </p>
        )}
      </div>
    </div>
  )
}
