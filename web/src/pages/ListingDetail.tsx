import { useState, type FormEvent } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'

interface Listing {
  id: string
  entity_id: string
  title: string
  description: string
  category: string
  tags: string[]
  pricing_model: string
  price_cents: number
  is_active: boolean
  is_featured: boolean
  view_count: number
  average_rating: number | null
  review_count: number
  created_at: string
}

interface Review {
  id: string
  listing_id: string
  reviewer_entity_id: string
  reviewer_display_name: string
  rating: number
  text: string | null
  created_at: string
}

function formatPrice(cents: number, model: string): string {
  if (model === 'free') return 'Free'
  const dollars = (cents / 100).toFixed(2)
  return model === 'subscription' ? `$${dollars}/mo` : `$${dollars}`
}

function Stars({ rating }: { rating: number }) {
  return (
    <span className="text-warning">
      {'★'.repeat(rating)}{'☆'.repeat(5 - rating)}
    </span>
  )
}

export default function ListingDetail() {
  const { listingId } = useParams<{ listingId: string }>()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [showReview, setShowReview] = useState(false)
  const [rating, setRating] = useState(5)
  const [reviewText, setReviewText] = useState('')

  const { data: listing, isLoading } = useQuery<Listing>({
    queryKey: ['listing', listingId],
    queryFn: async () => {
      const { data } = await api.get(`/marketplace/${listingId}`)
      return data
    },
    enabled: !!listingId,
  })

  const { data: reviews } = useQuery<{ reviews: Review[]; total: number; average_rating: number | null }>({
    queryKey: ['listing-reviews', listingId],
    queryFn: async () => {
      const { data } = await api.get(`/marketplace/${listingId}/reviews`)
      return data
    },
    enabled: !!listingId,
  })

  const submitReview = useMutation({
    mutationFn: async () => {
      await api.post(`/marketplace/${listingId}/reviews`, {
        rating,
        text: reviewText || null,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['listing-reviews', listingId] })
      queryClient.invalidateQueries({ queryKey: ['listing', listingId] })
      setShowReview(false)
      setReviewText('')
    },
  })

  const handleReview = (e: FormEvent) => {
    e.preventDefault()
    submitReview.mutate()
  }

  if (isLoading) {
    return <div className="text-text-muted text-center mt-10">Loading listing...</div>
  }

  if (!listing) {
    return <div className="text-danger text-center mt-10">Listing not found</div>
  }

  const isOwner = user?.id === listing.entity_id

  return (
    <div className="max-w-2xl mx-auto">
      <div className="bg-surface border border-border rounded-lg p-6 mb-6">
        <div className="flex items-start justify-between mb-3">
          <div>
            <h1 className="text-xl font-bold">{listing.title}</h1>
            <div className="flex items-center gap-2 mt-1">
              <span className="px-2 py-0.5 rounded text-xs bg-surface-hover capitalize">
                {listing.category}
              </span>
              {listing.is_featured && (
                <span className="px-2 py-0.5 rounded text-xs bg-warning/20 text-warning">
                  Featured
                </span>
              )}
            </div>
          </div>
          <div className="text-right">
            <div className="text-lg font-bold text-primary-light">
              {formatPrice(listing.price_cents, listing.pricing_model)}
            </div>
            <div className="text-xs text-text-muted capitalize">{listing.pricing_model}</div>
          </div>
        </div>

        <p className="text-sm whitespace-pre-wrap mb-4">{listing.description}</p>

        {listing.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-4">
            {listing.tags.map((tag) => (
              <span key={tag} className="text-xs px-2 py-0.5 bg-primary/10 text-primary-light rounded">
                {tag}
              </span>
            ))}
          </div>
        )}

        <div className="flex items-center gap-6 text-xs text-text-muted">
          <span>{listing.view_count} views</span>
          {listing.average_rating !== null && (
            <span>
              <Stars rating={Math.round(listing.average_rating)} />{' '}
              ({listing.review_count} reviews)
            </span>
          )}
          <span>Listed {new Date(listing.created_at).toLocaleDateString()}</span>
          <Link
            to={`/profile/${listing.entity_id}`}
            className="hover:text-primary-light transition-colors ml-auto"
          >
            View Seller
          </Link>
        </div>
      </div>

      {/* Reviews */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
          Reviews ({reviews?.total || 0})
        </h2>
        {user && !isOwner && (
          <button
            onClick={() => setShowReview(!showReview)}
            className="text-xs text-primary-light hover:underline cursor-pointer"
          >
            {showReview ? 'Cancel' : 'Write a Review'}
          </button>
        )}
      </div>

      {showReview && (
        <form onSubmit={handleReview} className="bg-surface border border-border rounded-lg p-4 mb-4 space-y-3">
          <div>
            <label className="block text-sm text-text-muted mb-1">Rating</label>
            <div className="flex gap-1">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setRating(n)}
                  className={`text-2xl cursor-pointer ${n <= rating ? 'text-warning' : 'text-border'}`}
                >
                  ★
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-sm text-text-muted mb-1">Review (optional)</label>
            <textarea
              value={reviewText}
              onChange={(e) => setReviewText(e.target.value)}
              rows={3}
              maxLength={5000}
              className="w-full bg-background border border-border rounded-md px-3 py-2 text-text text-sm focus:outline-none focus:border-primary resize-none"
            />
          </div>
          <button
            type="submit"
            disabled={submitReview.isPending}
            className="bg-primary hover:bg-primary-dark text-white px-4 py-1.5 rounded-md text-sm transition-colors disabled:opacity-50 cursor-pointer"
          >
            {submitReview.isPending ? 'Submitting...' : 'Submit Review'}
          </button>
        </form>
      )}

      <div className="space-y-3">
        {reviews?.reviews.map((review) => (
          <div key={review.id} className="bg-surface border border-border rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              <Link
                to={`/profile/${review.reviewer_entity_id}`}
                className="text-sm font-medium hover:text-primary-light transition-colors"
              >
                {review.reviewer_display_name}
              </Link>
              <Stars rating={review.rating} />
              <span className="text-xs text-text-muted ml-auto">
                {new Date(review.created_at).toLocaleDateString()}
              </span>
            </div>
            {review.text && <p className="text-xs text-text-muted">{review.text}</p>}
          </div>
        ))}
      </div>
    </div>
  )
}
