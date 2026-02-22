// MarketplaceViewModel — Browse, search, and filter marketplace listings

import Foundation
import Observation

enum MarketplaceCategory: String, CaseIterable, Sendable {
    case all = "all"
    case service = "service"
    case skill = "skill"
    case integration = "integration"
    case tool = "tool"
    case data = "data"

    var displayName: String {
        switch self {
        case .all: return "All"
        case .service: return "Services"
        case .skill: return "Skills"
        case .integration: return "Integrations"
        case .tool: return "Tools"
        case .data: return "Data"
        }
    }

    var icon: String {
        switch self {
        case .all: return "square.grid.2x2"
        case .service: return "gearshape.2"
        case .skill: return "brain.head.profile"
        case .integration: return "link"
        case .tool: return "wrench.and.screwdriver"
        case .data: return "cylinder"
        }
    }

    /// API value — nil for "all" so no filter is applied
    var apiValue: String? {
        self == .all ? nil : rawValue
    }
}

enum MarketplaceSortOption: String, CaseIterable, Sendable {
    case newest = "newest"
    case popular = "popular"
    case priceAsc = "price_asc"
    case priceDesc = "price_desc"

    var displayName: String {
        switch self {
        case .newest: return "Newest"
        case .popular: return "Popular"
        case .priceAsc: return "Price: Low to High"
        case .priceDesc: return "Price: High to Low"
        }
    }
}

@Observable @MainActor
final class MarketplaceViewModel {
    var listings: [MarketplaceListingResponse] = []
    var featuredListings: [MarketplaceListingResponse] = []
    var isLoading = false
    var isLoadingMore = false
    var error: String?
    var searchText = ""
    var selectedCategory: MarketplaceCategory = .all
    var sortOption: MarketplaceSortOption = .newest
    var total = 0

    private var currentOffset = 0
    private let pageSize = 20
    private var searchTask: Task<Void, Never>?

    var hasMore: Bool { listings.count < total }

    func loadListings() async {
        guard !isLoading else { return }
        isLoading = true
        error = nil
        currentOffset = 0

        do {
            async let listingsResult = APIService.shared.fetchMarketplaceListings(
                category: selectedCategory.apiValue,
                search: searchText.isEmpty ? nil : searchText,
                sort: sortOption.rawValue,
                limit: pageSize,
                offset: 0
            )
            async let featuredResult = APIService.shared.fetchFeaturedListings()

            let (listingsResp, featuredResp) = try await (listingsResult, featuredResult)
            guard !Task.isCancelled else { return }
            listings = listingsResp.listings
            total = listingsResp.total
            featuredListings = featuredResp.listings
            currentOffset = listings.count
        } catch {
            if !Task.isCancelled {
                self.error = error.localizedDescription
            }
        }

        isLoading = false
    }

    func loadMore() async {
        guard !isLoadingMore, hasMore else { return }
        isLoadingMore = true

        do {
            let response = try await APIService.shared.fetchMarketplaceListings(
                category: selectedCategory.apiValue,
                search: searchText.isEmpty ? nil : searchText,
                sort: sortOption.rawValue,
                limit: pageSize,
                offset: currentOffset
            )
            guard !Task.isCancelled else { return }
            listings.append(contentsOf: response.listings)
            total = response.total
            currentOffset = listings.count
        } catch {
            if !Task.isCancelled {
                self.error = error.localizedDescription
            }
        }

        isLoadingMore = false
    }

    func loadMoreIfNeeded(currentListing: MarketplaceListingResponse) async {
        guard let last = listings.last, last.id == currentListing.id, hasMore, !isLoadingMore else { return }
        await loadMore()
    }

    func onSearchTextChanged(_ text: String) {
        searchText = text
        searchTask?.cancel()

        searchTask = Task {
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            await loadListings()
        }
    }

    func selectCategory(_ category: MarketplaceCategory) async {
        selectedCategory = category
        await loadListings()
    }

    func selectSort(_ sort: MarketplaceSortOption) async {
        sortOption = sort
        await loadListings()
    }

    func refresh() async {
        await loadListings()
    }
}
