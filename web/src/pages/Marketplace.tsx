import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'
import { ListingSkeleton } from '../components/Skeleton'
import { formatPrice } from '../lib/formatters'

interface Listing {
  id: string
  entity_id: string
  title: string
  description: string
  category: string
  tags: string[]
  pricing_model: string
  price_cents: number
  is_featured: boolean
  view_count: number
  average_rating: number | null
  review_count: number
  created_at: string
}

interface MarketplaceResponse {
  listings: Listing[]
  total: number
}

interface CategoryStat {
  category: string
  listing_count: number
  avg_price_cents: number
}

interface CategoryStatsResponse {
  total_active_listings: number
  categories: CategoryStat[]
}

const CATEGORIES = ['all', 'service', 'skill', 'integration', 'tool', 'data'] as const
const PRICING_MODELS = ['all', 'free', 'one_time', 'subscription'] as const
const SORT_OPTIONS = [
  { value: 'newest', label: 'Newest' },
  { value: 'popular', label: 'Popular' },
  { value: 'price_asc', label: 'Price: Low to High' },
  { value: 'price_desc', label: 'Price: High to Low' },
] as const
const PAGE_SIZE = 18

function Stars({ rating }: { rating: number }) {
  return (
    <span className="text-warning text-[10px]">
      {'★'.repeat(Math.round(rating))}{'☆'.repeat(5 - Math.round(rating))}
    </span>
  )
}

export default function Marketplace() {
  const { user } = useAuth()
  const [activeCategory, setActiveCategory] = useState<string>('all')
  const [pricingFilter, setPricingFilter] = useState<string>('all')
  const [sortBy, setSortBy] = useState<string>('newest')
  const [searchInput, setSearchInput] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  useEffect(() => { document.title = 'Marketplace - AgentGraph' }, [])

  // Debounce search input
  useEffect(() => {
    debounceRef.current = setTimeout(() => {
      setSearchTerm(searchInput.trim())
    }, 300)
    return () => clearTimeout(debounceRef.current)
  }, [searchInput])

  const { data: featuredData } = useQuery<MarketplaceResponse>({
    queryKey: ['marketplace-featured'],
    queryFn: async () => {
      const { data } = await api.get('/marketplace/featured', { params: { limit: 6 } })
      return data
    },
    staleTime: 60_000,
  })

  const { data: categoryStats } = useQuery<CategoryStatsResponse>({
    queryKey: ['marketplace-category-stats'],
    queryFn: async () => {
      const { data } = await api.get('/marketplace/categories/stats')
      return data
    },
    staleTime: 60_000,
  })

  const {
    data,
    isLoading,
    isError,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery<MarketplaceResponse>({
    queryKey: ['marketplace', activeCategory, pricingFilter, sortBy, searchTerm],
    queryFn: async ({ pageParam }) => {
      const params: Record<string, unknown> = {
        limit: PAGE_SIZE,
        offset: pageParam,
        sort: sortBy,
      }
      if (activeCategory !== 'all') params.category = activeCategory
      if (pricingFilter !== 'all') params.pricing_model = pricingFilter
      if (searchTerm) params.search = searchTerm
      const { data } = await api.get('/marketplace', { params })
      if (Array.isArray(data)) {
        return { listings: data, total: data.length }
      }
      return {
        listings: data.listings || [],
        total: data.total || 0,
      }
    },
    initialPageParam: 0,
    getNextPageParam: (_lastPage, allPages) => {
      const loaded = allPages.reduce((acc, page) => acc + page.listings.length, 0)
      const total = allPages[0]?.total || 0
      if (loaded >= total) return undefined
      return loaded
    },
  })

  const allListings = data?.pages.flatMap((page) => page.listings) || []
  const totalCount = data?.pages[0]?.total || 0

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-6">
        {Array.from({ length: 6 }).map((_, i) => <ListingSkeleton key={i} />)}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="text-center py-10">
        <p className="text-danger mb-2">Failed to load marketplace</p>
        <button onClick={() => refetch()} className="text-sm text-primary-light hover:underline cursor-pointer">Retry</button>
      </div>
    )
  }

  return (
    <div>
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-4 gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold">Agent Marketplace</h1>
          {user && (
            <Link
              to="/marketplace/create"
              className="bg-primary hover:bg-primary-dark text-white px-3 py-1.5 rounded-md text-sm transition-colors"
            >
              + New Listing
            </Link>
          )}
        </div>
        <input
          type="search"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Search listings..."
          aria-label="Search marketplace listings"
          className="bg-surface border border-border rounded-md px-3 py-1.5 text-sm text-text focus:outline-none focus:border-primary w-56"
        />
      </div>

      {/* Filters row */}
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        {/* Category pills */}
        <div className="flex gap-1.5 flex-wrap">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`px-2.5 py-1 text-xs rounded-full border transition-colors capitalize cursor-pointer ${
                activeCategory === cat
                  ? 'border-primary text-primary bg-primary/10'
                  : 'border-border text-text-muted hover:border-primary hover:text-primary'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3">
          {/* Pricing filter */}
          <select
            value={pricingFilter}
            onChange={(e) => setPricingFilter(e.target.value)}
            className="bg-surface border border-border rounded-md px-2 py-1 text-xs text-text-muted focus:outline-none focus:border-primary cursor-pointer"
          >
            {PRICING_MODELS.map((pm) => (
              <option key={pm} value={pm}>
                {pm === 'all' ? 'Any Price' : pm === 'one_time' ? 'One-Time' : pm === 'free' ? 'Free' : 'Subscription'}
              </option>
            ))}
          </select>

          {/* Sort */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="bg-surface border border-border rounded-md px-2 py-1 text-xs text-text-muted focus:outline-none focus:border-primary cursor-pointer"
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Featured Listings */}
      {featuredData && featuredData.listings.length > 0 && !searchTerm && (
        <div className="mb-6">
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-2">Featured</h2>
          <div className="flex gap-3 overflow-x-auto pb-2">
            {featuredData.listings.map((listing) => (
              <Link
                key={listing.id}
                to={`/marketplace/${listing.id}`}
                className="bg-surface border border-warning/30 rounded-lg p-3 min-w-[200px] max-w-[240px] shrink-0 hover:border-warning/60 transition-colors"
              >
                <div className="flex items-center gap-1 mb-1">
                  <span className="text-warning text-xs">★</span>
                  <h3 className="text-sm font-medium line-clamp-1">{listing.title}</h3>
                </div>
                <p className="text-[10px] text-text-muted line-clamp-2 mb-2">{listing.description}</p>
                <div className="flex items-center justify-between text-[10px]">
                  <span className="text-primary-light font-medium">{formatPrice(listing.price_cents, listing.pricing_model)}</span>
                  {listing.average_rating !== null && (
                    <span className="flex items-center gap-0.5">
                      <Stars rating={listing.average_rating} />
                    </span>
                  )}
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Category Stats */}
      {categoryStats && categoryStats.categories.length > 0 && !searchTerm && activeCategory === 'all' && (
        <div className="grid grid-cols-3 sm:grid-cols-3 md:grid-cols-3 lg:grid-cols-6 gap-2 mb-4">
          {categoryStats.categories.map((cat) => (
            <button
              key={cat.category}
              onClick={() => setActiveCategory(cat.category)}
              className="bg-surface border border-border rounded-lg p-2 text-center hover:border-primary/50 transition-colors cursor-pointer"
            >
              <div className="text-xs font-medium capitalize">{cat.category}</div>
              <div className="text-lg font-bold text-primary-light">{cat.listing_count}</div>
              <div className="text-[10px] text-text-muted">
                avg {formatPrice(cat.avg_price_cents, cat.avg_price_cents === 0 ? 'free' : 'one_time')}
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Results count */}
      <div className="text-xs text-text-muted mb-3">
        {totalCount} {totalCount === 1 ? 'listing' : 'listings'}
        {searchTerm && <> matching &ldquo;{searchTerm}&rdquo;</>}
        {activeCategory !== 'all' && <> in {activeCategory}</>}
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {allListings.map((listing) => (
          <Link
            key={listing.id}
            to={`/marketplace/${listing.id}`}
            className="bg-surface border border-border rounded-lg p-4 hover:border-primary/50 transition-colors block"
          >
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-1.5 min-w-0">
                {listing.is_featured && (
                  <span className="text-warning text-xs shrink-0" title="Featured">★</span>
                )}
                <h3 className="font-medium line-clamp-1">{listing.title}</h3>
              </div>
              <span className="text-sm font-medium text-primary-light whitespace-nowrap ml-2">
                {formatPrice(listing.price_cents, listing.pricing_model)}
              </span>
            </div>
            <p className="text-xs text-text-muted line-clamp-2 mb-3">
              {listing.description}
            </p>
            {listing.tags && listing.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-2">
                {listing.tags.slice(0, 3).map((tag) => (
                  <span key={tag} className="text-[10px] px-1.5 py-0.5 bg-primary/10 text-primary-light rounded">
                    {tag}
                  </span>
                ))}
                {listing.tags.length > 3 && (
                  <span className="text-[10px] text-text-muted">+{listing.tags.length - 3}</span>
                )}
              </div>
            )}
            <div className="flex items-center justify-between text-xs text-text-muted">
              <div className="flex items-center gap-2">
                <span className="px-1.5 py-0.5 rounded bg-surface-hover capitalize">
                  {listing.category}
                </span>
                {listing.average_rating !== null && (
                  <span className="flex items-center gap-0.5">
                    <Stars rating={listing.average_rating} />
                    <span>({listing.review_count})</span>
                  </span>
                )}
              </div>
              <span>{listing.view_count} views</span>
            </div>
          </Link>
        ))}
      </div>

      {allListings.length === 0 && (
        <div className="text-text-muted text-center py-10">
          {searchTerm || activeCategory !== 'all' || pricingFilter !== 'all'
            ? 'No listings match your filters.'
            : 'No listings yet. Be the first to list a service!'}
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
      {!hasNextPage && allListings.length > 0 && (
        <p className="text-center text-xs text-text-muted py-4">No more listings</p>
      )}
    </div>
  )
}
