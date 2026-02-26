// ListingDetailView — Full listing detail with reviews and purchase

import SwiftUI

struct ListingDetailView: View {
    let listingId: UUID
    @Environment(AuthViewModel.self) private var auth
    @State private var viewModel = ListingDetailViewModel()
    @State private var showReviewForm = false
    @State private var showPurchaseConfirm = false
    @State private var showLoginPrompt = false
    @State private var showEditListing = false

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            if viewModel.isLoading && viewModel.listing == nil {
                LoadingStateView(state: .loading)
            } else if let error = viewModel.error, viewModel.listing == nil {
                LoadingStateView(state: .error(message: error, retry: {
                    await viewModel.loadListing(id: listingId)
                }))
            } else if let listing = viewModel.listing {
                ScrollView {
                    VStack(spacing: AGSpacing.lg) {
                        // Listing header
                        listingHeader(listing)

                        // Price and purchase section
                        purchaseSection(listing)

                        // Full description
                        descriptionSection(listing)

                        // Tags
                        if !listing.tags.isEmpty {
                            tagsSection(listing.tags)
                        }

                        // Seller info
                        if let seller = viewModel.sellerProfile {
                            sellerSection(seller)
                        }

                        // Reviews
                        reviewsSection(listing)
                    }
                    .padding(.horizontal, AGSpacing.base)
                    .padding(.top, AGSpacing.sm)
                    .padding(.bottom, AGSpacing.xxl)
                }
                .refreshable {
                    await viewModel.loadListing(id: listingId)
                }
            }
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .toolbar {
            if let listing = viewModel.listing, listing.entityId == auth.currentUser?.id {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        showEditListing = true
                    } label: {
                        Image(systemName: "pencil")
                    }
                    .tint(.agPrimary)
                }
            }
        }
        .sheet(isPresented: $showEditListing) {
            if let listing = viewModel.listing {
                EditListingView(listing: listing) { updated in
                    viewModel.listing = updated
                }
            }
        }
        .alert("Confirm Purchase", isPresented: $showPurchaseConfirm) {
            Button("Purchase") {
                Task { await viewModel.purchaseListing(id: listingId) }
            }
            Button("Cancel", role: .cancel) { }
        } message: {
            if let listing = viewModel.listing {
                Text("Purchase \"\(listing.title)\" for \(listing.formattedPrice)?")
            }
        }
        .alert("Purchase Successful", isPresented: $viewModel.purchaseSuccess) {
            Button("OK") { }
        } message: {
            Text("Your purchase has been completed successfully.")
        }
        .alert("Purchase Failed", isPresented: Binding(
            get: { viewModel.purchaseError != nil },
            set: { if !$0 { viewModel.purchaseError = nil } }
        )) {
            Button("OK") { }
        } message: {
            Text(viewModel.purchaseError ?? "An error occurred.")
        }
        .alert("Sign In Required", isPresented: $showLoginPrompt) {
            Button("Sign In") {
                auth.exitGuestMode()
            }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("Sign in to purchase listings and leave reviews.")
        }
        .sheet(isPresented: $showReviewForm) {
            ReviewFormSheet(listingId: listingId, viewModel: viewModel)
        }
        .task {
            await viewModel.loadListing(id: listingId)
        }
    }

    // MARK: - Header

    private func listingHeader(_ listing: MarketplaceListingResponse) -> some View {
        GlassCard {
            VStack(alignment: .leading, spacing: AGSpacing.md) {
                HStack {
                    VStack(alignment: .leading, spacing: AGSpacing.xs) {
                        if listing.isFeatured {
                            HStack(spacing: AGSpacing.xs) {
                                Image(systemName: "star.fill")
                                    .foregroundStyle(Color.agAccent)
                                Text("Featured")
                                    .foregroundStyle(Color.agAccent)
                            }
                            .font(AGTypography.xs)
                        }

                        Text(listing.title)
                            .font(AGTypography.xxl)
                            .foregroundStyle(Color.agText)
                    }

                    Spacer()
                }

                HStack(spacing: AGSpacing.base) {
                    Label(listing.categoryDisplay, systemImage: categoryIcon(listing.category))
                        .font(AGTypography.sm)
                        .foregroundStyle(Color.agPrimary)

                    Label(listing.pricingModelDisplay, systemImage: "creditcard")
                        .font(AGTypography.sm)
                        .foregroundStyle(Color.agMuted)
                }

                HStack(spacing: AGSpacing.base) {
                    if let rating = listing.averageRating {
                        HStack(spacing: 2) {
                            ForEach(1...5, id: \.self) { star in
                                Image(systemName: star <= Int(rating.rounded()) ? "star.fill" : "star")
                                    .foregroundStyle(Color.agWarning)
                            }
                            Text(String(format: "%.1f", rating))
                                .fontWeight(.medium)
                            Text("(\(listing.reviewCount))")
                                .foregroundStyle(Color.agMuted)
                        }
                        .font(AGTypography.sm)
                        .foregroundStyle(Color.agText)
                    }

                    Label("\(listing.viewCount) views", systemImage: "eye")
                        .font(AGTypography.sm)
                        .foregroundStyle(Color.agMuted)
                }
            }
        }
    }

    // MARK: - Purchase Section

    private func purchaseSection(_ listing: MarketplaceListingResponse) -> some View {
        GlassCard {
            VStack(spacing: AGSpacing.md) {
                HStack {
                    Text(listing.formattedPrice)
                        .font(AGTypography.xxxl)
                        .foregroundStyle(
                            listing.priceCents == 0 || listing.pricingModel == "free"
                                ? Color.agSuccess
                                : Color.agText
                        )

                    if listing.pricingModel == "subscription" {
                        Text("/ month")
                            .font(AGTypography.sm)
                            .foregroundStyle(Color.agMuted)
                    }

                    Spacer()
                }

                Button {
                    if auth.isAuthenticated {
                        showPurchaseConfirm = true
                    } else {
                        showLoginPrompt = true
                    }
                } label: {
                    HStack {
                        if viewModel.isPurchasing {
                            ProgressView()
                                .tint(.white)
                        } else {
                            Image(systemName: listing.priceCents == 0 ? "arrow.down.circle" : "cart")
                            Text(listing.priceCents == 0 ? "Get for Free" : "Purchase")
                        }
                    }
                    .font(AGTypography.base)
                    .fontWeight(.semibold)
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, AGSpacing.md)
                    .background(
                        RoundedRectangle(cornerRadius: AGRadii.lg)
                            .fill(
                                LinearGradient(
                                    colors: [.agPrimary, .agAccent],
                                    startPoint: .leading,
                                    endPoint: .trailing
                                )
                            )
                    )
                }
                .disabled(viewModel.isPurchasing)
            }
        }
    }

    // MARK: - Description

    private func descriptionSection(_ listing: MarketplaceListingResponse) -> some View {
        GlassCard {
            VStack(alignment: .leading, spacing: AGSpacing.md) {
                Text("Description")
                    .font(AGTypography.lg)
                    .fontWeight(.semibold)
                    .foregroundStyle(Color.agText)

                Text(listing.description)
                    .font(AGTypography.base)
                    .foregroundStyle(Color.agText)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: - Tags

    private func tagsSection(_ tags: [String]) -> some View {
        GlassCard {
            VStack(alignment: .leading, spacing: AGSpacing.md) {
                Text("Tags")
                    .font(AGTypography.lg)
                    .fontWeight(.semibold)
                    .foregroundStyle(Color.agText)

                FlowLayout(spacing: AGSpacing.sm) {
                    ForEach(tags, id: \.self) { tag in
                        Text(tag)
                            .font(AGTypography.sm)
                            .foregroundStyle(Color.agText)
                            .padding(.horizontal, AGSpacing.md)
                            .padding(.vertical, AGSpacing.xs)
                            .background(
                                Capsule()
                                    .fill(.ultraThinMaterial)
                                    .overlay(
                                        Capsule().stroke(Color.agBorder, lineWidth: 1)
                                    )
                            )
                    }
                }
            }
        }
    }

    // MARK: - Seller Info

    private func sellerSection(_ seller: ProfileResponse) -> some View {
        GlassCard {
            VStack(alignment: .leading, spacing: AGSpacing.md) {
                Text("Seller")
                    .font(AGTypography.lg)
                    .fontWeight(.semibold)
                    .foregroundStyle(Color.agText)

                NavigationLink(value: seller.id) {
                    HStack(spacing: AGSpacing.md) {
                        Circle()
                            .fill(
                                LinearGradient(
                                    colors: [.agPrimary, .agAccent],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )
                            .frame(width: 44, height: 44)
                            .overlay(
                                Text(String(seller.displayName.prefix(1)).uppercased())
                                    .font(.system(size: 18, weight: .bold))
                                    .foregroundStyle(.white)
                            )

                        VStack(alignment: .leading, spacing: 2) {
                            Text(seller.displayName)
                                .font(AGTypography.base)
                                .fontWeight(.medium)
                                .foregroundStyle(Color.agText)

                            Text(seller.type.capitalized)
                                .font(AGTypography.xs)
                                .foregroundStyle(Color.agMuted)
                        }

                        Spacer()

                        if let score = seller.trustScore {
                            TrustBadge(score: score)
                        }
                    }
                }
                .buttonStyle(.plain)
            }
        }
    }

    // MARK: - Reviews

    private func reviewsSection(_ listing: MarketplaceListingResponse) -> some View {
        GlassCard {
            VStack(alignment: .leading, spacing: AGSpacing.md) {
                HStack {
                    Text("Reviews (\(viewModel.reviewStats.total))")
                        .font(AGTypography.lg)
                        .fontWeight(.semibold)
                        .foregroundStyle(Color.agText)

                    Spacer()

                    if auth.isAuthenticated {
                        Button {
                            showReviewForm = true
                        } label: {
                            HStack(spacing: AGSpacing.xs) {
                                Image(systemName: "square.and.pencil")
                                Text("Write Review")
                            }
                            .font(AGTypography.sm)
                            .foregroundStyle(Color.agPrimary)
                        }
                    }
                }

                if viewModel.reviews.isEmpty {
                    Text("No reviews yet. Be the first to review!")
                        .font(AGTypography.sm)
                        .foregroundStyle(Color.agMuted)
                        .padding(.vertical, AGSpacing.base)
                } else {
                    ForEach(viewModel.reviews) { review in
                        VStack(alignment: .leading, spacing: AGSpacing.sm) {
                            HStack {
                                Text(review.reviewerDisplayName)
                                    .font(AGTypography.sm)
                                    .fontWeight(.medium)
                                    .foregroundStyle(Color.agText)

                                Spacer()

                                HStack(spacing: 2) {
                                    ForEach(1...5, id: \.self) { star in
                                        Image(systemName: star <= review.rating ? "star.fill" : "star")
                                            .font(AGTypography.xs)
                                            .foregroundStyle(Color.agWarning)
                                    }
                                }
                            }

                            if let text = review.text, !text.isEmpty {
                                Text(text)
                                    .font(AGTypography.sm)
                                    .foregroundStyle(Color.agMuted)
                                    .fixedSize(horizontal: false, vertical: true)
                            }

                            Divider()
                                .background(Color.agBorder)
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

// MARK: - Review Form Sheet

struct ReviewFormSheet: View {
    let listingId: UUID
    @Bindable var viewModel: ListingDetailViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var rating = 5
    @State private var reviewText = ""
    @State private var isSubmitting = false

    var body: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: AGSpacing.lg) {
                        GlassCard {
                            VStack(alignment: .leading, spacing: AGSpacing.md) {
                                Text("Rating")
                                    .font(AGTypography.sm)
                                    .foregroundStyle(Color.agMuted)

                                HStack(spacing: AGSpacing.md) {
                                    ForEach(1...5, id: \.self) { star in
                                        Button {
                                            rating = star
                                        } label: {
                                            Image(systemName: star <= rating ? "star.fill" : "star")
                                                .font(.system(size: 28))
                                                .foregroundStyle(
                                                    star <= rating ? Color.agWarning : Color.agMuted
                                                )
                                        }
                                    }
                                }

                                Text("Review (optional)")
                                    .font(AGTypography.sm)
                                    .foregroundStyle(Color.agMuted)

                                TextEditor(text: $reviewText)
                                    .scrollContentBackground(.hidden)
                                    .font(AGTypography.base)
                                    .foregroundStyle(Color.agText)
                                    .frame(minHeight: 100)
                                    .padding(AGSpacing.md)
                                    .background(Color.agSurface)
                                    .clipShape(RoundedRectangle(cornerRadius: AGRadii.md))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: AGRadii.md)
                                            .stroke(Color.agBorder, lineWidth: 1)
                                    )
                            }
                        }
                    }
                    .padding(.horizontal, AGSpacing.xl)
                    .padding(.top, AGSpacing.lg)
                }
            }
            .navigationTitle("Write Review")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                        .foregroundStyle(Color.agMuted)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Submit") {
                        isSubmitting = true
                        Task {
                            let text = reviewText.trimmingCharacters(in: .whitespacesAndNewlines)
                            let success = await viewModel.submitReview(
                                listingId: listingId,
                                rating: rating,
                                text: text.isEmpty ? nil : text
                            )
                            isSubmitting = false
                            if success {
                                dismiss()
                            }
                        }
                    }
                    .fontWeight(.semibold)
                    .tint(.agPrimary)
                    .disabled(isSubmitting)
                }
            }
        }
    }
}
