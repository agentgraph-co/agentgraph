// MarketplaceView — Browse, search, and filter marketplace listings

import SwiftUI

struct MarketplaceView: View {
    @Environment(AuthViewModel.self) private var auth
    @State private var viewModel = MarketplaceViewModel()
    @State private var showCreateListing = false

    var body: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                if viewModel.isLoading && viewModel.listings.isEmpty {
                    LoadingStateView(state: .loading)
                } else {
                    ScrollView {
                        VStack(spacing: AGSpacing.base) {
                            // Category filter bar
                            categoryFilterBar

                            // Sort picker
                            sortPicker

                            // Featured section (only when no search/filter active)
                            if viewModel.searchText.isEmpty
                                && viewModel.selectedCategory == .all
                                && !viewModel.featuredListings.isEmpty
                            {
                                featuredSection
                            }

                            // Error state
                            if let error = viewModel.error {
                                LoadingStateView(state: .error(message: error, retry: {
                                    await viewModel.refresh()
                                }))
                            } else if viewModel.listings.isEmpty && !viewModel.isLoading {
                                LoadingStateView(state: .empty(
                                    message: viewModel.searchText.isEmpty
                                        ? "No listings yet. Be the first to create one!"
                                        : "No listings found for \"\(viewModel.searchText)\""
                                ))
                            } else {
                                // Listing cards
                                LazyVStack(spacing: AGSpacing.base) {
                                    ForEach(viewModel.listings) { listing in
                                        NavigationLink(value: listing.id) {
                                            ListingCard(listing: listing)
                                        }
                                        .buttonStyle(.plain)
                                        .onAppear {
                                            Task { await viewModel.loadMoreIfNeeded(currentListing: listing) }
                                        }
                                    }
                                }

                                if viewModel.isLoadingMore {
                                    ProgressView()
                                        .tint(.agPrimary)
                                        .padding()
                                }
                            }
                        }
                        .padding(.horizontal, AGSpacing.base)
                        .padding(.top, AGSpacing.sm)
                    }
                    .refreshable {
                        await viewModel.refresh()
                    }
                }
            }
            .navigationTitle("Marketplace")
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                if auth.isAuthenticated {
                    ToolbarItem(placement: .primaryAction) {
                        Button {
                            showCreateListing = true
                        } label: {
                            Image(systemName: "plus")
                        }
                        .tint(.agPrimary)
                    }
                }
            }
            .searchable(
                text: Binding(
                    get: { viewModel.searchText },
                    set: { viewModel.onSearchTextChanged($0) }
                ),
                prompt: "Search listings..."
            )
            .navigationDestination(for: UUID.self) { listingId in
                ListingDetailView(listingId: listingId)
            }
            .sheet(isPresented: $showCreateListing) {
                CreateListingView {
                    await viewModel.refresh()
                }
            }
            .task {
                await viewModel.loadListings()
            }
        }
    }

    // MARK: - Category Filter Bar

    private var categoryFilterBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: AGSpacing.sm) {
                ForEach(MarketplaceCategory.allCases, id: \.self) { category in
                    Button {
                        Task { await viewModel.selectCategory(category) }
                    } label: {
                        HStack(spacing: AGSpacing.xs) {
                            Image(systemName: category.icon)
                                .font(AGTypography.xs)
                            Text(category.displayName)
                                .font(AGTypography.sm)
                        }
                        .foregroundStyle(
                            viewModel.selectedCategory == category
                                ? Color.white
                                : Color.agText
                        )
                        .padding(.horizontal, AGSpacing.base)
                        .padding(.vertical, AGSpacing.sm)
                        .background(
                            Capsule()
                                .fill(
                                    viewModel.selectedCategory == category
                                        ? Color.agPrimary
                                        : Color.clear
                                )
                        )
                        .overlay(
                            Capsule()
                                .stroke(
                                    viewModel.selectedCategory == category
                                        ? Color.agPrimary
                                        : Color.agBorder,
                                    lineWidth: 1
                                )
                        )
                    }
                }
            }
            .padding(.horizontal, AGSpacing.xs)
        }
    }

    // MARK: - Sort Picker

    private var sortPicker: some View {
        HStack {
            Text("\(viewModel.total) listing\(viewModel.total == 1 ? "" : "s")")
                .font(AGTypography.sm)
                .foregroundStyle(Color.agMuted)

            Spacer()

            Menu {
                ForEach(MarketplaceSortOption.allCases, id: \.self) { option in
                    Button {
                        Task { await viewModel.selectSort(option) }
                    } label: {
                        HStack {
                            Text(option.displayName)
                            if viewModel.sortOption == option {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                }
            } label: {
                HStack(spacing: AGSpacing.xs) {
                    Image(systemName: "arrow.up.arrow.down")
                    Text(viewModel.sortOption.displayName)
                }
                .font(AGTypography.sm)
                .foregroundStyle(Color.agPrimary)
            }
        }
    }

    // MARK: - Featured Section

    private var featuredSection: some View {
        VStack(alignment: .leading, spacing: AGSpacing.md) {
            HStack {
                Image(systemName: "star.fill")
                    .foregroundStyle(Color.agAccent)
                Text("Featured")
                    .font(AGTypography.lg)
                    .fontWeight(.semibold)
                    .foregroundStyle(Color.agText)
            }

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: AGSpacing.md) {
                    ForEach(viewModel.featuredListings) { listing in
                        NavigationLink(value: listing.id) {
                            FeaturedListingCard(listing: listing)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }
}

// MARK: - Listing Card

struct ListingCard: View {
    let listing: MarketplaceListingResponse

    var body: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: AGSpacing.md) {
                // Header: title + price
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: AGSpacing.xs) {
                        Text(listing.title)
                            .font(AGTypography.base)
                            .fontWeight(.semibold)
                            .foregroundStyle(Color.agText)
                            .lineLimit(2)
                            .multilineTextAlignment(.leading)

                        HStack(spacing: AGSpacing.sm) {
                            Label(listing.categoryDisplay, systemImage: categoryIcon(listing.category))
                                .font(AGTypography.xs)
                                .foregroundStyle(Color.agPrimary)

                            Text(listing.pricingModelDisplay)
                                .font(AGTypography.xs)
                                .foregroundStyle(Color.agMuted)
                        }
                    }

                    Spacer()

                    Text(listing.formattedPrice)
                        .font(AGTypography.lg)
                        .fontWeight(.bold)
                        .foregroundStyle(
                            listing.priceCents == 0 || listing.pricingModel == "free"
                                ? Color.agSuccess
                                : Color.agText
                        )
                }

                // Description
                Text(listing.description)
                    .font(AGTypography.sm)
                    .foregroundStyle(Color.agMuted)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)

                // Tags
                if !listing.tags.isEmpty {
                    HStack(spacing: AGSpacing.xs) {
                        ForEach(listing.tags.prefix(3), id: \.self) { tag in
                            Text(tag)
                                .font(AGTypography.xs)
                                .foregroundStyle(Color.agAccent)
                                .padding(.horizontal, AGSpacing.sm)
                                .padding(.vertical, 2)
                                .background(
                                    Capsule()
                                        .fill(Color.agAccent.opacity(0.15))
                                )
                        }
                        if listing.tags.count > 3 {
                            Text("+\(listing.tags.count - 3)")
                                .font(AGTypography.xs)
                                .foregroundStyle(Color.agMuted)
                        }
                    }
                }

                // Footer: rating + views
                HStack {
                    if let rating = listing.averageRating {
                        HStack(spacing: 2) {
                            Image(systemName: "star.fill")
                                .foregroundStyle(Color.agWarning)
                            Text(String(format: "%.1f", rating))
                                .fontWeight(.medium)
                            Text("(\(listing.reviewCount))")
                                .foregroundStyle(Color.agMuted)
                        }
                        .font(AGTypography.xs)
                        .foregroundStyle(Color.agText)
                    }

                    Spacer()

                    HStack(spacing: AGSpacing.sm) {
                        Label("\(listing.viewCount)", systemImage: "eye")
                            .font(AGTypography.xs)
                            .foregroundStyle(Color.agMuted)

                        if listing.isFeatured {
                            Label("Featured", systemImage: "star.fill")
                                .font(AGTypography.xs)
                                .foregroundStyle(Color.agAccent)
                        }
                    }
                }
            }
        }
    }

    private func categoryIcon(_ category: String) -> String {
        switch category {
        case "service": return "gearshape.2"
        case "skill": return "brain.head.profile"
        case "integration": return "link"
        case "tool": return "wrench.and.screwdriver"
        case "data": return "cylinder"
        default: return "square.grid.2x2"
        }
    }
}

// MARK: - Featured Listing Card (horizontal scroll)

struct FeaturedListingCard: View {
    let listing: MarketplaceListingResponse

    var body: some View {
        VStack(alignment: .leading, spacing: AGSpacing.sm) {
            HStack {
                Image(systemName: "star.fill")
                    .font(AGTypography.xs)
                    .foregroundStyle(Color.agAccent)
                Spacer()
                Text(listing.formattedPrice)
                    .font(AGTypography.sm)
                    .fontWeight(.bold)
                    .foregroundStyle(
                        listing.priceCents == 0 ? Color.agSuccess : Color.agText
                    )
            }

            Text(listing.title)
                .font(AGTypography.sm)
                .fontWeight(.semibold)
                .foregroundStyle(Color.agText)
                .lineLimit(2)
                .multilineTextAlignment(.leading)

            Text(listing.categoryDisplay)
                .font(AGTypography.xs)
                .foregroundStyle(Color.agPrimary)

            if let rating = listing.averageRating {
                HStack(spacing: 2) {
                    Image(systemName: "star.fill")
                        .foregroundStyle(Color.agWarning)
                    Text(String(format: "%.1f", rating))
                }
                .font(AGTypography.xs)
                .foregroundStyle(Color.agText)
            }
        }
        .frame(width: 160)
        .glassCard(padding: AGSpacing.base)
    }
}
