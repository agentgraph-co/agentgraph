import { useState, useEffect, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import api from '../lib/api'
import { useToast } from '../components/Toasts'
import { useUnsavedChanges } from '../hooks/useUnsavedChanges'

const CATEGORIES = ['service', 'skill', 'integration', 'tool', 'data'] as const
const PRICING_MODELS = ['free', 'one_time', 'subscription'] as const

export default function CreateListing() {
  const navigate = useNavigate()
  const { addToast } = useToast()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState<string>('service')
  const [pricingModel, setPricingModel] = useState<string>('free')
  const [priceCents, setPriceCents] = useState(0)
  const [tags, setTags] = useState('')
  const [error, setError] = useState('')

  useEffect(() => { document.title = 'Create Listing - AgentGraph' }, [])

  const hasChanges = title.trim().length > 0 || description.trim().length > 0 || tags.trim().length > 0
  useUnsavedChanges(hasChanges)

  const createListing = useMutation({
    mutationFn: async () => {
      const { data } = await api.post('/marketplace', {
        title,
        description,
        category,
        pricing_model: pricingModel,
        price_cents: pricingModel === 'free' ? 0 : priceCents,
        tags: tags.split(',').map((t) => t.trim()).filter(Boolean),
      })
      return data
    },
    onSuccess: (data) => {
      addToast('Listing created', 'success')
      navigate(`/marketplace/${data.id}`)
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg || 'Failed to create listing')
    },
  })

  const parsedTags = tags.split(',').map((t) => t.trim()).filter(Boolean)
  const formValid = title.trim().length > 0 && description.trim().length > 0 && parsedTags.length <= 10

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!formValid) return
    createListing.mutate()
  }

  return (
    <div className="max-w-lg mx-auto">
      <h1 className="text-xl font-bold mb-6">Create Marketplace Listing</h1>

      {error && (
        <div className="bg-danger/10 text-danger text-sm px-4 py-2 rounded mb-4">{error}</div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm text-text-muted mb-1">Title <span className="text-danger">*</span></label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            minLength={1}
            maxLength={200}
            className="w-full bg-surface border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary"
          />
        </div>

        <div>
          <label className="block text-sm text-text-muted mb-1">Description <span className="text-danger">*</span></label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            required
            minLength={1}
            rows={5}
            maxLength={5000}
            className="w-full bg-surface border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary resize-none"
          />
          <span className="text-[10px] text-text-muted">{description.length}/5000</span>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-text-muted mb-1">Category</label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full bg-surface border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary"
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-text-muted mb-1">Pricing Model</label>
            <select
              value={pricingModel}
              onChange={(e) => setPricingModel(e.target.value)}
              className="w-full bg-surface border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary"
            >
              {PRICING_MODELS.map((p) => (
                <option key={p} value={p}>
                  {p === 'one_time' ? 'One-Time' : p.charAt(0).toUpperCase() + p.slice(1)}
                </option>
              ))}
            </select>
          </div>
        </div>

        {pricingModel !== 'free' && (
          <div>
            <label className="block text-sm text-text-muted mb-1">
              Price ({pricingModel === 'subscription' ? 'per month' : 'one-time'})
            </label>
            <div className="relative">
              <span className="absolute left-3 top-2 text-text-muted">$</span>
              <input
                type="number"
                value={(priceCents / 100).toFixed(2)}
                onChange={(e) => {
                  const val = parseFloat(e.target.value || '0')
                  setPriceCents(Math.round(Math.max(0, val) * 100))
                }}
                min="0"
                step="0.01"
                className="w-full bg-surface border border-border rounded-md pl-7 pr-3 py-2 text-text focus:outline-none focus:border-primary"
              />
            </div>
          </div>
        )}

        <div>
          <label className="block text-sm text-text-muted mb-1">Tags (comma-separated, max 10)</label>
          <input
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="ai, automation, nlp"
            className="w-full bg-surface border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary"
          />
          {parsedTags.length > 0 && (
            <span className={`text-[10px] ${parsedTags.length > 10 ? 'text-danger' : 'text-text-muted'}`}>
              {parsedTags.length}/10 tags
            </span>
          )}
        </div>

        <button
          type="submit"
          disabled={createListing.isPending || !formValid}
          className="w-full bg-primary hover:bg-primary-dark text-white py-2 rounded-md transition-colors disabled:opacity-50 cursor-pointer"
        >
          {createListing.isPending ? 'Creating...' : 'Create Listing'}
        </button>
      </form>
    </div>
  )
}
