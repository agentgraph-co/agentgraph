import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useInfiniteQuery } from '@tanstack/react-query'
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

interface MarketplaceResponse {
  listings: Listing[]
  total: number
  has_more: boolean
}

const CATEGORIES = ['all', 'service', 'skill', 'integration', 'tool', 'data'] as const
const PAGE_SIZE = 18

function formatPrice(cents: number, model: string): string {
  if (model === 'free') return 'Free'
  const dollars = (cents / 100).toFixed(2)
  return model === 'subscription' ? `$${dollars}/mo` : `$${dollars}`
}

export default function Marketplace() {
  const [activeCategory, setActiveCategory] = useState<string>('all')

  const {
    data,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery<MarketplaceResponse>({
    queryKey: ['marketplace', activeCategory],
    queryFn: async ({ pageParam }) => {
      const params: Record<string, unknown> = { limit: PAGE_SIZE, offset: pageParam }
      if (activeCategory !== 'all') {
        params.category = activeCategory
      }
      const { data } = await api.get('/marketplace', { params })
      // Handle both response shapes
      if (Array.isArray(data)) {
        return { listings: data, total: data.length, has_more: false }
      }
      return {
        listings: data.listings || [],
        total: data.total || 0,
        has_more: data.has_more ?? (data.listings?.length === PAGE_SIZE),
      }
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      if (!lastPage.has_more) return undefined
      return allPages.reduce((acc, page) => acc + page.listings.length, 0)
    },
  })

  const allListings = data?.pages.flatMap((page) => page.listings) || []

  if (isLoading) {
    return <div className="text-text-muted text-center mt-10">Loading marketplace...</div>
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold">Agent Marketplace</h1>
          <Link
            to="/marketplace/create"
            className="bg-primary hover:bg-primary-dark text-white px-3 py-1.5 rounded-md text-sm transition-colors"
          >
            + New Listing
          </Link>
        </div>
        <div className="flex gap-2 flex-wrap">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`px-3 py-1 text-xs rounded-full border transition-colors capitalize cursor-pointer ${
                activeCategory === cat
                  ? 'border-primary text-primary bg-primary/10'
                  : 'border-border text-text-muted hover:border-primary hover:text-primary'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {allListings.map((listing) => (
          <Link
            key={listing.id}
            to={`/marketplace/${listing.id}`}
            className="bg-surface border border-border rounded-lg p-4 hover:border-primary/50 transition-colors block"
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
                <span className="hover:text-primary-light transition-colors">
                  {listing.seller_name}
                </span>
              </div>
              <span>{listing.view_count} views</span>
            </div>
          </Link>
        ))}
      </div>

      {allListings.length === 0 && (
        <div className="text-text-muted text-center py-10">
          No listings yet. Be the first to list a service!
        </div>
      )}

      {hasNextPage && (
        <div className="text-center py-6">
          <button
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
            className="text-sm text-primary-light hover:underline cursor-pointer disabled:opacity-50"
          >
            {isFetchingNextPage ? 'Loading more...' : 'Load More Listings'}
          </button>
        </div>
      )}
    </div>
  )
}
