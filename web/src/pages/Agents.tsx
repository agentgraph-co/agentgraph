import { useState, type FormEvent, type KeyboardEvent } from 'react'
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

interface CreatedAgent {
  agent: Agent
  api_key: string
}

const AUTONOMY_LABELS: Record<number, string> = {
  1: 'Fully supervised',
  2: 'Mostly supervised',
  3: 'Semi-autonomous',
  4: 'Mostly autonomous',
  5: 'Fully autonomous',
}

export default function Agents() {
  const queryClient = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [bio, setBio] = useState('')
  const [capabilities, setCapabilities] = useState<string[]>([])
  const [capInput, setCapInput] = useState('')
  const [autonomyLevel, setAutonomyLevel] = useState(3)
  const [error, setError] = useState('')
  const [createdResult, setCreatedResult] = useState<CreatedAgent | null>(null)
  const [copied, setCopied] = useState(false)

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
        capabilities,
        autonomy_level: autonomyLevel,
        bio_markdown: bio,
      })
      return data as CreatedAgent
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      setCreatedResult(result)
      setShowCreate(false)
      setName('')
      setBio('')
      setCapabilities([])
      setCapInput('')
      setAutonomyLevel(3)
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

  const addCapability = () => {
    const cap = capInput.trim().toLowerCase()
    if (cap && !capabilities.includes(cap) && capabilities.length < 50) {
      setCapabilities([...capabilities, cap])
      setCapInput('')
    }
  }

  const handleCapKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      addCapability()
    } else if (e.key === 'Backspace' && !capInput && capabilities.length > 0) {
      setCapabilities(capabilities.slice(0, -1))
    }
  }

  const removeCapability = (cap: string) => {
    setCapabilities(capabilities.filter((c) => c !== cap))
  }

  const copyApiKey = async (key: string) => {
    await navigator.clipboard.writeText(key)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (isLoading) {
    return <div className="text-text-muted text-center mt-10">Loading agents...</div>
  }

  return (
    <div className="max-w-2xl mx-auto">
      {/* API Key display — shown once after creation */}
      {createdResult && (
        <div className="bg-success/10 border border-success/30 rounded-lg p-4 mb-6">
          <h3 className="font-semibold text-success mb-2">
            Agent "{createdResult.agent.display_name}" created!
          </h3>
          <p className="text-sm text-text-muted mb-3">
            Save this API key now — it won't be shown again.
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 bg-background border border-border rounded px-3 py-2 text-sm font-mono break-all select-all">
              {createdResult.api_key}
            </code>
            <button
              onClick={() => copyApiKey(createdResult.api_key)}
              className="bg-surface border border-border hover:border-primary/50 px-3 py-2 rounded text-sm transition-colors cursor-pointer shrink-0"
            >
              {copied ? 'Copied!' : 'Copy'}
            </button>
          </div>
          <button
            onClick={() => setCreatedResult(null)}
            className="text-xs text-text-muted hover:text-text mt-3 cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">My Agents</h1>
        <button
          onClick={() => { setShowCreate(!showCreate); setCreatedResult(null) }}
          className="bg-primary hover:bg-primary-dark text-white px-4 py-1.5 rounded-md text-sm transition-colors cursor-pointer"
        >
          {showCreate ? 'Cancel' : 'Register Agent'}
        </button>
      </div>

      {showCreate && (
        <form onSubmit={handleCreate} className="bg-surface border border-border rounded-lg p-4 mb-6 space-y-4">
          {error && (
            <div className="bg-danger/10 text-danger text-sm px-3 py-2 rounded">{error}</div>
          )}
          <div>
            <label className="block text-sm text-text-muted mb-1">Agent Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. ResearchBot"
              required
              minLength={2}
              maxLength={100}
              className="w-full bg-background border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary"
            />
          </div>

          <div>
            <label className="block text-sm text-text-muted mb-1">
              Capabilities <span className="text-text-muted/60">({capabilities.length}/50)</span>
            </label>
            <div className="flex flex-wrap gap-1.5 bg-background border border-border rounded-md px-3 py-2 focus-within:border-primary min-h-[42px]">
              {capabilities.map((cap) => (
                <span
                  key={cap}
                  className="inline-flex items-center gap-1 text-xs bg-primary/10 text-primary-light px-2 py-1 rounded"
                >
                  {cap}
                  <button
                    type="button"
                    onClick={() => removeCapability(cap)}
                    className="hover:text-danger cursor-pointer leading-none"
                  >
                    &times;
                  </button>
                </span>
              ))}
              <input
                value={capInput}
                onChange={(e) => setCapInput(e.target.value)}
                onKeyDown={handleCapKeyDown}
                onBlur={addCapability}
                placeholder={capabilities.length === 0 ? 'Type a capability and press Enter...' : ''}
                className="flex-1 min-w-[120px] bg-transparent text-text text-sm focus:outline-none"
              />
            </div>
            <p className="text-xs text-text-muted/60 mt-1">
              Press Enter or comma to add. e.g. code-generation, web-search, data-analysis
            </p>
          </div>

          <div>
            <label className="block text-sm text-text-muted mb-1">
              Autonomy Level: {autonomyLevel}/5 — {AUTONOMY_LABELS[autonomyLevel]}
            </label>
            <input
              type="range"
              min={1}
              max={5}
              step={1}
              value={autonomyLevel}
              onChange={(e) => setAutonomyLevel(Number(e.target.value))}
              className="w-full accent-primary"
            />
            <div className="flex justify-between text-[10px] text-text-muted/60 px-0.5">
              <span>Supervised</span>
              <span>Autonomous</span>
            </div>
          </div>

          <div>
            <label className="block text-sm text-text-muted mb-1">Description</label>
            <textarea
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              placeholder="What does this agent do?"
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
