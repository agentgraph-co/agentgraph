// ListingDetailViewModel — Listing detail, reviews, and purchase

import Foundation
import Observation

@Observable @MainActor
final class ListingDetailViewModel {
    var listing: MarketplaceListingResponse?
    var reviews: [MarketplaceReviewResponse] = []
    var reviewStats: (average: Double?, total: Int) = (nil, 0)
    var sellerProfile: ProfileResponse?
    var isLoading = false
    var isLoadingReviews = false
    var isPurchasing = false
    var error: String?
    var purchaseError: String?
    var purchaseSuccess = false
    var reviewSubmitted = false

    func loadListing(id: UUID) async {
        isLoading = true
        error = nil

        do {
            listing = try await APIService.shared.getMarketplaceListing(id: id)

            // Load seller profile in parallel with reviews
            if let entityId = listing?.entityId {
                async let profileResult = APIService.shared.getProfile(entityId: entityId)
                async let reviewsResult = APIService.shared.getListingReviews(listingId: id)

                let (profile, reviewsResponse) = try await (profileResult, reviewsResult)
                if !Task.isCancelled {
                    sellerProfile = profile
                    reviews = reviewsResponse.reviews
                    reviewStats = (reviewsResponse.averageRating, reviewsResponse.total)
                }
            }
        } catch {
            if !Task.isCancelled {
                self.error = error.localizedDescription
            }
        }

        isLoading = false
    }

    func loadReviews(listingId: UUID) async {
        isLoadingReviews = true

        do {
            let response = try await APIService.shared.getListingReviews(listingId: listingId)
            if !Task.isCancelled {
                reviews = response.reviews
                reviewStats = (response.averageRating, response.total)
            }
        } catch {
            // Non-critical failure
        }

        isLoadingReviews = false
    }

    func purchaseListing(id: UUID) async {
        isPurchasing = true
        purchaseError = nil
        purchaseSuccess = false

        do {
            _ = try await APIService.shared.purchaseMarketplaceListing(id: id)
            purchaseSuccess = true
        } catch {
            purchaseError = error.localizedDescription
        }

        isPurchasing = false
    }

    func submitReview(listingId: UUID, rating: Int, text: String?) async -> Bool {
        do {
            let review = try await APIService.shared.createListingReview(
                listingId: listingId,
                rating: rating,
                text: text?.trimmingCharacters(in: .whitespacesAndNewlines)
            )
            reviews.insert(review, at: 0)
            reviewStats = (reviewStats.average, reviewStats.total + 1)
            reviewSubmitted = true
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }
}
