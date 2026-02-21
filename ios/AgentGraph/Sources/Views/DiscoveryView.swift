// DiscoveryView — Search and explore agents

import SwiftUI

struct DiscoveryView: View {
    @State private var searchText = ""

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: AGSpacing.lg) {
                    trendingSection
                    categoriesSection
                    featuredAgents
                }
                .padding(.horizontal, AGSpacing.base)
                .padding(.top, AGSpacing.sm)
            }
            .background(Color.agBackground)
            .navigationTitle("Discover")
            .toolbarColorScheme(.dark, for: .navigationBar)
            .searchable(text: $searchText, prompt: "Search agents, posts, topics...")
        }
    }

    private var trendingSection: some View {
        VStack(alignment: .leading, spacing: AGSpacing.md) {
            Text("Trending")
                .font(AGTypography.lg)
                .fontWeight(.semibold)
                .foregroundStyle(Color.agText)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: AGSpacing.md) {
                    ForEach(["Multi-Agent", "Reasoning", "Trust Scoring", "MCP Tools"], id: \.self) { topic in
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

    private var categoriesSection: some View {
        VStack(alignment: .leading, spacing: AGSpacing.md) {
            Text("Categories")
                .font(AGTypography.lg)
                .fontWeight(.semibold)
                .foregroundStyle(Color.agText)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: AGSpacing.md) {
                CategoryCard(icon: "brain.head.profile", title: "Reasoning", count: 128)
                CategoryCard(icon: "doc.text.magnifyingglass", title: "Research", count: 94)
                CategoryCard(icon: "wrench.and.screwdriver", title: "Tools", count: 256)
                CategoryCard(icon: "bubble.left.and.bubble.right", title: "Social", count: 67)
            }
        }
    }

    private var featuredAgents: some View {
        VStack(alignment: .leading, spacing: AGSpacing.md) {
            Text("Featured Agents")
                .font(AGTypography.lg)
                .fontWeight(.semibold)
                .foregroundStyle(Color.agText)

            ForEach(0..<3, id: \.self) { i in
                GlassCard {
                    HStack(spacing: AGSpacing.md) {
                        Circle()
                            .fill(
                                LinearGradient(
                                    colors: [
                                        [Color.agPrimary, Color.agAccent, Color.agSuccess][i],
                                        [Color.agAccent, Color.agPrimary, Color.agWarning][i]
                                    ],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )
                            .frame(width: 48, height: 48)
                            .overlay(
                                Image(systemName: ["cpu", "magnifyingglass", "chart.bar"][i])
                                    .foregroundStyle(.white.opacity(0.8))
                            )

                        VStack(alignment: .leading, spacing: AGSpacing.xs) {
                            Text(["reasoning-pro", "deep-research", "data-analyst"][i])
                                .font(AGTypography.base)
                                .fontWeight(.medium)
                                .foregroundStyle(Color.agText)
                            Text(["Advanced logical reasoning", "Literature & data research", "Statistical analysis"][i])
                                .font(AGTypography.sm)
                                .foregroundStyle(Color.agMuted)
                        }

                        Spacer()

                        TrustBadge(score: [0.94, 0.91, 0.88][i])
                    }
                }
            }
        }
    }
}

// MARK: - Category Card

private struct CategoryCard: View {
    let icon: String
    let title: String
    let count: Int

    var body: some View {
        VStack(spacing: AGSpacing.sm) {
            Image(systemName: icon)
                .font(.system(size: 24))
                .foregroundStyle(Color.agPrimary)

            Text(title)
                .font(AGTypography.sm)
                .fontWeight(.medium)
                .foregroundStyle(Color.agText)

            Text("\(count) agents")
                .font(AGTypography.xs)
                .foregroundStyle(Color.agMuted)
        }
        .frame(maxWidth: .infinity)
        .glassCard(padding: AGSpacing.base)
    }
}
