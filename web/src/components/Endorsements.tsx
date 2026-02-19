import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'
import { useToast } from './Toasts'

interface CapabilitySummary {
  capability: string
  tier: string
  endorsement_count: number
  endorsers: string[]
}

interface Endorsement {
  id: string
  agent_entity_id: string
  endorser_entity_id: string
  endorser_display_name: string
  capability: string
  tier: string
  comment: string | null
  created_at: string
}

const TIER_COLORS: Record<string, string> = {
  self_declared: 'bg-surface-hover text-text-muted',
  community_verified: 'bg-success/20 text-success',
  formally_audited: 'bg-primary/20 text-primary-light',
}

const TIER_LABELS: Record<string, string> = {
  self_declared: 'Self-declared',
  community_verified: 'Community Verified',
  formally_audited: 'Formally Audited',
}

export default function Endorsements({ entityId, isAgent }: { entityId: string; isAgent: boolean }) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [showForm, setShowForm] = useState(false)
  const [capability, setCapability] = useState('')
  const [comment, setComment] = useState('')

  const { data: capabilities } = useQuery<CapabilitySummary[]>({
    queryKey: ['capabilities', entityId],
    queryFn: async () => {
      const { data } = await api.get(`/entities/${entityId}/capabilities`)
      return data
    },
    enabled: isAgent,
  })

  const { data: endorsements } = useQuery<{ endorsements: Endorsement[]; total: number }>({
    queryKey: ['endorsements', entityId],
    queryFn: async () => {
      const { data } = await api.get(`/entities/${entityId}/endorsements`)
      return data
    },
    enabled: isAgent,
  })

  const endorseMutation = useMutation({
    mutationFn: async () => {
      await api.post(`/entities/${entityId}/endorsements`, {
        capability,
        comment: comment || null,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['capabilities', entityId] })
      queryClient.invalidateQueries({ queryKey: ['endorsements', entityId] })
      setShowForm(false)
      setCapability('')
      setComment('')
      addToast('Endorsement added', 'success')
    },
    onError: () => {
      addToast('Failed to add endorsement', 'error')
    },
  })

  const removeEndorsement = useMutation({
    mutationFn: async (cap: string) => {
      await api.delete(`/entities/${entityId}/endorsements/${encodeURIComponent(cap)}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['capabilities', entityId] })
      queryClient.invalidateQueries({ queryKey: ['endorsements', entityId] })
      addToast('Endorsement removed', 'success')
    },
    onError: () => {
      addToast('Failed to remove endorsement', 'error')
    },
  })

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (capability.trim()) {
      endorseMutation.mutate()
    }
  }

  if (!isAgent) return null

  const isOwn = user?.id === entityId

  return (
    <div className="mt-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
          Capabilities & Endorsements
        </h2>
        {user && !isOwn && (
          <button
            onClick={() => setShowForm(!showForm)}
            className="text-xs text-primary-light hover:underline cursor-pointer"
          >
            {showForm ? 'Cancel' : 'Endorse'}
          </button>
        )}
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="bg-surface border border-border rounded-lg p-4 mb-4 space-y-3">
          <div>
            <label className="block text-sm text-text-muted mb-1">Capability</label>
            <input
              value={capability}
              onChange={(e) => setCapability(e.target.value)}
              required
              maxLength={200}
              placeholder="e.g. natural-language-processing"
              className="w-full bg-background border border-border rounded-md px-3 py-2 text-text text-sm focus:outline-none focus:border-primary"
            />
          </div>
          <div>
            <label className="block text-sm text-text-muted mb-1">Comment (optional)</label>
            <input
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              maxLength={1000}
              placeholder="Why are you endorsing this capability?"
              className="w-full bg-background border border-border rounded-md px-3 py-2 text-text text-sm focus:outline-none focus:border-primary"
            />
          </div>
          <button
            type="submit"
            disabled={endorseMutation.isPending}
            className="bg-primary hover:bg-primary-dark text-white px-4 py-1.5 rounded-md text-sm transition-colors disabled:opacity-50 cursor-pointer"
          >
            {endorseMutation.isPending ? 'Endorsing...' : 'Endorse Capability'}
          </button>
        </form>
      )}

      {capabilities && capabilities.length > 0 && (
        <div className="space-y-2 mb-4">
          {capabilities.map((cap) => (
            <div key={cap.capability} className="bg-surface border border-border rounded-lg p-3">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-medium">{cap.capability}</span>
                <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${TIER_COLORS[cap.tier] || TIER_COLORS.self_declared}`}>
                  {TIER_LABELS[cap.tier] || cap.tier}
                </span>
                {cap.endorsement_count > 0 && (
                  <span className="text-xs text-text-muted">
                    {cap.endorsement_count} endorsement{cap.endorsement_count !== 1 ? 's' : ''}
                  </span>
                )}
              </div>
              {cap.endorsers.length > 0 && (
                <div className="text-xs text-text-muted">
                  Endorsed by: {cap.endorsers.join(', ')}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {endorsements && endorsements.endorsements.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider">Recent Endorsements</h3>
          {endorsements.endorsements.map((e) => (
            <div key={e.id} className="bg-surface border border-border rounded-lg p-3 flex items-center gap-3">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <Link
                    to={`/profile/${e.endorser_entity_id}`}
                    className="text-sm font-medium hover:text-primary-light transition-colors"
                  >
                    {e.endorser_display_name}
                  </Link>
                  <span className="text-xs text-text-muted">endorsed</span>
                  <span className="text-xs text-primary-light font-medium">{e.capability}</span>
                  <span className="text-xs text-text-muted ml-auto">
                    {new Date(e.created_at).toLocaleDateString()}
                  </span>
                </div>
                {e.comment && <p className="text-xs text-text-muted mt-1">{e.comment}</p>}
              </div>
              {user?.id === e.endorser_entity_id && (
                <button
                  onClick={() => removeEndorsement.mutate(e.capability)}
                  className="text-xs text-danger hover:underline cursor-pointer"
                >
                  Remove
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {(!capabilities || capabilities.length === 0) && (!endorsements || endorsements.endorsements.length === 0) && (
        <div className="text-text-muted text-sm">No capabilities or endorsements yet.</div>
      )}
    </div>
  )
}
