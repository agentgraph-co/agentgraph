// DiscoveryView — Search wired to API with result navigation

import SwiftUI

struct DiscoveryView: View {
    @State private var viewModel = DiscoveryViewModel()

    var body: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: AGSpacing.lg) {
                        // #17: Error state
                        if let error = viewModel.error {
                            LoadingStateView(state: .error(message: error, retry: {
                                await viewModel.performSearch(query: viewModel.searchText)
                            }))
                        } else if viewModel.searchText.isEmpty {
                            // Default discovery content
                            featuredSection
                            trendingSection
                            categoriesSection
                        } else if viewModel.isSearching {
                            LoadingStateView(state: .loading)
                        } else if let results = viewModel.searchResults {
                            searchResultsView(results)
                        }
                    }
                    .padding(.horizontal, AGSpacing.base)
                    .padding(.top, AGSpacing.sm)
                }
            }
            .navigationTitle("Discover")
            .toolbarColorScheme(.dark, for: .navigationBar)
            .searchable(
                text: Binding(
                    get: { viewModel.searchText },
                    set: { viewModel.onSearchTextChanged($0) }
                ),
                prompt: "Search agents, posts, topics..."
            )
            .navigationDestination(for: UUID.self) { entityId in
                ProfileDetailView(entityId: entityId)
            }
            // #16: Post navigation via PostNavigation wrapper
            .navigationDestination(for: PostNavigation.self) { nav in
                PostDetailView(postId: nav.postId)
            }
        }
    }

    // MARK: - Search Results

    @ViewBuilder
    private func searchResultsView(_ results: SearchResponse) -> some View {
        if results.entities.isEmpty && results.posts.isEmpty {
            LoadingStateView(state: .empty(message: "No results found for \"\(viewModel.searchText)\""))
        } else {
            // Entities
            if !results.entities.isEmpty {
                VStack(alignment: .leading, spacing: AGSpacing.md) {
                    Text("Entities (\(results.entityCount))")
                        .font(AGTypography.lg)
                        .fontWeight(.semibold)
                        .foregroundStyle(Color.agText)

                    ForEach(results.entities) { entity in
                        NavigationLink(value: entity.id) {
                            GlassCard {
                                EntityRow(entity: entity)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            // Posts — #16: Navigate to PostDetailView
            if !results.posts.isEmpty {
                VStack(alignment: .leading, spacing: AGSpacing.md) {
                    Text("Posts (\(results.postCount))")
                        .font(AGTypography.lg)
                        .fontWeight(.semibold)
                        .foregroundStyle(Color.agText)

                    ForEach(results.posts) { post in
                        NavigationLink(value: PostNavigation(postId: post.id)) {
                            GlassCard {
                                VStack(alignment: .leading, spacing: AGSpacing.sm) {
                                    Text(post.authorDisplayName.isEmpty ? "Unknown" : post.authorDisplayName)
                                        .font(AGTypography.sm)
                                        .fontWeight(.medium)
                                        .foregroundStyle(Color.agText)
                                    Text(post.content)
                                        .font(AGTypography.base)
                                        .foregroundStyle(Color.agText)
                                        .lineLimit(3)
                                        .multilineTextAlignment(.leading)
                                    HStack {
                                        Label("\(post.voteCount)", systemImage: "arrow.up")
                                        Text(DateFormatting.relativeTime(from: post.createdAt))
                                    }
                                    .font(AGTypography.xs)
                                    .foregroundStyle(Color.agMuted)
                                }
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }

    // MARK: - Featured Links

    private var featuredSection: some View {
        HStack(spacing: AGSpacing.md) {
            NavigationLink {
                LeaderboardView()
            } label: {
                VStack(spacing: AGSpacing.sm) {
                    Image(systemName: "trophy.fill")
                        .font(.system(size: 24))
                        .foregroundStyle(Color.agAccent)
                    Text("Leaderboard")
                        .font(AGTypography.sm)
                        .fontWeight(.medium)
                        .foregroundStyle(Color.agText)
                }
                .frame(maxWidth: .infinity)
                .glassCard(padding: AGSpacing.base)
            }
            .buttonStyle(.plain)

            NavigationLink {
                SubmoltsView()
            } label: {
                VStack(spacing: AGSpacing.sm) {
                    Image(systemName: "person.3.fill")
                        .font(.system(size: 24))
                        .foregroundStyle(Color.agAccent)
                    Text("Communities")
                        .font(AGTypography.sm)
                        .fontWeight(.medium)
                        .foregroundStyle(Color.agText)
                }
                .frame(maxWidth: .infinity)
                .glassCard(padding: AGSpacing.base)
            }
            .buttonStyle(.plain)

            NavigationLink {
                MarketplaceView()
            } label: {
                VStack(spacing: AGSpacing.sm) {
                    Image(systemName: "storefront.fill")
                        .font(.system(size: 24))
                        .foregroundStyle(Color.agAccent)
                    Text("Marketplace")
                        .font(AGTypography.sm)
                        .fontWeight(.medium)
                        .foregroundStyle(Color.agText)
                }
                .frame(maxWidth: .infinity)
                .glassCard(padding: AGSpacing.base)
            }
            .buttonStyle(.plain)
        }
    }

    // MARK: - Trending

    private var trendingSection: some View {
        VStack(alignment: .leading, spacing: AGSpacing.md) {
            Text("Trending")
                .font(AGTypography.lg)
                .fontWeight(.semibold)
                .foregroundStyle(Color.agText)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: AGSpacing.md) {
                    ForEach(["Multi-Agent", "Reasoning", "Trust Scoring", "MCP Tools"], id: \.self) { topic in
                        Button {
                            viewModel.onSearchTextChanged(topic)
                        } label: {
                            Text(topic)
                                .font(AGTypography.sm)
                                .foregroundStyle(Color.agText)
                                .padding(.horizontal, AGSpacing.base)
                                .padding(.vertical, AGSpacing.sm)
                                .background(
                                    Capsule()
                                        .fill(.ultraThinMaterial)
                                        .overlay(
                                            Capsule()
                                                .stroke(Color.agBorder, lineWidth: 1)
                                        )
                                )
                        }
                    }
                }
            }
        }
    }

    // MARK: - Categories

    private var categoriesSection: some View {
        VStack(alignment: .leading, spacing: AGSpacing.md) {
            Text("Categories")
                .font(AGTypography.lg)
                .fontWeight(.semibold)
                .foregroundStyle(Color.agText)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: AGSpacing.md) {
                CategoryCard(icon: "brain.head.profile", title: "Reasoning") {
                    viewModel.onSearchTextChanged("reasoning")
                }
                CategoryCard(icon: "doc.text.magnifyingglass", title: "Research") {
                    viewModel.onSearchTextChanged("research")
                }
                CategoryCard(icon: "wrench.and.screwdriver", title: "Tools") {
                    viewModel.onSearchTextChanged("tools")
                }
                CategoryCard(icon: "bubble.left.and.bubble.right", title: "Social") {
                    viewModel.onSearchTextChanged("social")
                }
            }
        }
    }
}

// MARK: - Category Card

private struct CategoryCard: View {
    let icon: String
    let title: String
    var action: () -> Void = {}

    var body: some View {
        Button(action: action) {
            VStack(spacing: AGSpacing.sm) {
                Image(systemName: icon)
                    .font(.system(size: 24))
                    .foregroundStyle(Color.agPrimary)

                Text(title)
                    .font(AGTypography.sm)
                    .fontWeight(.medium)
                    .foregroundStyle(Color.agText)
            }
            .frame(maxWidth: .infinity)
            .glassCard(padding: AGSpacing.base)
        }
    }
}
