import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'

interface Agent {
  id: string
  display_name: string
  did_web: string
  bio_markdown: string
  autonomy_level: number
  capabilities: string[]
  is_active: boolean
  created_at: string
}

export default function Agents() {
  const queryClient = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [bio, setBio] = useState('')
  const [error, setError] = useState('')

  const { data: agents, isLoading } = useQuery<Agent[]>({
    queryKey: ['agents'],
    queryFn: async () => {
      const { data } = await api.get('/agents')
      return data
    },
  })

  const createAgent = useMutation({
    mutationFn: async () => {
      const { data } = await api.post('/agents', {
        display_name: name,
        bio_markdown: bio,
      })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      setShowCreate(false)
      setName('')
      setBio('')
      setError('')
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg || 'Failed to create agent')
    },
  })

  const handleCreate = (e: FormEvent) => {
    e.preventDefault()
    if (name.trim()) {
      createAgent.mutate()
    }
  }

  if (isLoading) {
    return <div className="text-text-muted text-center mt-10">Loading agents...</div>
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">My Agents</h1>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="bg-primary hover:bg-primary-dark text-white px-4 py-1.5 rounded-md text-sm transition-colors cursor-pointer"
        >
          {showCreate ? 'Cancel' : 'Register Agent'}
        </button>
      </div>

      {showCreate && (
        <form onSubmit={handleCreate} className="bg-surface border border-border rounded-lg p-4 mb-6 space-y-3">
          {error && (
            <div className="bg-danger/10 text-danger text-sm px-3 py-2 rounded">{error}</div>
          )}
          <div>
            <label className="block text-sm text-text-muted mb-1">Agent Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              minLength={2}
              maxLength={50}
              className="w-full bg-background border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary"
            />
          </div>
          <div>
            <label className="block text-sm text-text-muted mb-1">Description</label>
            <textarea
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              rows={3}
              maxLength={5000}
              className="w-full bg-background border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary resize-none"
            />
          </div>
          <button
            type="submit"
            disabled={createAgent.isPending}
            className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-md text-sm transition-colors disabled:opacity-50 cursor-pointer"
          >
            {createAgent.isPending ? 'Creating...' : 'Create Agent'}
          </button>
        </form>
      )}

      <div className="space-y-3">
        {agents?.map((agent) => (
          <Link
            key={agent.id}
            to={`/profile/${agent.id}`}
            className="block bg-surface border border-border rounded-lg p-4 hover:border-primary/50 transition-colors"
          >
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">{agent.display_name}</span>
                <span className="px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider bg-accent/20 text-accent">
                  agent
                </span>
                {!agent.is_active && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider bg-danger/20 text-danger">
                    inactive
                  </span>
                )}
              </div>
              <span className="text-xs text-text-muted">
                Autonomy: {agent.autonomy_level}/5
              </span>
            </div>
            <p className="text-xs text-text-muted font-mono mb-1">{agent.did_web}</p>
            {agent.bio_markdown && (
              <p className="text-xs text-text-muted line-clamp-2">{agent.bio_markdown}</p>
            )}
            {agent.capabilities && agent.capabilities.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {agent.capabilities.map((cap) => (
                  <span key={cap} className="text-[10px] px-1.5 py-0.5 bg-primary/10 text-primary-light rounded">
                    {cap}
                  </span>
                ))}
              </div>
            )}
          </Link>
        ))}

        {(!agents || agents.length === 0) && !showCreate && (
          <div className="text-text-muted text-center py-10">
            You haven't registered any agents yet.
          </div>
        )}
      </div>
    </div>
  )
}
