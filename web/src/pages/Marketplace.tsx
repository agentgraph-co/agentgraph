import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'

interface Listing {
  id: string
  title: string
  description: string
  category: string
  pricing_model: string
  price_cents: number
  seller_name: string
  seller_id: string
  view_count: number
  created_at: string
}

const CATEGORIES = ['all', 'service', 'skill', 'integration', 'tool', 'data'] as const

function formatPrice(cents: number, model: string): string {
  if (model === 'free') return 'Free'
  const dollars = (cents / 100).toFixed(2)
  return model === 'subscription' ? `$${dollars}/mo` : `$${dollars}`
}

export default function Marketplace() {
  const { data, isLoading } = useQuery<Listing[]>({
    queryKey: ['marketplace'],
    queryFn: async () => {
      const { data } = await api.get('/marketplace', { params: { limit: 50 } })
      return data.listings || data
    },
  })

  if (isLoading) {
    return <div className="text-text-muted text-center mt-10">Loading marketplace...</div>
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">Agent Marketplace</h1>
        <div className="flex gap-2">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              className="px-3 py-1 text-xs rounded-full border border-border text-text-muted hover:border-primary hover:text-primary transition-colors capitalize cursor-pointer"
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {data?.map((listing) => (
          <div
            key={listing.id}
            className="bg-surface border border-border rounded-lg p-4 hover:border-primary/50 transition-colors"
          >
            <div className="flex items-start justify-between mb-2">
              <h3 className="font-medium line-clamp-1">{listing.title}</h3>
              <span className="text-sm font-medium text-primary-light whitespace-nowrap ml-2">
                {formatPrice(listing.price_cents, listing.pricing_model)}
              </span>
            </div>
            <p className="text-xs text-text-muted line-clamp-2 mb-3">
              {listing.description}
            </p>
            <div className="flex items-center justify-between text-xs text-text-muted">
              <div className="flex items-center gap-2">
                <span className="px-1.5 py-0.5 rounded bg-surface-hover capitalize">
                  {listing.category}
                </span>
                <Link
                  to={`/profile/${listing.seller_id}`}
                  className="hover:text-primary-light transition-colors"
                >
                  {listing.seller_name}
                </Link>
              </div>
              <span>{listing.view_count} views</span>
            </div>
          </div>
        ))}
      </div>

      {(!data || data.length === 0) && (
        <div className="text-text-muted text-center py-10">
          No listings yet. Be the first to list a service!
        </div>
      )}
    </div>
  )
}
