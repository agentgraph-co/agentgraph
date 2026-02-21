// ProfileDetailView — Full profile for any entity

import SwiftUI

struct ProfileDetailView: View {
    let entityId: UUID
    @State private var viewModel = ProfileViewModel()

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            if viewModel.isLoading {
                LoadingStateView(state: .loading)
            } else if let error = viewModel.error {
                LoadingStateView(state: .error(message: error, retry: {
                    await viewModel.loadProfile(entityId: entityId)
                }))
            } else if let profile = viewModel.profile {
                ScrollView {
                    VStack(spacing: AGSpacing.lg) {
                        // Header
                        GlassCard {
                            VStack(spacing: AGSpacing.base) {
                                Circle()
                                    .fill(
                                        LinearGradient(
                                            colors: [.agPrimary, .agAccent],
                                            startPoint: .topLeading,
                                            endPoint: .bottomTrailing
                                        )
                                    )
                                    .frame(width: 80, height: 80)
                                    .overlay(
                                        Text(String(profile.displayName.prefix(1)).uppercased())
                                            .font(.system(size: 32, weight: .bold))
                                            .foregroundStyle(.white)
                                    )

                                VStack(spacing: AGSpacing.xs) {
                                    Text(profile.displayName)
                                        .font(AGTypography.xxl)
                                        .foregroundStyle(Color.agText)

                                    Text(profile.type.capitalized)
                                        .font(AGTypography.sm)
                                        .foregroundStyle(Color.agMuted)

                                    Text(profile.didWeb)
                                        .font(AGTypography.xs)
                                        .foregroundStyle(Color.agPrimary)
                                }

                                if let score = profile.trustScore {
                                    TrustBadge(score: score)
                                }

                                // Bio
                                if !profile.bioMarkdown.isEmpty {
                                    Text(profile.bioMarkdown)
                                        .font(AGTypography.base)
                                        .foregroundStyle(Color.agText)
                                        .multilineTextAlignment(.center)
                                }

                                // Follow button (only for other profiles)
                                if !profile.isOwnProfile {
                                    Button {
                                        Task { await viewModel.toggleFollow(targetId: entityId) }
                                    } label: {
                                        Text(viewModel.isFollowing ? "Unfollow" : "Follow")
                                            .font(AGTypography.sm)
                                            .fontWeight(.semibold)
                                            .foregroundStyle(.white)
                                            .padding(.horizontal, AGSpacing.xl)
                                            .padding(.vertical, AGSpacing.sm)
                                    }
                                    .background(
                                        viewModel.isFollowing
                                            ? Color.agMuted
                                            : Color.agPrimary
                                    )
                                    .clipShape(Capsule())
                                }

                                // Badges
                                if !profile.badges.isEmpty {
                                    HStack {
                                        ForEach(profile.badges, id: \.self) { badge in
                                            Text(badge)
                                                .font(AGTypography.xs)
                                                .foregroundStyle(Color.agAccent)
                                                .padding(.horizontal, AGSpacing.sm)
                                                .padding(.vertical, 2)
                                                .background(
                                                    Capsule().fill(Color.agAccent.opacity(0.15))
                                                )
                                        }
                                    }
                                }
                            }
                            .frame(maxWidth: .infinity)
                        }

                        // Stats
                        HStack(spacing: AGSpacing.md) {
                            statCard(label: "Posts", value: "\(profile.postCount)")
                            statCard(label: "Followers", value: "\(profile.followerCount)")
                            statCard(label: "Following", value: "\(profile.followingCount)")
                        }

                        // Capabilities (agents only)
                        if let capabilities = profile.capabilities, !capabilities.isEmpty {
                            GlassCard {
                                VStack(alignment: .leading, spacing: AGSpacing.md) {
                                    Text("Capabilities")
                                        .font(AGTypography.lg)
                                        .fontWeight(.semibold)
                                        .foregroundStyle(Color.agText)

                                    FlowLayout(spacing: AGSpacing.sm) {
                                        ForEach(capabilities, id: \.self) { cap in
                                            Text(cap)
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

                        // Evolution timeline
                        if !viewModel.evolutionRecords.isEmpty {
                            GlassCard {
                                VStack(alignment: .leading, spacing: AGSpacing.md) {
                                    Text("Evolution Timeline")
                                        .font(AGTypography.lg)
                                        .fontWeight(.semibold)
                                        .foregroundStyle(Color.agText)

                                    ForEach(viewModel.evolutionRecords) { record in
                                        HStack(spacing: AGSpacing.md) {
                                            Circle()
                                                .fill(Color.agPrimary)
                                                .frame(width: 8, height: 8)

                                            VStack(alignment: .leading, spacing: 2) {
                                                Text(record.version)
                                                    .font(AGTypography.sm)
                                                    .fontWeight(.medium)
                                                    .foregroundStyle(Color.agText)
                                                Text(record.changeSummary)
                                                    .font(AGTypography.xs)
                                                    .foregroundStyle(Color.agMuted)
                                            }

                                            Spacer()

                                            Text(DateFormatting.relativeTime(from: record.createdAt))
                                                .font(AGTypography.xs)
                                                .foregroundStyle(Color.agMuted)
                                        }
                                    }
                                }
                            }
                        }

                        // Trust components
                        if let components = profile.trustComponents, !components.isEmpty {
                            GlassCard {
                                VStack(alignment: .leading, spacing: AGSpacing.md) {
                                    Text("Trust Components")
                                        .font(AGTypography.lg)
                                        .fontWeight(.semibold)
                                        .foregroundStyle(Color.agText)

                                    ForEach(components.sorted(by: { $0.key < $1.key }), id: \.key) { key, value in
                                        HStack {
                                            Text(key.capitalized)
                                                .font(AGTypography.sm)
                                                .foregroundStyle(Color.agMuted)
                                            Spacer()
                                            Text(String(format: "%.0f%%", value * 100))
                                                .font(AGTypography.sm)
                                                .fontWeight(.medium)
                                                .foregroundStyle(Color.agText)
                                        }
                                        ProgressView(value: value)
                                            .tint(value >= 0.8 ? .agSuccess : value >= 0.5 ? .agWarning : .agDanger)
                                    }
                                }
                            }
                        }
                    }
                    .padding(.horizontal, AGSpacing.base)
                    .padding(.top, AGSpacing.sm)
                }
            }
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .task {
            await viewModel.loadProfile(entityId: entityId)
        }
    }

    private func statCard(label: String, value: String) -> some View {
        VStack(spacing: AGSpacing.xs) {
            Text(value)
                .font(AGTypography.xl)
                .fontWeight(.bold)
                .foregroundStyle(Color.agText)
            Text(label)
                .font(AGTypography.xs)
                .foregroundStyle(Color.agMuted)
        }
        .frame(maxWidth: .infinity)
        .glassCard(padding: AGSpacing.md)
    }
}

// Simple flow layout for capabilities
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = arrange(proposal: proposal, subviews: subviews)
        return result.size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = arrange(proposal: proposal, subviews: subviews)
        for (index, position) in result.positions.enumerated() {
            subviews[index].place(at: CGPoint(x: bounds.minX + position.x, y: bounds.minY + position.y), proposal: .unspecified)
        }
    }

    private func arrange(proposal: ProposedViewSize, subviews: Subviews) -> (size: CGSize, positions: [CGPoint]) {
        let maxWidth = proposal.width ?? .infinity
        var positions: [CGPoint] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        var totalHeight: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxWidth && x > 0 {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            positions.append(CGPoint(x: x, y: y))
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
            totalHeight = y + rowHeight
        }

        return (CGSize(width: maxWidth, height: totalHeight), positions)
    }
}
